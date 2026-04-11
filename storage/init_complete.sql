-- ============================================================
-- Nanobot Database Schema - Complete Initialization
-- ============================================================
-- 
-- 此腳本包含完整的資料庫結構定義，支援：
-- 1. 兩階段攝入流程 (Phase 1: Agent, Phase 2: OpenDataLoader)
-- 2. 規則 A/B 行業分配
-- 3. JSONB 動態屬性
-- 4. 文檔處理歷史追蹤
-- ============================================================

-- 啟用必要的擴展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- 用於模糊搜索
CREATE EXTENSION IF NOT EXISTS vector;     -- 用於向量嵌入 (pgvector)

-- ============================================================
-- 核心表結構
-- ============================================================

-- ============================================================
-- 1. 公司主檔 (支援行業雙軌制 Dual-Track Industry)
-- ============================================================
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    name_en VARCHAR(255),
    name_zh VARCHAR(255),
    stock_code VARCHAR(50) UNIQUE,
    
    -- 🌟 核心修改：行業雙軌制
    is_industry_confirmed BOOLEAN DEFAULT FALSE, -- 是否已有權威定義？
    confirmed_industry VARCHAR(100), -- Rule A: 來自 Index Report 的絕對真理
    ai_extracted_industries JSONB, -- Rule B: 來自 AI 的預測
    
    sector VARCHAR(100),
    
    -- 保留舊版的基礎欄位 (Vanna 向後兼容需要)
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

-- 公司表索引
CREATE INDEX IF NOT EXISTS idx_companies_stock_code ON companies(stock_code);
CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector);
CREATE INDEX IF NOT EXISTS idx_companies_is_industry_confirmed ON companies(is_industry_confirmed);
CREATE INDEX IF NOT EXISTS idx_companies_confirmed_industry ON companies(confirmed_industry);
CREATE INDEX IF NOT EXISTS idx_companies_ai_industries ON companies USING GIN (ai_extracted_industries);

-- ============================================================
-- 2. 文檔主檔 (支援無母公司的 Index Report)
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(255) UNIQUE,  
    filename VARCHAR(500) NOT NULL,
    
    -- 🌟 核心修改：報告類型
    report_type VARCHAR(50) DEFAULT 'annual_report', -- 'annual_report' 或是 'index_report'
    
    -- 對於 Index Report (恆指報告)，這個欄位直接留空 (NULL)
    owner_company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    
    year INTEGER,
    
    -- 處理狀態（刪除了重疊的 status）
    processing_status VARCHAR(50) DEFAULT 'pending',
    
    -- JSONB 動態屬性（若需記錄行業主題，用 dynamic_attributes->>'theme'）
    dynamic_attributes JSONB DEFAULT '{}'::jsonb,
    
    -- 文件元數據
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

-- 文檔表索引
CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);
CREATE INDEX IF NOT EXISTS idx_documents_owner_id ON documents(owner_company_id);
CREATE INDEX IF NOT EXISTS idx_documents_processing_status ON documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents(uploaded_at);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_documents_dynamic_attributes ON documents USING GIN (dynamic_attributes);
CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);


-- ============================================================
-- 3. PDF 與 提及公司的橋樑表 (紀錄資料來源)
-- ============================================================
CREATE TABLE IF NOT EXISTS document_companies (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    
    -- 標明這間公司在 PDF 裡的角色
    -- 例如: 'owner_subsidiary', 'competitor', 或 'index_constituent' (指數成分股)
    relation_type VARCHAR(50) DEFAULT 'mentioned', 
    
    -- 🌟 核心修改：這份文件賦予這間公司的行業屬性
    extracted_industries JSONB,      
    
    -- 標示這個提取結果的來源級別
    -- 'index_rule' (恆指權威級別) 或 'ai_predict' (AI 預測級別)
    extraction_source VARCHAR(50) DEFAULT 'ai_predict',  
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, company_id)
);

-- 橋樑表索引
CREATE INDEX IF NOT EXISTS idx_dc_document_id ON document_companies(document_id);
CREATE INDEX IF NOT EXISTS idx_dc_company_id ON document_companies(company_id);
CREATE INDEX IF NOT EXISTS idx_dc_relation_type ON document_companies(relation_type);
CREATE INDEX IF NOT EXISTS idx_dc_extraction_source ON document_companies(extraction_source);
CREATE INDEX IF NOT EXISTS idx_dc_extracted_industries ON document_companies USING GIN (extracted_industries);

-- ============================================================
-- 瘦身後的 document_processing_history
-- ============================================================
CREATE TABLE IF NOT EXISTS document_processing_history (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    stage VARCHAR(100),               -- 🗑️ 刪除了重複的 action
    status VARCHAR(50) NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    error_message TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 處理歷史索引
CREATE INDEX IF NOT EXISTS idx_dph_document_id ON document_processing_history(document_id);
CREATE INDEX IF NOT EXISTS idx_dph_stage ON document_processing_history(stage);
CREATE INDEX IF NOT EXISTS idx_dph_status ON document_processing_history(status);
CREATE INDEX IF NOT EXISTS idx_dph_created_at ON document_processing_history(created_at);


-- ============================================================
-- document_pages 表 - Zone 2 Fallback (PDF 頁面 Markdown)
-- ============================================================
CREATE TABLE IF NOT EXISTS document_pages (
    -- 主鍵
    id SERIAL PRIMARY KEY,
    
    -- 關聯（刪除了多餘的 company_id，透過 JOIN documents 即可找到）
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 頁面信息
    page_num INTEGER NOT NULL,
    markdown_content TEXT NOT NULL,  -- PDF 頁面轉 Markdown (Zone 2 Fallback)
    
    -- OCR/解析元數據
    ocr_confidence FLOAT DEFAULT 0.0,
    has_tables BOOLEAN DEFAULT FALSE,
    has_images BOOLEAN DEFAULT FALSE,
    
    -- 向量嵌入（可选）
    embedding_vector VECTOR(1536),  -- OpenAI embedding 維度
    
    -- 元數據
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- 審計字段
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 約束
    CONSTRAINT unique_page UNIQUE (document_id, page_num)
);

-- 頁面表索引
CREATE INDEX IF NOT EXISTS idx_document_pages_document_id ON document_pages(document_id);
CREATE INDEX IF NOT EXISTS idx_document_pages_page_num ON document_pages(page_num);
CREATE INDEX IF NOT EXISTS idx_document_pages_has_tables ON document_pages(has_tables);
CREATE INDEX IF NOT EXISTS idx_document_pages_has_images ON document_pages(has_images);
CREATE INDEX IF NOT EXISTS idx_document_pages_content_search ON document_pages USING GIN (to_tsvector('english', markdown_content));


-- ============================================================
-- document_chunks 表 - 文檔切片 (Zone 2)
-- ============================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    -- 主鍵
    id SERIAL PRIMARY KEY,
    
    -- 關聯
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 切片信息
    chunk_index INTEGER NOT NULL,
    chunk_type VARCHAR(50) DEFAULT 'text',  -- text, table, image
    content TEXT NOT NULL,
    
    -- 位置信息
    page_number INTEGER,
    bounding_box JSONB,           -- {x, y, width, height}
    
    -- 向量嵌入
    embedding_vector VECTOR(1536),  -- OpenAI embedding 維度
    
    -- 元數據
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- 審計字段
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 切片表索引
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type ON document_chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_page_number ON document_chunks(page_number);


-- ============================================================
-- document_tables 表 - 提取的表格 (Zone 2)
-- ============================================================
CREATE TABLE IF NOT EXISTS document_tables (
    -- 主鍵
    id SERIAL PRIMARY KEY,
    
    -- 關聯
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL,
    
    -- 表格信息
    table_index INTEGER NOT NULL,
    table_type VARCHAR(100),        -- balance_sheet, income_statement, cash_flow, etc.
    title TEXT,
    
    -- 表格數據
    headers JSONB,                  -- ["Column1", "Column2", ...]
    rows JSONB NOT NULL,             -- [[row1], [row2], ...]
    
    -- 位置信息
    page_number INTEGER,
    bounding_box JSONB,
    
    -- 元數據
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- 審計字段
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 表格表索引
CREATE INDEX IF NOT EXISTS idx_tables_document_id ON document_tables(document_id);
CREATE INDEX IF NOT EXISTS idx_tables_table_type ON document_tables(table_type);
CREATE INDEX IF NOT EXISTS idx_tables_page_number ON document_tables(page_number);


-- ============================================================
-- review_queue 表 - 人工審核隊列
-- ============================================================
CREATE TABLE IF NOT EXISTS review_queue (
    -- 主鍵
    id SERIAL PRIMARY KEY,
    
    -- 關聯
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES document_companies(id) ON DELETE CASCADE,
    
    -- 審核信息
    review_type VARCHAR(100) NOT NULL,  -- industry_extraction, company_name, etc.
    priority INTEGER DEFAULT 5,          -- 1-10, 1 最高
    status VARCHAR(50) DEFAULT 'pending', -- pending, in_review, approved, rejected
    
    -- 問題描述
    issue_description TEXT,
    ai_suggestion TEXT,
    human_decision TEXT,
    
    -- 審核人員
    reviewer_id VARCHAR(100),
    reviewed_at TIMESTAMP,
    
    -- 審計字段
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 約束
    CONSTRAINT valid_review_status CHECK (status IN ('pending', 'in_review', 'approved', 'rejected', 'escalated'))
);

-- 審核隊列索引
CREATE INDEX IF NOT EXISTS idx_review_document_id ON review_queue(document_id);
CREATE INDEX IF NOT EXISTS idx_review_company_id ON review_queue(company_id);
CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_priority ON review_queue(priority);


-- ============================================================
-- Vanna 訓練數據表
-- ============================================================
CREATE TABLE IF NOT EXISTS vanna_training_data (
    -- 主鍵
    id SERIAL PRIMARY KEY,
    
    -- 訓練數據
    question TEXT NOT NULL,
    sql_query TEXT NOT NULL,
    
    -- 元數據
    table_name VARCHAR(255),
    documentation TEXT,
    
    -- 質量評分
    quality_score DECIMAL(3, 2),   -- 0.00 - 1.00
    is_verified BOOLEAN DEFAULT FALSE,
    
    -- 審計字段
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Vanna 訓練數據索引
CREATE INDEX IF NOT EXISTS idx_vanna_table_name ON vanna_training_data(table_name);
CREATE INDEX IF NOT EXISTS idx_vanna_is_verified ON vanna_training_data(is_verified);


-- ============================================================
-- 9. 财务指标表 (EAV 模式 - Entity-Attribute-Value)
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_metrics (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    fiscal_period VARCHAR(20) DEFAULT 'FY',  -- FY, H1, Q1, Q2, Q3, Q4
    
    -- 🌟 EAV 核心字段
    metric_name VARCHAR(100) NOT NULL,       -- 标准英文名 (Taxonomy)
    metric_name_zh VARCHAR(100),             -- 标准中文名
    original_metric_name VARCHAR(200),       -- 原始名称 (Traceability)
    
    -- 数值处理
    value NUMERIC(20, 2),                    -- 原始值
    unit VARCHAR(50),                        -- 原始单位
    standardized_value NUMERIC(20, 2),       -- 标准化值 (HKD)
    standardized_currency VARCHAR(10) DEFAULT 'HKD',
    
    -- 来源
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    source_page INTEGER,
    source_table_id VARCHAR(100),
    
    -- 元数据
    extraction_confidence FLOAT DEFAULT 0.8,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 约束
    CONSTRAINT unique_metric UNIQUE (company_id, year, fiscal_period, metric_name)
);

-- 财务指标表索引
CREATE INDEX IF NOT EXISTS idx_financial_metrics_company_id ON financial_metrics(company_id);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_year ON financial_metrics(year);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_metric_name ON financial_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_standardized_value ON financial_metrics(standardized_value);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_fiscal_period ON financial_metrics(fiscal_period);


-- ============================================================
-- 10. 市場數據表 (Market Data)
-- ============================================================
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    
    -- 日期與期間
    data_date DATE NOT NULL,
    period_type VARCHAR(20) DEFAULT 'daily',  -- daily, weekly, monthly
    
    -- 股價數據
    open_price NUMERIC(15, 4),
    high_price NUMERIC(15, 4),
    low_price NUMERIC(15, 4),
    close_price NUMERIC(15, 4),
    adj_close_price NUMERIC(15, 4),
    
    -- 交易數據
    volume BIGINT,
    turnover NUMERIC(20, 2),
    
    -- 估值指標
    market_cap NUMERIC(20, 2),
    pe_ratio NUMERIC(10, 4),
    pb_ratio NUMERIC(10, 4),
    dividend_yield NUMERIC(6, 4),
    
    -- 元數據
    source VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_market_data UNIQUE (company_id, data_date, period_type)
);

-- 市場數據索引
CREATE INDEX IF NOT EXISTS idx_market_data_company_id ON market_data(company_id);
CREATE INDEX IF NOT EXISTS idx_market_data_date ON market_data(data_date);
CREATE INDEX IF NOT EXISTS idx_market_data_period ON market_data(period_type);


-- ============================================================
-- 11. 收入分解表 (Revenue Breakdown)
-- ============================================================
CREATE TABLE IF NOT EXISTS revenue_breakdown (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    
    -- 收入類別
    segment_name VARCHAR(255) NOT NULL,
    segment_type VARCHAR(50) DEFAULT 'business',  -- business, geography, product
    
    -- 金額
    revenue_amount NUMERIC(20, 2),
    revenue_percentage NUMERIC(5, 2),
    currency VARCHAR(10) DEFAULT 'HKD',
    
    -- 元數據
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_revenue_segment UNIQUE (company_id, year, segment_name, segment_type)
);

-- 收入分解索引
CREATE INDEX IF NOT EXISTS idx_revenue_company_id ON revenue_breakdown(company_id);
CREATE INDEX IF NOT EXISTS idx_revenue_year ON revenue_breakdown(year);
CREATE INDEX IF NOT EXISTS idx_revenue_segment_type ON revenue_breakdown(segment_type);


-- ============================================================
-- 12. 關鍵人員表 (Key Personnel)
-- ============================================================
CREATE TABLE IF NOT EXISTS key_personnel (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,  -- 溯源：邊份 PDF 抽到嘅
    
    -- 年份 (對應 Qwen LLM 抽取出嚟嘅人物關係時間點)
    year INTEGER,
    
    -- 個人信息
    name_en VARCHAR(255),
    name_zh VARCHAR(255),
    
    -- 職位信息
    position_title_en VARCHAR(255),
    position_title_zh VARCHAR(255),
    position_type VARCHAR(50),  -- director, executive, secretary, etc.
    role VARCHAR(255),          -- 簡化版角色 (例如：Chairman, CEO)
    
    -- 董事會相關
    board_role VARCHAR(100),     -- chairman, ceo, cfo, independent_director, etc.
    committee_membership JSONB,  -- ['audit', 'remuneration', 'nomination']
    
    -- 任职信息
    appointment_date DATE,
    resignation_date DATE,
    is_current BOOLEAN DEFAULT TRUE,
    
    -- 元數據
    biography TEXT,
    source_page INTEGER,         -- 記錄 LiteParse 搵到嘅原圖/表格位置
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 關鍵人員索引
CREATE INDEX IF NOT EXISTS idx_personnel_company_id ON key_personnel(company_id);
CREATE INDEX IF NOT EXISTS idx_personnel_document_id ON key_personnel(document_id);
CREATE INDEX IF NOT EXISTS idx_personnel_year ON key_personnel(year);
CREATE INDEX IF NOT EXISTS idx_personnel_position_type ON key_personnel(position_type);
CREATE INDEX IF NOT EXISTS idx_personnel_board_role ON key_personnel(board_role);
CREATE INDEX IF NOT EXISTS idx_personnel_role ON key_personnel(role);
CREATE INDEX IF NOT EXISTS idx_personnel_is_current ON key_personnel(is_current);


-- ============================================================
-- 13. 股東結構表 (Shareholding Structure)
-- ============================================================
-- ============================================================
-- 13. 股東結構表 (Shareholding Structure)
-- ============================================================
CREATE TABLE IF NOT EXISTS shareholding_structure (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    
    -- 股東信息
    shareholder_name VARCHAR(255),
    shareholder_type VARCHAR(50),  -- individual, corporation, government, etc.
    
    -- 🌟 新增：信託信息 (Trust Info)
    trust_name VARCHAR(255),       -- 信託名稱 (例如: The Li Ka-Shing Unity Trust)
    trustee_name VARCHAR(255),     -- 受託人名稱 (例如: Li Ka-Shing Unity Trustee Company Limited)
    
    -- 持股信息
    shares_held NUMERIC(20, 2),
    percentage NUMERIC(6, 4),
    
    -- 股東類型
    is_controlling BOOLEAN DEFAULT FALSE,
    is_institutional BOOLEAN DEFAULT FALSE,
    
    -- 元數據
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_shareholder UNIQUE (company_id, year, shareholder_name)
);

-- 股東結構索引
CREATE INDEX IF NOT EXISTS idx_shareholding_company_id ON shareholding_structure(company_id);
CREATE INDEX IF NOT EXISTS idx_shareholding_year ON shareholding_structure(year);
CREATE INDEX IF NOT EXISTS idx_shareholding_type ON shareholding_structure(shareholder_type);
CREATE INDEX IF NOT EXISTS idx_shareholding_trust_name ON shareholding_structure(trust_name);
CREATE INDEX IF NOT EXISTS idx_shareholding_trustee_name ON shareholding_structure(trustee_name);


-- ============================================================
-- 14. 原始提取結果表 (Raw Artifacts - LiteParse 對應)
-- ============================================================
-- 這個表用於存儲 LiteParse 截出的圖片、Markdown 和空間排版信息
-- 支援「完美溯源」：如果 Qwen-VL 讀錯數，可以用 artifact_id 搵返原圖對質
-- ============================================================
CREATE TABLE IF NOT EXISTS raw_artifacts (
    id SERIAL PRIMARY KEY,
    artifact_id VARCHAR(255) UNIQUE,  
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 類型分類
    artifact_type VARCHAR(50),        -- 'text_chunk', 'table', 'image_screenshot', 'chart'
    
    -- LiteParse 嘔出的 Markdown 內容
    content TEXT,
    
    -- LiteParse Cap 圖的儲存路徑
    file_path VARCHAR(500),
    
    -- 空間排版位置 (Spatial Layout)
    page_num INTEGER,
    bbox JSONB,                       -- {x, y, width, height}
    
    -- Qwen-VL 解析結果 (可選)
    parsed_data JSONB,                -- Qwen-VL 解析出的結構化數據
    parsing_status VARCHAR(50) DEFAULT 'pending',  -- pending, parsed, failed
    parsing_error TEXT,
    
    -- 元數據
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 原始提取結果索引
CREATE INDEX IF NOT EXISTS idx_ra_document_id ON raw_artifacts(document_id);
CREATE INDEX IF NOT EXISTS idx_ra_artifact_id ON raw_artifacts(artifact_id);
CREATE INDEX IF NOT EXISTS idx_ra_artifact_type ON raw_artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_ra_page_num ON raw_artifacts(page_num);
CREATE INDEX IF NOT EXISTS idx_ra_parsing_status ON raw_artifacts(parsing_status);
CREATE INDEX IF NOT EXISTS idx_ra_parsed_data ON raw_artifacts USING GIN (parsed_data);


-- ============================================================
-- 15. 實體關係抽取表 (Entity Relations - Graph Extraction)
-- ============================================================
-- 用於存儲 LLM 抽取出的實體關係 (人物、事件、公司之間的關係)
-- 支援 Graph-based 查詢
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_relations (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 源實體
    source_entity_type VARCHAR(50),   -- 'person', 'company', 'event', 'location'
    source_entity_id INTEGER,         -- 可關聯到 key_personnel 或 companies
    source_entity_name VARCHAR(255),
    
    -- 目標實體
    target_entity_type VARCHAR(50),
    target_entity_id INTEGER,
    target_entity_name VARCHAR(255),
    
    -- 關係類型
    relation_type VARCHAR(100),       -- 'appointed', 'resigned', 'acquired', 'subsidiary_of'
    relation_strength FLOAT DEFAULT 1.0,  -- 關係強度/置信度
    
    -- 時間信息 (事件發生先後)
    event_date DATE,
    event_year INTEGER,
    
    -- 溯源
    source_page INTEGER,
    source_artifact_id VARCHAR(255) REFERENCES raw_artifacts(artifact_id) ON DELETE SET NULL,
    
    -- 元數據
    metadata JSONB DEFAULT '{}'::jsonb,
    extraction_confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 實體關係索引
CREATE INDEX IF NOT EXISTS idx_er_document_id ON entity_relations(document_id);
CREATE INDEX IF NOT EXISTS idx_er_source_type ON entity_relations(source_entity_type);
CREATE INDEX IF NOT EXISTS idx_er_target_type ON entity_relations(target_entity_type);
CREATE INDEX IF NOT EXISTS idx_er_relation_type ON entity_relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_er_event_date ON entity_relations(event_date);
CREATE INDEX IF NOT EXISTS idx_er_event_year ON entity_relations(event_year);


-- ============================================================
-- 實用函數
-- ============================================================

-- 更新 updated_at 觸發器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 創建觸發器（補齊所有有 updated_at 的表）
DROP TRIGGER IF EXISTS update_companies_updated_at ON companies;
CREATE TRIGGER update_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;
CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_review_queue_updated_at ON review_queue;
CREATE TRIGGER update_review_queue_updated_at
    BEFORE UPDATE ON review_queue
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_vanna_training_data_updated_at ON vanna_training_data;
CREATE TRIGGER update_vanna_training_data_updated_at
    BEFORE UPDATE ON vanna_training_data
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_key_personnel_updated_at ON key_personnel;
CREATE TRIGGER update_key_personnel_updated_at
    BEFORE UPDATE ON key_personnel
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================================

-- ============================================================
-- 重新建立正確的索引 (Indexes)
-- ============================================================
-- 文檔表索引
CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);
CREATE INDEX IF NOT EXISTS idx_documents_owner_id ON documents(owner_company_id);
CREATE INDEX IF NOT EXISTS idx_documents_dynamic_attributes ON documents USING GIN (dynamic_attributes);

-- 橋樑表索引
CREATE INDEX IF NOT EXISTS idx_dc_document_id ON document_companies(document_id);
CREATE INDEX IF NOT EXISTS idx_dc_company_id ON document_companies(company_id);
CREATE INDEX IF NOT EXISTS idx_dc_relation_type ON document_companies(relation_type);
CREATE INDEX IF NOT EXISTS idx_dc_extracted_industries ON document_companies USING GIN (extracted_industries);

-- ============================================================
-- 給前端與後端看的視圖 (Views) - 已適配 JSONB 與新架構
-- ============================================================
CREATE OR REPLACE VIEW document_summary AS
SELECT 
    d.id,
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
-- 🎯 給 Vanna 專用的展平視圖 (Flattened Views for Text-to-SQL)
-- ============================================================

-- 1. Vanna 專用文檔視圖
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

-- 2. Vanna 專用公司視圖 (🌟 這裡解決了你的雙軌制行業問題！)
CREATE OR REPLACE VIEW v_companies_for_vanna AS
SELECT 
    id,
    name_en,
    name_zh,
    stock_code,
    sector,
    is_industry_confirmed,
    -- 智能判定：如果有權威定義就用權威，沒有的話就拿 AI 預測的第一個行業
    COALESCE(
        confirmed_industry, 
        ai_extracted_industries->>0
    ) AS primary_industry,
    created_at
FROM companies;

-- ============================================================
-- 完成
-- ============================================================

-- 輸出初始化完成信息
DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Nanobot Database Schema 初始化完成 (v2.3)';
    RAISE NOTICE '============================================================';
    RAISE NOTICE '表結構:';
    RAISE NOTICE '  - companies (公司主表 - 雙軌制行業)';
    RAISE NOTICE '  - documents (文檔主表)';
    RAISE NOTICE '  - document_companies (關聯公司橋樑表)';
    RAISE NOTICE '  - document_processing_history (處理歷史)';
    RAISE NOTICE '  - document_chunks (切片)';
    RAISE NOTICE '  - document_tables (表格)';
    RAISE NOTICE '  - review_queue (審核隊列)';
    RAISE NOTICE '  - vanna_training_data (Vanna 訓練數據)';
    RAISE NOTICE '';
    RAISE NOTICE '深度內容抽取表 (LiteParse + Qwen-VL):';
    RAISE NOTICE '  - financial_metrics (財務指標 EAV)';
    RAISE NOTICE '  - market_data (市場數據)';
    RAISE NOTICE '  - revenue_breakdown (收入分解)';
    RAISE NOTICE '  - key_personnel (關鍵人員)';
    RAISE NOTICE '  - shareholding_structure (股東結構)';
    RAISE NOTICE '  - raw_artifacts (原始提取結果 - 完美溯源)';
    RAISE NOTICE '  - entity_relations (實體關係抽取 - Graph)';
    RAISE NOTICE '';
    RAISE NOTICE '視圖 (Vanna 專用):';
    RAISE NOTICE '  - document_summary';
    RAISE NOTICE '  - v_documents_for_vanna';
    RAISE NOTICE '  - v_companies_for_vanna (雙軌制行業解決方案)';
    RAISE NOTICE '';
    RAISE NOTICE '核心改進:';
    RAISE NOTICE '  ✅ 文檔瘦身完成 (移除冗餘欄位)';
    RAISE NOTICE '  ✅ JSONB 動態屬性支援';
    RAISE NOTICE '  ✅ Vanna 查詢優化視圖已建立';
    RAISE NOTICE '  ✅ 雙軌制行業邏輯已封裝在 View 中';
    RAISE NOTICE '  ✅ 舊版財務表已補回 (向後兼容)';
    RAISE NOTICE '  ✅ raw_artifacts 支援完美溯源';
    RAISE NOTICE '  ✅ entity_relations 支援 Graph Extraction';
    RAISE NOTICE '============================================================';
END $$;
