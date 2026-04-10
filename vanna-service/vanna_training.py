"""
Vanna Training Data Module
==========================
    
提供完整的 DDL、Documentation 和 SQL Examples 訓練資料
適配 v2.3 Schema（雙軌制行業、JSONB、完美溯源）

資料結構：
- DDL: 表結構定義
- Documentation: 表用途說明（給 Vanna 理解語義）
- SQL Examples: 問題 → SQL 查詢範例
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger


class VannaTrainingData:
    """Vanna 訓練資料管理器"""
    
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
            # 核心表
            'companies': """
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    name_en VARCHAR(255),
    name_zh VARCHAR(255),
    stock_code VARCHAR(50) UNIQUE,
    
    -- 🌟 雙軌制行業
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
    owner_company_id INTEGER REFERENCES companies(id),
    year INTEGER,
    processing_status VARCHAR(50) DEFAULT 'pending',
    dynamic_attributes JSONB DEFAULT '{}'::jsonb,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'document_companies': """
CREATE TABLE document_companies (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    company_id INTEGER NOT NULL REFERENCES companies(id),
    relation_type VARCHAR(50) DEFAULT 'mentioned',
    extracted_industries JSONB,
    extraction_source VARCHAR(50) DEFAULT 'ai_predict',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, company_id)
);
""",
            'financial_metrics': """
CREATE TABLE financial_metrics (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    year INTEGER NOT NULL,
    fiscal_period VARCHAR(20) DEFAULT 'FY',
    metric_name VARCHAR(100) NOT NULL,
    metric_name_zh VARCHAR(100),
    original_metric_name VARCHAR(200),
    value NUMERIC(20, 2),
    unit VARCHAR(50),
    standardized_value NUMERIC(20, 2),
    standardized_currency VARCHAR(10) DEFAULT 'HKD',
    source_document_id INTEGER REFERENCES documents(id),
    source_page INTEGER,
    extraction_confidence FLOAT DEFAULT 0.8,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_metric UNIQUE (company_id, year, fiscal_period, metric_name)
);
""",
            'market_data': """
CREATE TABLE market_data (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    data_date DATE NOT NULL,
    period_type VARCHAR(20) DEFAULT 'daily',
    close_price NUMERIC(15, 4),
    open_price NUMERIC(15, 4),
    high_price NUMERIC(15, 4),
    low_price NUMERIC(15, 4),
    volume BIGINT,
    turnover NUMERIC(20, 2),
    market_cap NUMERIC(20, 2),
    pe_ratio NUMERIC(10, 4),
    pb_ratio NUMERIC(10, 4),
    dividend_yield NUMERIC(6, 4),
    source VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'key_personnel': """
CREATE TABLE key_personnel (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    document_id INTEGER REFERENCES documents(id),
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'shareholding_structure': """
CREATE TABLE shareholding_structure (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    year INTEGER NOT NULL,
    shareholder_name VARCHAR(255),
    shareholder_type VARCHAR(50),
    shares_held NUMERIC(20, 2),
    percentage NUMERIC(6, 4),
    is_controlling BOOLEAN DEFAULT FALSE,
    is_institutional BOOLEAN DEFAULT FALSE,
    source_document_id INTEGER REFERENCES documents(id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'revenue_breakdown': """
CREATE TABLE revenue_breakdown (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    year INTEGER NOT NULL,
    segment_name VARCHAR(255) NOT NULL,
    segment_type VARCHAR(50) DEFAULT 'business',
    revenue_amount NUMERIC(20, 2),
    revenue_percentage NUMERIC(5, 2),
    currency VARCHAR(10) DEFAULT 'HKD',
    source_document_id INTEGER REFERENCES documents(id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            'raw_artifacts': """
CREATE TABLE raw_artifacts (
    id SERIAL PRIMARY KEY,
    artifact_id VARCHAR(255) UNIQUE,
    document_id INTEGER NOT NULL REFERENCES documents(id),
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
    document_id INTEGER NOT NULL REFERENCES documents(id),
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
    source_artifact_id VARCHAR(255),
    metadata JSONB DEFAULT '{}'::jsonb,
    extraction_confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
            # Vanna 视图 (重要！)
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
    d.dynamic_attributes->>'theme' AS doc_theme
FROM documents d
LEFT JOIN companies c ON d.owner_company_id = c.id;
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
"""
        }
    
    def _get_enhanced_documentation(self) -> Dict[str, str]:
        """返回適配 v2.3 Schema 的 Documentation"""
        return {
            'companies': """
Companies 表是公司主檔，包含：
- 基本信息：name_en, name_zh, stock_code (港股代碼如 00001, 00700)
- 🌟 雙軌制行業系統：
  * is_industry_confirmed: TRUE 表示行業來自 Index Report (權威)
  * confirmed_industry: Rule A - 恆指報告定義的行業
  * ai_extracted_industries: Rule B - AI 預測的行業列表 (JSONB)
- 審計信息：auditor, auditor_opinion (Unqualified/Qualified)
- 股權信息：ultimate_controlling_shareholder

查詢範例：
- 查公司：SELECT * FROM companies WHERE stock_code = '0001'
- 查行業：SELECT * FROM v_companies_for_vanna WHERE primary_industry LIKE '%Biotech%'
""",
            'documents': """
Documents 表是文檔主檔，包含：
- doc_id: 唯一文檔 ID (格式如 DOC-CKH-2023)
- report_type: 'annual_report' 或 'index_report'
- owner_company_id: 年報所屬公司 (Index Report 為 NULL)
- processing_status: pending, processing, completed, failed
- dynamic_attributes: JSONB 存儲額外信息（如 theme）

查詢範例：
- 查年報：SELECT * FROM documents WHERE report_type = 'annual_report' AND year = 2023
- 查處理狀態：SELECT * FROM documents WHERE processing_status = 'completed'
- 查行業主題：SELECT * FROM v_documents_for_vanna WHERE doc_theme LIKE '%Biotech%'
""",
            'document_companies': """
Document_Companies 是橋樑表，記錄文檔與公司的關聯：
- document_id: 關聯到 documents 表
- company_id: 關聯到 companies 表
- relation_type: 'owner', 'mentioned', 'index_constituent'
- extracted_industries: 文檔提取的行業信息
- extraction_source: 'index_rule' (權威) 或 'ai_predict' (預測)

這表支援「完美溯源」：知道數據來自哪份文檔。
""",
            'financial_metrics': """
Financial_Metrics 是財務指標表 (EAV 模式)：
- company_id: 關聯公司
- year, fiscal_period: 年度與期間 (FY, H1, Q1-Q4)
- metric_name: 指標英文名 (如 Total Revenue, Net Profit)
- metric_name_zh: 指標中文名
- value: 原始值, unit: 原始單位
- standardized_value: 标准化值 (HKD)
- source_document_id: 🌟 溯源到 documents 表
- source_page: 記錄數來源頁數

查詢範例：
- 查收入：SELECT * FROM financial_metrics WHERE metric_name = 'Total Revenue' AND year = 2023
- 查公司財務：SELECT fm.* FROM financial_metrics fm JOIN companies c ON fm.company_id = c.id WHERE c.stock_code = '0001'
""",
            'market_data': """
Market_Data 是市場數據表：
- company_id: 關聯公司
- data_date: 交易日期
- close_price, open_price, high_price, low_price: 股價
- volume: 成交量, turnover: 成交額
- market_cap: 市值
- pe_ratio, pb_ratio: 估值指標

查詢範例：
- 查股價：SELECT data_date, close_price FROM market_data WHERE company_id = X AND data_date BETWEEN '2022-01-01' AND '2022-12-31'
""",
            'key_personnel': """
Key_Personnel 是關鍵人員表：
- company_id: 關聯公司
- document_id: 🌟 溯源到 documents 表
- year: 年度
- name_en, name_zh: 姓名
- role, board_role: 職位 (Chairman, CEO, Executive Director)
- committee_membership: 委員會成員身份 (JSONB)
- biography: 個人簡介

查詢範例：
- 查董事：SELECT * FROM key_personnel WHERE company_id = X AND role LIKE '%Director%'
- 櫻主席：SELECT * FROM key_personnel WHERE board_role = 'chairman'
""",
            'shareholding_structure': """
Shareholding_Structure 是股東結構表：
- company_id: 關聯公司
- year: 年度
- shareholder_name: 股東名稱
- shareholder_type: individual, corporation, trust, government
- percentage: 持股比例
- is_controlling: 是否控股股東

查詢範例：
- 查控股股東：SELECT * FROM shareholding_structure WHERE is_controlling = TRUE
""",
            'v_companies_for_vanna': """
v_companies_for_vanna 是 Vanna 專用視圖：
- 🌟 智能判定 primary_industry：
  * 如果 confirmed_industry 存在 (權威) → 使用它
  * 否則 → 使用 ai_extracted_industries 的第一個值
- 這視圖解決了雙軌制行業問題！

這是 Vanna 查詢公司行業的最佳入口。
""",
            'v_documents_for_vanna': """
v_documents_for_vanna 是 Vanna 專用文檔視圖：
- 展平了 documents 和 companies 的關聯
- 包含 owner_company_name_en, owner_stock_code
- 從 dynamic_attributes JSONB 提取 doc_theme

這是 Vanna 查詢文檔的最佳入口。
""",
            'raw_artifacts': """
Raw_Artifacts 是 LiteParse 原始提取結果表：
- artifact_id: 唯一識別 ID
- document_id: 🌟 關聯到 documents (溯源)
- artifact_type: text_chunk, table, chart, image_screenshot
- content: LiteParse 提取的 Markdown 內容
- file_path: Cap 圖儲存路徑
- parsed_data: Qwen-VL 解析結果 (JSONB)
- parsing_status: pending, parsed, failed

支援「完美溯源」：如果 AI 讀錯數，可以用 artifact_id 搵返原圖對質。
""",
            'entity_relations': """
Entity_Relations 是實體關係抽取表 (Graph)：
- source_entity → target_entity 的關係
- relation_type: appointed, resigned, acquired, subsidiary_of
- event_date, event_year: 事件時間
- 支援 Graph-based 查詢

查詢範例：
- 查任命：SELECT * FROM entity_relations WHERE relation_type = 'appointed_as_chairman'
"""
        }
    
    def _get_enhanced_sql_examples(self) -> List[Dict[str, str]]:
        """返回適配 v2.3 Schema 的 SQL Examples"""
        return [
            # ===== 公司查詢 =====
            {
                'question': '列出所有生物科技公司',
                'sql': "SELECT stock_code, name_en, name_zh, primary_industry FROM v_companies_for_vanna WHERE primary_industry LIKE '%Biotech%' OR primary_industry LIKE '%Pharma%'"
            },
            {
                'question': '哪間公司的負債最高？',
                'sql': "SELECT c.name_en, c.stock_code, fm.value as total_liabilities, fm.unit FROM financial_metrics fm JOIN companies c ON fm.company_id = c.id WHERE fm.metric_name = 'Total Liabilities' AND fm.year = 2024 ORDER BY fm.value DESC LIMIT 5"
            },
            {
                'question': 'INNOCARE 2023 年和 2024 年的收入是多少？',
                'sql': "SELECT year, value, unit FROM financial_metrics WHERE company_id = (SELECT id FROM companies WHERE stock_code = '9969') AND metric_name = 'Total Revenue' AND year BETWEEN 2023 AND 2024 ORDER BY year"
            },
            {
                'question': 'CK Hutchison 过去5年的收入趋势',
                'sql': "SELECT year, value FROM financial_metrics WHERE company_id = (SELECT id FROM companies WHERE stock_code = '0001') AND metric_name = 'Total Revenue' ORDER BY year"
            },
            {
                'question': '找出所有使用 Deloitte 作为审计师的公司',
                'sql': "SELECT name_en, name_zh, stock_code, auditor FROM companies WHERE auditor = 'Deloitte'"
            },
            {
                'question': '哪些公司的行业是已确认的（来自 Index Report）？',
                'sql': "SELECT name_en, stock_code, confirmed_industry FROM companies WHERE is_industry_confirmed = TRUE"
            },
            {
                'question': '哪些公司的行业是 AI 预测的？',
                'sql': "SELECT name_en, stock_code, ai_extracted_industries FROM companies WHERE is_industry_confirmed = FALSE"
            },
            {
                'question': '获取公司的主行业（智能判定）',
                'sql': "SELECT name_en, stock_code, primary_industry FROM v_companies_for_vanna"
            },
            
            # ===== 关键人员查询 =====
            {
                'question': 'CK Hutchison 的执行董事是谁？',
                'sql': "SELECT name_en, name_zh, role FROM key_personnel WHERE company_id = (SELECT id FROM companies WHERE stock_code = '0001') AND role LIKE '%Director%'"
            },
            {
                'question': 'Lisa Chen 的背景介绍',
                'sql': "SELECT name_en, biography FROM key_personnel WHERE name_en = 'Lisa Chen'"
            },
            {
                'question': '2024年有哪些公司更换了董事长？',
                'sql': "SELECT er.source_entity_name, er.target_entity_name, er.event_date FROM entity_relations er WHERE er.relation_type = 'appointed_as_chairman' AND er.event_year = 2024"
            },
            
            # ===== 文档查询 =====
            {
                'question': '列出所有已完成的年报',
                'sql': "SELECT filename, year, processing_status FROM v_documents_for_vanna WHERE report_type = 'annual_report' AND processing_status = 'completed'"
            },
            {
                'question': '这份文档提到哪些公司？',
                'sql': "SELECT c.name_en, dc.relation_type, dc.extracted_industries FROM document_companies dc JOIN companies c ON dc.company_id = c.id WHERE dc.document_id = (SELECT id FROM documents WHERE filename LIKE '%CKH%')"
            },
            
            # ===== 股东查询 =====
            {
                'question': 'CK Hutchison 的控股股东是谁？',
                'sql': "SELECT shareholder_name, percentage FROM shareholding_structure WHERE company_id = (SELECT id FROM companies WHERE stock_code = '0001') AND is_controlling = TRUE"
            },
            
            # ===== 收入分解查询 =====
            {
                'question': 'CK Hutchison 2023 年的收入按地区分布',
                'sql': "SELECT segment_name, revenue_amount, revenue_percentage FROM revenue_breakdown WHERE company_id = (SELECT id FROM companies WHERE stock_code = '0001') AND year = 2023 AND segment_type = 'geography'"
            },
            
            # ===== 市场数据查询 =====
            {
                'question': 'INNOCARE 2022 年的股价走势',
                'sql': "SELECT data_date, close_price FROM market_data WHERE company_id = (SELECT id FROM companies WHERE stock_code = '9969') AND data_date BETWEEN '2022-01-01' AND '2022-12-31' ORDER BY data_date"
            },
            
            # ===== 溯源查询 =====
            {
                'question': '这个财务数据的来源文档是什么？',
                'sql': "SELECT d.filename, d.year, fm.source_page FROM financial_metrics fm JOIN documents d ON fm.source_document_id = d.id WHERE fm.id = {metric_id}"
            },
            {
                'question': '查看原始提取结果',
                'sql': "SELECT artifact_id, artifact_type, page_num, parsing_status FROM raw_artifacts WHERE document_id = (SELECT id FROM documents WHERE filename = 'CKH_AR_2023.pdf')"
            },
            
            # ===== 综合查询 =====
            {
                'question': '计算 INNOCARE 的市值',
                'sql': "SELECT c.name_en, md.close_price, md.volume, (md.close_price * md.volume) as approx_market_cap FROM market_data md JOIN companies c ON md.company_id = c.id WHERE c.stock_code = '9969' AND md.data_date = '2024-12-31'"
            },
            {
                'question': '比较两间公司的财务表现',
                'sql': "SELECT c.stock_code, c.name_en, fm.metric_name, fm.value, fm.year FROM financial_metrics fm JOIN companies c ON fm.company_id = c.id WHERE c.stock_code IN ('9969', '9926') AND fm.metric_name = 'Total Revenue' AND fm.year = 2024"
            }
        ]


def create_training_json_files(data_dir: str = "/app/data/vanna"):
    """創建 JSON 訓練資料檔案（供 Docker 環境使用）"""
    trainer = VannaTrainingData(data_dir)
    
    # 儲存 DDL
    ddl_path = Path(data_dir) / "ddl.json"
    with open(ddl_path, 'w', encoding='utf-8') as f:
        json.dump(trainer._get_enhanced_ddl(), f, indent=2, ensure_ascii=False)
    
    # 儲存 Documentation
    docs_path = Path(data_dir) / "documentation.json"
    with open(docs_path, 'w', encoding='utf-8') as f:
        json.dump(trainer._get_enhanced_documentation(), f, indent=2, ensure_ascii=False)
    
    # 儲存 SQL Examples
    sql_path = Path(data_dir) / "sql_examples.json"
    with open(sql_path, 'w', encoding='utf-8') as f:
        json.dump(trainer._get_enhanced_sql_examples(), f, indent=2, ensure_ascii=False)
    
    logger.info(f"✅ 訓練資料已儲存到 {data_dir}")


if __name__ == "__main__":
    # 本地測試：生成訓練資料
    create_training_json_files("./data/vanna")