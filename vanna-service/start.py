"""
Vanna Service - Text-to-SQL API for Financial Document Analysis
================================================================

Features:
1. Initialize Vanna with ChromaDB + OpenAI/Custom LLM
2. Auto-train on PostgreSQL Schema
3. Train with comprehensive DDL, Documentation, and SQL Examples
4. REST API for training and queries
5. Support continuous learning (邊做邊學)

【v2.3 Schema Updates】
- Column name changes applied in SQL generation hints
- JSONB dynamic attributes support
- Vector embedding support (pgvector)
"""

import os
import time
import json
from pathlib import Path
from loguru import logger
import sys
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

# FastAPI imports
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# Database
import psycopg2
from psycopg2.extras import RealDictCursor

# Vanna imports with fallback
try:
    from vanna.chromadb import ChromaDB_VectorStore
    from vanna.openai import OpenAI_Chat
    from openai import OpenAI

    class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
        def __init__(self, config):
            # Separate configs for parent classes
            chroma_config = {'path': config.get('path', './chromadb')} if config else {}
            openai_config = {k: v for k, v in config.items() if k != 'path'} if config else {}
            
            # Initialize parent classes
            ChromaDB_VectorStore.__init__(self, config=chroma_config)
            OpenAI_Chat.__init__(self, config=openai_config)
            
            # Explicitly set client if using custom OpenAI-compatible API
            if config and 'client' in config:
                self.client = config['client']

    VANNA_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ Vanna import failed: {e}. Running in mock mode.")
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

# Ensure data directories exist
Path(chroma_path).mkdir(parents=True, exist_ok=True)

# 🆕 v2.3: Column name change hints for SQL generation
COLUMN_CHANGE_HINTS = """
【⚠️ v2.3 Schema 欄位名稱變更提醒】

market_data 表:
- trade_date → data_date
- closing_price → close_price
- opening_price → open_price
- trading_volume → volume

revenue_breakdown 表:
- category → segment_name
- category_type → segment_type
- amount → revenue_amount

key_personnel 表:
- person_name → name_en
- person_name_zh → name_zh
- committee → committee_membership (JSONB)

document_pages 表:
- ❌ 已刪除 company_id 欄位！必須 JOIN documents！

raw_artifacts 表:
- ❌ 已刪除 company_id 欄位！必須 JOIN documents！
"""


class TrainRequest(BaseModel):
    """Training request model"""
    train_type: str = "schema"  # schema, ddl, sql
    doc_id: Optional[str] = None  # Optional: specific document ID to train on


class AskRequest(BaseModel):
    """Question request model"""
    question: str
    include_sql: bool = True
    include_summary: bool = False


class ExtractRequest(BaseModel):
    """Extraction request model"""
    text: str
    extract_type: str = "company_info"  # company_info, financial_metrics, key_personnel


class AskResponse(BaseModel):
    """Query response model"""
    question: str
    sql: Optional[str] = None
    answer: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    status: str = "ready"


def get_db_connection():
    """Get PostgreSQL connection - requires DATABASE_URL environment variable"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(db_url, connect_timeout=10)


def load_openai_api_key() -> tuple:
    """
    Load API key, base URL, and model from config file or environment variable
    
    Returns:
        tuple: (api_key, api_base, model) - api_base and model may be None for default OpenAI
    """
    # Try to load from config files first (following nanobot pattern)
    config_paths = [
        Path("/app/config/config.json"),           # Docker mounted config
        Path.home() / ".nanobot" / "config.json",  # User nanobot config
        Path.home() / ".openharness" / "config.json",  # Fallback home path
    ]
    
    logger.debug(f"🔍 Searching for config files in {len(config_paths)} locations...")
    
    for config_path in config_paths:
        logger.debug(f"  Checking: {config_path}")
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                logger.info(f"✅ Found config at {config_path}")
                
                # Check for custom OpenAI-compatible API (like Qwen, DeepSeek, etc.)
                # This has priority - agents.provider = 'custom' means use custom endpoint
                if 'providers' in config and 'custom' in config['providers']:
                    api_key = config['providers']['custom'].get('api_key')
                    api_base = config['providers']['custom'].get('api_base')
                    if api_base and api_key and not api_key.startswith("sk-YOUR-"):
                        logger.info(f"✅ Loaded custom API from config: {config_path}")
                        logger.debug(f"   API base: {api_base}")
                        # Get model from agents config if available
                        model = None
                        if 'agents' in config and 'defaults' in config['agents']:
                            model = config['agents']['defaults'].get('model')
                            if model:
                                logger.debug(f"   Model from config: {model}")
                        return (api_key, api_base, model)
                
                # Check for OpenAI key in providers.openai.api_key (fallback)
                if 'providers' in config and 'openai' in config['providers']:
                    api_key = config['providers']['openai'].get('api_key')
                    # Skip placeholder keys
                    if api_key and not api_key.startswith("sk-YOUR-") and api_key != "YOUR_OPENAI_KEY":
                        logger.info(f"✅ Loaded OpenAI key from config: {config_path}")
                        return (api_key, None, None)
                        
            except Exception as e:
                logger.warning(f"⚠️ Failed to load config from {config_path}: {e}")
        else:
            logger.debug(f"   ❌ Not found: {config_path}")
    
    # Fallback to environment variable
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        logger.info("✅ Loaded OPENAI_API_KEY from environment")
        return (api_key, None, None)
    
    return (None, None, None)


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
            logger.error("❌ API key not set. Vanna needs an API key.")
            logger.error("   Please set it in:")
            logger.error("   - /app/config/config.json (providers.custom.api_key)")
            logger.error("   - ~/.nanobot/config.json")
            logger.error("   - Or environment variable OPENAI_API_KEY")
            return False
        
        # Build config for Vanna
        config = {
            'path': chroma_path,
        }
        
        # Use OpenAI client with custom base_url if using alternative provider
        if api_base:
            # Custom OpenAI-compatible API (e.g., Qwen, DeepSeek, etc.)
            logger.info(f"🔄 Using custom OpenAI client with base_url: {api_base}")
            client = OpenAI(
                api_key=api_key,
                base_url=api_base
            )
            config['client'] = client
        else:
            # Default OpenAI API
            config['api_key'] = api_key
        
        # Use model from config, env var, or default
        if model:
            config['model'] = model
        else:
            config['model'] = os.getenv("VANNA_MODEL", "gpt-4o-mini")
        logger.info(f"   Using model: {config['model']}")
        
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
        return
    
    try:
        conn = get_db_connection()
        logger.info("✅ Connected to PostgreSQL for schema inspection")
        
        # Get database connection details from DATABASE_URL
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
        conn.close()
        return
        
    except Exception as e:
        logger.error(f"❌ Failed to connect Vanna to PostgreSQL: {e}")
        return


def train_vanna_on_schema():
    """讓 Vanna 學習 PostgreSQL Schema 並進行基本訓練"""
    global vn
    
    if vn is None:
        logger.warning("⚠️ Vanna not initialized, cannot train")
        return
    
    try:
        logger.info("🧠 正在讓 Vanna 學習 Database Schema...")
        
        # Get all table information from information_schema
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Tables to skip for Vanna training (RAG-specific tables)
        RAG_SKIP_TABLES = {'document_pages', 'document_chunks', 'raw_artifacts'}
        
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            AND table_name NOT IN ('document_pages', 'document_chunks', 'raw_artifacts')
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        logger.info(f"📊 找到 {len(tables)} 張資料表")
        
        trained_count = 0
        for table in tables:
            table_name = table['table_name']
            
            # Get table structure from information_schema
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
                    for col in columns:
                        col_type = col['data_type']
                        if col_type == 'character varying' and col['character_maximum_length']:
                            col_type = f"varchar({col['character_maximum_length']})"
                        elif col_type == 'character' and col['character_maximum_length']:
                            col_type = f"char({col['character_maximum_length']})"
                        
                        nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                        col_defs.append(f"    {col['column_name']} {col_type} {nullable}")
                    
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
        
        logger.info(f"✅ Vanna Schema 訓練完成！共訓練 {trained_count} 張資料表")
        return True
        
    except Exception as e:
        logger.error(f"❌ Schema 訓練失敗：{e}")
        import traceback
        traceback.print_exc()
        return False


def train_vanna_with_enhanced_data():
    """
    訓練 Vanna 完整的 DDL、Documentation 和 SQL Examples
    🔧 從 JSON 檔案載入訓練資料（資料與代碼分離）
    """
    global vn
    
    if vn is None:
        logger.warning("⚠️ Vanna not initialized, cannot train")
        return False
    
    try:
        logger.info("🧠 開始訓練 Vanna 增強數據...")
        
        # 📂 載入 JSON 訓練模組（資料與代碼分離）
        # Use relative path to ensure Docker and local dev both work
        from pathlib import Path
        
        # Add current directory to path to ensure vanna_training can be found
        current_dir = Path(__file__).parent
        if str(current_dir) not in sys.path:
            sys.path.insert(0, str(current_dir))
        
        try:
            from vanna_training import VannaTrainingData
        except ImportError:
            # Fallback: try relative import
            from .vanna_training import VannaTrainingData
        
        # Determine data directory (Docker or local)
        data_dir = "/app/data"
        if not Path(data_dir).exists():
            # Local dev environment
            data_dir = str(current_dir / "data")
        
        trainer = VannaTrainingData(data_dir=str(data_dir))
        
        # Execute training (with validation)
        stats = trainer.train_vanna(vn, validate=True)
        
        logger.info("✅ Vanna 增強訓練完成！")
        logger.info(f"   DDL: {stats['ddl_trained']}")
        logger.info(f"   Documentation: {stats['documentation_trained']}")
        logger.info(f"   SQL: {stats['sql_trained']}")
        
        if stats['errors']:
            logger.warning(f"⚠️ 錯誤: {len(stats['errors'])}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 增強訓練失敗：{e}")
        import traceback
        traceback.print_exc()
        return False


def train_vanna_on_document(doc_id: str) -> bool:
    """針對特定文檔進行訓練（從解析的 PDF 內容）"""
    global vn
    
    if vn is None:
        logger.warning("⚠️ Vanna not available, cannot train")
        return False
    
    try:
        logger.info(f"🧠 正在針對文檔 {doc_id} 進行訓練...")
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. 獲取文檔的表格資料（使用 document_id 字段）
        cursor.execute("""
            SELECT file_path, metadata 
            FROM raw_artifacts 
            WHERE document_id = (SELECT id FROM documents WHERE doc_id = %s)
            AND artifact_type = 'table'
            LIMIT 10
        """, (doc_id,))
        
        tables = cursor.fetchall()
        
        for table in tables:
            try:
                # 讀取表格資料
                table_path = Path(table['file_path'])
                if table_path.exists():
                    with open(table_path, 'r', encoding='utf-8') as f:
                    table_data = json.load(f)
                    
                    # 將表格結構訓練給 Vanna
                    table_name = f"extracted_{table_path.stem}"
                    ddl = f"CREATE TABLE {table_name} (extracted_data JSONB);"
                    vn.train(ddl=ddl)
                    
                    # 訓練一個範例查詢
                    vn.train(
                        question=f"從 {table_name} 中查詢資料",
                        sql=f"SELECT * FROM {table_name}"
                    )
                    
                    logger.info(f"   ✅ Trained table: {table_path.name}")
            except Exception as e:
                logger.warning(f"   ⚠️ Failed to train table: {e}")
                continue
        
        # 2. 獲取文檔的 chunks 數量
        cursor.execute("""
            SELECT COUNT(*) as chunk_count 
            FROM document_chunks
            WHERE document_id = (SELECT id FROM documents WHERE doc_id = %s)
        """, (doc_id,))
        
        result = cursor.fetchone()
        if result:
            logger.info(f"   📄 文檔包含 {result['chunk_count']} 個 chunks")
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ 文檔 {doc_id} 訓練完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 文檔訓練失敗：{e}")
        import traceback
        traceback.print_exc()
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager"""
    # Startup
    logger.info("🚀 Vanna Service Starting...")
    logger.info("=" * 50)
    
    # Wait for database
    max_retries = 30
    retry_delay = 2
    
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        logger.error("❌ DATABASE_URL environment variable is not set")
        logger.error("   Required for production deployment. Example:")
        logger.error("   DATABASE_URL=postgresql://user:password@host:port/database")
        sys.exit(1)
    
    for i in range(max_retries):
        try:
            logger.info(f"⏳ Waiting for database (Attempt {i+1}/{max_retries})...")
            conn = get_db_connection()
            conn.close()
            logger.info("✅ Database connection successful")
            break
        except Exception as e:
            logger.warning(f"Database not ready: {e}")
            if i < max_retries - 1:
                logger.info(f"   Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("❌ Cannot connect to database after max retries")
                sys.exit(1)
    
    # Initialize Vanna
    if initialize_vanna():
        connect_vanna_to_postgres()
        train_vanna_on_schema()
        train_vanna_with_enhanced_data()  # 訓練 DDL + Documentation + SQL Examples
        logger.info("✅ Vanna Service ready!")
    else:
        logger.warning("⚠️ Vanna initialization failed, running in mock mode")
    
    yield
    
    # Shutdown
    logger.info("🛑 Vanna Service shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Vanna AI Service",
    description="Text-to-SQL with RAG for financial document analysis (v2.3 Schema)",
    version="2.3.0",
    lifespan=lifespan
)


# --- API Endpoints ---

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "vanna_available": VANNA_AVAILABLE,
        "vanna_initialized": vn is not None,
        "chroma_path": chroma_path,
        "schema_version": "2.3.0"
    }


@app.get("/status")
async def get_status():
    """Get Vanna service status"""
    return {
        "vanna_initialized": vn is not None,
        "database_connected": True,
        "chroma_status": "ready" if vn else "not_initialized",
        "schema_version": "2.3.0",
        "column_changes": {
            "market_data": {"trade_date": "data_date", "closing_price": "close_price", "trading_volume": "volume"},
            "revenue_breakdown": {"category": "segment_name", "category_type": "segment_type", "amount": "revenue_amount"},
            "key_personnel": {"person_name": "name_en", "committee": "committee_membership"},
            "document_pages": {"company_id": "REMOVED - must JOIN documents"}
        }
    }


@app.post("/api/train")
async def trigger_training(
    request: TrainRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger training for Vanna
    
    This endpoint is called by PDF Ingestion Worker.
    When a new document is processed, call this to make Vanna learn.
    
    Args:
        request.train_type: "schema" (全結構) | "ddl" (特定 DDL) | "sql" (SQL 範例)
        request.doc_id: Optional - specific document ID to train on
    """
    if vn is None:
        raise HTTPException(status_code=503, detail="Vanna not initialized")
    
    logger.info(f"📥 Received training request: type={request.train_type}, doc_id={request.doc_id}")
    
    try:
        if request.doc_id:
            # 針對特定文檔訓練
            background_tasks.add_task(train_vanna_on_document, request.doc_id)
            return {
                "status": "training_started",
                "message": f"Vanna is learning from document {request.doc_id} in background."
            }
        else:
            # 全庫結構訓練
            background_tasks.add_task(train_vanna_on_schema)
            return {
                "status": "training_started",
                "message": "Vanna is learning database schema in background."
            }
        
    except Exception as e:
        logger.error(f"❌ Training request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ask", response_model=AskResponse)
async def ask_vanna(request: AskRequest):
    """
    Ask Vanna a question
    
    Convert natural language to SQL and execute query
    
    Args:
        request.question: Natural language question
        request.include_sql: Return SQL (default: true)
        request.include_summary: Return summary (default: false)
    """
    if vn is None:
        # Mock response for demo
        return AskResponse(
            question=request.question,
            sql="SELECT * FROM documents LIMIT 10;",
            answer="[Mock] Vanna is not initialized. This is a demo response.",
            data=[{"demo": "data"}],
            status="mock"
        )
    
    try:
        logger.info(f"🤔 Received question: {request.question}")
        
        # 🆕 v2.3: Inject column change hints into prompt
        enhanced_question = f"""
{COLUMN_CHANGE_HINTS}

用戶問題：{request.question}

請根據 v2.3 Schema 生成 SQL 查詢。
"""
        
        # Generate SQL
        sql = vn.generate_sql(enhanced_question) if request.include_sql else None
        
        if sql:
            logger.debug(f"📝 Generated SQL: {sql}")
            
            # Run SQL
            try:
                df = vn.run_sql(sql)
                
                # Generate explanation if requested
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
                    status="ready"
                )
            except Exception as sql_error:
                logger.warning(f"SQL execution error: {sql_error}")
                return AskResponse(
                    question=request.question,
                    sql=sql,
                    error=str(sql_error),
                    status="error"
                )
        else:
            return AskResponse(
                question=request.question,
                error="無法生成 SQL，請嘗試重新表述問題",
                status="failed"
            )
        
    except Exception as e:
        logger.error(f"❌ Query failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/train_ddl")
async def train_with_ddl(ddl: str):
    """Provide DDL for training"""
    if vn is None:
        raise HTTPException(status_code=503, detail="Vanna not initialized")
    
    try:
        vn.train(ddl=ddl)
        logger.info("✅ DDL training successful")
        return {"status": "success", "message": "DDL trained successfully"}
    except Exception as e:
        logger.error(f"❌ DDL training failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/train_sql")
async def train_with_sql(question: str, sql: str):
    """Train with question + SQL example"""
    if vn is None:
        raise HTTPException(status_code=503, detail="Vanna not initialized")
    
    try:
        vn.train(question=question, sql=sql)
        logger.info(f"✅ SQL training successful for: {question}")
        return {"status": "success", "message": "SQL example trained successfully"}
    except Exception as e:
        logger.error(f"❌ SQL training failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/extract")
async def extract_info(request: ExtractRequest):
    """
    Extract structured information from text using LLM
    
    Args:
        request.text: Text content to extract from
        request.extract_type: Extraction type (company_info | financial_metrics | key_personnel)
    
    Returns:
        Extracted structured data
    """
    if vn is None:
        # Fallback: use regex extraction
        return _extract_with_regex(request.text, request.extract_type)
    
    try:
        logger.info(f"🔍 Extracting info: type={request.extract_type}")
        
        if request.extract_type == "company_info":
            # Build prompt for company info extraction
            prompt = f"""從以下財報內容中提取公司信息，返回 JSON 格式。

需要提取的信息：
- stock_code: 股票代碼（港股格式如 00001, 00700 等）
- name_en: 公司英文名稱
- name_zh: 公司中文名稱
- ai_extracted_industries: 行業列表（JSON Array，如 ["Biotech", "Healthcare"]）
- sector: 所屬大板塊

文本內容：
{request.text[:3000]}

請只返回 JSON 格式，不要包含其他說明。如果無法提取某個字段，請返回 null。

示例輸出：
{{"stock_code": "00001", "name_en": "CK Hutchison Holdings Limited", "name_zh": "長江和記實業有限公司", "ai_extracted_industries": ["Conglomerates", "Infrastructure"], "sector": "Conglomerates"}}
"""
            
            # Use Vanna's LLM for extraction
            response = vn.client.chat.completions.create(
                model=vn.config.get('model', 'gpt-4o-mini'),
                messages=[
                    {"role": "system", "content": "你是一個專業的財報分析助手，擅長從財報中提取結構化信息。只返回 JSON 格式。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Try to parse JSON
            try:
                # Remove possible markdown code block markers
                if result_text.startswith("```"):
                    result_text = result_text.split("```")[1]
                    if result_text.startswith("json"):
                        result_text = result_text[4:]
                
                company_info = json.loads(result_text)
                logger.info(f"✅ Extraction successful: {company_info}")
                return {"company_info": company_info}
            except json.JSONDecodeError:
                logger.warning(f"⚠️ JSON parsing failed, falling back to regex")
                return _extract_with_regex(request.text, request.extract_type)
        
        else:
            # Other extraction types (future expansion)
            return {"extracted_data": None, "message": f"Extract type '{request.extract_type}' not implemented yet"}
        
    except Exception as e:
        logger.error(f"❌ Extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return _extract_with_regex(request.text, request.extract_type)


def _extract_with_regex(text: str, extract_type: str) -> dict:
    """Regex-based extraction (fallback)"""
    import re
    
    if extract_type == "company_info":
        # HK stock format: 00001, 00700, etc.
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
                "ai_extracted_industries": None,
                "sector": None
            }
        }
    
    return {"extracted_data": None}


@app.get("/api/column_changes")
async def get_column_changes():
    """Get v2.3 schema column name changes"""
    return {
        "version": "2.3.0",
        "changes": COLUMN_CHANGE_HINTS,
        "mapping": {
            "market_data": {
                "trade_date": "data_date",
                "closing_price": "close_price",
                "opening_price": "open_price",
                "trading_volume": "volume"
            },
            "revenue_breakdown": {
                "category": "segment_name",
                "category_type": "segment_type",
                "amount": "revenue_amount"
            },
            "key_personnel": {
                "person_name": "name_en",
                "person_name_zh": "name_zh",
                "committee": "committee_membership"
            },
            "document_pages": {
                "company_id": "REMOVED - must JOIN documents to filter by owner_company_id"
            },
            "raw_artifacts": {
                "company_id": "REMOVED - must JOIN documents"
            }
        },
        "new_features": {
            "documents": "dynamic_attributes JSONB for theme, region, index_quarter etc.",
            "market_data": "Added market_cap, pe_ratio, pb_ratio, dividend_yield",
            "shareholding_structure": "Added trust_name, trustee_name for trust holdings",
            "document_pages": "Added ocr_confidence, embedding_vector VECTOR(1536)",
            "views": [
                "v_companies_for_vanna - resolves dual-track industry logic",
                "v_documents_for_vanna - flattens JSONB and joins companies",
                "document_summary - quick document overview"
            ]
        }
    }


if __name__ == "__main__":
    logger.info("🚀 Starting Vanna API Service...")
    uvicorn.run(app, host="0.0.0.0", port=8000)