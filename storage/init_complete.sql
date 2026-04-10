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

-- ============================================================
-- 核心表結構
-- ============================================================

-- ============================================================
-- documents 表 - 文檔主表
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    -- 主鍵
    id SERIAL PRIMARY KEY,
    
    -- 基本信息
    filename VARCHAR(500) NOT NULL,
    file_path VARCHAR(1000),
    file_size BIGINT,
    mime_type VARCHAR(100),
    
    -- 報告類型識別
    report_type VARCHAR(50) DEFAULT 'annual_report',  -- 'annual_report' 或 'index_report'
    is_index_report BOOLEAN DEFAULT FALSE,
    
    -- 公司信息
    parent_company VARCHAR(255),  -- 年報的母公司，指數報告為 NULL
    
    -- 指數報告專用字段
    index_theme VARCHAR(255),     -- 指數主題，如 'Hang Seng Biotech Index'
    confirmed_industry VARCHAR(100), -- 文檔級別確認的行業 (規則 A)
    
    -- AI 提取信息
    ai_extracted_industries JSONB,  -- AI 提取的行業列表
    confidence_score DECIMAL(5, 4),  -- 提取置信度
    
    -- JSONB 動態屬性
    dynamic_attributes JSONB DEFAULT '{}'::jsonb,
    
    -- 處理狀態
    processing_status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, completed, failed
    processing_error TEXT,
    last_processed_at TIMESTAMP,
    
    -- 審計字段
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 約束
    CONSTRAINT valid_report_type CHECK (report_type IN ('annual_report', 'index_report')),
    CONSTRAINT valid_processing_status CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed', 'review'))
);

-- 文檔表索引
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);
CREATE INDEX IF NOT EXISTS idx_documents_report_type ON documents(report_type);
CREATE INDEX IF NOT EXISTS idx_documents_is_index_report ON documents(is_index_report);
CREATE INDEX IF NOT EXISTS idx_documents_parent_company ON documents(parent_company);
CREATE INDEX IF NOT EXISTS idx_documents_index_theme ON documents(index_theme);
CREATE INDEX IF NOT EXISTS idx_documents_confirmed_industry ON documents(confirmed_industry);
CREATE INDEX IF NOT EXISTS idx_documents_processing_status ON documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);

-- JSONB 動態屬性索引 (GIN 索引用於高效查詢)
CREATE INDEX IF NOT EXISTS idx_documents_dynamic_attributes ON documents USING GIN (dynamic_attributes);
CREATE INDEX IF NOT EXISTS idx_documents_ai_industries ON documents USING GIN (ai_extracted_industries);


-- ============================================================
-- document_companies 表 - 文檔關聯公司
-- ============================================================
CREATE TABLE IF NOT EXISTS document_companies (
    -- 主鍵
    id SERIAL PRIMARY KEY,
    
    -- 關聯
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 公司信息
    company_name VARCHAR(255) NOT NULL,
    stock_code VARCHAR(50),       -- 如 '0001.HK', '0700.HK'
    isin_code VARCHAR(20),        -- ISIN 代碼
    
    -- 行業分配 (核心邏輯)
    assigned_industry VARCHAR(100),     -- 最終分配的行業 (規則 A 強制值或規則 B AI 值)
    ai_suggested_industries JSONB,      -- AI 提取的多個候選行業 (規則 B 使用)
    industry_source VARCHAR(50) DEFAULT 'ai_extracted',  -- 'confirmed' (規則 A) 或 'ai_extracted' (規則 B)
    industry_confidence DECIMAL(5, 4), -- 行業分配的置信度
    
    -- JSONB 動態屬性
    dynamic_attributes JSONB DEFAULT '{}'::jsonb,
    
    -- 審計字段
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 約束
    CONSTRAINT valid_industry_source CHECK (industry_source IN ('confirmed', 'ai_extracted', 'manual', 'pending'))
);

-- 公司表索引
CREATE INDEX IF NOT EXISTS idx_dc_document_id ON document_companies(document_id);
CREATE INDEX IF NOT EXISTS idx_dc_company_name ON document_companies(company_name);
CREATE INDEX IF NOT EXISTS idx_dc_stock_code ON document_companies(stock_code);
CREATE INDEX IF NOT EXISTS idx_dc_assigned_industry ON document_companies(assigned_industry);
CREATE INDEX IF NOT EXISTS idx_dc_industry_source ON document_companies(industry_source);

-- JSONB 索引
CREATE INDEX IF NOT EXISTS idx_dc_dynamic_attributes ON document_companies USING GIN (dynamic_attributes);
CREATE INDEX IF NOT EXISTS idx_dc_ai_suggested ON document_companies USING GIN (ai_suggested_industries);


-- ============================================================
-- document_processing_history 表 - 處理歷史
-- ============================================================
CREATE TABLE IF NOT EXISTS document_processing_history (
    -- 主鍵
    id SERIAL PRIMARY KEY,
    
    -- 關聯
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 處理信息
    stage VARCHAR(100) NOT NULL,        -- 處理階段
    status VARCHAR(50) NOT NULL,        -- 狀態
    details JSONB DEFAULT '{}'::jsonb,  -- 詳細信息
    error_message TEXT,                 -- 錯誤信息
    
    -- 審計字段
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 約束
    CONSTRAINT valid_history_status CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'skipped'))
);

-- 處理歷史索引
CREATE INDEX IF NOT EXISTS idx_dph_document_id ON document_processing_history(document_id);
CREATE INDEX IF NOT EXISTS idx_dph_stage ON document_processing_history(stage);
CREATE INDEX IF NOT EXISTS idx_dph_status ON document_processing_history(status);
CREATE INDEX IF NOT EXISTS idx_dph_created_at ON document_processing_history(created_at);


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

-- 創建觸發器
DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;
CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_dc_updated_at ON document_companies;
CREATE TRIGGER update_dc_updated_at
    BEFORE UPDATE ON document_companies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 視圖
-- ============================================================

-- 文檔摘要視圖
CREATE OR REPLACE VIEW document_summary AS
SELECT 
    d.id,
    d.filename,
    d.report_type,
    d.is_index_report,
    d.parent_company,
    d.index_theme,
    d.confirmed_industry,
    d.processing_status,
    d.created_at,
    COUNT(dc.id) AS companies_count,
    COALESCE(
        json_agg(
            json_build_object(
                'name', dc.company_name,
                'stock_code', dc.stock_code,
                'industry', dc.assigned_industry
            )
        ) FILTER (WHERE dc.id IS NOT NULL), 
        '[]'::json
    ) AS companies
FROM documents d
LEFT JOIN document_companies dc ON d.id = dc.document_id
GROUP BY d.id;

-- 指數報告視圖 (規則 A 專用)
CREATE OR REPLACE VIEW index_reports_view AS
SELECT 
    d.id,
    d.filename,
    d.index_theme,
    d.confirmed_industry,
    d.created_at,
    COUNT(dc.id) AS constituent_count
FROM documents d
LEFT JOIN document_companies dc ON d.id = dc.document_id
WHERE d.is_index_report = TRUE
GROUP BY d.id;

-- 待審核項目視圖
CREATE OR REPLACE VIEW pending_reviews AS
SELECT 
    rq.id,
    rq.review_type,
    rq.priority,
    rq.issue_description,
    rq.ai_suggestion,
    d.filename,
    dc.company_name,
    rq.created_at
FROM review_queue rq
LEFT JOIN documents d ON rq.document_id = d.id
LEFT JOIN document_companies dc ON rq.company_id = dc.id
WHERE rq.status = 'pending'
ORDER BY rq.priority ASC, rq.created_at ASC;


-- ============================================================
-- 初始數據
-- ============================================================

-- 插入 Vanna 訓練示例
INSERT INTO vanna_training_data (question, sql_query, table_name, documentation, quality_score, is_verified) VALUES
-- 基本查詢
('Show me all documents', 'SELECT * FROM documents ORDER BY created_at DESC;', 'documents', '列出所有文檔', 1.0, TRUE),
('Find documents by filename', 'SELECT * FROM documents WHERE filename ILIKE ''%{keyword}%'', 'documents', '按檔名搜索文檔', 1.0, TRUE),

-- 指數報告查詢
('Show all index reports', 'SELECT * FROM documents WHERE is_index_report = TRUE ORDER BY created_at DESC;', 'documents', '列出所有指數報告', 1.0, TRUE),
('Find documents by index theme', 'SELECT * FROM documents WHERE index_theme ILIKE ''%{theme}%'', 'documents', '按指數主題搜索', 1.0, TRUE),

-- 行業查詢
('Find companies in a specific industry', 'SELECT dc.*, d.filename FROM document_companies dc JOIN documents d ON dc.document_id = d.id WHERE dc.assigned_industry = ''{industry}'';', 'document_companies', '按行業查找公司', 1.0, TRUE),

-- JSONB 查詢
('Find documents by dynamic attribute', 'SELECT * FROM documents WHERE dynamic_attributes->>''{key}'' = ''{value}'';', 'documents', '按 JSONB 動態屬性搜索', 0.9, TRUE),
('Get all dynamic attribute keys', 'SELECT DISTINCT jsonb_object_keys(dynamic_attributes) AS key FROM documents WHERE dynamic_attributes IS NOT NULL;', 'documents', '獲取所有動態屬性鍵', 0.9, TRUE)
ON CONFLICT DO NOTHING;


-- ============================================================
-- 完成
-- ============================================================

-- 輸出初始化完成信息
DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Nanobot Database Schema 初始化完成';
    RAISE NOTICE '============================================================';
    RAISE NOTICE '表結構:';
    RAISE NOTICE '  - documents (文檔主表)';
    RAISE NOTICE '  - document_companies (關聯公司)';
    RAISE NOTICE '  - document_processing_history (處理歷史)';
    RAISE NOTICE '  - document_chunks (切片)';
    RAISE NOTICE '  - document_tables (表格)';
    RAISE NOTICE '  - review_queue (審核隊列)';
    RAISE NOTICE '  - vanna_training_data (Vanna 訓練)';
    RAISE NOTICE '';
    RAISE NOTICE '視圖:';
    RAISE NOTICE '  - document_summary';
    RAISE NOTICE '  - index_reports_view';
    RAISE NOTICE '  - pending_reviews';
    RAISE NOTICE '';
    RAISE NOTICE '規則 A/B 行業分配: ✅ 已支援';
    RAISE NOTICE 'JSONB 動態屬性: ✅ 已支援';
    RAISE NOTICE '============================================================';
END $$;