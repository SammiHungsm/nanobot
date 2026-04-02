"""
Repository Module - PostgreSQL 數據庫操作層

集中所有 SQL 操作，遵循單一職責原則。
"""

import os
from typing import Optional, Dict, Any, List
from pathlib import Path
from loguru import logger
import asyncpg


class DBClient:
    """
    數據庫客戶端
    
    負責所有 PostgreSQL 操作，包括：
    - 公司 CRUD
    - Revenue Breakdown CRUD
    - Document 狀態管理
    """
    
    def __init__(self, db_url: str = None):
        """
        初始化
        
        Args:
            db_url: PostgreSQL 連接字符串
        """
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
        )
        self.conn: Optional[asyncpg.Connection] = None
    
    async def connect(self):
        """連接數據庫"""
        self.conn = await asyncpg.connect(self.db_url)
        logger.info("✅ 數據庫連接成功")
    
    async def close(self):
        """關閉連接"""
        if self.conn:
            await self.conn.close()
            logger.info("📴 數據庫連接已關閉")
    
    # ===========================================
    # Company Operations
    # ===========================================
    
    async def get_or_create_company(
        self,
        stock_code: str = None,
        name_en: str = None,
        name_zh: str = None,
        industry: str = None,
        sector: str = None
    ) -> Optional[int]:
        """
        獲取或創建公司記錄
        
        Args:
            stock_code: 股票代碼
            name_en: 英文名稱
            name_zh: 中文名稱
            industry: 行業
            sector: 板塊
            
        Returns:
            int: 公司 ID
        """
        if not stock_code and not name_en:
            logger.warning("⚠️ 缺少股票代碼和公司名稱，無法創建公司記錄")
            return None
        
        try:
            # 1. 先嘗試查找現有公司
            if stock_code:
                existing_id = await self.conn.fetchval(
                    "SELECT id FROM companies WHERE stock_code = $1",
                    stock_code
                )
                if existing_id:
                    logger.info(f"✅ 找到現有公司: ID={existing_id}, Stock Code={stock_code}")
                    return existing_id
            
            if name_en:
                existing_id = await self.conn.fetchval(
                    "SELECT id FROM companies WHERE name_en ILIKE $1",
                    f"%{name_en}%"
                )
                if existing_id:
                    logger.info(f"✅ 找到現有公司: ID={existing_id}, Name={name_en}")
                    return existing_id
            
            # 2. 創建新公司
            new_id = await self.conn.fetchval(
                """
                INSERT INTO companies (name_en, name_zh, stock_code, industry, sector)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                name_en or f"Company_{stock_code or 'Unknown'}",
                name_zh,
                stock_code,
                industry,
                sector
            )
            logger.info(f"✅ 創建新公司: ID={new_id}, Stock Code={stock_code}")
            return new_id
            
        except Exception as e:
            logger.error(f"❌ 查找/創建公司失敗: {e}")
            return None
    
    async def get_company_by_id(self, company_id: int) -> Optional[Dict[str, Any]]:
        """根據 ID 獲取公司信息"""
        row = await self.conn.fetchrow(
            "SELECT * FROM companies WHERE id = $1",
            company_id
        )
        return dict(row) if row else None
    
    # ===========================================
    # Revenue Breakdown Operations
    # ===========================================
    
    async def insert_revenue_breakdown(
        self,
        company_id: int,
        year: int,
        extracted_data: Dict[str, Any],
        source_file: str,
        source_page: int,
        category_type: str = "Region",
        currency: str = "HKD"
    ) -> int:
        """
        插入 Revenue Breakdown 數據
        
        Args:
            company_id: 公司 ID
            year: 年份
            extracted_data: 提取的數據 Dict
            source_file: 源文件名
            source_page: 源頁碼
            category_type: 分類類型
            currency: 貨幣
            
        Returns:
            int: 插入的記錄數量
        """
        try:
            inserted_count = 0
            
            for category, data in extracted_data.items():
                percentage = data.get("percentage")
                amount = data.get("amount")
                
                # 使用 UPSERT (ON CONFLICT DO UPDATE)
                await self.conn.execute(
                    """
                    INSERT INTO revenue_breakdown 
                    (company_id, year, category, category_type, percentage, amount, currency, source_file, source_page)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (company_id, year, category, category_type) 
                    DO UPDATE SET 
                        percentage = $5, 
                        amount = $6,
                        source_file = $8,
                        source_page = $9
                    """,
                    company_id,
                    year,
                    category,
                    category_type,
                    percentage,
                    amount,
                    currency,
                    source_file,
                    source_page
                )
                inserted_count += 1
            
            logger.info(f"✅ 已寫入 {inserted_count} 條 Revenue Breakdown 記錄")
            return inserted_count
            
        except Exception as e:
            logger.error(f"❌ Revenue Breakdown 入庫失敗: {e}")
            return 0
    
    async def get_revenue_breakdown(
        self,
        company_id: int,
        year: int
    ) -> List[Dict[str, Any]]:
        """獲取 Revenue Breakdown 數據"""
        rows = await self.conn.fetch(
            """
            SELECT * FROM revenue_breakdown 
            WHERE company_id = $1 AND year = $2
            ORDER BY percentage DESC
            """,
            company_id,
            year
        )
        return [dict(row) for row in rows]
    
    # ===========================================
    # Document Operations
    # ===========================================
    
    async def create_document(
        self,
        doc_id: str,
        company_id: Optional[int],
        title: str,
        file_path: str,
        file_hash: str,
        file_size: int,
        document_type: str = "annual_report"
    ):
        """創建文檔記錄"""
        await self.conn.execute(
            """
            INSERT INTO documents (
                doc_id, company_id, title, document_type, 
                file_path, file_hash, file_size_bytes,
                processing_status, uploaded_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (doc_id) DO UPDATE SET
                processing_status = 'pending',
                updated_at = NOW()
            """,
            doc_id,
            company_id,
            title,
            document_type,
            file_path,
            file_hash,
            file_size,
            "pending"
        )
    
    async def update_document_status(
        self,
        doc_id: str,
        status: str,
        stats: Dict = None,
        error: str = None
    ):
        """更新文檔處理狀態"""
        if status == "completed" and stats:
            await self.conn.execute(
                """
                UPDATE documents SET
                    processing_status = 'completed',
                    processing_completed_at = NOW(),
                    total_chunks = $1,
                    total_artifacts = $2,
                    updated_at = NOW()
                WHERE doc_id = $3
                """,
                stats.get("total_chunks", 0),
                stats.get("total_tables", 0) + stats.get("total_images", 0),
                doc_id
            )
        elif status == "failed":
            await self.conn.execute(
                """
                UPDATE documents SET
                    processing_status = 'failed',
                    processing_error = $1,
                    updated_at = NOW()
                WHERE doc_id = $2
                """,
                error,
                doc_id
            )
    
    async def check_document_exists(self, doc_id: str, file_hash: str) -> bool:
        """檢查文檔是否已存在"""
        exists = await self.conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM documents 
                WHERE doc_id = $1 OR file_hash = $2
            )
            """,
            doc_id, file_hash
        )
        return exists
    
    async def delete_document(self, doc_id: str):
        """刪除文檔及其所有相關數據"""
        logger.info(f"🗑️ 正在刪除文檔 {doc_id} 的所有數據...")
        
        # 刪除相關數據
        await self.conn.execute("DELETE FROM document_chunks WHERE doc_id = $1", doc_id)
        await self.conn.execute("DELETE FROM raw_artifacts WHERE doc_id = $1", doc_id)
        await self.conn.execute("DELETE FROM documents WHERE doc_id = $1", doc_id)
        
        logger.info(f"✅ 文檔 {doc_id} 已刪除")
    
    # ===========================================
    # Utility Methods
    # ===========================================
    
    async def execute_query(self, sql: str, *args) -> Any:
        """執行原始 SQL 查詢"""
        return await self.conn.execute(sql, *args)
    
    async def fetch_one(self, sql: str, *args) -> Optional[Dict]:
        """獲取單行"""
        row = await self.conn.fetchrow(sql, *args)
        return dict(row) if row else None
    
    async def fetch_all(self, sql: str, *args) -> List[Dict]:
        """獲取多行"""
        rows = await self.conn.fetch(sql, *args)
        return [dict(row) for row in rows]