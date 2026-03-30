"""
Financial Storage Layer - PostgreSQL + MongoDB

Migrated from AnnualReportPoC/src/storage/
Adapted for Nanobot integration.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from loguru import logger
import json
import hashlib


@dataclass
class FinancialMetric:
    """Structured financial metric for storage"""
    company_name: str
    company_name_zh: Optional[str]
    year: int
    fiscal_period: str  # 'FY', 'H1', 'Q1', etc.
    metric_name: str  # Canonical English name
    metric_name_zh: str  # Canonical Chinese name
    value: float
    unit: str  # 'CNY', 'USD', 'percentage'
    category: str  # 'revenue', 'profit', 'asset', etc.
    source_file: str
    source_page: int
    source_table_id: Optional[str]
    extraction_confidence: float


class PostgresStorage:
    """
    PostgreSQL storage for structured financial data.
    
    Example:
        storage = PostgresStorage()
        storage.connect()
        storage.add_metric(metric_data)
        results = storage.query("SELECT * FROM ...")
    """
    
    def __init__(self, connection_string: Optional[str] = None):
        """
        Args:
            connection_string: PostgreSQL connection string
                              Default: postgresql://postgres:postgres@localhost:5433/annual_reports
        """
        self.connection_string = connection_string or "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
        self.engine = None
        self.Session = None
        logger.info(f"PostgresStorage initialized with connection: {self._sanitize_connection_string()}")
    
    def _sanitize_connection_string(self) -> str:
        """Return sanitized connection string for logging"""
        import re
        return re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', self.connection_string)
    
    def connect(self):
        """Create database connection"""
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.orm import sessionmaker
            
            self.engine = create_engine(self.connection_string, echo=False)
            self.Session = sessionmaker(bind=self.engine)
            
            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def query(self, sql: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Execute raw SQL query.
        
        Args:
            sql: SQL query string
            params: Query parameters
        
        Returns:
            List of result dictionaries
        """
        if not self.Session:
            self.connect()
        
        session = self.Session()
        try:
            from sqlalchemy import text
            result = session.execute(text(sql), params or {})
            columns = result.keys()
            rows = [dict(zip(columns, row)) for row in result]
            logger.debug(f"Query returned {len(rows)} rows")
            return rows
        
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise
        finally:
            session.close()
    
    def add_company(self, name_en: str, name_zh: str, stock_code: Optional[str] = None,
                    industry: Optional[str] = None, sector: Optional[str] = None) -> int:
        """
        Add or get company.
        
        Returns:
            Company ID
        """
        if not self.Session:
            self.connect()
        
        session = self.Session()
        try:
            from sqlalchemy import text
            
            # Check if exists
            result = session.execute(text("""
                SELECT id FROM companies 
                WHERE name_en = :name_en OR name_zh = :name_zh OR stock_code = :stock_code
            """), {'name_en': name_en, 'name_zh': name_zh, 'stock_code': stock_code}).fetchone()
            
            if result:
                logger.debug(f"Company already exists: {name_en}")
                return result[0]
            
            # Add new company
            result = session.execute(text("""
                INSERT INTO companies (name_en, name_zh, stock_code, industry, sector)
                VALUES (:name_en, :name_zh, :stock_code, :industry, :sector)
                RETURNING id
            """), {
                'name_en': name_en,
                'name_zh': name_zh,
                'stock_code': stock_code,
                'industry': industry,
                'sector': sector
            }).fetchone()
            
            session.commit()
            logger.info(f"Added new company: {name_en}")
            return result[0]
        
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add company: {e}")
            raise
        finally:
            session.close()
    
    def add_metric(self, metric: FinancialMetric) -> int:
        """
        Add a financial metric record.
        
        Returns:
            Record ID
        """
        if not self.Session:
            self.connect()
        
        session = self.Session()
        try:
            from sqlalchemy import text
            
            # Get or create company
            company_id = self.add_company(
                name_en=metric.company_name,
                name_zh=metric.company_name_zh
            )
            
            # Check for duplicate
            result = session.execute(text("""
                SELECT id FROM metric_records
                WHERE company_id = :company_id
                  AND year = :year
                  AND fiscal_period = :fiscal_period
                  AND metric_name = :metric_name
            """), {
                'company_id': company_id,
                'year': metric.year,
                'fiscal_period': metric.fiscal_period,
                'metric_name': metric.metric_name
            }).fetchone()
            
            if result:
                logger.debug(f"Metric already exists, skipping: {metric.metric_name} for {metric.company_name} {metric.year}")
                return result[0]
            
            # Add new record
            result = session.execute(text("""
                INSERT INTO metric_records (
                    company_id, year, fiscal_period, metric_name, metric_name_zh,
                    value, unit, category, source_file, source_page,
                    source_table_id, extraction_confidence
                ) VALUES (
                    :company_id, :year, :fiscal_period, :metric_name, :metric_name_zh,
                    :value, :unit, :category, :source_file, :source_page,
                    :source_table_id, :extraction_confidence
                ) RETURNING id
            """), {
                'company_id': company_id,
                'year': metric.year,
                'fiscal_period': metric.fiscal_period,
                'metric_name': metric.metric_name,
                'metric_name_zh': metric.metric_name_zh,
                'value': metric.value,
                'unit': metric.unit,
                'category': metric.category,
                'source_file': metric.source_file,
                'source_page': metric.source_page,
                'source_table_id': metric.source_table_id,
                'extraction_confidence': metric.extraction_confidence
            }).fetchone()
            
            session.commit()
            logger.debug(f"Added metric: {metric.metric_name} = {metric.value} for {metric.company_name}")
            return result[0]
        
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add metric: {e}")
            raise
        finally:
            session.close()
    
    def get_metric_trend(self, company_name: str, metric_name: str, years: Optional[List[int]] = None) -> List[Dict]:
        """
        Get metric trend over years for a company.
        
        Example:
            trend = storage.get_metric_trend("Tencent", "Revenue", years=[2020, 2021, 2022, 2023])
        """
        sql = """
            SELECT m.year, m.value, m.unit, c.name_en
            FROM metric_records m
            JOIN companies c ON m.company_id = c.id
            WHERE c.name_en = :company_name
              AND m.metric_name = :metric_name
              AND m.fiscal_period = 'FY'
        """
        
        params = {'company_name': company_name, 'metric_name': metric_name}
        
        if years:
            sql += " AND m.year IN :years"
            params['years'] = tuple(years)
        
        sql += " ORDER BY m.year"
        
        return self.query(sql, params)
    
    def get_top_companies(self, metric_name: str, year: int, limit: int = 10) -> List[Dict]:
        """
        Get top N companies by metric for a year.
        
        Example:
            top10 = storage.get_top_companies("Revenue", 2023, limit=10)
        """
        sql = """
            SELECT c.name_en, c.name_zh, m.value, m.unit
            FROM metric_records m
            JOIN companies c ON m.company_id = c.id
            WHERE m.metric_name = :metric_name
              AND m.year = :year
              AND m.fiscal_period = 'FY'
            ORDER BY m.value DESC
            LIMIT :limit
        """
        
        return self.query(sql, {
            'metric_name': metric_name,
            'year': year,
            'limit': limit
        })
    
    def get_highest_growth(self, metric_name: str, min_year: int, max_year: int, limit: int = 10) -> List[Dict]:
        """
        Get companies with highest growth rate for a metric over a period.
        """
        sql = """
            WITH company_growth AS (
                SELECT 
                    c.name_en,
                    c.name_zh,
                    MAX(CASE WHEN m.year = :max_year THEN m.value END) as latest_value,
                    MAX(CASE WHEN m.year = :min_year THEN m.value END) as earliest_value
                FROM metric_records m
                JOIN companies c ON m.company_id = c.id
                WHERE m.metric_name = :metric_name
                  AND m.year IN (:min_year, :max_year)
                  AND m.fiscal_period = 'FY'
                GROUP BY c.id, c.name_en, c.name_zh
                HAVING COUNT(DISTINCT m.year) = 2
            )
            SELECT 
                name_en,
                name_zh,
                latest_value,
                earliest_value,
                ((latest_value - earliest_value) / earliest_value * 100) as growth_rate
            FROM company_growth
            WHERE earliest_value > 0
            ORDER BY growth_rate DESC
            LIMIT :limit
        """
        
        return self.query(sql, {
            'metric_name': metric_name,
            'min_year': min_year,
            'max_year': max_year,
            'limit': limit
        })


class MongoDocumentStore:
    """
    MongoDB storage for unstructured text and documents.
    
    Example:
        store = MongoDocumentStore()
        store.connect()
        store.add_document(doc_data)
        results = store.search_text("keywords")
    """
    
    def __init__(self, connection_string: Optional[str] = None, database: str = "annual_reports"):
        """
        Args:
            connection_string: MongoDB connection string
                              Default: mongodb://mongo:mongo_password_change_me@localhost:27018
            database: Database name (default: annual_reports)
        """
        self.connection_string = connection_string or "mongodb://mongo:mongo_password_change_me@localhost:27018"
        self.database_name = database
        self.client = None
        self.db = None
        logger.info(f"MongoDocumentStore initialized with connection: {self._sanitize_connection_string()}")
    
    def _sanitize_connection_string(self) -> str:
        """Return sanitized connection string for logging"""
        import re
        return re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', self.connection_string)
    
    def connect(self):
        """Create database connection"""
        try:
            from pymongo import MongoClient
            
            self.client = MongoClient(self.connection_string)
            self.db = self.client[self.database_name]
            
            # Test connection
            self.client.admin.command('ping')
            logger.info("MongoDB connection established")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    def add_document(self, title: str, content: str, company_name: str,
                    year: Optional[int] = None, document_type: str = "annual_report",
                    source_file: str = "", source_page: Optional[int] = None,
                    metadata: Optional[Dict] = None) -> str:
        """
        Add a document to the store.
        
        Returns:
            Document ID
        """
        if not self.db:
            self.connect()
        
        doc = {
            'title': title,
            'content': content,
            'company_name': company_name,
            'year': year,
            'document_type': document_type,
            'source_file': source_file,
            'source_page': source_page,
            'metadata': metadata or {},
            'created_at': datetime.utcnow()
        }
        
        result = self.db.documents.insert_one(doc)
        logger.debug(f"Added document: {title}")
        return str(result.inserted_id)
    
    def semantic_search(self, query: str, company_name: Optional[str] = None,
                       year: Optional[int] = None, limit: int = 10) -> List[Dict]:
        """
        語義檢索（Semantic Search）使用 MongoDB $vectorSearch 或 $text search
        
        如果安裝咗 RagAnything 或者 MongoDB Atlas，可以用向量檢索。
        否則使用 MongoDB $text search 作為後備方案。
        
        Args:
            query: 檢索查詢
            company_name: 公司名稱過濾
            year: 年份過濾
            limit: 返回結果數量限制
        
        Returns:
            List of matching documents with relevance scores
        
        Example:
            results = store.semantic_search("營收增長", company_name="Tencent", year=2023)
        """
        if not self.db:
            self.connect()
        
        try:
            # 方法 1: 使用 MongoDB $vectorSearch (如果有向量索引)
            # 需要先安裝 mongodb-atlas 或者 raganything
            try:
                from pymongo import errors
                
                # 檢查是否有 vector_search 方法 (MongoDB Atlas)
                if hasattr(self.db.documents, 'vector_search'):
                    # 使用向量檢索
                    pipeline = [
                        {
                            '$vectorSearch': {
                                'index': 'vector_index',
                                'path': 'content_embedding',
                                'queryVector': self._get_embedding(query),
                                'numCandidates': 100,
                                'limit': limit
                            }
                        },
                        {
                            '$addFields': {
                                'score': { '$meta': 'vectorSearchScore' }
                            }
                        }
                    ]
                    
                    # 添加過濾條件
                    match_stage = {'$match': {}}
                    if company_name:
                        match_stage['$match']['company_name'] = company_name
                    if year:
                        match_stage['$match']['year'] = year
                    
                    if match_stage['$match']:
                        pipeline.insert(1, match_stage)
                    
                    results = list(self.db.documents.aggregate(pipeline))
                    
                    # 轉換 ObjectId 為字符串
                    for doc in results:
                        doc['_id'] = str(doc['_id'])
                    
                    logger.info(f"語義檢索 (向量) 返回 {len(results)} 個結果")
                    return results
                    
            except (ImportError, errors.OperationFailure) as e:
                # 向量檢索不可用，使用 $text search 作為後備
                logger.debug(f"向量檢索不可用：{e}，使用 $text search")
                pass
            
            # 方法 2: 使用 MongoDB $text search (後備方案)
            search_query = {}
            
            # 文本檢索
            if query:
                search_query['$text'] = {'$search': query}
            
            # 過濾條件
            if company_name:
                search_query['company_name'] = company_name
            if year:
                search_query['year'] = year
            
            # 執行檢索並添加相關性評分
            results = list(
                self.db.documents.find(
                    search_query,
                    {'score': {'$meta': 'textScore'}}
                )
                .sort([('score', {'$meta': 'textScore'})])
                .limit(limit)
            )
            
            # 轉換 ObjectId 為字符串
            for doc in results:
                doc['_id'] = str(doc['_id'])
            
            logger.info(f"語義檢索 (text search) 返回 {len(results)} 個結果")
            return results
            
        except Exception as e:
            logger.error(f"語義檢索失敗：{e}")
            return []
    
    def _get_embedding(self, text: str) -> List[float]:
        """
        獲取文本的向量嵌入 (需要 RagAnything 或其他嵌入模型)
        
        這是一個佔位符方法，實際使用時需要連接 RagAnything API
        或者其他嵌入模型服務。
        
        Args:
            text: 要轉換為向量的文本
        
        Returns:
            向量嵌入列表
        """
        # TODO: 整合 RagAnything 或者其他嵌入模型 API
        # 例如：
        # from raganything import RagAnything
        # rag = RagAnything(api_key="...")
        # return rag.embed(text)
        
        logger.warning("嵌入模型未配置，返回空向量")
        return [0.0] * 768  # 返回 768 維空向量作為佔位符
    
    def search_text(self, query: str, company_name: Optional[str] = None,
                   year: Optional[int] = None, limit: int = 10) -> List[Dict]:
        """
        Search documents by text.
        
        Returns:
            List of matching documents
        """
        if not self.db:
            self.connect()
        
        search_query = {}
        
        # Text search
        if query:
            search_query['$text'] = {'$search': query}
        
        # Filters
        if company_name:
            search_query['company_name'] = company_name
        if year:
            search_query['year'] = year
        
        # Execute search
        results = list(self.db.documents.find(search_query).limit(limit))
        
        # Convert ObjectId to string
        for doc in results:
            doc['_id'] = str(doc['_id'])
        
        logger.debug(f"Text search returned {len(results)} results")
        return results
    
    def get_company_documents(self, company_name: str, year: Optional[int] = None) -> List[Dict]:
        """
        Get all documents for a company.
        """
        if not self.db:
            self.connect()
        
        query = {'company_name': company_name}
        if year:
            query['year'] = year
        
        results = list(self.db.documents.find(query))
        
        for doc in results:
            doc['_id'] = str(doc['_id'])
        
        return results


# Convenience functions
def create_storage(connection_string: Optional[str] = None) -> PostgresStorage:
    """Create PostgreSQL storage instance"""
    storage = PostgresStorage(connection_string)
    storage.connect()
    return storage


def create_document_store(connection_string: Optional[str] = None) -> MongoDocumentStore:
    """Create MongoDB document store instance"""
    store = MongoDocumentStore(connection_string)
    store.connect()
    return store


if __name__ == "__main__":
    # Test connections
    print("Testing PostgreSQL connection...")
    pg = create_storage()
    results = pg.query("SELECT COUNT(*) FROM companies")
    print(f"Companies in database: {results[0]['count']}")
    
    print("\nTesting MongoDB connection...")
    mongo = create_document_store()
    print(f"MongoDB connected: {mongo.db is not None}")
