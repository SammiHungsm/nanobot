"""
Vanna AI Text-to-SQL Integration

Provides RAG-powered text-to-SQL generation with schema training.
Replaces manual SQL generation with AI-powered accurate queries.

Usage:
    from nanobot.agent.tools.vanna_tool import VannaSQL
    
    vanna = VannaSQL()
    vanna.train_schema()
    
    sql = vanna.generate_sql("Show Tencent's revenue for 2020-2023")
    result = vanna.execute(sql)
"""

from typing import Optional, List, Dict, Any
from loguru import logger
import os


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
                 api_key: Optional[str] = None):
        """
        Initialize Vanna AI.
        
        Args:
            database_url: PostgreSQL connection URL
            model_name: Vanna model name
            api_key: Vanna API key (optional, uses default if not provided)
        """
        self.database_url = database_url or "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
        self.model_name = model_name
        self.api_key = api_key
        
        self._vn = None
        self._trained = False
        
        logger.info(f"VannaSQL initialized (model={model_name})")
    
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
            
            return {'status': 'trained', **stats}
            
        except Exception as e:
            logger.error(f"Training failed: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _get_table_ddl(self) -> List[str]:
        """Get DDL statements for all tables"""
        return [
            """
            CREATE TABLE companies (
                id SERIAL PRIMARY KEY,
                name_en VARCHAR(255) NOT NULL,
                name_zh VARCHAR(255),
                stock_code VARCHAR(20) UNIQUE,
                industry VARCHAR(100),
                sector VARCHAR(100)
            )
            """,
            """
            CREATE TABLE metric_records (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                year INTEGER NOT NULL,
                fiscal_period VARCHAR(10) NOT NULL,
                metric_name VARCHAR(100) NOT NULL,
                metric_name_zh VARCHAR(100) NOT NULL,
                value DOUBLE PRECISION NOT NULL,
                unit VARCHAR(20) NOT NULL,
                category VARCHAR(50),
                source_file VARCHAR(500),
                source_page INTEGER,
                source_table_id VARCHAR(100)
            )
            """,
            """
            CREATE TABLE documents (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                title VARCHAR(500) NOT NULL,
                document_type VARCHAR(50),
                year INTEGER,
                parsed_text TEXT,
                metadata_json JSONB
            )
            """
        ]
    
    def _get_schema_docs(self) -> List[str]:
        """Get schema documentation"""
        return [
            "The 'companies' table stores master data for companies covered in annual reports",
            "The 'metric_records' table stores financial metrics extracted from annual reports with exact values",
            "The 'documents' table stores parsed text and metadata from annual report PDFs",
            "fiscal_period can be 'FY' (full year), 'H1' (half year), 'Q1' (quarterly), etc.",
            "unit can be 'CNY' (Chinese Yuan), 'USD', 'percentage', etc.",
            "category includes 'revenue', 'profit', 'asset', 'liability', 'equity', etc."
        ]
    
    def _get_example_queries(self) -> List[tuple]:
        """Get example SQL queries for training"""
        return [
            (
                "SELECT year, value FROM metric_records WHERE company_id = (SELECT id FROM companies WHERE name_en = 'Tencent Holdings') AND metric_name = 'Revenue' ORDER BY year DESC",
                "Show Tencent's revenue for the most recent years"
            ),
            (
                "SELECT c.name_en, m.value, m.unit FROM metric_records m JOIN companies c ON m.company_id = c.id WHERE m.metric_name = 'Revenue' AND m.year = 2023 ORDER BY m.value DESC LIMIT 10",
                "What are the top 10 companies by revenue in 2023?"
            ),
            (
                "SELECT AVG(m.value) FROM metric_records m JOIN companies c ON m.company_id = c.id WHERE m.metric_name = 'Net Margin' AND m.year = 2023 AND c.industry = 'Technology'",
                "What is the average net margin for technology companies in 2023?"
            ),
            (
                "SELECT c.name_en, m.value FROM metric_records m JOIN companies c ON m.company_id = c.id WHERE m.metric_name = 'Revenue' AND m.year IN (2022, 2023) AND c.name_en LIKE '%Tencent%' ORDER BY m.year",
                "Show Tencent's revenue growth from 2022 to 2023"
            )
        ]
    
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
