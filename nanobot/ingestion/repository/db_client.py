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
        industry: str = None,  # 向後兼容，但會映射到 sector
        sector: str = None,
        auditor: str = None,
        auditor_opinion: str = None,
        ultimate_controlling_shareholder: str = None,
        principal_banker: str = None,
        # 🌟 新增：指數報告專用參數（Schema v2.3）
        confirmed_industry: str = None,
        is_industry_confirmed: bool = False
    ) -> Optional[int]:
        """
        🎯 漸進式 Upsert 公司信息（Schema v2.3 完全對齊）
        
        核心邏輯：
        1. 如果公司已存在，只更新「空值」欄位（不覆蓋已有數據）
        2. 如果公司不存在，創建新記錄
        3. 名字來源分為 index（恆指報表）和 extracted（PDF 擷取）
        
        🌟 Schema v2.3 變更：
        - name_en_index, name_en_extracted → 統一為 name_en
        - name_zh_extracted → 統一為 name_zh
        - industry → 已刪除，映射到 sector 或 confirmed_industry
        
        Args:
            stock_code: 股票代碼（必須）
            name_en: 英文名稱
            name_zh: 中文名稱
            name_source: 名字來源 ('index' 或 'extracted')
            industry: 行業（向後兼容，映射到 sector）
            sector: 板塊
            auditor: 核數師
            auditor_opinion: 核數師意見
            ultimate_controlling_shareholder: 最終控股股東
            principal_banker: 主要銀行
            confirmed_industry: 確認行業（規則 A）
            is_industry_confirmed: 是否已確認行業
            
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
                
                # 🌟 修正：Schema v2.3 只有 name_en 和 name_zh
                if name_en and not existing.get('name_en'):
                    update_fields['name_en'] = name_en
                if name_zh and not existing.get('name_zh'):
                    update_fields['name_zh'] = name_zh
                
                # 🌟 修正：industry 欄位已刪除，映射到 sector 或 confirmed_industry
                actual_sector = sector or industry
                if actual_sector and not existing.get('sector'):
                    update_fields['sector'] = actual_sector
                
                # 🌟 新增：確認行業（規則 A）
                if confirmed_industry and not existing.get('confirmed_industry'):
                    update_fields['confirmed_industry'] = confirmed_industry
                    update_fields['is_industry_confirmed'] = is_industry_confirmed
                
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
                    'sector': sector or industry or 'Unknown',
                    'name_en': name_en,
                    'name_zh': name_zh
                }
                
                # 🌟 新增：確認行業（規則 A）
                if confirmed_industry:
                    insert_data['confirmed_industry'] = confirmed_industry
                    insert_data['is_industry_confirmed'] = is_industry_confirmed
                
                if auditor:
                    insert_data['auditor'] = auditor
                if auditor_opinion:
                    insert_data['auditor_opinion'] = auditor_opinion
                if ultimate_controlling_shareholder:
                    insert_data['ultimate_controlling_shareholder'] = ultimate_controlling_shareholder
                if principal_banker:
                    insert_data['principal_banker'] = principal_banker
                
                # 過濾掉 None 的值
                insert_data = {k: v for k, v in insert_data.items() if v is not None}
                
                company_id = await self.insert_company(insert_data)
                logger.info(f"✅ 創建新公司: Stock Code={normalized_code}, ID={company_id}")
                return company_id
                
        except Exception as e:
            logger.error(f"❌ Upsert 公司失敗: {e}")
            return None
    
    async def add_mentioned_company(
        self,
        document_id: int,
        company_id: int,
        relation_type: str = "mentioned",
        extracted_industries: list = None,
        extraction_source: str = "ai_predict"
    ) -> bool:
        """
        🎯 記錄 PDF 中提及的公司 (寫入橋樑表)
        
        Args:
            document_id: documents 表的 ID (不是 doc_id 字串，是 Integer ID)
            company_id: companies 表的 ID
            relation_type: 關係類型 (如 'subsidiary', 'competitor', 'index_constituent', 'mentioned')
            extracted_industries: 提取到的行業列表 (例如 ["Gaming", "Cloud"])
            extraction_source: 來源 ('ai_predict' 或 'index_rule')
            
        Returns:
            bool: 是否成功
        """
        import json
        
        industries_json = json.dumps(extracted_industries) if extracted_industries else None
        
        try:
            await self.conn.execute(
                """
                INSERT INTO document_companies (
                    document_id, company_id, relation_type, 
                    extracted_industries, extraction_source
                ) VALUES ($1, $2, $3, $4::jsonb, $5)
                ON CONFLICT (document_id, company_id) DO UPDATE SET
                    relation_type = $3,
                    extracted_industries = $4::jsonb,
                    extraction_source = $5
                """,
                document_id,
                company_id,
                relation_type,
                industries_json,
                extraction_source
            )
            logger.info(f"✅ 已記錄提及公司: doc_id={document_id}, company_id={company_id}, relation={relation_type}")
            return True
        except Exception as e:
            logger.error(f"❌ 寫入 document_companies 失敗: {e}")
            return False
    
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
        segment_type: str = "business",  # 🌟 Schema v2.3: category_type -> segment_type
        currency: str = "HKD",
        source_document_id: int = None  # 🌟 Schema v2.3: 替代 source_file/source_page
    ) -> int:
        """
        插入 Revenue Breakdown 數據（Schema v2.3 完全對齊）
        
        🌟 Schema v2.3 變更：
        - category -> segment_name
        - category_type -> segment_type
        - percentage -> revenue_percentage
        - amount -> revenue_amount
        - source_file/source_page -> source_document_id
        
        Args:
            company_id: 公司 ID
            year: 年份
            extracted_data: 提取的數據 Dict
            source_file: 源文件名（保留向後兼容）
            source_page: 源頁碼（保留向後兼容）
            segment_type: 分類類型 (business/geography/product)
            currency: 貨幣
            source_document_id: documents 表的 Integer ID
            
        Returns:
            int: 插入的記錄數量
        """
        # 導入實體對齊器
        from ..extractors.entity_resolver import resolve_region_name
        
        try:
            inserted_count = 0
            
            # 🌟 如果没有 source_document_id，尝试从 source_file 推断
            if source_document_id is None and source_file:
                logger.warning("⚠️ source_document_id 未传入，Revenue Breakdown 将无法追溯")
            
            # 🌟 遍历 extracted_data 中的所有条目
            for segment_name, data in extracted_data.items():
                percentage = data.get("percentage")
                amount = data.get("amount")
                
                # 🚀 实体对齐：统一地区名称（如果是 geography 类型）
                if segment_type == "geography":
                    canonical_en, canonical_zh = resolve_region_name(segment_name)
                    standardized_segment_name = canonical_en
                else:
                    standardized_segment_name = segment_name
                
                # 🌟 Schema v2.3: 使用新的列名
                await self.conn.execute(
                    """
                    INSERT INTO revenue_breakdown 
                    (company_id, year, segment_name, segment_type, revenue_percentage, revenue_amount, currency, source_document_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (company_id, year, segment_name, segment_type) 
                    DO UPDATE SET 
                        revenue_percentage = $5, 
                        revenue_amount = $6,
                        source_document_id = $8
                    """,
                    company_id,
                    year,
                    standardized_segment_name,  # 🌟 segment_name
                    segment_type,               # 🌟 segment_type
                    percentage,                 # 🌟 revenue_percentage
                    amount,                     # 🌟 revenue_amount
                    currency,
                    source_document_id          # 🌟 source_document_id (Integer)
                )
                inserted_count += 1
            
            logger.info(f"✅ 已寫入 {inserted_count} 條 Revenue Breakdown 記錄（Schema v2.3）")
            return inserted_count
            
        except Exception as e:
            logger.error(f"❌ Revenue Breakdown 入庫失敗: {e}")
            return 0
    
    async def get_revenue_breakdown(
        self,
        company_id: int,
        year: int
    ) -> List[Dict[str, Any]]:
        """獲取 Revenue Breakdown 數據（Schema v2.3）"""
        rows = await self.conn.fetch(
            """
            SELECT * FROM revenue_breakdown 
            WHERE company_id = $1 AND year = $2
            ORDER BY revenue_percentage DESC
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
        company_id: int,  # 保留參數但不寫入 db（Schema v2.3 已刪除）
        doc_id: str,
        year: int,  # 保留參數但不寫入 db（Schema v2.3 已刪除）
        page_num: int,
        markdown_content: str,
        source_file: str,  # 保留參數但不寫入 db（Schema v2.3 已刪除）
        content_type: str = "markdown",  # 保留參數但不寫入 db（Schema v2.3 已刪除）
        has_images: bool = False,
        has_charts: bool = False
    ) -> bool:
        """
        插入單個 PDF 頁面的原始 Markdown 到兜底表
        
        🌟 Schema v2.3 變更：
        - 已刪除欄位：company_id, doc_id (字串), year, source_file, content_type
        - 現在只依賴 document_id (Integer) 關聯
        
        這是「雙軌制」的 Zone 2，確保所有原始數據都被保存，
        供 Vanna 在找不到精準數據時進行全文搜索。
        
        Args:
            company_id: 公司 ID（參數保留但不寫入）
            doc_id: 文檔 ID（用於查詢 document_id）
            year: 年份（參數保留但不寫入）
            page_num: 頁碼
            markdown_content: 原始 Markdown 內容
            source_file: 源文件名（參數保留但不寫入）
            content_type: 內容類型（參數保留但不寫入）
            has_images: 是否包含圖片
            has_charts: 是否包含圖表
            
        Returns:
            bool: 是否成功
        """
        try:
            # 🌟 修正：用 doc_id (字串) 查出 document_id (Integer)
            # 🌟 修正：移除已刪除的欄位 (company_id, year, source_file, content_type)
            await self.conn.execute(
                """
                INSERT INTO document_pages 
                (document_id, page_num, markdown_content, has_images, has_tables)
                VALUES (
                    (SELECT id FROM documents WHERE doc_id = $1), 
                    $2, $3, $4, $5
                )
                ON CONFLICT (document_id, page_num) 
                DO UPDATE SET 
                    markdown_content = $3,
                    has_images = $4,
                    has_tables = $5
                """,
                doc_id,
                page_num,
                markdown_content,
                has_images,
                has_charts  # 映射到 has_tables
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
                f"dp.markdown_content ILIKE '%{keyword}%'" 
                for keyword in keywords
            ])
            
            # 🌟 修正：JOIN documents 表來過濾 company_id 和 year，並獲取 filename 代替 source_file
            sql = f"""
                SELECT dp.page_num, dp.markdown_content, d.filename as source_file
                FROM document_pages dp
                JOIN documents d ON dp.document_id = d.id
                WHERE ({ilike_conditions})
            """
            
            params = []
            param_idx = 1
            
            if company_id:
                sql += f" AND d.owner_company_id = ${param_idx}"
                params.append(company_id)
                param_idx += 1
            
            if year:
                sql += f" AND d.year = ${param_idx}"
                params.append(year)
                param_idx += 1
            
            sql += f" ORDER BY dp.page_num LIMIT ${param_idx}"
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
        company_id: Optional[int],  # 這裡傳入的其實是母公司 ID
        title: str = None,  # 保留參數以防其他地方報錯，但不寫入 DB（向後兼容）
        filename: str = None,  # 🌟 新增：優先使用此參數
        file_path: str = None,
        file_hash: str = None,
        file_size: int = 0,
        document_type: str = "annual_report"  # 保持參數名不變以防其他地方報錯
    ):
        """創建文檔記錄 (適配新 Schema v2.3)"""
        # 🌟 優先使用 filename 參數，如果沒有則從 file_path 提取
        actual_filename = filename or (Path(file_path).name if file_path else "unknown.pdf")
        
        await self.conn.execute(
            """
            INSERT INTO documents (
                doc_id, owner_company_id, filename, file_path, file_hash, 
                file_size_bytes, report_type, processing_status, uploaded_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (doc_id) DO UPDATE SET
                processing_status = 'pending',
                updated_at = NOW()
            """,
            doc_id,
            company_id,  # 寫入 owner_company_id
            actual_filename,
            file_path,
            file_hash,
            file_size,  # 寫入 file_size_bytes
            document_type,  # 寫入 report_type
            "pending"
        )
    
    async def update_document_status(
        self,
        doc_id: str,
        status: str,
        stats: Dict = None,
        error: str = None
    ):
        """更新文檔處理狀態 (Schema v2.3: 只更新 processing_status)"""
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
        else:
            await self.conn.execute(
                """
                UPDATE documents SET
                    processing_status = $1,
                    updated_at = NOW()
                WHERE doc_id = $2
                """,
                status,
                doc_id
            )
    
    async def update_document_company_id(self, doc_id: str, company_id: int, year: int = None):
        """更新文檔的母公司 ID 和年份"""
        if year:
            await self.conn.execute(
                """
                UPDATE documents SET
                    owner_company_id = $1,
                    year = $2,
                    updated_at = NOW()
                WHERE doc_id = $3
                """,
                company_id,
                year,
                doc_id
            )
            logger.info(f"✅ 已更新文檔 {doc_id} 的 owner_company_id={company_id}, year={year}")
        else:
            await self.conn.execute(
                """
                UPDATE documents SET
                    owner_company_id = $1,
                    updated_at = NOW()
                WHERE doc_id = $2
                """,
                company_id,
                doc_id
            )
            logger.info(f"✅ 已更新文檔 {doc_id} 的 owner_company_id={company_id}")
    
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
        
        # 先獲取 document.id (raw_artifacts 使用 document_id FK，不是 doc_id)
        doc_row = await self.conn.fetchrow("SELECT id FROM documents WHERE doc_id = $1", doc_id)
        if doc_row:
            document_id = doc_row['id']
            # 刪除相關數據 (document_chunks 已移除 - No RAG Option)
            await self.conn.execute("DELETE FROM raw_artifacts WHERE document_id = $1", document_id)
            await self.conn.execute("DELETE FROM document_companies WHERE document_id = $1", document_id)
            await self.conn.execute("DELETE FROM document_processing_history WHERE document_id = $1", document_id)
        
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
        company_id: Optional[int],  # 參數保留但不寫入此表（Schema v2.3 已刪除）
        file_type: str,
        file_path: str,
        page_num: int = None,
        metadata: str = None,
        file_size: int = 0  # 參數保留但不寫入此表（Schema v2.3 已刪除）
    ) -> bool:
        """
        插入 Raw Artifact 記錄
        
        🌟 Schema v2.3 變更：
        - file_type → artifact_type (值: table, image_screenshot, text_chunk, chart)
        - file_size_bytes, source_file → 已刪除
        - doc_id (字串) → document_id (Integer)
        
        Args:
            artifact_id: Artifact ID
            doc_id: 文檔 ID（用於查詢 document_id）
            company_id: 公司 ID（參數保留但不寫入）
            file_type: 文件類型 (table_json, image, etc.)
            file_path: 文件路徑
            page_num: 頁碼
            metadata: 元數據 JSON 字串
            file_size: 文件大小（參數保留但不寫入）
            
        Returns:
            bool: 是否成功
        """
        try:
            # 🌟 修正：轉換 file_type 為 artifact_type
            artifact_type = "table" if "table" in file_type.lower() else \
                            "image_screenshot" if "image" in file_type.lower() else \
                            "text_chunk" if "text" in file_type.lower() else \
                            "chart" if "chart" in file_type.lower() else \
                            file_type
            
            # 🌟 修正：查出 document_id (Integer)，移除已刪除欄位
            await self.conn.execute(
                """
                INSERT INTO raw_artifacts (
                    artifact_id, document_id, artifact_type,
                    file_path, page_num, parsed_data
                ) VALUES (
                    $1, 
                    (SELECT id FROM documents WHERE doc_id = $2), 
                    $3, $4, $5, $6::jsonb
                )
                ON CONFLICT (artifact_id) DO UPDATE SET
                    file_path = $4,
                    page_num = $5,
                    parsed_data = $6::jsonb
                """,
                artifact_id,
                doc_id,
                artifact_type,
                file_path,
                page_num,
                metadata or '{}'
            )
            logger.debug(f"✅ Artifact {artifact_id} ({artifact_type}) 已保存")
            return True
            
        except Exception as e:
            logger.error(f"❌ Artifact 入庫失敗: {e}")
            return False