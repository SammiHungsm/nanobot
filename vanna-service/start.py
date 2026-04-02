"""
Vanna Service Startup Script

Features:
1. Initialize Vanna AI with ChromaDB + PostgreSQL
2. Auto-train on Database Schema
3. Train with comprehensive DDL, documentation, and SQL examples
4. Provide REST API for training and queries
5. Support continuous learning (邊做邊學)
"""

import os
import time
import json
from pathlib import Path
from loguru import logger
import sys
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

# FastAPI imports
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# Database
import psycopg2
from psycopg2.extras import RealDictCursor

# Vanna
try:
    from vanna.chromadb import ChromaDB_VectorStore
    from vanna.openai import OpenAI_Chat
    from openai import OpenAI
    
    class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
        def __init__(self, config=None):
            # Separate configs for each parent class
            chroma_config = {'path': config.get('path')} if config else {}
            openai_config = {k: v for k, v in (config or {}).items() if k != 'path'}
            
            # Initialize parent classes
            ChromaDB_VectorStore.__init__(self, config=chroma_config)
            OpenAI_Chat.__init__(self, config=openai_config)
            
            # Explicitly set client if provided (for custom OpenAI-compatible APIs)
            if config and 'client' in config:
                self.client = config['client']
    
    VANNA_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ Vanna imports failed: {e}. Running in mock mode.")
    VANNA_AVAILABLE = False
    MyVanna = None

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=os.getenv("LOG_LEVEL", "INFO")
)

# Global Vanna instance
vn: Optional[MyVanna] = None
db_url: str = ""
chroma_path: str = "/app/data/chromadb"

# Ensure data directory exists
Path(chroma_path).mkdir(parents=True, exist_ok=True)


class TrainRequest(BaseModel):
    """Training request model"""
    train_type: str = "schema"  # schema | ddl | sql
    doc_id: Optional[str] = None  # Optional: specific document ID to train on


class AskRequest(BaseModel):
    """Query request model"""
    question: str
    include_sql: bool = True
    include_summary: bool = True


class ExtractRequest(BaseModel):
    """Extraction request model"""
    text: str
    extract_type: str = "company_info"  # company_info | financial_metrics | key_personnel


class AskResponse(BaseModel):
    """Query response model"""
    question: str
    sql: Optional[str] = None
    answer: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    training_status: str = "ready"


def get_db_connection():
    """Get PostgreSQL connection"""
    return psycopg2.connect(
        os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports"
        ),
        connect_timeout=10
    )


def load_openai_api_key() -> tuple:
    """Load API key, api_base, and model from config file or environment variable
    
    Returns:
        tuple: (api_key, api_base, model) - api_base and model may be None for default OpenAI
    """
    # Try to load from config file first (following nanobot pattern)
    config_paths = [
        Path("/app/config/config.json"),           # Docker mounted config
        Path("/root/.nanobot/config.json"),        # User nanobot config
        Path(os.path.expanduser("~/.nanobot/config.json")),  # Fallback home dir
    ]
    
    logger.info(f"🔍 Searching for config file in {len(config_paths)} locations...")
    
    for config_path in config_paths:
        logger.debug(f"  Checking: {config_path}")
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                logger.info(f"✅ Found config file at {config_path}")
                
                # Check for custom provider FIRST (OpenAI-compatible APIs like Qwen, DeepSeek, etc.)
                # This takes priority since agents.defaults.provider is usually set to "custom"
                if 'providers' in config and 'custom' in config['providers']:
                    api_key = config['providers']['custom'].get('api_key')
                    api_base = config['providers']['custom'].get('api_base')
                    if api_key and not api_key.startswith("sk-YOUR-"):
                        logger.info(f"✅ Loaded API key from providers.custom in {config_path}")
                        logger.info(f"   API base: {api_base}")
                        # Get model from agents.defaults if available
                        model = None
                        if 'agents' in config and 'defaults' in config['agents']:
                            model = config['agents']['defaults'].get('model')
                            if model:
                                logger.info(f"   Model from config: {model}")
                        return (api_key, api_base, model)
                
                # Check for OpenAI key in providers.openai.api_key (fallback)
                if 'providers' in config and 'openai' in config['providers']:
                    api_key = config['providers']['openai'].get('api_key')
                    # Skip placeholder keys
                    if api_key and not api_key.startswith("sk-YOUR-") and api_key != "YOUR_OPENAI_API_KEY_HERE":
                        logger.info(f"✅ Loaded OpenAI API key from {config_path}")
                        return (api_key, None, None)
                    elif api_key and (api_key.startswith("sk-YOUR-") or api_key == "YOUR_OPENAI_API_KEY_HERE"):
                        logger.debug(f"   Skipping OpenAI placeholder key")
                        
            except Exception as e:
                logger.warning(f"⚠️ Failed to load config from {config_path}: {e}")
        else:
            logger.debug(f"  ❌ Not found: {config_path}")
    
    # Fallback to environment variable
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        logger.info("✅ Loaded OPENAI_API_KEY from environment variable")
    
    return (api_key, None, None)


def initialize_vanna() -> bool:
    """Initialize Vanna AI with ChromaDB and OpenAI-compatible LLM"""
    global vn
    
    if not VANNA_AVAILABLE:
        logger.warning("⚠️ Vanna not available, running in mock mode")
        return False
    
    try:
        # Get configuration from config file or environment
        api_key, api_base, model = load_openai_api_key()
        if not api_key:
            logger.error("❌ API key not set. Vanna requires an API key.")
            logger.error("   Please set it in:")
            logger.error("   - /app/config/config.json (providers.custom.api_key)")
            logger.error("   - ~/.nanobot/config.json (providers.custom.api_key)")
            logger.error("   - Or environment variable OPENAI_API_KEY")
            return False
        
        # Build config for Vanna
        config = {
            'path': chroma_path
        }
        
        # Create OpenAI client (with custom base_url if using custom provider)
        if api_base:
            # Custom OpenAI-compatible API (e.g., Qwen, DeepSeek)
            logger.info(f"   Creating OpenAI client with custom base_url: {api_base}")
            client = OpenAI(
                api_key=api_key,
                base_url=api_base
            )
            config['client'] = client
        else:
            # Default OpenAI API
            config['api_key'] = api_key
        
        # Use model from config, env var, or default
        if not model:
            model = os.getenv("VANNA_MODEL", "gpt-4o-mini")
        config['model'] = model
        logger.info(f"   Using model: {model}")
        
        vn = MyVanna(config=config)
        logger.info(f"✅ Vanna initialized with ChromaDB (path: {chroma_path})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Vanna initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def connect_vanna_to_postgres():
    """Connect Vanna to PostgreSQL database"""
    global vn, db_url
    
    if vn is None:
        logger.warning("⚠️ Vanna not initialized, skipping database connection")
        return False
    
    try:
        conn = get_db_connection()
        logger.info("✅ Vanna connected to PostgreSQL")
        
        # Get database connection details from URL
        # Format: postgresql://user:password@host:port/dbname
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        
        vn.connect_to_postgres(
            host=parsed.hostname,
            dbname=parsed.path.lstrip('/'),
            user=parsed.username,
            password=parsed.password,
            port=parsed.port or 5432
        )
        
        logger.info("✅ Vanna PostgreSQL connection established")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to connect Vanna to PostgreSQL: {e}")
        return False


def train_vanna_on_schema():
    """讓 Vanna 讀取 PostgreSQL 的結構並進行自我訓練"""
    global vn
    
    if vn is None:
        logger.warning("⚠️ Vanna not initialized, cannot train")
        return False
    
    try:
        logger.info("🧠 正在讓 Vanna 學習 Database Schema...")
        
        # Get all tables from information_schema
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Tables to skip from Vanna training (RAG-specific tables that Vanna shouldn't use)
        RAG_TABLES = {'document_chunks', 'knowledge_graph'}
        
        cursor.execute("""
            SELECT table_name, table_schema 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_name NOT IN ('document_chunks', 'knowledge_graph')
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        logger.info(f"📊 找到 {len(tables)} 張資料表")
        
        trained_count = 0
        for table in tables:
            table_name = table['table_name']
            
            # Get table structure from information_schema (compatible with all PostgreSQL versions)
            try:
                cursor.execute("""
                    SELECT column_name, data_type, is_nullable, character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))
                
                columns = cursor.fetchall()
                
                if columns:
                    # Build CREATE TABLE statement
                    col_defs = []
                    for c in columns:
                        col_type = c['data_type']
                        if col_type == 'character varying' and c['character_maximum_length']:
                            col_type = f"varchar({c['character_maximum_length']})"
                        elif col_type == 'character' and c['character_maximum_length']:
                            col_type = f"char({c['character_maximum_length']})"
                        
                        nullable = "NULL" if c['is_nullable'] == 'YES' else "NOT NULL"
                        col_defs.append(f"    {c['column_name']} {col_type} {nullable}")
                    
                    ddl = f"CREATE TABLE {table_name} (\n" + ",\n".join(col_defs) + "\n);"
                    vn.train(ddl=ddl)
                    trained_count += 1
                    logger.info(f"   ✅ Trained: {table_name}")
                else:
                    logger.warning(f"   ⚠️ No columns found for {table_name}")
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Failed to train {table_name}: {e}")
                continue
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Vanna 訓練完成！共訓練 {trained_count} 張資料表")
        return True
        
    except Exception as e:
        logger.error(f"❌ 訓練失敗：{e}")
        import traceback
        traceback.print_exc()
        return False


def train_vanna_with_enhanced_data() -> bool:
    """
    訓練 Vanna 完整的 DDL、Documentation 和 SQL Examples
    基於所有 Sample Questions 的完整訓練
    """
    global vn
    
    if vn is None:
        logger.warning("⚠️ Vanna not initialized, cannot train")
        return False
    
    try:
        logger.info("🧠 開始訓練 Vanna 增強數據...")
        
        # ===========================================
        # 1. Documentation Training - 商業邏輯
        # ===========================================
        documentation_items = [
            # Market Cap 計算
            "Market Capital is calculated by multiplying the closing price by the issued shares. Formula: Market Capital = closing_price * issued_shares",
            "IMPORTANT: Do NOT use a market_cap column. Always calculate market_cap as (closing_price * issued_shares) in your SQL query.",
            
            # BioTech Sector
            "The BioTech list is flexible. Always query the companies table where sector = 'BioTech' instead of using a hardcoded list of stock codes.",
            "BioTech sector includes pharmaceutical companies, biotechnology firms, medical device manufacturers, and healthcare technology companies.",
            
            # Auditor Opinion ENUM values
            "Auditor opinion types (ENUM): 'Unqualified' (clean opinion), 'Qualified' (with reservations), 'Disclaimer' (unable to express opinion), 'Adverse' (material misstatements), 'Not Applicable'.",
            "A 'Qualified Opinion' indicates that the auditor has reservations about certain aspects of the financial statements.",
            
            # Event Category ENUM values (IMPORTANT for correct WHERE clauses)
            "Event categories (ENUM): 'Property Acquisition', 'Listing Reform', 'Consultation', 'Regulatory Action', 'Market Initiative', 'Enforcement', 'Other'.",
            "When searching for property purchases, use event_category = 'Property Acquisition'.",
            "When searching for listing reforms, use event_category = 'Listing Reform'.",
            "When searching for consultations, use event_category = 'Consultation'.",
            
            # Category Type ENUM values
            "Revenue breakdown category types (ENUM): 'Region', 'Business', 'Product', 'Segment'.",
            "Use category_type = 'Region' for geographic breakdown (e.g., Canada, Asia, Australia).",
            "Use category_type = 'Business' for business segment breakdown (e.g., Retail, Wholesale).",
            
            # Currency Handling (CRITICAL)
            "CURRENCY WARNING: When summing amounts from revenue_breakdown or debt_maturity tables, ALWAYS GROUP BY currency.",
            "NEVER sum amounts with different currencies together. Use GROUP BY currency or filter by a specific currency.",
            "Example: SELECT SUM(amount), currency FROM debt_maturity GROUP BY currency;",
            
            # Fiscal Periods
            "Fiscal periods: 'FY' = Full Year, 'H1' = First Half, 'H2' = Second Half, 'Q1/Q2/Q3/Q4' = Quarters.",
            
            # Stock Codes
            "Hong Kong stock codes are typically 4-5 digits, e.g., '00001' for CK Hutchison, '00700' for Tencent.",
            "Stock codes in the database do NOT include the '.HK' suffix.",
            
            # Revenue Categories
            "Revenue breakdown categories can be by region (e.g., 'Canada', 'Asia', 'Australia') or by business segment (e.g., 'Retail', 'Wholesale').",
            
            # Shareholding
            "Trust holdings are recorded with both the trust name and the trustee name. For example, 'Li Ka-Shing Unity Trust' with trustee 'Li Ka-Shing Unity Trustee Company Limited'.",
            
            # Principal Banker
            "Principal banker refers to the main bank or banks that provide significant banking services to the company.",
            
            # Ultimate Controlling Shareholder
            "Ultimate controlling shareholder is the person or entity that has ultimate control over the company, which may be different from the direct shareholders.",
            
            # Macro Data
            "listing_applications table contains macro-level market data. company_id can be NULL for SFC-level statistics.",
        ]
        
        logger.info("📚 訓練 Documentation...")
        for doc in documentation_items:
            try:
                vn.train(documentation=doc)
            except Exception as e:
                logger.warning(f"   ⚠️ Documentation training error: {e}")
        logger.info(f"   ✅ Documentation 訓練完成 ({len(documentation_items)} 條)")
        
        # ===========================================
        # 2. SQL Training - Sample Questions
        # ===========================================
        sql_examples = [
            # Stock 00001 Questions
            {
                "question": "What is the percentage of shareholding of Li Ka-Shing Unity Trustee Company Limited as trustee of The Li Ka-Shing Unity Trust?",
                "sql": "SELECT shareholder_name, trust_name, percentage_held FROM shareholdings WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND trustee_name LIKE '%Li Ka-Shing Unity Trustee%' AND trust_name LIKE '%Li Ka-Shing Unity Trust%';"
            },
            {
                "question": "List all executive directors of a company",
                "sql": "SELECT person_name, role, committee FROM key_personnel WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND role LIKE '%Executive Director%' ORDER BY person_name;"
            },
            {
                "question": "What is the percentage of total revenue from Canada?",
                "sql": "SELECT category, percentage, amount FROM revenue_breakdown WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND year = 2023 AND category = 'Canada' AND category_type = 'Region';"
            },
            {
                "question": "What is the amount of total debt to be matured in 2027?",
                "sql": "SELECT maturity_year, SUM(amount) as total_amount, currency FROM debt_maturity WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND maturity_year = 2027 GROUP BY maturity_year, currency;"
            },
            {
                "question": "Provide revenue figures from 2019 to 2023",
                "sql": "SELECT year, value, unit FROM financial_metrics WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND metric_name LIKE '%revenue%' AND year BETWEEN 2019 AND 2023 AND fiscal_period = 'FY' ORDER BY year;"
            },
            {
                "question": "Provide fixed assets figures from 2019 to 2023",
                "sql": "SELECT year, value, unit FROM financial_metrics WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND metric_name LIKE '%fixed asset%' AND year BETWEEN 2019 AND 2023 AND fiscal_period = 'FY' ORDER BY year;"
            },
            # SFC Questions
            {
                "question": "List all members of the Securities Compensation Fund Committee",
                "sql": "SELECT person_name, committee_position FROM key_personnel WHERE company_id = (SELECT id FROM companies WHERE stock_code = 'SFC') AND committee LIKE '%Securities Compensation Fund%' ORDER BY person_name;"
            },
            {
                "question": "Generate the bio of Lisa Chen",
                "sql": "SELECT person_name, biography, role FROM key_personnel WHERE company_id = (SELECT id FROM companies WHERE stock_code = 'SFC') AND person_name LIKE '%Lisa Chen%';"
            },
            {
                "question": "How many floors did SFC purchase for the OIE office?",
                "sql": "SELECT event_title, metric_value, metric_unit, event_detail FROM specific_events WHERE company_id = (SELECT id FROM companies WHERE stock_code = 'SFC') AND event_category = 'Property Acquisition' AND event_detail LIKE '%OIE%';"
            },
            {
                "question": "When was the effective date of the SEHK GEM listing reform?",
                "sql": "SELECT event_title, effective_date, event_detail FROM specific_events WHERE company_id = (SELECT id FROM companies WHERE stock_code = 'SFC') AND event_category = 'Listing Reform' AND event_detail LIKE '%GEM%';"
            },
            # BioTech Questions
            {
                "question": "Provide the Top 10 stock codes and names of the market capital from the BioTech Sector",
                "sql": "SELECT c.stock_code, c.name_en as company_name, (m.closing_price * m.issued_shares) as market_capital FROM companies c JOIN market_data m ON c.id = m.company_id WHERE c.sector = 'BioTech' AND m.trade_date = (SELECT MAX(trade_date) FROM market_data) ORDER BY market_capital DESC LIMIT 10;"
            },
            {
                "question": "Provide the Top 5 stock codes and names with the highest total liabilities in BioTech sector",
                "sql": "SELECT c.stock_code, c.name_en as company_name, fm.value as total_liabilities FROM companies c JOIN financial_metrics fm ON c.id = fm.company_id WHERE c.sector = 'BioTech' AND fm.metric_name LIKE '%total liabilit%' AND fm.year = 2024 AND fm.fiscal_period = 'FY' ORDER BY fm.value DESC LIMIT 5;"
            },
            {
                "question": "List all BioTech stocks which has the same auditor as stock 6160 Beone Medicines",
                "sql": "SELECT c.stock_code, c.name_en, c.auditor FROM companies c WHERE c.sector = 'BioTech' AND c.auditor = (SELECT auditor FROM companies WHERE stock_code = '6160') ORDER BY c.stock_code;"
            },
            {
                "question": "Provide all the ultimate controlling shareholders of each BioTech stock",
                "sql": "SELECT stock_code, name_en, ultimate_controlling_shareholder FROM companies WHERE sector = 'BioTech' AND ultimate_controlling_shareholder IS NOT NULL ORDER BY stock_code;"
            },
            {
                "question": "List all BioTech companies which has a Qualified Opinion from auditor",
                "sql": "SELECT stock_code, name_en, auditor, auditor_opinion FROM companies WHERE sector = 'BioTech' AND auditor_opinion = 'Qualified' ORDER BY stock_code;"
            },
            {
                "question": "What is the total revenue of stock 09969 in 2023 and 2024",
                "sql": "SELECT year, value as total_revenue, unit FROM financial_metrics WHERE company_id = (SELECT id FROM companies WHERE stock_code = '09969') AND metric_name LIKE '%total revenue%' AND year IN (2023, 2024) AND fiscal_period = 'FY' ORDER BY year;"
            },
            {
                "question": "What is the average trading volume for stock 09969 in 2022",
                "sql": "SELECT AVG(trading_volume) as avg_volume FROM market_data WHERE company_id = (SELECT id FROM companies WHERE stock_code = '09969') AND trade_date BETWEEN '2022-01-01' AND '2022-12-31';"
            },
            {
                "question": "Show closing price and trading volume for stock 09969 in 2022",
                "sql": "SELECT trade_date, closing_price, trading_volume FROM market_data WHERE company_id = (SELECT id FROM companies WHERE stock_code = '09969') AND trade_date BETWEEN '2022-01-01' AND '2022-12-31' ORDER BY trade_date;"
            },
            {
                "question": "List all BioTech stocks which principal bankers are HSBC",
                "sql": "SELECT stock_code, name_en, principal_banker FROM companies WHERE sector = 'BioTech' AND principal_banker LIKE '%HSBC%';"
            },
        ]
        
        logger.info("💾 訓練 SQL Examples...")
        trained_sql = 0
        for example in sql_examples:
            try:
                vn.train(question=example["question"], sql=example["sql"])
                trained_sql += 1
            except Exception as e:
                logger.warning(f"   ⚠️ SQL training error: {e}")
        logger.info(f"   ✅ SQL Examples 訓練完成 ({trained_sql}/{len(sql_examples)} 條)")
        
        logger.info("✅ Vanna 增強訓練完成！")
        return True
        
    except Exception as e:
        logger.error(f"❌ 增強訓練失敗：{e}")
        import traceback
        traceback.print_exc()
        return False


def train_vanna_on_document(doc_id: str) -> bool:
    """針對特定文件進行訓練 (例如新解析的 PDF)"""
    global vn
    
    if vn is None:
        logger.warning("⚠️ Vanna not initialized, cannot train")
        return False
    
    try:
        logger.info(f"🧠 正在針對文件 {doc_id} 進行訓練...")
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. 獲取文件的表格
        cursor.execute("""
            SELECT file_path, metadata
            FROM raw_artifacts
            WHERE doc_id = %s AND file_type = 'table_json'
            LIMIT 10
        """, (doc_id,))
        
        tables = cursor.fetchall()
        
        for table in tables:
            try:
                # 讀取表格 JSON
                table_path = Path("/app/data/raw") / table['file_path']
                if table_path.exists():
                    with open(table_path, 'r', encoding='utf-8') as f:
                        table_data = json.load(f)
                    
                    # 將表格結構訓練給 Vanna
                    table_name = f"extracted_table_{table_path.stem}"
                    ddl = f"CREATE TABLE {table_name} (extracted_data JSONB)"
                    vn.train(ddl=ddl)
                    
                    # 訓練一個範例查詢
                    vn.train(
                        question=f"從 {table_name} 中提取資料",
                        sql=f"SELECT * FROM {table_name}"
                    )
                    
                    logger.info(f"   ✅ Trained table: {table_path.name}")
            except Exception as e:
                logger.warning(f"   ⚠️ Failed to train table: {e}")
                continue
        
        # 2. 獲取文件的 chunks
        cursor.execute("""
            SELECT COUNT(*) as chunk_count
            FROM document_chunks
            WHERE doc_id = %s
        """, (doc_id,))
        
        result = cursor.fetchone()
        if result:
            logger.info(f"   📄 文件包含 {result['chunk_count']} 個 chunks")
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ 文件 {doc_id} 訓練完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 文件訓練失敗：{e}")
        import traceback
        traceback.print_exc()
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager"""
    # Startup
    logger.info("="*60)
    logger.info("Vanna Service Starting...")
    logger.info("="*60)
    
    global db_url
    
    # Wait for database
    max_retries = 30
    retry_delay = 2
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports"
    )
    
    for i in range(max_retries):
        try:
            logger.info(f"Attempting database connection (Attempt {i+1}/{max_retries})...")
            conn = get_db_connection()
            conn.close()
            logger.info("✅ Database connection successful")
            break
        except Exception as e:
            logger.warning(f"Database not ready: {e}")
            if i < max_retries - 1:
                logger.info(f"Waiting {retry_delay} seconds before retry...")
                time.sleep(retry_delay)
            else:
                logger.error("❌ Cannot connect to database, exiting")
                sys.exit(1)
    
    # Initialize Vanna
    if initialize_vanna():
        connect_vanna_to_postgres()
        train_vanna_on_schema()
        train_vanna_with_enhanced_data()  # 訓練 DDL + Documentation + SQL Examples
        logger.info("✅ Vanna Service ready")
    else:
        logger.warning("⚠️ Vanna initialization failed, running in mock mode")
    
    yield
    
    # Shutdown
    logger.info("Vanna Service shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Vanna AI Service",
    description="Text-to-SQL with RAG training for financial queries",
    version="1.0.0",
    lifespan=lifespan
)


# --- API Endpoints ---

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "vanna_available": VANNA_AVAILABLE and vn is not None,
        "chroma_path": chroma_path
    }


@app.get("/status")
async def get_status():
    """Get Vanna service status"""
    return {
        "vanna_initialized": vn is not None,
        "training_status": "ready" if vn else "not_initialized",
        "chroma_path": chroma_path
    }


@app.post("/api/train")
async def trigger_training(
    request: TrainRequest,
    background_tasks: BackgroundTasks
):
    """
    提供給 PDF Ingestion Worker 呼叫。
    當有新文件解析完畢，打這支 API，Vanna 就會在背景學習。
    
    Args:
        train_type: "schema" (全庫結構) | "ddl" (特定 DDL) | "sql" (SQL 範例)
        doc_id: Optional - 特定文件 ID
    """
    if vn is None:
        raise HTTPException(status_code=503, detail="Vanna not initialized")
    
    logger.info(f"📥 收到訓練請求：type={request.train_type}, doc_id={request.doc_id}")
    
    try:
        if request.doc_id:
            # 針對特定文件訓練
            background_tasks.add_task(train_vanna_on_document, request.doc_id)
            return {
                "status": "training_started",
                "message": f"Vanna is learning document {request.doc_id} in background."
            }
        else:
            # 全庫結構訓練
            background_tasks.add_task(train_vanna_on_schema)
            return {
                "status": "training_started",
                "message": "Vanna is learning the database schema in background."
            }
    
    except Exception as e:
        logger.error(f"❌ 訓練請求失敗：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    提供給 WebUI 呼叫，用自然語言生出 SQL 並回答
    
    Args:
        question: 自然語言問題
        include_sql: 是否返回 SQL
        include_summary: 是否返回摘要
    """
    if vn is None:
        # Mock response for demo
        return AskResponse(
            question=request.question,
            sql="SELECT * FROM documents LIMIT 10;",
            answer="[Mock] Vanna is not initialized. This is a demo response.",
            data=[{"demo": "data"}],
            training_status="not_initialized"
        )
    
    try:
        logger.info(f"🤔 收到問題：{request.question}")
        
        # Generate SQL
        sql = vn.generate_sql(request.question) if request.include_sql else None
        
        if sql:
            logger.info(f"📝 生成的 SQL: {sql}")
            
            # Run SQL
            df = vn.run_sql(sql) if request.include_sql else None
            
            # Generate answer
            answer = None
            if request.include_summary and df is not None:
                answer = vn.generate_summary(request.question, df)
            
            # Convert DataFrame to list of dicts
            data = None
            if df is not None:
                data = df.to_dict('records')
            
            return AskResponse(
                question=request.question,
                sql=sql,
                answer=answer,
                data=data,
                training_status="ready"
            )
        else:
            return AskResponse(
                question=request.question,
                sql=None,
                answer="無法生成 SQL，請嘗試重新表述問題",
                training_status="ready"
            )
    
    except Exception as e:
        logger.error(f"❌ 問題回答失敗：{e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/train/ddl")
async def train_with_ddl(ddl: str):
    """直接提供 DDL 進行訓練"""
    if vn is None:
        raise HTTPException(status_code=503, detail="Vanna not initialized")
    
    try:
        vn.train(ddl=ddl)
        logger.info(f"✅ DDL 訓練成功")
        return {"status": "success", "message": "DDL trained successfully"}
    except Exception as e:
        logger.error(f"❌ DDL 訓練失敗：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/train/sql")
async def train_with_sql(question: str, sql: str):
    """提供問題 + SQL 範例進行訓練"""
    if vn is None:
        raise HTTPException(status_code=503, detail="Vanna not initialized")
    
    try:
        vn.train(question=question, sql=sql)
        logger.info(f"✅ SQL 範例訓練成功：{question}")
        return {"status": "success", "message": "SQL example trained successfully"}
    except Exception as e:
        logger.error(f"❌ SQL 訓練失敗：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/extract")
async def extract_info(request: ExtractRequest):
    """
    使用 LLM 從文本中提取結構化信息
    
    Args:
        text: 要提取的文本內容
        extract_type: 提取類型 (company_info | financial_metrics | key_personnel)
    
    Returns:
        提取的結構化數據
    """
    if vn is None:
        # Fallback: 使用正則表達式提取
        return _extract_with_regex(request.text, request.extract_type)
    
    try:
        logger.info(f"🔍 提取信息：type={request.extract_type}")
        
        if request.extract_type == "company_info":
            # 構建提取公司信息的 prompt
            prompt = f"""從以下財報內容中提取公司信息，返回 JSON 格式。

需要提取的信息：
- stock_code: 股票代碼（港股格式如 00001, 00700 等）
- name_en: 公司英文名稱
- name_zh: 公司中文名稱
- industry: 所屬行業
- sector: 所屬板塊

文本內容：
{request.text[:3000]}

請只返回 JSON 格式，不要包含其他說明。如果無法提取某個字段，請返回 null。

示例輸出：
{{"stock_code": "00001", "name_en": "CK Hutchison Holdings Limited", "name_zh": "長江和記實業有限公司", "industry": "Conglomerates", "sector": "Conglomerates"}}
"""
            
            # 使用 Vanna 的 LLM 進行提取
            response = vn.client.chat.completions.create(
                model=vn.config.get('model', 'gpt-4o-mini'),
                messages=[
                    {"role": "system", "content": "你是一個專業的財報分析助手，擅長從財報中提取結構化信息。只返回 JSON 格式，不要包含其他說明。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # 嘗試解析 JSON
            try:
                # 移除可能的 markdown 代碼塊標記
                if result_text.startswith("```"):
                    result_text = result_text.split("```")[1]
                    if result_text.startswith("json"):
                        result_text = result_text[4:]
                
                import json
                company_info = json.loads(result_text)
                logger.info(f"✅ 提取成功：{company_info}")
                return {"company_info": company_info}
            except json.JSONDecodeError:
                logger.warning(f"⚠️ JSON 解析失敗，嘗試正則提取")
                return _extract_with_regex(request.text, request.extract_type)
        
        else:
            # 其他類型的提取（未來擴展）
            return {"extracted_data": None, "message": f"Extract type '{request.extract_type}' not implemented yet"}
    
    except Exception as e:
        logger.error(f"❌ 信息提取失敗：{e}")
        import traceback
        traceback.print_exc()
        # Fallback to regex extraction
        return _extract_with_regex(request.text, request.extract_type)


def _extract_with_regex(text: str, extract_type: str) -> dict:
    """使用正則表達式提取信息（後備方案）"""
    import re
    
    if extract_type == "company_info":
        # 港股格式: 00001, 00700 等
        hk_pattern = r'\b(\d{4,5})(?:\.HK)?\b'
        matches = re.findall(hk_pattern, text)
        
        stock_code = None
        for match in matches:
            code_num = int(match)
            if 1 <= code_num <= 99999 and code_num > 1000:
                stock_code = match.zfill(5)
                break
        
        return {
            "company_info": {
                "stock_code": stock_code,
                "name_en": None,
                "name_zh": None,
                "industry": None,
                "sector": None
            }
        }
    
    return {"extracted_data": None}


if __name__ == "__main__":
    logger.info("🚀 啟動 Vanna API 服務...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("VANNA_PORT", "8082")),
        log_level="info"
    )
