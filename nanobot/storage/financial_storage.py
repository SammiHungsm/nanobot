"""
Financial Storage Layer - PostgreSQL Only

Migrated from AnnualReportPoC/src/storage/
Adapted for Nanobot integration.

All data (structured metrics, unstructured text, documents) stored in PostgreSQL using JSONB.
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


# Convenience functions
def create_storage(connection_string: Optional[str] = None) -> PostgresStorage:
    """Create PostgreSQL storage instance"""
    storage = PostgresStorage(connection_string)
    storage.connect()
    return storage


if __name__ == "__main__":
    # Test PostgreSQL connection
    print("Testing PostgreSQL connection...")
    pg = create_storage()
    results = pg.query("SELECT COUNT(*) FROM companies")
    print(f"Companies in database: {results[0]['count']}")
