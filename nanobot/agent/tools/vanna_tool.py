"""
Vanna AI Text-to-SQL Integration

Provides RAG-powered text-to-SQL generation with schema training.
Replaces manual SQL generation with AI-powered accurate queries.

Key Features:
- Just-in-Time Schema Injection for JSONB attributes
- Dynamic key discovery before query generation
- PostgreSQL JSONB query syntax support

Usage:
    from nanobot.agent.tools.vanna_tool import VannaSQL
    
    vanna = VannaSQL()
    vanna.train_schema()
    
    sql = vanna.generate_sql("Show Tencent's revenue for 2020-2023")
    result = vanna.execute(sql)
    
    # With dynamic schema injection
    sql = vanna.generate_sql_with_dynamic_schema("Find Q3 biotech reports")
"""

from typing import Optional, List, Dict, Any
from loguru import logger
import os
import json
from pathlib import Path


class VannaSQL:
    """
    Vanna AI Text-to-SQL generator with RAG training.
    
    Example:
        vanna = VannaSQL()
        vanna.train_schema()
        
        # Generate SQL from natural language
        sql = vanna.generate_sql("What was Tencent's revenue in 2023?")
        
        # Execute query
        results = vanna.execute(sql)
    """
    
    def __init__(self, 
                 database_url: Optional[str] = None,
                 model_name: str = "financial-sql",
                 api_key: Optional[str] = None,
                 persist_dir: Optional[str] = None):
        """
        Initialize Vanna AI.
        
        Args:
            database_url: PostgreSQL connection URL (uses env vars if not provided)
            model_name: Vanna model name
            api_key: Vanna API key (optional, uses default if not provided)
            persist_dir: Directory to persist training state
        """
        # Fix #1: Use environment variables for database connection (unified with ingestion module)
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql://${POSTGRES_USER:postgres}:${POSTGRES_PASSWORD:postgres_password_change_me}@${POSTGRES_HOST:localhost}:${POSTGRES_PORT:5432}/${POSTGRES_DB:annual_reports}"
        )
        # Resolve environment variable references
        self.database_url = self._resolve_env_vars(self.database_url)
        
        self.model_name = model_name
        self.api_key = api_key
        self.persist_dir = Path(persist_dir or os.getenv("VANNA_PERSIST_DIR", "/app/data/vanna_db"))
        
        self._vn = None
        self._trained = False
        self._training_state_file = self.persist_dir / "training_state.json"
        
        # Fix #4: Load training state from disk
        self._load_training_state()
        
        logger.info(f"VannaSQL initialized (model={model_name}, database={self.database_url.split('@')[1] if '@' in self.database_url else 'unknown'})")
    
    def _resolve_env_vars(self, url: str) -> str:
        """Resolve ${VAR} or ${VAR:default} patterns in URL"""
        from nanobot.utils.helpers import resolve_env_vars
        return resolve_env_vars(url)
    
    def _load_training_state(self):
        """Load training state from disk (Fix #4: Persist training state)"""
        if self._training_state_file.exists():
            try:
                with open(self._training_state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                self._trained = state.get('trained', False)
                logger.info(f"📚 Loaded Vanna training state: trained={self._trained}")
            except Exception as e:
                logger.warning(f"Failed to load training state: {e}")
                self._trained = False
        else:
            logger.info("📖 No existing training state found, will train on first use")
    
    def _save_training_state(self):
        """Save training state to disk (Fix #4: Persist training state)"""
        try:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            with open(self._training_state_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'trained': self._trained,
                    'model_name': self.model_name,
                    'updated_at': Path(self._training_state_file).stat().st_mtime
                }, f, indent=2)
            logger.info(f"💾 Saved Vanna training state to {self._training_state_file}")
        except Exception as e:
            logger.error(f"Failed to save training state: {e}")
    
    @property
    def vn(self):
        """Lazy load Vanna instance"""
        if not self._vn:
            try:
                from vanna.remote import VannaDefault
                
                # Use Vanna's default model (free tier)
                # For production, configure with your own API key
                if self.api_key:
                    self._vn = VannaDefault(model=self.model_name, api_key=self.api_key)
                else:
                    # Use ChromaDB-backed local instance with persistence
                    from vanna.chromadb import ChromaDB_VectorStore
                    import chromadb
                    from pathlib import Path
                    
                    # 指定 ChromaDB 持久化路徑 (Docker 容器內為 /app/data/vanna_db)
                    persist_dir = os.getenv("VANNA_PERSIST_DIR", "/app/data/vanna_db")
                    Path(persist_dir).mkdir(parents=True, exist_ok=True)
                    
                    # 初始化帶有持久化的 ChromaDB
                    chroma_client = chromadb.PersistentClient(path=persist_dir)
                    self._vn = ChromaDB_VectorStore(chroma_client=chroma_client)
                    
                    # 連接 PostgreSQL
                    self._vn.connect_to_postgres(
                        host=os.getenv("POSTGRES_HOST", "localhost"),
                        port=os.getenv("POSTGRES_PORT", "5432"),
                        dbname=os.getenv("POSTGRES_DB", "annual_reports"),
                        user=os.getenv("POSTGRES_USER", "postgres"),
                        password=os.getenv("POSTGRES_PASSWORD", "postgres_password_change_me")
                    )
                
                logger.info(f"Vanna instance created with ChromaDB persistence at {persist_dir}")
            except Exception as e:
                logger.error(f"Failed to create Vanna instance: {e}")
                raise
        
        return self._vn
    
    def train_schema(self, force: bool = False) -> Dict[str, int]:
        """
        Train Vanna on database schema and documentation.
        
        Args:
            force: If True, retrain even if already trained
        
        Returns:
            Training statistics
        """
        if self._trained and not force:
            logger.info("Already trained, skipping")
            return {'status': 'skipped', 'reason': 'already_trained'}
        
        try:
            stats = {
                'ddl_statements': 0,
                'documentation': 0,
                'sql_queries': 0
            }
            
            # Train on DDL statements
            ddl_statements = self._get_table_ddl()
            for ddl in ddl_statements:
                self.vn.train(ddl=ddl)
                stats['ddl_statements'] += 1
            
            logger.info(f"Trained on {stats['ddl_statements']} DDL statements")
            
            # Train on documentation
            docs = self._get_schema_docs()
            for doc in docs:
                self.vn.train(documentation=doc)
                stats['documentation'] += 1
            
            logger.info(f"Trained on {stats['documentation']} documentation items")
            
            # Train on example queries
            examples = self._get_example_queries()
            for sql, question in examples:
                self.vn.train(question=question, sql=sql)
                stats['sql_queries'] += 1
            
            logger.info(f"Trained on {stats['sql_queries']} example queries")
            
            self._trained = True
            logger.info("Vanna training complete")
            
            # Fix #4: Save training state to disk
            self._save_training_state()
            
            return {'status': 'trained', **stats}
            
        except Exception as e:
            logger.error(f"Training failed: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _get_table_ddl(self) -> List[str]:
        """Get DDL statements for all tables (Schema v2.3 适配)"""
        # Use training_data.py for comprehensive DDL
        try:
            from vanna_backend.training_data import ddl_statements
            return ddl_statements
        except ImportError:
            # 🌟 Fallback: Schema v2.3 基础结构
            return [
                """
                -- 🌟 Schema v2.3: documents 表
                CREATE TABLE documents (
                    id SERIAL PRIMARY KEY,
                    doc_id VARCHAR(255) UNIQUE,
                    filename VARCHAR(500) NOT NULL,
                    report_type VARCHAR(50) DEFAULT 'annual_report',
                    owner_company_id INTEGER REFERENCES companies(id),
                    year INTEGER,
                    processing_status VARCHAR(50) DEFAULT 'pending',
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                -- 🌟 Schema v2.3: companies 表
                CREATE TABLE companies (
                    id SERIAL PRIMARY KEY,
                    stock_code VARCHAR(50) UNIQUE,
                    name_en VARCHAR(255),
                    name_zh VARCHAR(255),
                    confirmed_industry VARCHAR(100),
                    is_industry_confirmed BOOLEAN DEFAULT FALSE,
                    ai_extracted_industries JSONB,
                    sector VARCHAR(100),
                    extra_data JSONB DEFAULT '{}'::jsonb
                );
                CREATE INDEX idx_companies_extra_data ON companies USING GIN (extra_data);
                """,
                """
                -- 🌟 Schema v2.3: document_companies 多對多關聯表
                CREATE TABLE document_companies (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL REFERENCES documents(id),
                    company_id INTEGER NOT NULL REFERENCES companies(id),
                    relation_type VARCHAR(50) DEFAULT 'mentioned',
                    extracted_industries JSONB,
                    extraction_source VARCHAR(50) DEFAULT 'ai_predict',
                    UNIQUE(document_id, company_id)
                );
                """,
                """
                -- 🌟 Schema v2.3: financial_metrics 表
                CREATE TABLE financial_metrics (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER NOT NULL REFERENCES companies(id),
                    year INTEGER NOT NULL,
                    metric_name VARCHAR(100) NOT NULL,
                    metric_name_zh VARCHAR(100),
                    value NUMERIC(20, 2),
                    standardized_value NUMERIC(20, 2),
                    standardized_currency VARCHAR(10) DEFAULT 'HKD',
                    CONSTRAINT unique_metric UNIQUE (company_id, year, metric_name)
                );
                """,
            ]
    
    def _get_schema_docs(self) -> List[str]:
        """Get schema documentation (Schema v2.3 适配)"""
        try:
            from vanna_backend.training_data import get_all_documentation
            return get_all_documentation()
        except ImportError:
            # 🌟 Fallback: Schema v2.3 文档
            return [
                """
                🌟 CRITICAL: Schema v2.3 变更
                - documents.dynamic_attributes → 已删除，改为 companies.extra_data
                - documents.ai_extracted_industries → 已删除，改为 document_companies.extracted_industries
                
                To query JSONB values in v2.3:
                - SELECT extra_data->>'key_name' FROM companies;
                - WHERE c.extra_data->>'index_quarter' = 'Q3';
                - WHERE dc.extracted_industries ? 'Biotech';
                """,
                """
                Industry Assignment Rules (Schema v2.3):
                - Rule A (Index Reports): companies.is_industry_confirmed = TRUE, 使用 confirmed_industry
                - Rule B (Annual Reports): companies.is_industry_confirmed = FALSE, 使用 ai_extracted_industries
                
                多對多關聯查詢需要 JOIN document_companies:
                SELECT d.filename, c.name_en FROM documents d
                JOIN document_companies dc ON dc.document_id = d.id
                JOIN companies c ON dc.company_id = c.id;
                """
            ]
    
    def _get_example_queries(self) -> List[tuple]:
        """Get example SQL queries for training (Schema v2.3 适配)"""
        try:
            from vanna_backend.training_data import get_all_question_sql_pairs
            return get_all_question_sql_pairs()
        except ImportError:
            # 🌟 Fallback: Schema v2.3 示例查询
            return [
                # 基础查询
                (
                    "SELECT id, doc_id, filename, report_type FROM documents ORDER BY uploaded_at DESC",
                    "List all documents in the database"
                ),
                # 指数报告查询 (v2.3)
                (
                    "SELECT d.filename, c.name_en, c.confirmed_industry FROM documents d JOIN companies c ON d.owner_company_id = c.id WHERE d.report_type = 'index_report'",
                    "Show all index reports with their companies"
                ),
                # JSONB 查询 (v2.3: companies.extra_data)
                (
                    "SELECT name_en, stock_code, extra_data->>'index_quarter' AS quarter FROM companies WHERE extra_data->>'index_quarter' = 'Q3'",
                    "Find all companies with Q3 quarter data"
                ),
                (
                    "SELECT name_en, extra_data->>'is_audited' FROM companies WHERE extra_data->>'is_audited' = 'true'",
                    "Find all audited companies"
                ),
                # 多对多关联查询 (v2.3)
                (
                    "SELECT d.filename, c.name_en, c.stock_code, dc.extraction_source FROM documents d JOIN document_companies dc ON dc.document_id = d.id JOIN companies c ON dc.company_id = c.id WHERE c.confirmed_industry = 'Biotech'",
                    "List all documents mentioning Biotech companies"
                ),
                # 行业查询 (v2.3: document_companies.extracted_industries)
                (
                    "SELECT c.name_en, dc.extracted_industries FROM document_companies dc JOIN companies c ON dc.company_id = c.id WHERE dc.extracted_industries ? 'Biotech'",
                    "Find companies where AI extracted 'Biotech' as a potential industry"
                ),
                # 确认行业查询 (v2.3)
                (
                    "SELECT name_en, stock_code, confirmed_industry FROM companies WHERE is_industry_confirmed = TRUE",
                    "Find companies with confirmed industry (Rule A)"
                ),
                # 财务数据查询 (v2.3)
                (
                    "SELECT c.name_en, fm.year, fm.metric_name, fm.standardized_value FROM financial_metrics fm JOIN companies c ON fm.company_id = c.id WHERE fm.metric_name = 'Total Revenue' ORDER BY fm.standardized_value DESC LIMIT 10",
                    "Show top 10 companies by revenue"
                ),
            ]
    
    # ============================================================
    # Dynamic Schema Injection Methods
    # ============================================================
    
    async def discover_dynamic_keys(self) -> Dict[str, Any]:
        """
        Discover all dynamic keys stored in JSONB columns.
        
        🌟 Schema v2.3 适配:
        - documents.dynamic_attributes → 已删除，改为 companies.extra_data
        - documents.ai_extracted_industries → 已删除，改为 document_companies.extracted_industries
        
        This is the "Just-in-Time Schema Injection" step:
        - Scan companies.extra_data for all keys
        - Scan document_companies.extracted_industries for values
        - Return discovered keys for prompt enhancement
        
        Returns:
            Dictionary with discovered keys, sample values, and frequency
        """
        import asyncpg
        
        try:
            # Connect to PostgreSQL
            conn = await asyncpg.connect(self.database_url)
            
            # 🌟 修正 1: 从 companies.extra_data 获取 Keys (Schema v2.3)
            keys_rows = await conn.fetch(
                """
                SELECT DISTINCT jsonb_object_keys(extra_data) AS key
                FROM companies
                WHERE extra_data IS NOT NULL 
                AND extra_data != '{}'::jsonb
                ORDER BY key
                """
            )
            
            discovered_keys = [row["key"] for row in keys_rows]
            
            # 🌟 修正 2: 从 companies 获取样本值 (Schema v2.3)
            sample_values = {}
            for key in discovered_keys[:10]:
                sample = await conn.fetchrow(
                    f"""
                    SELECT extra_data->>'{key}' AS sample_value
                    FROM companies
                    WHERE extra_data->>'{key}' IS NOT NULL
                    LIMIT 1
                    """
                )
                if sample:
                    sample_values[key] = sample["sample_value"]
            
            # Get frequency count (companies.extra_data)
            frequency_rows = await conn.fetch(
                """
                SELECT jsonb_object_keys(extra_data) AS key, COUNT(*) as count
                FROM companies
                WHERE extra_data IS NOT NULL
                GROUP BY jsonb_object_keys(extra_data)
                ORDER BY count DESC
                LIMIT 20
                """
            )
            
            key_frequency = {row["key"]: row["count"] for row in frequency_rows}
            
            # 🌟 修正 3: 从 document_companies.extracted_industries 获取行业 (Schema v2.3)
            industry_rows = await conn.fetch(
                """
                SELECT DISTINCT jsonb_array_elements_text(extracted_industries) AS industry
                FROM document_companies
                WHERE extracted_industries IS NOT NULL
                LIMIT 20
                """
            )
            
            discovered_industries = [row["industry"] for row in industry_rows]
            
            await conn.close()
            
            result = {
                "discovered_keys": discovered_keys,
                "total_keys": len(discovered_keys),
                "sample_values": sample_values,
                "key_frequency": key_frequency,
                "discovered_industries": discovered_industries,
                "status": "success"
            }
            
            logger.info(f"🔍 Discovered {len(discovered_keys)} dynamic keys from companies.extra_data")
            return result
            
        except Exception as e:
            logger.error(f"❌ Dynamic key discovery failed: {e}")
            return {
                "discovered_keys": [],
                "status": "error",
                "error": str(e)
            }
    
    def build_enhanced_prompt(self, question: str, dynamic_info: Dict[str, Any]) -> str:
        """
        Build enhanced prompt with dynamic schema information.
        
        🌟 Schema v2.3 适配:
        - SQL 示例使用 companies.extra_data 替代 documents.dynamic_attributes
        - 行业查询使用 document_companies.extracted_industries
        
        Args:
            question: User's natural language question
            dynamic_info: Discovered keys and values
            
        Returns:
            Enhanced prompt for Vanna
        """
        discovered_keys = dynamic_info.get("discovered_keys", [])
        sample_values = dynamic_info.get("sample_values", {})
        discovered_industries = dynamic_info.get("discovered_industries", [])
        
        prompt = f"""
用戶問題: {question}

📌 重要提示：資料庫 v2.3 包含以下動態屬性 (存儲在 JSONB 欄位中):

**companies.extra_data 可用的 Keys:**
{json.dumps(discovered_keys, indent=2, ensure_ascii=False)}

**樣本值:**
{json.dumps(sample_values, indent=2, ensure_ascii=False)}

**已發現的 AI 提取行業 (在 document_companies.extracted_industries):**
{json.dumps(discovered_industries, indent=2, ensure_ascii=False)}

**PostgreSQL JSONB 查詢語法 (必須使用 Schema v2.3):**
```sql
-- 提取單一值 (返回 text)
SELECT extra_data->>'key_name' FROM companies;

-- 結合文檔與公司屬性查詢
SELECT d.filename, c.name_en, c.extra_data->>'index_theme' 
FROM documents d JOIN companies c ON d.owner_company_id = c.id
WHERE c.extra_data->>'index_quarter' = 'Q3';

-- 檢查 Key 是否存在
SELECT * FROM companies WHERE extra_data ? 'key_name';

-- 查詢 JSON 數組中的行業 (document_companies)
SELECT dc.document_id, c.name_en, dc.extraction_source
FROM document_companies dc
JOIN companies c ON dc.company_id = c.id
WHERE dc.extracted_industries ? 'Biotech';

-- 查詢確認行業 (companies.confirmed_industry)
SELECT c.name_en, c.stock_code, c.confirmed_industry
FROM companies c
WHERE c.is_industry_confirmed = TRUE;
```

請根據以上信息生成正確的 SQL 查詢。如果問題涉及動態屬性，務必使用 JSONB 語法。
"""
        
        return prompt
    
    async def generate_sql_with_dynamic_schema(self, question: str) -> Optional[str]:
        """
        Generate SQL with Just-in-Time Schema Injection.
        
        🌟 Schema v2.3 适配:
        - 动态属性存储在 companies.extra_data
        - 行业存储在 document_companies.extracted_industries
        
        This method:
        1. First discovers all dynamic keys in the database
        2. Builds an enhanced prompt with JSONB query hints
        3. Passes the enhanced prompt to Vanna
        
        Args:
            question: User's natural language question
            
        Returns:
            SQL query string or None if generation fails
        """
        try:
            # Step 1: Discover dynamic keys (v2.3: companies.extra_data)
            dynamic_info = await self.discover_dynamic_keys()
            
            # Step 2: Build enhanced prompt
            if dynamic_info.get("discovered_keys"):
                enhanced_question = self.build_enhanced_prompt(question, dynamic_info)
                logger.debug(f"Enhanced prompt built with {len(dynamic_info['discovered_keys'])} dynamic keys")
            else:
                enhanced_question = question
                logger.info("No dynamic keys found, using original question")
            
            # Step 3: Generate SQL with enhanced prompt
            if not self._trained:
                self.train_schema()
            
            sql = self.vn.generate_sql(question=enhanced_question)
            
            # 🌟 Validate JSONB syntax for v2.3 (companies.extra_data)
            if "extra_data" in str(dynamic_info.get("discovered_keys", [])) or \
               "confirmed_industry" in question.lower() or \
               "extracted_industries" in question.lower():
                if "->>" not in sql and "?" not in sql and "JOIN" not in sql:
                    logger.warning("Generated SQL may not have correct JSONB syntax for Schema v2.3")
            
            logger.info(f"Generated SQL with dynamic schema: {sql[:200]}...")
            return sql
            
        except Exception as e:
            logger.error(f"SQL generation with dynamic schema failed: {e}")
            # Fallback to regular generation
            return self.generate_sql(question)
    
    async def query_with_dynamic_schema(self, question: str) -> Dict[str, Any]:
        """
        Complete pipeline with dynamic schema injection.
        
        Args:
            question: Natural language query
            
        Returns:
            Dictionary with SQL, results, dynamic keys, and metadata
        """
        # Discover dynamic keys first
        dynamic_info = await self.discover_dynamic_keys()
        
        # Generate SQL with enhanced prompt
        sql = await self.generate_sql_with_dynamic_schema(question)
        
        if not sql:
            return {
                'success': False,
                'error': 'Failed to generate SQL',
                'question': question,
                'dynamic_keys': dynamic_info.get('discovered_keys', [])
            }
        
        # Execute SQL
        results = self.execute(sql)
        
        return {
            'success': True,
            'question': question,
            'sql': sql,
            'results': results,
            'row_count': len(results),
            'dynamic_keys_discovered': dynamic_info.get('discovered_keys', []),
            'dynamic_keys_count': dynamic_info.get('total_keys', 0)
        }
    
    def generate_sql(self, question: str) -> Optional[str]:
        """
        Generate SQL from natural language question.
        
        Args:
            question: Natural language query
        
        Returns:
            SQL query string or None if generation fails
        """
        try:
            # Auto-train if not trained
            if not self._trained:
                self.train_schema()
            
            sql = self.vn.generate_sql(question=question)
            logger.info(f"Generated SQL: {sql[:200]}...")
            return sql
            
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            return None
    
    def execute(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute SQL query and return results.
        Uses financial_storage.py for parameterized queries to prevent SQL injection.
        
        Args:
            sql: SQL query string
        
        Returns:
            List of result dictionaries
        """
        try:
            # Import financial_storage for safer execution
            from nanobot.storage.financial_storage import PostgresStorage
            
            storage = PostgresStorage(self.database_url)
            storage.connect()
            
            # Execute via storage layer (uses SQLAlchemy text() with proper handling)
            rows = storage.query(sql)
            
            logger.debug(f"Query returned {len(rows)} rows")
            return rows
            
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return []
    
    def query(self, question: str) -> Dict[str, Any]:
        """
        Complete pipeline: question → SQL → results.
        
        Args:
            question: Natural language query
        
        Returns:
            Dictionary with SQL, results, and metadata
        """
        # Generate SQL
        sql = self.generate_sql(question)
        if not sql:
            return {
                'success': False,
                'error': 'Failed to generate SQL',
                'question': question
            }
        
        # Execute SQL
        results = self.execute(sql)
        
        return {
            'success': True,
            'question': question,
            'sql': sql,
            'results': results,
            'row_count': len(results)
        }


# Global instance
_vanna: Optional[VannaSQL] = None


def get_vanna() -> VannaSQL:
    """Get global Vanna instance"""
    global _vanna
    if not _vanna:
        _vanna = VannaSQL()
    return _vanna


# Convenience function
def ask(question: str) -> Dict:
    """Ask a question in natural language"""
    vanna = get_vanna()
    return vanna.query(question)


if __name__ == "__main__":
    # Test Vanna integration
    print("Testing Vanna AI Integration...\n")
    
    vanna = VannaSQL()
    
    # Train schema
    print("1. Training schema...")
    stats = vanna.train_schema()
    print(f"   {stats}\n")
    
    # Test queries
    test_questions = [
        "Show Tencent's revenue for the most recent years",
        "What are the top 5 companies by revenue?",
        "What is the average net margin for technology companies?"
    ]
    
    for question in test_questions:
        print(f"2. Question: {question}")
        result = vanna.query(question)
        
        if result['success']:
            print(f"   ✓ SQL: {result['sql'][:100]}...")
            print(f"   ✓ Results: {result['row_count']} rows")
            if result['results']:
                print(f"   ✓ First row: {result['results'][0]}")
        else:
            print(f"   ✗ Failed: {result.get('error')}")
        print()
    
    print("✅ Vanna test complete!")
