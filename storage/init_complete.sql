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
    dynamic_attributes JSONB DEFAULT '{}'::jsonb,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 文檔表索引
CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);
CREATE INDEX IF NOT EXISTS idx_documents_owner_id ON documents(owner_company_id);  -- ✅ 修正：owner_company_id
CREATE INDEX IF NOT EXISTS idx_documents_processing_status ON documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents(uploaded_at);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_documents_dynamic_attributes ON documents USING GIN (dynamic_attributes);
CREATE INDEX IF NOT EXISTS idx_documents_ai_industries ON documents USING GIN (ai_extracted_industries);


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

-- 公司表索引
CREATE INDEX IF NOT EXISTS idx_dc_document_id ON document_companies(document_id);
CREATE INDEX IF NOT EXISTS idx_dc_company_id ON document_companies(company_id);
CREATE INDEX IF NOT EXISTS idx_dc_relation_type ON document_companies(relation_type);
CREATE INDEX IF NOT EXISTS idx_dc_extracted_industries ON document_companies USING GIN (extracted_industries);

-- JSONB 索引
CREATE INDEX IF NOT EXISTS idx_dc_dynamic_attributes ON document_companies USING GIN (dynamic_attributes);

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
CREATE INDEX IF NOT EXISTS idx_dph_action ON document_processing_history(action);
CREATE INDEX IF NOT EXISTS idx_dph_status ON document_processing_history(status);
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
    RAISE NOTICE 'Nanobot Database Schema 初始化完成 (v2.1)';
    RAISE NOTICE '============================================================';
    RAISE NOTICE '表結構:';
    RAISE NOTICE '  - documents (文檔主表)';
    RAISE NOTICE '  - document_companies (關聯公司)';
    RAISE NOTICE '  - document_processing_history (處理歷史)';
    RAISE NOTICE '  - document_chunks (切片)';
    RAISE NOTICE '  - document_tables (表格)';
    RAISE NOTICE '  - review_queue (審核隊列)';
    RAISE NOTICE '  - companies (公司主表)';
    RAISE NOTICE '  - financial_metrics (財務指標 EAV)';
    RAISE NOTICE '  - market_data (市場數據)';
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
    RAISE NOTICE '============================================================';
END $$;
