"""
Vanna Training Data Module
==========================
    
提供完整的 DDL、Documentation 和 SQL Examples 訓練資料
適配 v2.3 Schema（雙軌制行業、JSONB、完美溯源）

資料結構：
- DDL: 表結構定義
- Documentation: 表用途說明（給 Vanna 理解語義）
- SQL Examples: 問題 → SQL 查詢範例

【v2.3 重要更新】
1. documents: 新增 dynamic_attributes JSONB 欄位
2. market_data: 欄位名稱變更 (trade_date→data_date, closing_price→close_price, trading_volume→volume)
3. key_personnel: 欄位名稱變更 (person_name→name_en, committee→committee_membership)
4. revenue_breakdown: 欄位名稱變更 (category→segment_name, category_type→segment_type, amount→revenue_amount)
5. shareholding_structure: 新增 trust_name, trustee_name 信託欄位
6. document_pages: 新增 ocr_confidence, embedding_vector, metadata
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger


class VannaTrainingData:
    """Vanna 訓練資料管理器"""
    
    # 🆕 v2.3: 欄位名稱變更映射（用於提示 Vanna）
    COLUMN_MAPPINGS = {
        'market_data': {
            'trade_date': 'data_date',
            'closing_price': 'close_price',
            'opening_price': 'open_price',
            'trading_volume': 'volume'
        },
        'revenue_breakdown': {
            'category': 'segment_name',
            'category_type': 'segment_type',
            'amount': 'revenue_amount'
        },
        'key_personnel': {
            'person_name': 'name_en',
            'person_name_zh': 'name_zh',
            'committee': 'committee_membership'
        },
        'document_pages': {
            'company_id': None  # 已刪除，必須 JOIN documents 才能按公司篩選
        },
        'raw_artifacts': {
            'company_id': None  # 已刪除，必須 JOIN documents
        }
    }
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.training_dir = self.data_dir / "vanna"
        self.training_dir.mkdir(parents=True, exist_ok=True)
        
    def _load_json_file(self, filename: str) -> Dict:
        """載入 JSON 訓練檔案"""
        filepath = self.training_dir / filename
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def train_vanna(self, vn, validate: bool = True) -> Dict[str, int]:
        """
        訓練 Vanna 完整的 DDL、Documentation 和 SQL Examples
        
        Args:
            vn: Vanna instance
            validate: 是否驗證 SQL 可執行
            
        Returns:
            統計資訊：訓練數量、錯誤數
        """
        stats = {
            'ddl_trained': 0,
            'documentation_trained': 0,
            'sql_trained': 0,
            'errors': []
        }
        
        # 1. 訓練 DDL (Enhanced with v2.3 schema)
        ddl_data = self._get_enhanced_ddl()
        for table_name, ddl in ddl_data.items():
            try:
                vn.train(ddl=ddl)
                stats['ddl_trained'] += 1
                logger.info(f"   ✅ DDL: {table_name}")
            except Exception as e:
                stats['errors'].append(f"DDL {table_name}: {e}")
                logger.warning(f"   ⚠️ DDL failed {table_name}: {e}")
        
        # 2. 訓練 Documentation (給 Vanna 理解表用途)
        docs_data = self._get_enhanced_documentation()
        for table_name, doc in docs_data.items():
            try:
                vn.train(documentation=doc)
                stats['documentation_trained'] += 1
                logger.info(f"   ✅ Doc: {table_name}")
            except Exception as e:
                stats['errors'].append(f"Doc {table_name}: {e}")
                logger.warning(f"   ⚠️ Doc failed {table_name}: {e}")
        
        # 3. 訓練 SQL Examples (適配雙軌制行業)
        sql_data = self._get_enhanced_sql_examples()
        for item in sql_data:
            try:
                vn.train(question=item['question'], sql=item['sql'])
                stats['sql_trained'] += 1
                logger.info(f"   ✅ SQL: {item['question'][:50]}...")
            except Exception as e:
                stats['errors'].append(f"SQL {item['question'][:30]}: {e}")
                logger.warning(f"   ⚠️ SQL failed: {e}")
        
        return stats
    
    def _get_enhanced_ddl(self) -> Dict[str, str]:
        """返回適配 v2.3 Schema 的 DDL"""
        return {
            # ===== 核心表 =====
            'companies': """
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    name_en VARCHAR(255),
    name_zh VARCHAR(255),
    stock_code VARCHAR(50) UNIQUE,
    is_industry_confirmed BOOLEAN DEFAULT FALSE,
    confirmed_industry VARCHAR(100),
    ai_extracted_industries JSONB,
    sector VARCHAR(100),
    auditor VARCHAR(200),
    auditor_opinion VARCHAR(50),
    ultimate_controlling_shareholder TEXT,
    principal_banker TEXT,
    extra_data JSONB DEFAULT '{}'::jsonb,
    listing_status VARCHAR(50) DEFAULT 'listed',
    listing_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'documents': """
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(255) UNIQUE,
    filename VARCHAR(500) NOT NULL,
    report_type VARCHAR(50) DEFAULT 'annual_report',
    owner_company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    year INTEGER,
    processing_status VARCHAR(50) DEFAULT 'pending',
    dynamic_attributes JSONB DEFAULT '{}'::jsonb,
    file_path TEXT,
    file_hash VARCHAR(64),
    file_size_bytes INTEGER,
    processing_error TEXT,
    processing_completed_at TIMESTAMP,
    total_chunks INTEGER DEFAULT 0,
    total_artifacts INTEGER DEFAULT 0,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'document_companies': """
CREATE TABLE document_companies (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) DEFAULT 'mentioned',
    extracted_industries JSONB,
    extraction_source VARCHAR(50) DEFAULT 'ai_predict',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, company_id)
);
""",
            'document_processing_history': """
CREATE TABLE document_processing_history (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    stage VARCHAR(100),
    status VARCHAR(50) NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'review_queue': """
CREATE TABLE review_queue (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES document_companies(id) ON DELETE CASCADE,
    review_type VARCHAR(100) NOT NULL,
    priority INTEGER DEFAULT 5,
    status VARCHAR(50) DEFAULT 'pending',
    issue_description TEXT,
    ai_suggestion TEXT,
    human_decision TEXT,
    reviewer_id VARCHAR(100),
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_review_status CHECK (status IN ('pending', 'in_review', 'approved', 'rejected', 'escalated'))
);
""",
            'vanna_training_data': """
CREATE TABLE vanna_training_data (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    sql_query TEXT NOT NULL,
    table_name VARCHAR(255),
    documentation TEXT,
    quality_score DECIMAL(3, 2),
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'financial_metrics': """
CREATE TABLE financial_metrics (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    fiscal_period VARCHAR(20) DEFAULT 'FY',
    metric_name VARCHAR(100) NOT NULL,
    metric_name_zh VARCHAR(100),
    original_metric_name VARCHAR(200),
    value NUMERIC(20, 2),
    unit VARCHAR(50),
    standardized_value NUMERIC(20, 2),
    standardized_currency VARCHAR(10) DEFAULT 'HKD',
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    source_page INTEGER,
    source_table_id VARCHAR(100),
    extraction_confidence FLOAT DEFAULT 0.8,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_metric UNIQUE (company_id, year, fiscal_period, metric_name)
);
""",
            'market_data': """
CREATE TABLE market_data (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    data_date DATE NOT NULL,
    period_type VARCHAR(20) DEFAULT 'daily',
    open_price NUMERIC(15, 4),
    high_price NUMERIC(15, 4),
    low_price NUMERIC(15, 4),
    close_price NUMERIC(15, 4),
    adj_close_price NUMERIC(15, 4),
    volume BIGINT,
    turnover NUMERIC(20, 2),
    market_cap NUMERIC(20, 2),
    pe_ratio NUMERIC(10, 4),
    pb_ratio NUMERIC(10, 4),
    dividend_yield NUMERIC(6, 4),
    source VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_market_data UNIQUE (company_id, data_date, period_type)
);
""",
            'revenue_breakdown': """
CREATE TABLE revenue_breakdown (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    segment_name VARCHAR(255) NOT NULL,
    segment_type VARCHAR(50) DEFAULT 'business',
    revenue_amount NUMERIC(20, 2),
    revenue_percentage NUMERIC(5, 2),
    currency VARCHAR(10) DEFAULT 'HKD',
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_revenue_segment UNIQUE (company_id, year, segment_name, segment_type)
);
""",
            'key_personnel': """
CREATE TABLE key_personnel (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    year INTEGER,
    name_en VARCHAR(255),
    name_zh VARCHAR(255),
    position_title_en VARCHAR(255),
    position_title_zh VARCHAR(255),
    position_type VARCHAR(50),
    role VARCHAR(255),
    board_role VARCHAR(100),
    committee_membership JSONB,
    appointment_date DATE,
    resignation_date DATE,
    is_current BOOLEAN DEFAULT TRUE,
    biography TEXT,
    source_page INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'shareholding_structure': """
CREATE TABLE shareholding_structure (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    shareholder_name VARCHAR(255),
    shareholder_type VARCHAR(50),
    trust_name VARCHAR(255),
    trustee_name VARCHAR(255),
    shares_held NUMERIC(20, 2),
    percentage NUMERIC(6, 4),
    is_controlling BOOLEAN DEFAULT FALSE,
    is_institutional BOOLEAN DEFAULT FALSE,
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_shareholder UNIQUE (company_id, year, shareholder_name)
);
""",
            'document_pages': """
CREATE TABLE document_pages (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_num INTEGER NOT NULL,
    markdown_content TEXT NOT NULL,
    ocr_confidence FLOAT DEFAULT 0.0,
    has_tables BOOLEAN DEFAULT FALSE,
    has_images BOOLEAN DEFAULT FALSE,
    embedding_vector VECTOR(384),  -- 🌟 本地 Embedding 模型維度 (sentence-transformers all-MiniLM-L6-v2)
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_page UNIQUE (document_id, page_num)
);
""",
            'document_chunks': """
CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_type VARCHAR(50) DEFAULT 'text',
    content TEXT NOT NULL,
    page_number INTEGER,
    bounding_box JSONB,
    embedding_vector VECTOR(384),  -- 🌟 本地 Embedding 模型維度 (sentence-transformers all-MiniLM-L6-v2)
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"",
            'document_tables': """
CREATE TABLE document_tables (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL,
    table_index INTEGER NOT NULL,
    table_type VARCHAR(100),
    title TEXT,
    headers JSONB,
    rows JSONB NOT NULL,
    page_number INTEGER,
    bounding_box JSONB,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'raw_artifacts': """
CREATE TABLE raw_artifacts (
    id SERIAL PRIMARY KEY,
    artifact_id VARCHAR(255) UNIQUE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    artifact_type VARCHAR(50),
    content TEXT,
    file_path VARCHAR(500),
    page_num INTEGER,
    bbox JSONB,
    parsed_data JSONB,
    parsing_status VARCHAR(50) DEFAULT 'pending',
    parsing_error TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'entity_relations': """
CREATE TABLE entity_relations (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_entity_type VARCHAR(50),
    source_entity_id INTEGER,
    source_entity_name VARCHAR(255),
    target_entity_type VARCHAR(50),
    target_entity_id INTEGER,
    target_entity_name VARCHAR(255),
    relation_type VARCHAR(100),
    relation_strength FLOAT DEFAULT 1.0,
    event_date DATE,
    event_year INTEGER,
    source_page INTEGER,
    source_artifact_id VARCHAR(255) REFERENCES raw_artifacts(artifact_id) ON DELETE SET NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    extraction_confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            # ===== Vanna 專用視圖 =====
            'v_companies_for_vanna': """
CREATE OR REPLACE VIEW v_companies_for_vanna AS
SELECT 
    id,
    name_en,
    name_zh,
    stock_code,
    sector,
    is_industry_confirmed,
    COALESCE(confirmed_industry, ai_extracted_industries->>0) AS primary_industry,
    created_at
FROM companies;
""",
            'v_documents_for_vanna': """
CREATE OR REPLACE VIEW v_documents_for_vanna AS
SELECT 
    d.id,
    d.doc_id,
    d.filename,
    d.report_type,
    d.year,
    d.processing_status,
    d.uploaded_at,
    c.name_en AS owner_company_name_en,
    c.name_zh AS owner_company_name_zh,
    c.stock_code AS owner_stock_code,
    d.dynamic_attributes->>'theme' AS doc_theme,
    d.dynamic_attributes->>'region' AS doc_region
FROM documents d
LEFT JOIN companies c ON d.owner_company_id = c.id;
""",
            'document_summary': """
CREATE OR REPLACE VIEW document_summary AS
SELECT 
    d.id,
    d.filename,
    d.report_type,
    d.year,
    d.processing_status,
    d.uploaded_at,
    d.dynamic_attributes->>'index_theme' AS index_theme,
    c_owner.name_en AS owner_company_name,
    COUNT(dc.id) AS mentioned_companies_count
FROM documents d
LEFT JOIN companies c_owner ON d.owner_company_id = c_owner.id
LEFT JOIN document_companies dc ON d.id = dc.document_id
GROUP BY d.id, c_owner.name_en;
"""
        }
    
    def _get_enhanced_documentation(self) -> Dict[str, str]:
        """返回適配 v2.3 Schema 的 Documentation"""
        return {
            'companies': """
【公司主檔】Companies 表是上市公司基本資訊的核心表。

【主要欄位】
- name_en, name_zh: 公司英文名/中文名
- stock_code: 港股代碼（格式如 00001, 00700，5位數字，不含 .HK）
- sector: 板塊分類

【🌟 雙軌制行業系統】
- is_industry_confirmed: TRUE 表示行業來自 Index Report（權威）
- confirmed_industry: Rule A - 恆指報告定義的行業（絕對真理）
- ai_extracted_industries: Rule B - AI 預測的行業列表（JSONB Array）

【最佳查詢方式】
⭐ 查公司行業請使用 v_companies_for_vanna 視圖，它自動處理雙軌制邏輯：
SELECT primary_industry FROM v_companies_for_vanna WHERE stock_code = '00001'

【其他欄位】
- auditor: 審計師
- auditor_opinion: 審計意見（Unqualified/Qualified/Disclaimer/Adverse）
- ultimate_controlling_shareholder: 最終控股股東
- principal_banker: 主要銀行
- extra_data: JSONB 動態屬性（CEO、主要客戶等）
""",
            'documents': """
【文檔主檔】Documents 表是所有上傳文檔的核心表。

【主要欄位】
- doc_id: 唯一文檔 ID
- filename: 文檔檔案名稱
- report_type: 報告類型（annual_report / index_report）
- owner_company_id: 文檔所屬公司（Index Report 為 NULL）
- year: 年份
- processing_status: 處理狀態（pending/processing/completed/failed）

【🌟 v2.3 JSONB 動態屬性】
- dynamic_attributes: JSONB 擴展欄位
  * 可存放：theme、region、index_quarter 等
  * 查詢方式：dynamic_attributes->>'theme'

【最佳查詢方式】
⭐ 使用 v_documents_for_vanna 視圖，它自動展平 JSONB 和關聯公司：
SELECT * FROM v_documents_for_vanna WHERE owner_company_name_en ILIKE '%Tencent%'
""",
            'document_companies': """
【文檔-公司關聯表】Document_Companies 是橋樑表。

【主要欄位】
- document_id: 關聯文檔
- company_id: 關聯公司
- relation_type: 公司角色（owner/mentioned/subsidiary/competitor/index_constituent）
- extracted_industries: 行業資訊（JSONB）
- extraction_source: 提取來源（index_rule / ai_predict）
""",
            'financial_metrics': """
【財務指標表】EAV 模式儲存財務數據。

【⚠️ CRITICAL】
- EAV 模式：metric_name 是指標名（如 Revenue），不是欄位名！
- 跨公司比較必須使用 standardized_value（已轉換 HKD）
- 不要用 raw value 排名，單位不同！

【主要欄位】
- metric_name: 指標英文名（Revenue, Net Profit, Total Assets 等）
- value: 原始值（不可跨公司比較）
- standardized_value: ⭐標準化值（HKD，用於排名）
- source_document_id, source_page: 溯源欄位
""",
            'market_data': """
【市場數據表】股價、成交量、估值指標。

【⚠️ v2.3 欄位名稱變更】
- trade_date → data_date
- closing_price → close_price
- trading_volume → volume

【主要欄位】
- data_date: 交易日期
- close_price, open_price, high_price, low_price: 股價
- volume: 成交量
- turnover: 成交額
- market_cap: 市值
- pe_ratio, pb_ratio, dividend_yield: 估值指標
""",
            'revenue_breakdown': """
【收入分解表】收入按業務/地區/產品分解。

【⚠️ v2.3 欄位名稱變更】
- category → segment_name
- category_type → segment_type
- amount → revenue_amount

【主要欄位】
- segment_name: 分部名稱（動態）
- segment_type: 分部類型（business/geography/product）
- revenue_amount: 收入金額
- revenue_percentage: 收入佔比
""",
            'key_personnel': """
【關鍵人員表】董事、高管資訊。

【⚠️ v2.3 欄位名稱變更】
- person_name → name_en
- person_name_zh → name_zh
- committee → committee_membership（JSONB）

【主要欄位】
- name_en, name_zh: 姓名
- role, board_role: 職位
- committee_membership: ⭐ JSONB 委員會成員身份
  * 查詢：committee_membership ? 'audit'
- is_current: 是否現任
""",
            'shareholding_structure': """
【股東結構表】持股資訊。

【🌟 v2.3 新增信託欄位】
- trust_name: 信託名稱
- trustee_name: 受託人名稱

【主要欄位】
- shareholder_name: 股東名稱
- shareholder_type: 股東類型（individual/corporation/trust/government）
- percentage: 持股比例
- is_controlling: 是否控股股東
""",
            'document_pages': """
【PDF 頁面表】Markdown 內容（Zone 2 Fallback）。

【⚠️ CRITICAL】
document_pages 沒有 company_id 欄位！
必須 JOIN documents 來 filter by owner_company_id！

【正確查詢方式】
SELECT dp.* FROM document_pages dp
JOIN documents d ON dp.document_id = d.id
WHERE d.owner_company_id = 1

【錯誤查詢】
SELECT * FROM document_pages WHERE company_id = 1（此欄位不存在！）
""",
            'raw_artifacts': """
【原始提取結果表】支援完美溯源。

【⚠️ 沒有 company_id】
必須通過 document_id JOIN documents！

【主要欄位】
- artifact_id: 唯一識別碼
- artifact_type: 類型（text_chunk/table/image_screenshot/chart）
- file_path: 截圖儲存路徑
- parsing_status: 解析狀態（pending/parsed/failed）
""",
            'entity_relations': """
【實體關係表】支援 Graph-based 查詢。

【主要欄位】
- source_entity_name: 源實體名稱
- target_entity_name: 目標實體名稱
- relation_type: 關係類型（appointed/resigned/acquired/subsidiary_of）
- event_year: 事件年份
""",
            'v_companies_for_vanna': """
【⭐ Vanna 專用公司視圖】查詢公司行業的最佳入口！

【智能判定 primary_industry】
- 如果 confirmed_industry 存在 → 使用它
- 否則 → 使用 ai_extracted_industries 第一個值

【欄位】
- primary_industry: 智能判定的主行業
""",
            'v_documents_for_vanna': """
【⭐ Vanna 專用文檔視圖】查詢文檔的最佳入口！

【自動展平】
- owner_company_name_en/zh, owner_stock_code
- doc_theme, doc_region（從 dynamic_attributes 提取）
"""
        }
    
    def _get_enhanced_sql_examples(self) -> List[Dict[str, str]]:
        """返回適配 v2.3 Schema 的 SQL Examples"""
        return [
            # ===== 公司查詢 =====
            {
                'question': '列出所有生物科技公司',
                'sql': "SELECT stock_code, name_en, name_zh, primary_industry FROM v_companies_for_vanna WHERE primary_industry ILIKE '%Biotech%'"
            },
            {
                'question': '哪間公司的負債最高？',
                'sql': "SELECT c.name_en, c.stock_code, fm.standardized_value as total_liabilities FROM financial_metrics fm JOIN companies c ON fm.company_id = c.id WHERE fm.metric_name = 'Total Liabilities' AND fm.year = 2024 ORDER BY fm.standardized_value DESC LIMIT 5"
            },
            {
                'question': 'INNOCARE 2023 年和 2024 年的收入是多少？',
                'sql': "SELECT year, standardized_value, unit FROM financial_metrics WHERE company_id = (SELECT id FROM companies WHERE stock_code = '09969') AND metric_name = 'Revenue' AND year IN (2023, 2024) ORDER BY year"
            },
            {
                'question': 'CK Hutchison 过去5年的收入趋势',
                'sql': "SELECT year, standardized_value FROM financial_metrics WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND metric_name = 'Revenue' ORDER BY year DESC LIMIT 5"
            },
            {
                'question': '找出所有使用 Deloitte 作为审计师的公司',
                'sql': "SELECT name_en, name_zh, stock_code, auditor FROM companies WHERE auditor ILIKE '%Deloitte%'"
            },
            {
                'question': '获取公司的主行业',
                'sql': "SELECT name_en, stock_code, primary_industry FROM v_companies_for_vanna"
            },
            # ===== 关键人员查询 =====
            {
                'question': 'CK Hutchison 的执行董事是谁？',
                'sql': "SELECT name_en, name_zh, role, board_role FROM key_personnel WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND role ILIKE '%Director%'"
            },
            {
                'question': '审计委员会成员有哪些？',
                'sql': "SELECT name_en, name_zh FROM key_personnel WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND committee_membership ? 'audit'"
            },
            # ===== 文档查询 =====
            {
                'question': '列出所有已完成的年报',
                'sql': "SELECT filename, year, processing_status FROM v_documents_for_vanna WHERE report_type = 'annual_report' AND processing_status = 'completed'"
            },
            {
                'question': '查找所有恆指報告',
                'sql': "SELECT filename, year, dynamic_attributes->>'theme' as theme FROM documents WHERE report_type = 'index_report'"
            },
            # ===== 股东查询 =====
            {
                'question': 'CK Hutchison 的控股股东是谁？',
                'sql': "SELECT shareholder_name, percentage FROM shareholding_structure WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND is_controlling = TRUE"
            },
            {
                'question': '查询信託持股信息',
                'sql': "SELECT shareholder_name, trust_name, trustee_name, percentage FROM shareholding_structure WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND trust_name IS NOT NULL"
            },
            # ===== 收入分解查询 =====
            {
                'question': 'CK Hutchison 2023 年的收入按地区分布',
                'sql': "SELECT segment_name, revenue_amount, revenue_percentage FROM revenue_breakdown WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND year = 2023 AND segment_type = 'geography'"
            },
            # ===== 市场数据查询 =====
            {
                'question': 'INNOCARE 2022 年的股价走势',
                'sql': "SELECT data_date, close_price, volume FROM market_data WHERE company_id = (SELECT id FROM companies WHERE stock_code = '09969') AND data_date BETWEEN '2022-01-01' AND '2022-12-31' ORDER BY data_date"
            },
            {
                'question': '查询市盈率排名',
                'sql': "SELECT c.stock_code, c.name_en, m.pe_ratio FROM market_data m JOIN companies c ON m.company_id = c.id WHERE m.pe_ratio IS NOT NULL ORDER BY m.pe_ratio DESC LIMIT 10"
            },
            # ===== Fallback 查询 =====
            {
                'question': '文檔中有關 ESG 的內容',
                'sql': "SELECT page_num, markdown_content FROM document_pages dp JOIN documents d ON dp.document_id = d.id WHERE d.owner_company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND dp.markdown_content ILIKE '%ESG%' LIMIT 5"
            },
            # ===== JSONB 查询 =====
            {
                'question': '查询 documents 的动态属性',
                'sql': "SELECT filename, dynamic_attributes->>'theme' as theme FROM documents WHERE dynamic_attributes ? 'theme'"
            },
            {
                'question': '查询 companies 的 extra_data',
                'sql': "SELECT stock_code, name_en, extra_data->>'chief_executive' as ceo FROM companies WHERE extra_data ? 'chief_executive'"
            }
        ]


def create_training_json_files(data_dir: str = "/app/data/vanna"):
    """創建 JSON 訓練資料檔案"""
    trainer = VannaTrainingData(data_dir)
    
    ddl_path = Path(data_dir) / "ddl.json"
    with open(ddl_path, 'w', encoding='utf-8') as f:
        json.dump(trainer._get_enhanced_ddl(), f, indent=2, ensure_ascii=False)
    
    docs_path = Path(data_dir) / "documentation.json"
    with open(docs_path, 'w', encoding='utf-8') as f:
        json.dump(trainer._get_enhanced_documentation(), f, indent=2, ensure_ascii=False)
    
    sql_path = Path(data_dir) / "sql_examples.json"
    with open(sql_path, 'w', encoding='utf-8') as f:
        json.dump(trainer._get_enhanced_sql_examples(), f, indent=2, ensure_ascii=False)
    
    logger.info(f"✅ 訓練資料已儲存到 {data_dir}")


if __name__ == "__main__":
    create_training_json_files("./data/vanna")