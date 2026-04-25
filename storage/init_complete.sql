-- ============================================================
-- Nanobot Database Schema - Complete Initialization
-- ============================================================
--
-- 【Combined Initialization - 單一文件】
-- 本文件包含完整的數據庫初始化：
-- 1. Apache AGE 圖譜擴展 + pgvector 向量擴展
-- 2. 關係型表結構
-- 3. 視圖和索引
--
-- 【版本 Version】 v2.4
-- ============================================================

-- ============================================================
-- 【擴展 Extensions】
-- ============================================================

-- Apache AGE 圖譜擴展
CREATE EXTENSION IF NOT EXISTS age;

-- pgvector 向量嵌入
CREATE EXTENSION IF NOT EXISTS vector;

-- UUID 生成
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 模糊搜索
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- 【注意】AGE 圖譜創建已移至 01-init-age.sql
-- 這裡只創建關係型表結構
-- ============================================================

-- 設置 AGE search path（如果 AGE 已啟用）
SET search_path = public, "$user", ag_catalog;

-- 圖譜創建已由 01-init-age.sql 處理，這裡不再重複創建
-- SELECT create_graph('ownership_graph');

-- ============================================================
-- 【核心表結構 Core Tables】
-- ============================================================

-- ============================================================
-- 【表 1: companies 公司主檔】
-- 【功能 Purpose】
-- 儲存上市公司基本資訊，支援行業雙軌制分類
--
-- 【設計理念 Design Philosophy】
-- 行業雙軌制 (Dual-Track Industry Classification):
-- - Rule A (confirmed_industry): 來自恆指報告的權威定義，視為絕對真理
-- - Rule B (ai_extracted_industries): AI 從年報預測的行業分類
-- - is_industry_confirmed: 標識是否已有權威定義
--
-- 【關聯 Relationships】
-- - 一間公司可擁有多份文檔 (documents.owner_company_id)
-- - 一間公司可在多份文檔中被提及 (document_companies.company_id)
-- - 一間公司有多條財務指標記錄 (financial_metrics.company_id)
-- - 一間公司有多條市場數據記錄 (market_data.company_id)
-- - 一間公司有多個關鍵人員 (key_personnel.company_id)
-- - 一間公司有多條股東結構記錄 (shareholding_structure.company_id)
--
-- 【關鍵欄位 Key Fields】
-- - stock_code: 股票代碼，唯一識別碼
-- - confirmed_industry: Rule A 行業分類（權威來源）
-- - ai_extracted_industries: Rule B 行業分類（AI 預測，JSONB 格式）
-- - extra_data: 彈性擴展欄位，支援 JSONB 動態屬性
-- ============================================================
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    name_en VARCHAR(255),
    name_zh VARCHAR(255),
    stock_code VARCHAR(50) UNIQUE,
    
    -- 【行業雙軌制欄位 Industry Dual-Track Fields】
    is_industry_confirmed BOOLEAN DEFAULT FALSE, -- 是否已有權威定義
    confirmed_industry VARCHAR(100), -- Rule A: 來自 Index Report 的權威行業分類
    ai_extracted_industries JSONB, -- Rule B: AI 預測的行業分類列表
    
    sector VARCHAR(100),
    
    -- 【向後兼容欄位 Backward Compatibility Fields】
    industry VARCHAR(100), -- 兼容舊版 (已廢棄，建議使用 confirmed_industry 或 ai_extracted_industries)
    
    -- 【動態擴展欄位 Dynamic Fields】
    extra_data JSONB DEFAULT '{}', -- 🌟 v2.3: 通用動態屬性欄位
    
    -- 【時間戳】
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_companies_stock_code ON companies(stock_code);
CREATE INDEX IF NOT EXISTS idx_companies_name_en ON companies(name_en);
CREATE INDEX IF NOT EXISTS idx_companies_name_zh ON companies(name_zh);
CREATE INDEX IF NOT EXISTS idx_companies_confirmed_industry ON companies(confirmed_industry);
CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector);
-- JSONB 索引
CREATE INDEX IF NOT EXISTS idx_companies_extra_data ON companies USING GIN(extra_data);
CREATE INDEX IF NOT EXISTS idx_companies_ai_industries ON companies USING GIN(ai_extracted_industries);

-- ============================================================
-- 【表 2: documents 文檔主檔】
-- 【功能 Purpose】
-- 儲存文檔基本資訊和處理狀態
--
-- 【關聯 Relationships】
-- - 屬於一個公司 (documents.owner_company_id)
-- - 包含多個頁面 (document_pages.document_id)
-- - 包含多個切片 (document_chunks.document_id)
-- - 包含多個表格 (document_tables.document_id)
-- - 在 document_companies 中被多個公司提及
-- - 在 review_queue 中有待審核記錄
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(100) UNIQUE, -- 全域唯一 ID (UUID 或自定義格式)
    
    -- 【基本資訊】
    filename VARCHAR(500),
    file_path VARCHAR(1000),
    file_hash VARCHAR(128), -- 文件 SHA256 哈希
    file_size_bytes BIGINT, -- 文件大小（位元組）
    report_type VARCHAR(50), -- annual_report | index_report
    
    -- 【公司關聯】
    owner_company_id INTEGER REFERENCES companies(id),
    
    -- 【時間維度】
    year INTEGER,
    fiscal_period VARCHAR(20), -- e.g., "FY2023", "H1-2023"
    
    -- 【處理狀態】
    processing_status VARCHAR(50) DEFAULT 'pending', -- pending | processing | completed | failed
    processing_completed_at TIMESTAMP, -- 處理完成時間
    processing_error TEXT, -- 處理錯誤信息
    
    -- 【統計欄位】
    total_chunks INTEGER DEFAULT 0, -- 文本塊數量
    total_artifacts INTEGER DEFAULT 0, -- 圖表/表格數量
    
    -- 【動態屬性】
    dynamic_attributes JSONB DEFAULT '{}', -- 🌟 v2.3: 彈性擴展欄位
    
    -- 【時間戳】
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_owner_company ON documents(owner_company_id);
CREATE INDEX IF NOT EXISTS idx_documents_year ON documents(year);
CREATE INDEX IF NOT EXISTS idx_documents_report_type ON documents(report_type);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_documents_dynamic_attrs ON documents USING GIN(dynamic_attributes);

-- ============================================================
-- 【表 3: document_companies 文檔-公司關聯表】
-- 【功能 Purpose】
-- 記錄文檔中提及的公司，以及 AI 提取的行業分類
--
-- 【用途 Use Cases】
-- - 追蹤哪些公司在哪些文檔中被提及
-- - 存儲 AI 預測的行業分類
-- - 支持跨文檔的公司行業分析
-- ============================================================
CREATE TABLE IF NOT EXISTS document_companies (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id),
    
    -- 【提及信息】
    is_owner BOOLEAN DEFAULT FALSE, -- 是否是文檔所屬公司
    mention_context TEXT, -- 提及上下文（如段落）
    page_references TEXT, -- 頁碼引用
    relation_type VARCHAR(50) DEFAULT 'mentioned', -- 關聯類型 (mentioned|subsidiary|competitor|owner)
    extraction_source VARCHAR(50) DEFAULT 'ai_predict', -- 提取來源 (ai_predict|confirmed|manual)
    
    -- 【AI 提取的行業分類】
    extracted_industries JSONB, -- AI 預測的行業分類列表
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(document_id, company_id)
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_document_companies_doc ON document_companies(document_id);
CREATE INDEX IF NOT EXISTS idx_document_companies_company ON document_companies(company_id);
CREATE INDEX IF NOT EXISTS idx_document_companies_industries ON document_companies USING GIN(extracted_industries);

-- ============================================================
-- 【表 4: document_pages 文檔頁面】
-- 【功能 Purpose】
-- 存儲文檔每頁的內容，支持多模態（文字+圖片+表格）
-- ============================================================
CREATE TABLE IF NOT EXISTS document_pages (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    page_num INTEGER NOT NULL,
    
    -- 【文字內容】
    content TEXT,
    
    -- 【多模態標誌】(用於快速判斷)
    has_images BOOLEAN DEFAULT FALSE,
    has_tables BOOLEAN DEFAULT FALSE,
    has_charts BOOLEAN DEFAULT FALSE,
    
    -- 【原始數據路徑】(可選)
    original_image_path VARCHAR(1000),
    
    -- 【元數據】
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(document_id, page_num)
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_document_pages_document ON document_pages(document_id);
CREATE INDEX IF NOT EXISTS idx_document_pages_page_num ON document_pages(document_id, page_num);

-- ============================================================
-- 【表 5: document_tables 文檔表格】
-- 【功能 Purpose】
-- 存儲從文檔中提取的表格數據（財務報表、統計數據等）
-- ============================================================
CREATE TABLE IF NOT EXISTS document_tables (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    page_num INTEGER,
    
    -- 【表格內容】
    table_type VARCHAR(100), -- income_statement, balance_sheet, cash_flow, statistics
    title VARCHAR(500),
    headers JSONB, -- 表頭
    rows JSONB, -- 數據行
    footer TEXT, -- 表尾注釋
    
    -- 【元數據】
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_document_tables_document ON document_tables(document_id);
CREATE INDEX IF NOT EXISTS idx_document_tables_type ON document_tables(table_type);

-- ============================================================
-- 【表 6: review_queue 人工審核隊列】
-- 【功能 Purpose】
-- 需要人工審核的記錄隊列
-- ============================================================
CREATE TABLE IF NOT EXISTS review_queue (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    review_type VARCHAR(50), -- industry_classification | financial_data | entity_extraction
    status VARCHAR(50) DEFAULT 'pending', -- pending | approved | rejected
    priority INTEGER DEFAULT 0,
    
    -- 【審核內容】
    original_data JSONB,
    suggested_data JSONB,
    reviewer_notes TEXT,
    
    -- 【時間戳】
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100)
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_review_queue_document ON review_queue(document_id);
CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_queue_type ON review_queue(review_type);

-- ============================================================
-- 【表 7: raw_artifacts 完美溯源表】
-- 【功能 Purpose】
-- 存儲所有 LLM 提取的原始結果，支持完美溯源
--
-- 【設計理念】
-- - 每一個提取結果都有 source_location
-- - 可追溯到具體文檔、頁碼、段落
-- - 支援版本控制和差異比較
-- ============================================================
CREATE TABLE IF NOT EXISTS raw_artifacts (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 【artifact 標識】
    artifact_id VARCHAR(100) UNIQUE, -- UUID
    artifact_type VARCHAR(50), -- table | image | text_chunk | chart | figure
    
    -- 【內容】
    content TEXT, -- 原始 Markdown 內容
    markdown_representation TEXT, -- 格式化輸出
    
    -- 【來源位置】(完美溯源的關鍵)
    source_page INTEGER,
    source_bbox JSONB, -- 邊界框
    source_paragraph TEXT, -- 原始段落
    
    -- 【LLM 分析】
    llm_summary TEXT, -- LLM 生成的摘要
    semantic_description TEXT, -- 語意描述（用於 Vector Search）
    
    -- 【元數據】
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_raw_artifacts_document ON raw_artifacts(document_id);
CREATE INDEX IF NOT EXISTS idx_raw_artifacts_artifact_id ON raw_artifacts(artifact_id);
CREATE INDEX IF NOT EXISTS idx_raw_artifacts_type ON raw_artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_raw_artifacts_page ON raw_artifacts(document_id, source_page);

-- ============================================================
-- 【表 8: artifact_relations 跨模態關聯表】
-- 【功能 Purpose】
-- 建立不同 artifacts 之間的關聯，解決圖文跨頁斷裂問題
--
-- 【使用場景】
-- - 表格 (table) ↔ 解釋文字 (text_chunk)
-- - 圖表 (chart) ↔ 數據引用 (data_reference)
-- - 圖片 (image) ↔ 標題說明 (caption)
-- ============================================================
CREATE TABLE IF NOT EXISTS artifact_relations (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 【關聯的兩個 artifact】
    source_artifact_id VARCHAR(100) REFERENCES raw_artifacts(artifact_id),
    target_artifact_id VARCHAR(100) REFERENCES raw_artifacts(artifact_id),
    
    -- 【關係類型】
    relation_type VARCHAR(50), -- explained_by | contains | references | same_topic
    confidence FLOAT DEFAULT 1.0,
    
    -- 【提取方式】
    extraction_method VARCHAR(50), -- regex | llm_matched | page_position
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_artifact_relations_document ON artifact_relations(document_id);
CREATE INDEX IF NOT EXISTS idx_artifact_relations_source ON artifact_relations(source_artifact_id);
CREATE INDEX IF NOT EXISTS idx_artifact_relations_target ON artifact_relations(target_artifact_id);

-- ============================================================
-- 【深度內容提取表 Deep Content Extraction Tables】
-- ============================================================

-- ============================================================
-- 【表 9: financial_metrics 財務指標 (EAV 模式)】
-- 【功能 Purpose】
-- 存儲結構化財務指標，支援多維度查詢
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_metrics (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id),
    
    -- 【時間維度】
    year INTEGER,
    fiscal_period VARCHAR(20),
    
    -- 【指標識別】
    metric_name VARCHAR(100), -- 英文指標名 (e.g., "Revenue")
    metric_name_zh VARCHAR(100), -- 中文指標名 (e.g., "營收")
    category VARCHAR(50), -- income_statement | balance_sheet | cash_flow | per_share | market_data
    
    -- 【數值】
    value NUMERIC(20, 4),
    standardized_value NUMERIC(20, 4), -- 統一貨幣單位後的值
    unit VARCHAR(20), -- million | billion | percent
    standardized_currency VARCHAR(10), -- 統一後的貨幣 (e.g., "USD")
    
    -- 【語意增強】
    segment VARCHAR(100), -- 業務分類 (e.g., "雲端服務")
    region VARCHAR(100), -- 地區分類 (e.g., "中國大陸")
    
    -- 【數據來源追蹤】
    source_artifact_id VARCHAR(100) REFERENCES raw_artifacts(artifact_id),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_financial_metrics_company_year ON financial_metrics(company_id, year);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_metric ON financial_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_category ON financial_metrics(category);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_segment ON financial_metrics(segment);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_region ON financial_metrics(region);

-- ============================================================
-- 【表 10: market_data 市場數據】
-- 【功能 Purpose】
-- 存儲市場數據（股價、市值、估值指標等）
-- ============================================================
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id),
    
    -- 【時間】
    year INTEGER,
    fiscal_period VARCHAR(20),
    
    -- 【市場指標】
    stock_price DECIMAL(20, 4),
    market_cap DECIMAL(20, 2),
    pe_ratio DECIMAL(10, 2),
    dividend_yield DECIMAL(10, 4),
    
    -- 【附加數據】
    additional_data JSONB DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_market_data_company_year ON market_data(company_id, year);

-- ============================================================
-- 【表 11: revenue_breakdown 收入分解】
-- 【功能 Purpose】
-- 存儲收入按業務分類或地區分類的分解數據
-- ============================================================
CREATE TABLE IF NOT EXISTS revenue_breakdown (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id),
    
    year INTEGER,
    fiscal_period VARCHAR(20),
    
    -- 【分類】
    segment_name VARCHAR(100), -- 業務分類名稱
    segment_type VARCHAR(50), -- business | region | product
    region VARCHAR(100), -- 如果是地區分類
    
    -- 【數值】
    revenue_amount DECIMAL(20, 2),
    revenue_percentage DECIMAL(10, 4), -- 佔比
    currency VARCHAR(10),
    
    -- 【對比數據】
    YoY_change DECIMAL(10, 4), -- 年同比變化
    previous_year_amount DECIMAL(20, 2), -- 去年金額
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_revenue_breakdown_company_year ON revenue_breakdown(company_id, year);
CREATE INDEX IF NOT EXISTS idx_revenue_breakdown_segment ON revenue_breakdown(segment_name);

-- ============================================================
-- 【表 12: key_personnel 關鍵人員】
-- 【功能 Purpose】
-- 存儲公司關鍵人員（董事、獨立董事、管理層）
-- ============================================================
CREATE TABLE IF NOT EXISTS key_personnel (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id),
    
    year INTEGER,
    
    -- 【人員信息】
    name_en VARCHAR(100),
    name_zh VARCHAR(100),
    
    -- 【職位信息】
    position_title_en VARCHAR(200),
    position_title_zh VARCHAR(200),
    role VARCHAR(50), -- executive | non_executive | independent
    board_role VARCHAR(100), -- Chairman | CEO | CFO | Director
    
    -- 【任職信息】
    appointment_date DATE,
    tenure_years INTEGER,
    
    -- 【薪酬】(可選)
    compensation DECIMAL(20, 2),
    compensation_currency VARCHAR(10),
    
    -- 【背景】(可選)
    background JSONB DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_key_personnel_company_year ON key_personnel(company_id, year);
CREATE INDEX IF NOT EXISTS idx_key_personnel_name ON key_personnel(name_en);
CREATE INDEX IF NOT EXISTS idx_key_personnel_role ON key_personnel(role);

-- ============================================================
-- 【表 13: shareholding_structure 股東結構】
-- 【功能 Purpose】
-- 存儲公司主要股東信息
-- ============================================================
CREATE TABLE IF NOT EXISTS shareholding_structure (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id),
    
    year INTEGER,
    
    -- 【股東信息】
    shareholder_name VARCHAR(200),
    shareholder_type VARCHAR(50), -- individual | institution | government | trust
    
    -- 【持股信息】
    shares_held DECIMAL(20, 2),
    share_percentage DECIMAL(10, 4),
    share_class VARCHAR(50), -- 股份類別
    
    -- 【變化】
    change_in_shares DECIMAL(20, 2), -- 持股變化
    change_percentage DECIMAL(10, 4),
    
    -- 【性質】
    is_ultimate_beneficial_owner BOOLEAN DEFAULT FALSE,
    is_controlling_shareholder BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_shareholding_company_year ON shareholding_structure(company_id, year);
CREATE INDEX IF NOT EXISTS idx_shareholding_shareholder ON shareholding_structure(shareholder_name);

-- ============================================================
-- 【表 14: entity_relations 實體關係】
-- 【功能 Purpose】
-- 存儲公司間的關係（子公司、聯營、競爭等）
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_relations (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 【關係主體】
    source_company_id INTEGER REFERENCES companies(id),
    target_company_id INTEGER REFERENCES companies(id),
    
    -- 【關係類型】
    relation_type VARCHAR(50), -- subsidiary | associate | joint_venture | competitor | partner
    description TEXT,
    
    -- 【 details】
    ownership_percentage DECIMAL(10, 4),
    details JSONB DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_entity_relations_source ON entity_relations(source_company_id);
CREATE INDEX IF NOT EXISTS idx_entity_relations_target ON entity_relations(target_company_id);
CREATE INDEX IF NOT EXISTS idx_entity_relations_type ON entity_relations(relation_type);

-- ============================================================
-- 【表 15: document_chunks 向量搜索切片】
-- 【功能 Purpose】
-- 存儲文檔切片，用於向量搜索
-- ============================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    page_num INTEGER,
    chunk_index INTEGER,
    
    -- 【內容】
    chunk_text TEXT,
    char_count INTEGER,
    paragraph_count INTEGER,
    
    -- 【向量】
    embedding vector(1536), -- OpenAI embedding dimension
    
    -- 【元數據】
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding ON document_chunks USING ivfflat(embedding vector_cosine_ops);

-- ============================================================
-- 【表 16: document_processing_history 處理歷史】
-- 【功能 Purpose】
-- 記錄文檔處理的每個階段
-- ============================================================
CREATE TABLE IF NOT EXISTS document_processing_history (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    
    stage VARCHAR(50), -- stage0 | stage1 | stage2 | ...
    status VARCHAR(50), -- started | completed | failed
    message TEXT,
    
    -- 【處理詳情】
    input_params JSONB,
    output_result JSONB,
    error_message TEXT,
    
    -- 【時間戳】
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_document_processing_history_document ON document_processing_history(document_id);
CREATE INDEX IF NOT EXISTS idx_document_processing_history_stage ON document_processing_history(stage);

-- ============================================================
-- 【表 17: keyword_registry 關鍵詞註冊表】
-- 【功能 Purpose】
-- 記錄 Agent 註冊的新關鍵詞，用於 Continuous Learning
-- ============================================================
CREATE TABLE IF NOT EXISTS keyword_registry (
    id SERIAL PRIMARY KEY,
    keyword VARCHAR(200) UNIQUE,
    keyword_zh VARCHAR(200),
    metric_type VARCHAR(100), -- revenue | profit | ratio | etc
    data_type VARCHAR(50), -- numeric | percentage | text
    examples JSONB, -- 示例值
    usage_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_keyword_registry_keyword ON keyword_registry(keyword);
CREATE INDEX IF NOT EXISTS idx_keyword_registry_metric_type ON keyword_registry(metric_type);

-- ============================================================
-- 【視圖 Views】
-- ============================================================

-- ============================================================
-- 【視圖: document_summary 文檔摘要視圖】
-- ============================================================
CREATE OR REPLACE VIEW document_summary AS
SELECT 
    d.id,
    d.doc_id,
    d.filename,
    d.report_type,
    d.year,
    d.processing_status,
    d.uploaded_at,
    -- 從 JSONB 中提取舊有的特徵
    d.dynamic_attributes->>'index_theme' AS index_theme,
    -- 獲取這份文件的母公司名稱
    c_owner.name_en AS owner_company_name,
    -- 獲取這份文件提及的所有公司數量
    COUNT(dc.id) AS mentioned_companies_count
FROM documents d
LEFT JOIN companies c_owner ON d.owner_company_id = c_owner.id
LEFT JOIN document_companies dc ON d.id = dc.document_id
GROUP BY d.id, c_owner.name_en;

-- ============================================================
-- 【視圖: v_companies_summary - DirectSQL 專用公司視圖】
-- ============================================================
CREATE OR REPLACE VIEW v_companies_summary AS
SELECT 
    id,
    name_en,
    name_zh,
    stock_code,
    sector,
    is_industry_confirmed,
    COALESCE(
        confirmed_industry, 
        (ai_extracted_industries->>0)
    ) AS primary_industry,
    extra_data,
    created_at
FROM companies;

-- ============================================================
-- 【視圖: v_financial_metrics_summary - 財務指標摘要】
-- ============================================================
CREATE OR REPLACE VIEW v_financial_metrics_summary AS
SELECT 
    fm.id,
    fm.company_id,
    c.name_en AS company_name,
    fm.year,
    fm.fiscal_period,
    fm.metric_name,
    fm.metric_name_zh,
    fm.value,
    fm.unit,
    fm.standardized_value,
    fm.standardized_currency,
    fm.category
FROM financial_metrics fm
LEFT JOIN companies c ON fm.company_id = c.id;

-- ============================================================
-- 【視圖: v_revenue_breakdown_summary - 收入分解摘要】
-- ============================================================
CREATE OR REPLACE VIEW v_revenue_breakdown_summary AS
SELECT 
    rb.id,
    rb.company_id,
    c.name_en AS company_name,
    rb.year,
    rb.segment_name,
    rb.segment_type,
    rb.revenue_percentage,
    rb.revenue_amount,
    rb.currency
FROM revenue_breakdown rb
LEFT JOIN companies c ON rb.company_id = c.id;

-- ============================================================
-- 【視圖: v_key_personnel_summary - 關鍵人員摘要】
-- ============================================================
CREATE OR REPLACE VIEW v_key_personnel_summary AS
SELECT 
    kp.id,
    kp.company_id,
    c.name_en AS company_name,
    kp.year,
    kp.name_en,
    kp.name_zh,
    kp.position_title_en,
    kp.role,
    kp.board_role
FROM key_personnel kp
LEFT JOIN companies c ON kp.company_id = c.id;

-- ============================================================
-- 【初始化完成通知】
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Nanobot Database Schema 初始化完成 (v2.4)';
    RAISE NOTICE '============================================================';
    RAISE NOTICE '';
    RAISE NOTICE '【核心表結構 Core Tables】';
    RAISE NOTICE '  - companies (公司主檔 - 行業雙軌制)';
    RAISE NOTICE '  - documents (文檔主檔)';
    RAISE NOTICE '  - document_companies (文檔-公司關聯表)';
    RAISE NOTICE '  - document_processing_history (文檔處理歷史)';
    RAISE NOTICE '  - document_pages (文檔頁面)';
    RAISE NOTICE '  - document_chunks (文檔切片)';
    RAISE NOTICE '  - document_tables (文檔表格)';
    RAISE NOTICE '  - review_queue (人工審核隊列)';
    RAISE NOTICE '';
    RAISE NOTICE '【深度內容提取表 Deep Content Extraction Tables】';
    RAISE NOTICE '  - financial_metrics (財務指標 EAV)';
    RAISE NOTICE '  - market_data (市場數據)';
    RAISE NOTICE '  - revenue_breakdown (收入分解)';
    RAISE NOTICE '  - key_personnel (關鍵人員)';
    RAISE NOTICE '  - shareholding_structure (股東結構)';
    RAISE NOTICE '  - raw_artifacts (原始提取結果 - 完美溯源)';
    RAISE NOTICE '  - entity_relations (實體關係 - Graph)';
    RAISE NOTICE '  - artifact_relations (跨模態關聯)';
    RAISE NOTICE '  - document_chunks (向量切片)';
    RAISE NOTICE '  - keyword_registry (關鍵詞註冊)';
    RAISE NOTICE '';
    RAISE NOTICE '【擴展 Extensions】';
    RAISE NOTICE '  - Apache AGE (圖譜查詢) - ownership_graph';
    RAISE NOTICE '  - pgvector (向量搜索)';
    RAISE NOTICE '  - pg_trgm (模糊搜索)';
    RAISE NOTICE '';
    RAISE NOTICE '【視圖 Views】';
    RAISE NOTICE '  - document_summary (文檔摘要)';
    RAISE NOTICE '  - v_companies_summary (公司摘要)';
    RAISE NOTICE '  - v_financial_metrics_summary (財務指標)';
    RAISE NOTICE '  - v_revenue_breakdown_summary (收入分解)';
    RAISE NOTICE '  - v_key_personnel_summary (關鍵人員)';
    RAISE NOTICE '';
    RAISE NOTICE '【License】';
    RAISE NOTICE '  🌟 完全商用友好：Apache 2.0 + PostgreSQL License';
    RAISE NOTICE '  🌟 無 GPL 傳染風險';
    RAISE NOTICE '============================================================';
END $$;
