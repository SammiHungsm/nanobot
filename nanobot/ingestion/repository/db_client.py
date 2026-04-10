"""
Repository Module - PostgreSQL 數據庫操作層

集中所有 SQL 操作，遵循單一職責原則。
"""

import os
from typing import Optional, Dict, Any, List
from pathlib import Path
from loguru import logger
import asyncpg
from contextlib import asynccontextmanager


class DBClient:
    """
    數據庫客戶端
    
    負責所有 PostgreSQL 操作，包括：
    - 公司 CRUD
    - Revenue Breakdown CRUD
    - Document 狀態管理
    
    Fix #2: 使用連接池代替單連接
    Fix #3: 添加事務管理
    """
    
    def __init__(self, db_url: str = None, 
                 pool_size: int = 10,
                 max_inactive_connection_lifetime: float = 300.0):
        """
        初始化
        
        Args:
            db_url: PostgreSQL 連接字符串
            pool_size: 連接池大小（Fix #2）
            max_inactive_connection_lifetime: 連接最大空閒時間（秒）
        """
        # Fix #1: 統一使用環境變數，端口改為 5432（與 ingestion 一致）
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://${POSTGRES_USER:postgres}:${POSTGRES_PASSWORD:postgres_password_change_me}@${POSTGRES_HOST:localhost}:${POSTGRES_PORT:5432}/${POSTGRES_DB:annual_reports}"
        )
        # 解析環境變數
        self.db_url = self._resolve_env_vars(self.db_url)
        
        self.pool: Optional[asyncpg.Pool] = None
        self._conn: Optional[asyncpg.Connection] = None  # 🔧 單連接（向後兼容）
        self.pool_size = pool_size
        self.max_inactive_connection_lifetime = max_inactive_connection_lifetime
        
        logger.info(f"DBClient initialized (pool_size={pool_size})")
    
    def _resolve_env_vars(self, url: str) -> str:
        """解析 ${VAR} 或 ${VAR:default} 模式"""
        import re
        
        def replace_var(match):
            var_expr = match.group(1)
            if ':' in var_expr:
                var_name, default = var_expr.split(':', 1)
                return os.getenv(var_name, default)
            else:
                return os.getenv(var_expr, match.group(0))
        
        return re.sub(r'\$\{([^}]+)\}', replace_var, url)
    
    async def connect(self):
        """
        連接數據庫（創建連接池 + 單連接向後兼容）
        
        Fix #2: 使用連接池代替單連接
        """
        try:
            # 創建連接池
            self.pool = await asyncpg.create_pool(
                self.db_url,
                min_size=2,
                max_size=self.pool_size,
                max_inactive_connection_lifetime=self.max_inactive_connection_lifetime,
                command_timeout=60
            )
            # 🔧 同時創建單連接（向後兼容 self.conn）
            self._conn = await asyncpg.connect(self.db_url)
            
            logger.info(f"✅ 數據庫連接池創建成功 (size={self.pool_size})")
        except Exception as e:
            logger.error(f"❌ 創建數據庫連接池失敗：{e}")
            raise
    
    @property
    def conn(self):
        """向後兼容屬性：返回單連接"""
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn
    
    async def close(self):
        """關閉連接池和單連接"""
        if self._conn:
            await self._conn.close()
            logger.info("📴 單連接已關閉")
        if self.pool:
            await self.pool.close()
            logger.info("📴 數據庫連接池已關閉")
    
    @asynccontextmanager
    async def transaction(self):
        """
        事務上下文管理器（Fix #3）
        
        Usage:
            async with db.transaction():
                await db.insert_company(...)
                await db.insert_metrics(...)
        """
        if not self.pool:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn
    
    @asynccontextmanager
    async def connection(self):
        """
        連接上下文管理器（從連接池獲取連接）
        
        Usage:
            async with db.connection() as conn:
                result = await conn.fetchrow(...)
        """
        if not self.pool:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        async with self.pool.acquire() as conn:
            yield conn
    
    # ===========================================
    # Company Operations (漸進式資料充實架構)
    # ===========================================
    
    async def get_company_by_stock_code(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        根據股票代碼獲取公司信息
        
        Args:
            stock_code: 股票代碼（如 '00001', '00700'）
            
        Returns:
            Dict: 公司信息，或 None
        """
        if not stock_code:
            return None
        
        # 標準化股票代碼（補零至 5 位）
        normalized_code = stock_code.zfill(5)
        
        # Fix #2: 使用連接池
        async with self.connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM companies WHERE stock_code = $1",
                normalized_code
            )
            return dict(row) if row else None
    
    async def upsert_company(
        self,
        stock_code: str,
        name_en: str = None,
        name_zh: str = None,
        name_source: str = "extracted",
        industry: str = None,
        sector: str = None,
        auditor: str = None,
        auditor_opinion: str = None,
        ultimate_controlling_shareholder: str = None,
        principal_banker: str = None
    ) -> Optional[int]:
        """
        🎯 漸進式 Upsert 公司信息（Update as need）
        
        核心邏輯：
        1. 如果公司已存在，只更新「空值」欄位（不覆蓋已有數據）
        2. 如果公司不存在，創建新記錄
        3. 名字來源分為 index（恆指報表）和 extracted（PDF 擷取）
        
        Args:
            stock_code: 股票代碼（必須）
            name_en: 英文名稱
            name_zh: 中文名稱
            name_source: 名字來源 ('index' 或 'extracted')
            industry: 行業
            sector: 板塊
            auditor: 核數師
            auditor_opinion: 核數師意見
            ultimate_controlling_shareholder: 最終控股股東
            principal_banker: 主要銀行
            
        Returns:
            int: 公司 ID
        """
        if not stock_code:
            logger.warning("⚠️ 缺少股票代碼，無法 upsert 公司")
            return None
        
        # 標準化股票代碼
        normalized_code = stock_code.zfill(5)
        
        try:
            # 1. 查找現有公司
            existing = await self.get_company_by_stock_code(normalized_code)
            
            if existing:
                # 2. 公司已存在，執行「按需更新」
                company_id = existing['id']
                update_fields = {}
                
                # 根據名字來源決定更新哪個欄位
                if name_source == "index":
                    # 恆指報表的名字是權威的，可以覆蓋
                    if name_en:
                        update_fields['name_en_index'] = name_en
                    if name_zh:
                        update_fields['name_zh_extracted'] = name_zh  # 恆指也可能有中文名
                else:
                    # PDF 擷取的名字只填空值
                    if name_en and not existing.get('name_en_extracted'):
                        update_fields['name_en_extracted'] = name_en
                    if name_zh and not existing.get('name_zh_extracted'):
                        update_fields['name_zh_extracted'] = name_zh
                
                # 其他欄位只更新空值
                if industry and not existing.get('industry'):
                    update_fields['industry'] = industry
                if sector and not existing.get('sector'):
                    update_fields['sector'] = sector
                if auditor and not existing.get('auditor'):
                    update_fields['auditor'] = auditor
                if auditor_opinion and not existing.get('auditor_opinion'):
                    update_fields['auditor_opinion'] = auditor_opinion
                if ultimate_controlling_shareholder and not existing.get('ultimate_controlling_shareholder'):
                    update_fields['ultimate_controlling_shareholder'] = ultimate_controlling_shareholder
                if principal_banker and not existing.get('principal_banker'):
                    update_fields['principal_banker'] = principal_banker
                
                if update_fields:
                    await self.update_company(company_id, update_fields)
                    logger.info(f"✅ 公司 {normalized_code} 已更新欄位: {list(update_fields.keys())}")
                else:
                    logger.debug(f"ℹ️ 公司 {normalized_code} 無需更新")
                
                return company_id
            
            else:
                # 3. 創建新公司
                insert_data = {
                    'stock_code': normalized_code,
                    'sector': sector or 'Unknown',
                    'industry': industry
                }
                
                # 根據名字來源設置欄位
                if name_source == "index":
                    if name_en:
                        insert_data['name_en_index'] = name_en
                    if name_zh:
                        insert_data['name_zh_extracted'] = name_zh
                else:
                    if name_en:
                        insert_data['name_en_extracted'] = name_en
                    if name_zh:
                        insert_data['name_zh_extracted'] = name_zh
                
                # 其他欄位
                if auditor:
                    insert_data['auditor'] = auditor
                if auditor_opinion:
                    insert_data['auditor_opinion'] = auditor_opinion
                if ultimate_controlling_shareholder:
                    insert_data['ultimate_controlling_shareholder'] = ultimate_controlling_shareholder
                if principal_banker:
                    insert_data['principal_banker'] = principal_banker
                
                company_id = await self.insert_company(insert_data)
                logger.info(f"✅ 創建新公司: Stock Code={normalized_code}, ID={company_id}")
                return company_id
                
        except Exception as e:
            logger.error(f"❌ Upsert 公司失敗: {e}")
            return None
    
    async def insert_company(self, data: Dict[str, Any]) -> int:
        """
        插入新公司記錄
        
        Args:
            data: 公司數據字典
            
        Returns:
            int: 新公司 ID
        """
        columns = list(data.keys())
        values = [data[col] for col in columns]
        placeholders = [f"${i+1}" for i in range(len(columns))]
        
        sql = f"""
            INSERT INTO companies ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING id
        """
        
        # Fix #2: 使用連接池
        async with self.connection() as conn:
            company_id = await conn.fetchval(sql, *values)
            return company_id
    
    async def update_company(self, company_id: int, data: Dict[str, Any]) -> bool:
        """
        更新公司特定欄位
        
        Args:
            company_id: 公司 ID
            data: 要更新的欄位
            
        Returns:
            bool: 是否成功
        """
        if not data:
            return True
        
        set_clauses = [f"{key} = ${i+2}" for i, key in enumerate(data.keys())]
        values = [company_id] + list(data.values())
        
        sql = f"""
            UPDATE companies 
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = $1
        """
        
        # Fix #2: 使用連接池
        async with self.connection() as conn:
            await conn.execute(sql, *values)
            return True
    
    # ===========================================
    # 內部輔助方法（用於事務內操作）
    # ===========================================
    
    async def _insert_company_conn(self, conn, data: Dict[str, Any]) -> int:
        """內部方法：使用提供的連接插入公司（用於事務內）"""
        columns = list(data.keys())
        values = [data[col] for col in columns]
        placeholders = [f"${i+1}" for i in range(len(columns))]
        
        sql = f"""
            INSERT INTO companies ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING id
        """
        
        return await conn.fetchval(sql, *values)
    
    async def _update_company_conn(self, conn, company_id: int, data: Dict[str, Any]) -> bool:
        """內部方法：使用提供的連接更新公司（用於事務內）"""
        if not data:
            return True
        
        set_clauses = [f"{key} = ${i+2}" for i, key in enumerate(data.keys())]
        values = [company_id] + list(data.values())
        
        sql = f"""
            UPDATE companies 
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = $1
        """
        
        await conn.execute(sql, *values)
        return True
    
    async def get_or_create_company(
        self,
        stock_code: str = None,
        name_en: str = None,
        name_zh: str = None,
        industry: str = None,
        sector: str = None
    ) -> Optional[int]:
        """
        獲取或創建公司記錄（向後兼容方法）
        
        🔧 已重構為調用 upsert_company，支援漸進式資料充實
        
        Args:
            stock_code: 股票代碼
            name_en: 英文名稱
            name_zh: 中文名稱
            industry: 行業
            sector: 板塊
            
        Returns:
            int: 公司 ID
        """
        return await self.upsert_company(
            stock_code=stock_code,
            name_en=name_en,
            name_zh=name_zh,
            name_source="extracted",  # 預設為 PDF 擷取來源
            industry=industry,
            sector=sector
        )
    
    async def get_company_by_id(self, company_id: int) -> Optional[Dict[str, Any]]:
        """根據 ID 獲取公司信息"""
        row = await self.conn.fetchrow(
            "SELECT * FROM companies WHERE id = $1",
            company_id
        )
        return dict(row) if row else None
    
    # ===========================================
    # Financial Metrics Operations (扁平化核心表)
    # ===========================================
    
    async def insert_financial_metric(
        self,
        company_id: int,
        year: int,
        metric_name_raw: str,
        value: float,
        unit: str,
        fiscal_period: str = "FY",
        category: str = None,
        source_file: str = None,
        source_page: int = None
    ) -> bool:
        """
        插入財務指標到扁平表（使用實體對齊 + 數值標準化）
        
        🔧 這是 PoC 核心方法，解決兩個致命傷：
        1. Entity Resolution: 統一指標名稱 (resolve_metric_name)
        2. Value Normalization: 統一數值單位和幣別 (normalize_financial_value)
        
        Args:
            company_id: 公司 ID
            year: 年份
            metric_name_raw: 原始指標名稱（會被標準化）
            value: 數值
            unit: 單位
            fiscal_period: 財政期間
            category: 分類
            source_file: 源文件
            source_page: 源頁碼
            
        Returns:
            bool: 是否成功
        """
        from ..extractors.entity_resolver import resolve_metric_name
        from ..extractors.value_normalizer import normalize_financial_value
        
        try:
            # 🚀 Step 1: 實體對齊 - 統一指標名稱
            canonical_en, canonical_zh = resolve_metric_name(metric_name_raw)
            
            # 🚀 Step 2: 數值標準化 - 統一為港幣絕對單位
            standardized_value, standardized_currency = normalize_financial_value(
                raw_value=value,
                unit_str=unit,
                target_currency='HKD'  # 預設統一為港幣
            )
            
            # 將 Decimal 轉換為 float（PostgreSQL 兼容）
            standardized_value_float = float(standardized_value)
            
            await self.conn.execute(
                """
                INSERT INTO financial_metrics 
                (company_id, year, fiscal_period, metric_name, metric_name_zh, 
                 original_metric_name, value, unit, 
                 standardized_value, standardized_currency,
                 category, source_file, source_page)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (company_id, year, fiscal_period, metric_name) 
                DO UPDATE SET 
                    original_metric_name = $6,
                    value = $7,
                    unit = $8,
                    standardized_value = $9,
                    standardized_currency = $10,
                    source_file = $12,
                    source_page = $13
                """,
                company_id,
                year,
                fiscal_period,
                canonical_en,              # 標準化英文名稱
                canonical_zh,              # 標準化中文名稱
                metric_name_raw,           # 🔧 原始名稱（供溯源）
                value,                     # 原始數值
                unit,                      # 原始單位
                standardized_value_float,  # 🔧 標準化數值（港幣絕對單位）
                standardized_currency,     # 🔧 標準化幣別（HKD）
                category,
                source_file,
                source_page
            )
            
            logger.debug(
                f"✅ 寫入指標: {canonical_en} = {value} {unit} → "
                f"{standardized_value_float} {standardized_currency}"
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ 寫入財務指標失敗: {e}")
            return False
    
    async def insert_financial_metrics_batch(
        self,
        company_id: int,
        year: int,
        metrics: List[Dict[str, Any]],
        source_file: str = None,
        source_page: int = None
    ) -> int:
        """
        批量插入財務指標
        
        Args:
            company_id: 公司 ID
            year: 年份
            metrics: 指標列表 [{"name": "...", "value": ..., "unit": "..."}]
            source_file: 源文件
            source_page: 源頁碼
            
        Returns:
            int: 成功插入的數量
        """
        inserted = 0
        for metric in metrics:
            success = await self.insert_financial_metric(
                company_id=company_id,
                year=year,
                metric_name_raw=metric.get("name", metric.get("metric_name", "")),
                value=metric.get("value", 0),
                unit=metric.get("unit", "HKD"),
                fiscal_period=metric.get("fiscal_period", "FY"),
                category=metric.get("category"),
                source_file=source_file,
                source_page=source_page
            )
            if success:
                inserted += 1
        
        logger.info(f"✅ 批量寫入 {inserted}/{len(metrics)} 個財務指標")
        return inserted
    
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
        插入 Revenue Breakdown 數據（使用實體對齊）
        
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
        # 導入實體對齊器
        from ..extractors.entity_resolver import resolve_region_name
        
        try:
            inserted_count = 0
            
            for category, data in extracted_data.items():
                percentage = data.get("percentage")
                amount = data.get("amount")
                
                # 🚀 實體對齊：統一地區名稱
                canonical_en, canonical_zh = resolve_region_name(category)
                
                # 使用標準英文名稱作為 category
                standardized_category = canonical_en
                
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
                    standardized_category,  # 使用標準化名稱
                    category_type,
                    percentage,
                    amount,
                    currency,
                    source_file,
                    source_page
                )
                inserted_count += 1
            
            logger.info(f"✅ 已寫入 {inserted_count} 條 Revenue Breakdown 記錄（已標準化地區名稱）")
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
    # Document Pages Operations (兜底表 - Zone 2)
    # ===========================================
    
    async def insert_document_page(
        self,
        company_id: int,
        doc_id: str,
        year: int,
        page_num: int,
        markdown_content: str,
        source_file: str,
        content_type: str = "markdown",
        has_images: bool = False,
        has_charts: bool = False
    ) -> bool:
        """
        插入單個 PDF 頁面的原始 Markdown 到兜底表
        
        這是「雙軌制」的 Zone 2，確保所有原始數據都被保存，
        供 Vanna 在找不到精準數據時進行全文搜索。
        
        Args:
            company_id: 公司 ID
            doc_id: 文檔 ID
            year: 年份
            page_num: 頁碼
            markdown_content: 原始 Markdown 內容
            source_file: 源文件名
            content_type: 內容類型
            has_images: 是否包含圖片
            has_charts: 是否包含圖表
            
        Returns:
            bool: 是否成功
        """
        try:
            await self.conn.execute(
                """
                INSERT INTO document_pages 
                (company_id, doc_id, year, page_num, markdown_content, 
                 content_type, has_images, has_charts, source_file)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (company_id, year, page_num, source_file) 
                DO UPDATE SET 
                    markdown_content = $5,
                    content_type = $6,
                    has_images = $7,
                    has_charts = $8
                """,
                company_id,
                doc_id,
                year,
                page_num,
                markdown_content,
                content_type,
                has_images,
                has_charts,
                source_file
            )
            
            logger.debug(f"✅ Page {page_num} 已寫入 document_pages 兜底表")
            return True
            
        except Exception as e:
            logger.error(f"❌ document_pages 入庫失敗 (Page {page_num}): {e}")
            return False
    
    async def insert_document_pages_batch(
        self,
        pages: List[Dict[str, Any]]
    ) -> int:
        """
        批量插入多個 PDF 頁面
        
        Args:
            pages: 頁面列表，每個元素包含 company_id, doc_id, year, page_num, markdown_content 等
            
        Returns:
            int: 成功插入的頁面數
        """
        inserted_count = 0
        
        for page in pages:
            success = await self.insert_document_page(
                company_id=page.get("company_id"),
                doc_id=page.get("doc_id"),
                year=page.get("year"),
                page_num=page.get("page_num"),
                markdown_content=page.get("markdown_content"),
                source_file=page.get("source_file"),
                content_type=page.get("content_type", "markdown"),
                has_images=page.get("has_images", False),
                has_charts=page.get("has_charts", False)
            )
            if success:
                inserted_count += 1
        
        logger.info(f"✅ 已寫入 {inserted_count} 個頁面到 document_pages 兜底表")
        return inserted_count
    
    async def search_document_pages(
        self,
        keywords: List[str],
        company_id: int = None,
        year: int = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        全文搜索兜底表
        
        使用 ILIKE 進行模糊搜索，供 Vanna 在找不到精準數據時調用。
        
        Args:
            keywords: 關鍵字列表
            company_id: 公司 ID (可選)
            year: 年份 (可選)
            limit: 返回結果數量限制
            
        Returns:
            List[Dict]: 匹配的頁面列表
        """
        try:
            # 構建 ILIKE 條件
            ilike_conditions = " OR ".join([
                f"markdown_content ILIKE '%{keyword}%'" 
                for keyword in keywords
            ])
            
            sql = f"""
                SELECT page_num, markdown_content, source_file
                FROM document_pages
                WHERE ({ilike_conditions})
            """
            
            params = []
            param_idx = 1
            
            if company_id:
                sql += f" AND company_id = ${param_idx}"
                params.append(company_id)
                param_idx += 1
            
            if year:
                sql += f" AND year = ${param_idx}"
                params.append(year)
                param_idx += 1
            
            sql += f" ORDER BY page_num LIMIT ${param_idx}"
            params.append(limit)
            
            rows = await self.conn.fetch(sql, *params)
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"❌ 全文搜索失敗: {e}")
            return []
    
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
        # 從 file_path 提取 filename
        filename = Path(file_path).name
        
        await self.conn.execute(
            """
            INSERT INTO documents (
                doc_id, company_id, filename, title, document_type, 
                file_path, file_hash, file_size_bytes,
                processing_status, status, uploaded_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            ON CONFLICT (doc_id) DO UPDATE SET
                processing_status = 'pending',
                status = 'pending',
                updated_at = NOW()
            """,
            doc_id,
            company_id,
            filename,
            title,
            document_type,
            file_path,
            file_hash,
            file_size,
            "pending",
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
                    status = 'completed',
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
                    status = 'failed',
                    processing_error = $1,
                    updated_at = NOW()
                WHERE doc_id = $2
                """,
                error,
                doc_id
            )
        else:
            await self.conn.execute(
                """
                UPDATE documents SET
                    processing_status = $1,
                    status = $1,
                    updated_at = NOW()
                WHERE doc_id = $2
                """,
                status,
                doc_id
            )
    
    async def update_document_company_id(self, doc_id: str, company_id: int, year: int = None):
        """更新文檔的公司 ID 和年份"""
        if year:
            await self.conn.execute(
                """
                UPDATE documents SET
                    company_id = $1,
                    year = $2,
                    updated_at = NOW()
                WHERE doc_id = $3
                """,
                company_id,
                year,
                doc_id
            )
            logger.info(f"✅ 已更新文檔 {doc_id} 的 company_id={company_id}, year={year}")
        else:
            await self.conn.execute(
                """
                UPDATE documents SET
                    company_id = $1,
                    updated_at = NOW()
                WHERE doc_id = $2
                """,
                company_id,
                doc_id
            )
            logger.info(f"✅ 已更新文檔 {doc_id} 的 company_id={company_id}")
    
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
        
        # 刪除相關數據 (document_chunks 已移除 - No RAG Option)
        await self.conn.execute("DELETE FROM raw_artifacts WHERE doc_id = $1", doc_id)
        await self.conn.execute("DELETE FROM documents WHERE doc_id = $1", doc_id)
        
        logger.info(f"✅ 文檔 {doc_id} 已刪除")
    
    # ===========================================
    # JSONB Dynamic Attributes (companies.extra_data)
    # ===========================================
    
    async def update_company_extra_data(
        self,
        company_id: int,
        attribute_key: str,
        attribute_value: Any
    ) -> bool:
        """
        🎯 動態寫入公司屬性到 JSONB 字段
        
        用於存儲不隨年度變化的靜態屬性（如 CEO、核數師等），
        避免 ALTER TABLE 風險，實現「資料驅動」架構。
        
        Args:
            company_id: 公司 ID
            attribute_key: 屬性名稱（必須使用標準化名稱）
            attribute_value: 屬性值（可以是 string, number, dict, list）
            
        Returns:
            bool: 是否成功
            
        Example:
            await db.update_company_extra_data(1, "chief_executive", "張三")
            await db.update_company_extra_data(1, "auditor", {"firm": "德勤", "opinion": "無保留"})
        """
        try:
            import json
            
            # 將值轉換為 JSONB 格式
            json_val = json.dumps(attribute_value, ensure_ascii=False)
            
            # 使用 jsonb_set 進行深度更新（支持嵌套結構）
            await self.conn.execute(
                """
                UPDATE companies 
                SET extra_data = jsonb_set(
                    COALESCE(extra_data, '{}'::jsonb), 
                    array[$2::text], 
                    $3::jsonb, 
                    true
                ),
                updated_at = NOW()
                WHERE id = $1;
                """,
                company_id,
                attribute_key,
                json_val
            )
            
            logger.info(f"✅ 已更新公司 {company_id} 的 extra_data.{attribute_key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ JSONB 更新失敗: {e}")
            return False
    
    async def get_company_extra_data(
        self,
        company_id: int,
        attribute_key: str = None
    ) -> Any:
        """
        從 JSONB 字段讀取公司屬性
        
        Args:
            company_id: 公司 ID
            attribute_key: 屬性名稱（如果為 None，返回整個 extra_data）
            
        Returns:
            Any: 屬性值或整個 extra_data Dict
        """
        try:
            if attribute_key:
                # 讀取單個屬性
                value = await self.conn.fetchval(
                    """
                    SELECT extra_data->>$2 
                    FROM companies 
                    WHERE id = $1;
                    """,
                    company_id,
                    attribute_key
                )
                return value
            else:
                # 讀取整個 extra_data
                row = await self.conn.fetchrow(
                    """
                    SELECT extra_data 
                    FROM companies 
                    WHERE id = $1;
                    """,
                    company_id
                )
                if row and row['extra_data']:
                    import json
                    return json.loads(row['extra_data'])
                return {}
                
        except Exception as e:
            logger.error(f"❌ JSONB 讀取失敗: {e}")
            return None
    
    async def batch_update_company_extra_data(
        self,
        company_id: int,
        attributes: Dict[str, Any]
    ) -> int:
        """
        批量更新公司 JSONB 屬性
        
        Args:
            company_id: 公司 ID
            attributes: 屬性字典 {"key": value, ...}
            
        Returns:
            int: 成功更新的屬性數量
        """
        updated = 0
        for key, value in attributes.items():
            success = await self.update_company_extra_data(company_id, key, value)
            if success:
                updated += 1
        
        logger.info(f"✅ 批量更新 {updated}/{len(attributes)} 個 JSONB 屬性")
        return updated
    
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
    
    # ===========================================
    # Raw Artifacts Operations
    # ===========================================
    
    async def insert_raw_artifact(
        self,
        artifact_id: str,
        doc_id: str,
        company_id: Optional[int],
        file_type: str,
        file_path: str,
        page_num: int = None,
        metadata: str = None,
        file_size: int = 0
    ) -> bool:
        """
        插入 Raw Artifact 記錄
        
        Args:
            artifact_id: Artifact ID
            doc_id: 文檔 ID
            company_id: 公司 ID
            file_type: 文件類型 (table_json, image, etc.)
            file_path: 文件路徑
            page_num: 頁碼
            metadata: 元數據 JSON 字串
            file_size: 文件大小
            
        Returns:
            bool: 是否成功
        """
        try:
            await self.conn.execute(
                """
                INSERT INTO raw_artifacts (
                    artifact_id, doc_id, company_id, file_type,
                    file_path, file_size_bytes, metadata, page_num, source_file
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (artifact_id) DO UPDATE SET
                    file_path = $5,
                    metadata = $7,
                    page_num = $8
                """,
                artifact_id,
                doc_id,
                company_id,
                file_type,
                file_path,
                file_size,
                metadata,
                page_num,
                doc_id
            )
            logger.debug(f"✅ Artifact {artifact_id} 已保存")
            return True
            
        except Exception as e:
            logger.error(f"❌ Artifact 入庫失敗: {e}")
            return False