-- ============================================================
-- Agentic Dynamic Ingestion Database Schema
-- Version: 2.0 (支持 JSONB 動態屬性)
-- ============================================================

-- 擴展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- 用於模糊搜索

-- ============================================================
-- Document Table (文檔主表)
-- 核心設計：實體欄位 + JSONB 動態屬性
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- 基礎信息
    filename VARCHAR(500) NOT NULL,
    original_filename VARCHAR(500),
    file_path VARCHAR(1000),
    file_size BIGINT,
    mime_type VARCHAR(100),
    
    -- 公司信息 (可為 NULL - 如恒指報告)
    parent_company_id INTEGER REFERENCES companies(id),
    parent_company_name VARCHAR(255),  -- 快速查詢用
    
    -- 🌟 指數報告專用欄位
    index_theme VARCHAR(255),            -- 指數主題 (如 'Hang Seng Biotech Index')
    is_index_report BOOLEAN DEFAULT FALSE, -- 是否為指數報告
    
    -- 行業信息
    confirmed_industry VARCHAR(255),     -- 最終人工/權威確認的行業
    ai_extracted_industries JSONB,       -- AI 抽取的行業 (可能多個)
    
    -- 文檔元數據
    document_type VARCHAR(100),          -- 'annual_report', 'index_report', etc.
    fiscal_year INTEGER,
    fiscal_period VARCHAR(20),           -- 'FY', 'Q1', 'Q2', etc.
    reporting_currency VARCHAR(10),
    
    -- 🌟 核心設計：JSONB 動態屬性
    zone1_raw_data JSONB,                -- Zone 1: 原始提取數據
    dynamic_attributes JSONB,            -- 其他 AI 發現的動態屬性
    extraction_metadata JSONB,           -- 提取過程元數據
    
    -- 處理狀態
    processing_status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    processing_progress INTEGER DEFAULT 0,
    processing_error TEXT,
    
    -- 審計欄位
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    
    -- 索引優化
    CONSTRAINT valid_status CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed', 'reviewing'))
);

-- 索引
CREATE INDEX idx_documents_parent_company ON documents(parent_company_id);
CREATE INDEX idx_documents_fiscal_year ON documents(fiscal_year);
CREATE INDEX idx_documents_status ON documents(processing_status);
CREATE INDEX idx_documents_type ON documents(document_type);
CREATE INDEX idx_documents_zone1_raw_data ON documents USING GIN(zone1_raw_data);
CREATE INDEX idx_documents_dynamic_attributes ON documents USING GIN(dynamic_attributes);
CREATE INDEX idx_documents_ai_industries ON documents USING GIN(ai_extracted_industries);

-- ============================================================
-- Document Companies Table (文檔關聯公司表)
-- 處理 1 對多關係 (一份文檔可能包含多間公司)
-- ============================================================
CREATE TABLE IF NOT EXISTS document_companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id),
    
    -- 公司信息 (冗餘存儲，方便查詢)
    company_name VARCHAR(255) NOT NULL,
    company_name_zh VARCHAR(255),
    stock_code VARCHAR(20),
    
    -- 🌟 行業指派 (核心邏輯)
    assigned_industry VARCHAR(255),       -- 指派的行業 (來自報告定義或 AI 提取)
    ai_suggested_industries JSONB,        -- AI 建議的多個行業 (僅當報告無明確定義時)
    industry_source VARCHAR(50),          -- 'report_defined', 'ai_extracted', 'manual'
    
    -- 關係類型
    relation_type VARCHAR(50) NOT NULL,  -- 'parent', 'subsidiary', 'index_constituent', 'associate'
    is_primary BOOLEAN DEFAULT FALSE,     -- 是否為主要公司
    
    -- 頁面引用
    mentioned_pages INTEGER[],            -- 提到的頁碼
    mentioned_sections TEXT[],            -- 提到的章節
    
    -- 審計
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 唯一約束
    UNIQUE(document_id, company_id, relation_type)
);

-- 索引
CREATE INDEX idx_doc_companies_document ON document_companies(document_id);
CREATE INDEX idx_doc_companies_company ON document_companies(company_id);
CREATE INDEX idx_doc_companies_stock_code ON document_companies(stock_code);
CREATE INDEX idx_doc_companies_relation ON document_companies(relation_type);
CREATE INDEX idx_doc_companies_assigned_industry ON document_companies(assigned_industry);
CREATE INDEX idx_doc_companies_industry_source ON document_companies(industry_source);

-- ============================================================
-- Data Review Queue (待覆核隊列)
-- Human-in-the-Loop 機制
-- ============================================================
CREATE TABLE IF NOT EXISTS data_review_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- 關聯
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id),
    
    -- 審核類型
    review_type VARCHAR(50) NOT NULL,    -- 'industry_confirmation', 'data_validation', 'entity_resolution'
    priority VARCHAR(20) DEFAULT 'normal', -- 'high', 'normal', 'low'
    
    -- 審核狀態
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'escalated'
    
    -- AI 建議
    ai_suggestions JSONB,                -- AI 的建議值和置信度
    ai_confidence_score DECIMAL(3, 2),   -- 0.00 - 1.00
    
    -- 人工反饋
    human_feedback TEXT,
    corrected_value JSONB,
    
    -- 來源信息
    source_file VARCHAR(500),
    source_page INTEGER,
    source_element_id VARCHAR(100),
    
    -- 審計
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100),
    
    CONSTRAINT valid_review_status CHECK (status IN ('pending', 'approved', 'rejected', 'escalated'))
);

-- 索引
CREATE INDEX idx_review_queue_status ON data_review_queue(status);
CREATE INDEX idx_review_queue_document ON data_review_queue(document_id);
CREATE INDEX idx_review_queue_type ON data_review_queue(review_type);

-- ============================================================
-- Document Tasks (文檔處理任務表)
-- ============================================================
CREATE TABLE IF NOT EXISTS document_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- 文件信息
    file_path VARCHAR(1000) NOT NULL,
    original_filename VARCHAR(500),
    
    -- 關聯
    document_id UUID REFERENCES documents(id),
    company_id INTEGER REFERENCES companies(id),
    fiscal_year INTEGER,
    
    -- 狀態
    status VARCHAR(20) DEFAULT 'queued',
    progress INTEGER DEFAULT 0,           -- 0-100
    error_message TEXT,
    error_stack TEXT,
    
    -- 統計
    pages_total INTEGER,
    pages_processed INTEGER DEFAULT 0,
    tables_extracted INTEGER DEFAULT 0,
    metrics_extracted INTEGER DEFAULT 0,
    
    -- 審計
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    CONSTRAINT valid_task_status CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled'))
);

-- 索引
CREATE INDEX idx_document_tasks_task_id ON document_tasks(task_id);
CREATE INDEX idx_document_tasks_status ON document_tasks(status);
CREATE INDEX idx_document_tasks_created ON document_tasks(created_at);

-- ============================================================
-- Document Pages (文檔頁面內容表)
-- 用於溯源和全文搜索
-- ============================================================
CREATE TABLE IF NOT EXISTS document_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 頁面信息
    page_num INTEGER NOT NULL,
    
    -- 內容
    markdown_content TEXT,
    text_content TEXT,
    
    -- 元數據
    content_type VARCHAR(50),            -- 'financial', 'narrative', 'tables', 'images'
    has_tables BOOLEAN DEFAULT FALSE,
    has_charts BOOLEAN DEFAULT FALSE,
    has_images BOOLEAN DEFAULT FALSE,
    
    -- 元素座標 (用於溯源高亮)
    elements_json JSONB,                 -- [{"type": "text", "bbox": [...], "content": "..."}]
    
    -- 審計
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(document_id, page_num)
);

-- 索引
CREATE INDEX idx_document_pages_document ON document_pages(document_id);
CREATE INDEX idx_document_pages_page ON document_pages(page_num);
CREATE INDEX idx_document_pages_elements ON document_pages USING GIN(elements_json);

-- 全文搜索索引
CREATE INDEX idx_document_pages_text_search ON document_pages USING GIN(to_tsvector('english', text_content));
CREATE INDEX idx_document_pages_markdown_search ON document_pages USING GIN(to_tsvector('english', markdown_content));

-- ============================================================
-- Agent Ingestion Logs (Agent 處理日誌)
-- 用於追蹤 AI 決策過程
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_ingestion_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    task_id VARCHAR(100),
    
    -- Agent 信息
    agent_type VARCHAR(50),              -- 'ingestion', 'extraction', 'validation'
    model_used VARCHAR(100),
    
    -- 決策過程
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    
    -- 結果
    action_taken VARCHAR(100),           -- 'schema_reflection', 'entity_extraction', 'data_insert'
    action_result JSONB,
    
    -- 錯誤
    error_message TEXT,
    
    -- 審計
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER
);

-- 索引
CREATE INDEX idx_agent_logs_document ON agent_ingestion_logs(document_id);
CREATE INDEX idx_agent_logs_task ON agent_ingestion_logs(task_id);
CREATE INDEX idx_agent_logs_agent ON agent_ingestion_logs(agent_type);

-- ============================================================
-- Views (視圖)
-- ============================================================

-- 文檔摘要視圖
CREATE OR REPLACE VIEW v_document_summary AS
SELECT 
    d.id,
    d.filename,
    d.parent_company_name,
    d.confirmed_industry,
    d.document_type,
    d.fiscal_year,
    d.processing_status,
    d.processing_progress,
    COUNT(dc.id) as company_count,
    COUNT(dp.id) as page_count,
    d.created_at,
    d.processed_at
FROM documents d
LEFT JOIN document_companies dc ON d.id = dc.document_id
LEFT JOIN document_pages dp ON d.id = dp.document_id
GROUP BY d.id;

-- 待審核項視圖
CREATE OR REPLACE VIEW v_pending_reviews AS
SELECT 
    rq.*,
    d.filename,
    d.parent_company_name,
    c.name_en as company_name_en,
    c.stock_code
FROM data_review_queue rq
LEFT JOIN documents d ON rq.document_id = d.id
LEFT JOIN companies c ON rq.company_id = c.id
WHERE rq.status = 'pending'
ORDER BY 
    CASE rq.priority 
        WHEN 'high' THEN 1 
        WHEN 'normal' THEN 2 
        WHEN 'low' THEN 3 
    END,
    rq.created_at;

-- ============================================================
-- Functions (函數)
-- ============================================================

-- 更新 updated_at 觸發器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at 
    BEFORE UPDATE ON documents 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- JSONB 合併函數
CREATE OR REPLACE FUNCTION merge_jsonb(base JSONB, new_data JSONB)
RETURNS JSONB AS $$
BEGIN
    RETURN COALESCE(base, '{}'::JSONB) || COALESCE(new_data, '{}'::JSONB);
END;
$$ LANGUAGE plpgsql;

-- 獲取 Schema 信息函數 (供 Agent 使用)
CREATE OR REPLACE FUNCTION get_document_schema()
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_object_agg(
        table_name,
        jsonb_agg(column_name || ' (' || data_type || ')' || 
            CASE WHEN is_nullable = 'YES' THEN ' NULL' ELSE '' END
        )
    ) INTO result
    FROM information_schema.columns
    WHERE table_schema = 'public' 
    AND table_name IN ('documents', 'document_companies', 'companies')
    GROUP BY table_name;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 初始化數據
-- ============================================================

-- 插入默認行業列表
INSERT INTO industries (name_en, name_zh, category) VALUES
    ('Banking', '銀行業', 'Financial Services'),
    ('Insurance', '保險業', 'Financial Services'),
    ('Real Estate', '地產業', 'Property'),
    ('Technology', '科技業', 'Technology'),
    ('Healthcare', '醫療保健', 'Healthcare'),
    ('Retail', '零售業', 'Consumer'),
    ('Manufacturing', '製造業', 'Industrial'),
    ('Energy', '能源業', 'Energy'),
    ('Telecommunications', '電信業', 'Communications'),
    ('Utilities', '公用事業', 'Utilities')
ON CONFLICT (name_en) DO NOTHING;

-- ============================================================
-- 權限設置
-- ============================================================

-- 創建只讀用戶 (可選)
-- CREATE USER nanobot_readonly WITH PASSWORD 'readonly_password';
-- GRANT CONNECT ON DATABASE annual_reports TO nanobot_readonly;
-- GRANT USAGE ON SCHEMA public TO nanobot_readonly;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO nanobot_readonly;

-- 創建讀寫用戶 (應用使用)
-- CREATE USER nanobot_app WITH PASSWORD 'app_password';
-- GRANT CONNECT ON DATABASE annual_reports TO nanobot_app;
-- GRANT USAGE ON SCHEMA public TO nanobot_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nanobot_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nanobot_app;