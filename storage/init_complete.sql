-- ============================================================
-- Nanobot Database Schema - Complete Initialization
-- ============================================================
-- 
-- 【系統概述 System Overview】
-- 本資料庫架構支援金融文檔智能處理系統，主要功能包括：
-- 
-- 【核心功能 Core Functions】
-- 1. 文檔管理 (Document Management)
--    - 支援年報 (annual_report) 及指數報告 (index_report) 兩種類型
--    - 完整的文檔處理生命週期追蹤
--    - PDF 頁面、切片、表格等多層次內容存儲
--
-- 2. 公司資訊管理 (Company Information Management)
--    - 公司基本資料（名稱、股票代碼、板塊等）
--    - 行業雙軌制（Rule A: 權威定義，Rule B: AI 預測）
--    - 與文檔的多對多關聯
--
-- 3. 數據攝入流程 (Data Ingestion Pipeline)
--    - Phase 1: Agent 初步處理
--    - Phase 2: OpenDataLoader 深度提取
--    - 支援完美溯源（可追溯到原始 PDF 位置）
--
-- 4. 深度內容提取 (Deep Content Extraction)
--    - 財務指標 (Financial Metrics)
--    - 市場數據 (Market Data)
--    - 收入分解 (Revenue Breakdown)
--    - 關鍵人員 (Key Personnel)
--    - 股東結構 (Shareholding Structure)
--    - 實體關係 (Entity Relations)
--
-- 5. 審核與品質控制 (Review & Quality Control)
--    - 人工審核隊列
--    - Vanna 訓練數據管理
--
-- 【技術特性 Technical Features】
-- - JSONB 動態屬性支援彈性擴展
-- - pgvector 向量嵌入支援語意搜索
-- - pg_trgm 支援模糊搜索
-- - 完整的索引策略優化查詢效能
--
-- 【版本 Version】v2.3
-- ============================================================

-- ============================================================
-- 【擴展模組 Extensions】
-- 啟用 PostgreSQL 必要擴展功能
-- ============================================================
-- uuid-ossp: 提供 UUID 生成函數
-- pg_trgm: 支援三字母組模糊搜索
-- vector: pgvector 向量嵌入擴展
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS vector;

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
    -- 保留予 Vanna 系統及其他舊版功能使用
    auditor VARCHAR(200),
    auditor_opinion VARCHAR(50),
    ultimate_controlling_shareholder TEXT,
    principal_banker TEXT,
    
    -- 【Stage 0 Vision 提取欄位 v2.5 新增】
    address TEXT,                          -- 公司註冊地址
    chairman VARCHAR(200),                 -- 主席/董事姓名
    
    extra_data JSONB DEFAULT '{}'::jsonb,
    listing_status VARCHAR(50) DEFAULT 'listed',
    listing_date DATE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引策略 Index Strategy】
-- 針對常用查詢條件建立索引，提升查詢效能
CREATE INDEX IF NOT EXISTS idx_companies_stock_code ON companies(stock_code);
CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector);
CREATE INDEX IF NOT EXISTS idx_companies_is_industry_confirmed ON companies(is_industry_confirmed);
CREATE INDEX IF NOT EXISTS idx_companies_confirmed_industry ON companies(confirmed_industry);
CREATE INDEX IF NOT EXISTS idx_companies_ai_industries ON companies USING GIN (ai_extracted_industries);

-- ============================================================
-- 【表 2: documents 文檔主檔】
-- 【功能 Purpose】
-- 儲存所有上傳文檔的元數據及處理狀態
-- 
-- 【設計理念 Design Philosophy】
-- 支援兩種報告類型：
-- - annual_report: 公司年報，有明確的 owner_company_id
-- - index_report: 恆指報告，無單一母公司，owner_company_id 為 NULL
--
-- 【關聯 Relationships】
-- - 屬於一間公司 (owner_company_id -> companies.id)，但可為 NULL
-- - 一份文檔有多個頁面 (document_pages.document_id)
-- - 一份文檔有多個切片 (document_chunks.document_id)
-- - 一份文檔有多個表格 (document_tables.document_id)
-- - 一份文檔有多個原始提取結果 (raw_artifacts.document_id)
-- - 一份文檔有多條處理歷史 (document_processing_history.document_id)
-- - 一份文檔可關聯多間公司 (document_companies.document_id)
--
-- 【關鍵欄位 Key Fields】
-- - doc_id: 文檔唯一識別碼
-- - report_type: 報告類型 (annual_report / index_report)
-- - processing_status: 處理狀態 (pending / processing / completed / failed)
-- - dynamic_attributes: JSONB 動態屬性，支援擴展
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(255) UNIQUE,  
    filename VARCHAR(500) NOT NULL,
    
    -- 【報告類型欄位 Report Type Fields】
    report_type VARCHAR(50) DEFAULT 'annual_report', -- annual_report 或 index_report
    
    -- 【公司關聯欄位 Company Relationship Field】
    -- 對於 index_report，此欄位為 NULL
    owner_company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    
    year INTEGER,
    
    -- 【處理狀態欄位 Processing Status Fields】
    processing_status VARCHAR(50) DEFAULT 'pending',
    
    -- 【動態屬性欄位 Dynamic Attributes Field】
    -- 支援存放主題 (theme)、地區 (region) 等擴展屬性
    dynamic_attributes JSONB DEFAULT '{}'::jsonb,
    
    -- 【文件元數據欄位 File Metadata Fields】
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

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);
CREATE INDEX IF NOT EXISTS idx_documents_owner_id ON documents(owner_company_id);
CREATE INDEX IF NOT EXISTS idx_documents_processing_status ON documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents(uploaded_at);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_documents_dynamic_attributes ON documents USING GIN (dynamic_attributes);
CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);


-- ============================================================
-- 【表 3: document_companies 文檔-公司關聯表】
-- 【功能 Purpose】
-- 建立文檔與公司之間的多對多關係，記錄公司在文檔中的角色及行業提取結果
-- 
-- 【設計理念 Design Philosophy】
-- 一份文檔可能提及多間公司，一間公司可能在多份文檔中被提及。
-- 此橋樑表記錄：
-- - 公司在文檔中的角色（母公司、子公司、競爭對手、指數成分股等）
-- - 從該文檔提取的公司行業資訊
-- - 提取來源的級別（權威級別 vs AI 預測級別）
--
-- 【關聯 Relationships】
-- - 多對一關聯至 documents (document_id -> documents.id)
-- - 多對一關聯至 companies (company_id -> companies.id)
--
-- 【關鍵欄位 Key Fields】
-- - relation_type: 公司在文檔中的角色
--   - owner_subsidiary: 母公司或子公司
--   - competitor: 競爭對手
--   - index_constituent: 指數成分股
-- - extracted_industries: 從此文檔提取的行業資訊（JSONB）
-- - extraction_source: 提取來源級別
--   - index_rule: 恆指權威級別
--   - ai_predict: AI 預測級別
-- ============================================================
CREATE TABLE IF NOT EXISTS document_companies (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    
    -- 【公司角色欄位 Company Role Field】
    relation_type VARCHAR(50) DEFAULT 'mentioned', 
    
    -- 【行業提取欄位 Industry Extraction Fields】
    extracted_industries JSONB,      -- 從此文檔提取的行業分類
    
    -- 【提取來源級別欄位 Extraction Source Level Field】
    extraction_source VARCHAR(50) DEFAULT 'ai_predict',  -- index_rule 或 ai_predict
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, company_id)
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_dc_document_id ON document_companies(document_id);
CREATE INDEX IF NOT EXISTS idx_dc_company_id ON document_companies(company_id);
CREATE INDEX IF NOT EXISTS idx_dc_relation_type ON document_companies(relation_type);
CREATE INDEX IF NOT EXISTS idx_dc_extraction_source ON document_companies(extraction_source);
CREATE INDEX IF NOT EXISTS idx_dc_extracted_industries ON document_companies USING GIN (extracted_industries);

-- ============================================================
-- 【表 4: document_processing_history 文檔處理歷史表】
-- 【功能 Purpose】
-- 記錄文檔處理過程中每個階段的狀態，用於追蹤及除錯
-- 
-- 【設計理念 Design Philosophy】
-- 文檔處理是一個多階段的過程，每個階段可能有不同的狀態：
-- - pending: 等待處理
-- - processing: 處理中
-- - completed: 完成
-- - failed: 失敗
-- 此表記錄每個階段的處理結果，便於問題排查及進度追蹤。
--
-- 【關聯 Relationships】
-- - 多對一關聯至 documents (document_id -> documents.id)
--
-- 【關鍵欄位 Key Fields】
-- - stage: 處理階段名稱（如：upload, ocr, extraction, embedding）
-- - status: 該階段的處理狀態
-- - details: JSONB 格式的詳細資訊
-- - error_message: 錯誤訊息（如有）
-- ============================================================
CREATE TABLE IF NOT EXISTS document_processing_history (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 【處理階段欄位 Processing Stage Fields】
    stage VARCHAR(100),               -- 處理階段名稱
    status VARCHAR(50) NOT NULL,      -- 處理狀態
    details JSONB DEFAULT '{}'::jsonb, -- 詳細資訊
    error_message TEXT,               -- 錯誤訊息
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_dph_document_id ON document_processing_history(document_id);
CREATE INDEX IF NOT EXISTS idx_dph_stage ON document_processing_history(stage);
CREATE INDEX IF NOT EXISTS idx_dph_status ON document_processing_history(status);
CREATE INDEX IF NOT EXISTS idx_dph_created_at ON document_processing_history(created_at);


-- ============================================================
-- 【表 5: document_pages 文檔頁面表】
-- 【功能 Purpose】
-- 儲存 PDF 每一頁轉換後的 Markdown 內容，作為 Zone 2 Fallback
-- 
-- 【設計理念 Design Philosophy】
-- 當精確的表格/切片提取失敗時，可以使用頁面級別的 Markdown 內容作為備援。
-- 此表支援：
-- - 全文搜索（透過 to_tsvector 索引）
-- - 向量嵌入（支援語意搜索）
-- - OCR 置信度追蹤
--
-- 【關聯 Relationships】
-- - 多對一關聯至 documents (document_id -> documents.id)
--
-- 【關鍵欄位 Key Fields】
-- - page_num: 頁碼
-- - markdown_content: PDF 頁面轉換後的 Markdown 內容
-- - ocr_confidence: OCR 識別置信度
-- - has_tables / has_images: 標識頁面是否包含表格/圖片
-- - embedding_vector: 頁面內容的向量嵌入（用於語意搜索）
-- ============================================================
CREATE TABLE IF NOT EXISTS document_pages (
    -- 【主鍵 Primary Key】
    id SERIAL PRIMARY KEY,
    
    -- 【關聯欄位 Relationship Field】
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 【頁面資訊欄位 Page Information Fields】
    page_num INTEGER NOT NULL,
    markdown_content TEXT NOT NULL,  -- PDF 頁面轉 Markdown (Zone 2 Fallback)
    
    -- 【OCR/解析元數據欄位 OCR/Parsing Metadata Fields】
    ocr_confidence FLOAT DEFAULT 0.0,
    has_tables BOOLEAN DEFAULT FALSE,
    has_images BOOLEAN DEFAULT FALSE,
    has_charts BOOLEAN DEFAULT FALSE,

    -- 【向量嵌入欄位 Vector Embedding Field】
    embedding_vector VECTOR(384),  -- 🌟 本地 Embedding 模型維度（sentence-transformers）
    
    -- 【元數據欄位 Metadata Field】
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- 【審計欄位 Audit Field】
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 【約束 Constraint】
    CONSTRAINT unique_page UNIQUE (document_id, page_num)
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_document_pages_document_id ON document_pages(document_id);
CREATE INDEX IF NOT EXISTS idx_document_pages_page_num ON document_pages(page_num);
CREATE INDEX IF NOT EXISTS idx_document_pages_has_tables ON document_pages(has_tables);
CREATE INDEX IF NOT EXISTS idx_document_pages_has_images ON document_pages(has_images);
CREATE INDEX IF NOT EXISTS idx_document_pages_content_search ON document_pages USING GIN (to_tsvector('english', markdown_content));


-- ============================================================
-- 【表 6: document_chunks 文檔切片表】
-- 【功能 Purpose】
-- 儲存文檔的切片內容，用於 RAG (Retrieval-Augmented Generation) 檢索
-- 
-- 【設計理念 Design Philosophy】
-- 將長文檔分割成較小的切片，每個切片可以：
-- - 獨立進行向量嵌入
-- - 用於語意搜索
-- - 作為 LLM 的上下文輸入
-- 切片類型包括：文字、表格、圖片
--
-- 【關聯 Relationships】
-- - 多對一關聯至 documents (document_id -> documents.id)
--
-- 【關鍵欄位 Key Fields】
-- - chunk_index: 切片序號
-- - chunk_type: 切片類型（text / table / image）
-- - content: 切片內容
-- - page_number: 所在頁碼
-- - bounding_box: 在頁面中的位置座標
-- - embedding_vector: 切片內容的向量嵌入
-- ============================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    -- 【主鍵 Primary Key】
    id SERIAL PRIMARY KEY,
    
    -- 【關聯欄位 Relationship Field】
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 【切片資訊欄位 Chunk Information Fields】
    chunk_index INTEGER NOT NULL,
    chunk_type VARCHAR(50) DEFAULT 'text',  -- text, table, image
    content TEXT NOT NULL,
    
    -- 【位置資訊欄位 Position Information Fields】
    page_number INTEGER,
    bounding_box JSONB,           -- {x, y, width, height}
    
    -- 【向量嵌入欄位 Vector Embedding Field】
    embedding_vector VECTOR(384),  -- 🌟 本地 Embedding 模型維度（sentence-transformers）
    
    -- 【元數據欄位 Metadata Field】
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- 【審計欄位 Audit Field】
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type ON document_chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_page_number ON document_chunks(page_number);


-- ============================================================
-- 【表 7: document_tables 文檔表格表】
-- 【功能 Purpose】
-- 儲存從文檔中提取的表格結構化數據
-- 
-- 【設計理念 Design Philosophy】
-- 表格是財務文檔中最重要的數據載體之一。此表將表格轉換為結構化格式：
-- - headers: 表頭列表
-- - rows: 數據行列表
-- 支援多種表格類型：資產負債表、損益表、現金流量表等
--
-- 【關聯 Relationships】
-- - 多對一關聯至 documents (document_id -> documents.id)
-- - 可選關聯至 document_chunks (chunk_id -> document_chunks.id)
--
-- 【關鍵欄位 Key Fields】
-- - table_index: 表格序號
-- - table_type: 表格類型（balance_sheet, income_statement, cash_flow 等）
-- - title: 表格標題
-- - headers: 表頭 JSONB 陣列
-- - rows: 數據行 JSONB 陣列
-- - page_number / bounding_box: 表格在文檔中的位置
-- ============================================================
CREATE TABLE IF NOT EXISTS document_tables (
    -- 【主鍵 Primary Key】
    id SERIAL PRIMARY KEY,
    
    -- 【關聯欄位 Relationship Fields】
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL,
    
    -- 【表格資訊欄位 Table Information Fields】
    table_index INTEGER NOT NULL,
    table_type VARCHAR(100),        -- balance_sheet, income_statement, cash_flow, etc.
    title TEXT,
    
    -- 【表格數據欄位 Table Data Fields】
    headers JSONB,                  -- ["Column1", "Column2", ...]
    rows JSONB NOT NULL,             -- [[row1], [row2], ...]
    
    -- 【位置資訊欄位 Position Information Fields】
    page_number INTEGER,
    bounding_box JSONB,
    
    -- 【元數據欄位 Metadata Field】
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- 【審計欄位 Audit Field】
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_doc_page_table UNIQUE (document_id, page_number, table_index)
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_tables_document_id ON document_tables(document_id);
CREATE INDEX IF NOT EXISTS idx_tables_table_type ON document_tables(table_type);
CREATE INDEX IF NOT EXISTS idx_tables_page_number ON document_tables(page_number);

-- ============================================================
-- 【表 8: review_queue 人工審核隊列表】
-- 【功能 Purpose】
-- 管理需要人工審核的項目，支援人機協作流程
-- 
-- 【設計理念 Design Philosophy】
-- AI 提取的數據可能存在不確定性，需要人工覆核。此表提供：
-- - 優先級排序（priority 欄位）
-- - 狀態追蹤（pending, in_review, approved, rejected, escalated）
-- - AI 建議及人工決策記錄
-- 審核類型包括：行業提取、公司名稱識別等
--
-- 【關聯 Relationships】
-- - 可選關聯至 documents (document_id -> documents.id)
-- - 可選關聯至 document_companies (company_id -> document_companies.id)
--
-- 【關鍵欄位 Key Fields】
-- - review_type: 審核類型（industry_extraction, company_name 等）
-- - priority: 優先級（1-10，1 為最高）
-- - status: 審核狀態
-- - issue_description: 問題描述
-- - ai_suggestion: AI 的建議答案
-- - human_decision: 人工的最終決定
-- - reviewer_id: 審核人員 ID
-- ============================================================
CREATE TABLE IF NOT EXISTS review_queue (
    -- 【主鍵 Primary Key】
    id SERIAL PRIMARY KEY,
    
    -- 【關聯欄位 Relationship Fields】
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES document_companies(id) ON DELETE CASCADE,
    
    -- 【審核資訊欄位 Review Information Fields】
    review_type VARCHAR(100) NOT NULL,  -- industry_extraction, company_name, etc.
    priority INTEGER DEFAULT 5,          -- 1-10, 1 最高
    status VARCHAR(50) DEFAULT 'pending', -- pending, in_review, approved, rejected
    
    -- 【問題描述欄位 Issue Description Fields】
    issue_description TEXT,
    ai_suggestion TEXT,
    human_decision TEXT,
    
    -- 【審核人員欄位 Reviewer Fields】
    reviewer_id VARCHAR(100),
    reviewed_at TIMESTAMP,
    
    -- 【審計欄位 Audit Fields】
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 【約束 Constraint】
    CONSTRAINT valid_review_status CHECK (status IN ('pending', 'in_review', 'approved', 'rejected', 'escalated'))
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_review_document_id ON review_queue(document_id);
CREATE INDEX IF NOT EXISTS idx_review_company_id ON review_queue(company_id);
CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_priority ON review_queue(priority);


-- ============================================================
-- 【表 10: financial_metrics 財務指標表】
-- 【功能 Purpose】
-- 儲存公司的財務指標數據，採用 EAV (Entity-Attribute-Value) 模式
-- 
-- 【設計理念 Design Philosophy】
-- EAV 模式的優點：
-- - 靈活支援不同公司的不同財務指標
-- - 易於擴展新的指標類型
-- - 支援標準化（將不同幣別轉換為 HKD）
-- - 支援追溯（記錄數據來源）
--
-- 【關聯 Relationships】
-- - 多對一關聯至 companies (company_id -> companies.id)
-- - 可選關聯至 documents (source_document_id -> documents.id)
--
-- 【關鍵欄位 Key Fields】
-- - metric_name: 標準英文名稱（Taxonomy）
-- - metric_name_zh: 標準中文名稱
-- - original_metric_name: 原始名稱（用於追溯）
-- - value: 原始數值
-- - unit: 原始單位
-- - standardized_value: 標準化數值（HKD）
-- - fiscal_period: 財政期間（FY, H1, Q1, Q2, Q3, Q4）
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_metrics (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    fiscal_period VARCHAR(20) DEFAULT 'FY',  -- FY, H1, Q1, Q2, Q3, Q4
    
    -- 【EAV 核心欄位 EAV Core Fields】
    metric_name VARCHAR(100) NOT NULL,       -- 標準英文名 (Taxonomy)
    metric_name_zh VARCHAR(100),             -- 標準中文名
    original_metric_name VARCHAR(200),       -- 原始名稱 (Traceability)
    
    -- 【數值處理欄位 Value Processing Fields】
    value NUMERIC(20, 2),                    -- 原始值
    unit VARCHAR(50),                        -- 原始單位
    standardized_value NUMERIC(20, 2),       -- 標準化值 (HKD)
    standardized_currency VARCHAR(10) DEFAULT 'HKD',
    
    -- 【來源欄位 Source Fields】
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    source_page INTEGER,
    source_table_id VARCHAR(100),
    
    -- 【元數據欄位 Metadata Fields】
    extraction_confidence FLOAT DEFAULT 0.8,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 【約束 Constraint】
    CONSTRAINT unique_metric UNIQUE (company_id, year, fiscal_period, metric_name)
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_financial_metrics_company_id ON financial_metrics(company_id);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_year ON financial_metrics(year);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_metric_name ON financial_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_standardized_value ON financial_metrics(standardized_value);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_fiscal_period ON financial_metrics(fiscal_period);


-- ============================================================
-- 【表 11: market_data 市場數據表】
-- 【功能 Purpose】
-- 儲存公司的市場交易數據（股價、成交量等）
-- 
-- 【設計理念 Design Philosophy】
-- 記錄股票市場的歷史數據，支援：
-- - 日線、週線、月線數據
-- - 價格數據（開高低收）
-- - 交易數據（成交量、成交額）
-- - 估值指標（市值、市盈率、市淨率、股息率）
--
-- 【關聯 Relationships】
-- - 多對一關聯至 companies (company_id -> companies.id)
--
-- 【關鍵欄位 Key Fields】
-- - data_date: 數據日期
-- - period_type: 期間類型（daily, weekly, monthly）
-- - open_price / high_price / low_price / close_price: 股價數據
-- - adj_close_price: 調整後收盤價
-- - volume: 成交量
-- - turnover: 成交額
-- - market_cap: 市值
-- - pe_ratio / pb_ratio: 市盈率 / 市淨率
-- - dividend_yield: 股息率
-- ============================================================
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    
    -- 【日期與期間欄位 Date and Period Fields】
    data_date DATE NOT NULL,
    period_type VARCHAR(20) DEFAULT 'daily',  -- daily, weekly, monthly
    
    -- 【股價數據欄位 Stock Price Fields】
    open_price NUMERIC(15, 4),
    high_price NUMERIC(15, 4),
    low_price NUMERIC(15, 4),
    close_price NUMERIC(15, 4),
    adj_close_price NUMERIC(15, 4),
    
    -- 【交易數據欄位 Trading Data Fields】
    volume BIGINT,
    turnover NUMERIC(20, 2),
    
    -- 【估值指標欄位 Valuation Metrics Fields】
    market_cap NUMERIC(20, 2),
    pe_ratio NUMERIC(10, 4),
    pb_ratio NUMERIC(10, 4),
    dividend_yield NUMERIC(6, 4),
    
    -- 【元數據欄位 Metadata Fields】
    source VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_market_data UNIQUE (company_id, data_date, period_type)
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_market_data_company_id ON market_data(company_id);
CREATE INDEX IF NOT EXISTS idx_market_data_date ON market_data(data_date);
CREATE INDEX IF NOT EXISTS idx_market_data_period ON market_data(period_type);


-- ============================================================
-- 【表 12: revenue_breakdown 收入分解表】
-- 【功能 Purpose】
-- 儲存公司收入按業務/地區/產品的分解數據
-- 
-- 【設計理念 Design Philosophy】
-- 公司收入通常按不同維度分解：
-- - 業務分部（business segment）
-- - 地理區域（geography）
-- - 產品類別（product）
-- 此表支援這些維度的收入構成分析
--
-- 【關聯 Relationships】
-- - 多對一關聯至 companies (company_id -> companies.id)
-- - 可選關聯至 documents (source_document_id -> documents.id)
--
-- 【關鍵欄位 Key Fields】
-- - segment_name: 分部名稱
-- - segment_type: 分部類型（business / geography / product）
-- - revenue_amount: 收入金額
-- - revenue_percentage: 收入佔比
-- - currency: 幣別
-- ============================================================
CREATE TABLE IF NOT EXISTS revenue_breakdown (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    
    -- 【收入類別欄位 Revenue Category Fields】
    segment_name VARCHAR(255) NOT NULL,
    segment_type VARCHAR(50) DEFAULT 'business',  -- business, geography, product
    
    -- 【金額欄位 Amount Fields】
    revenue_amount NUMERIC(20, 2),
    revenue_percentage NUMERIC(5, 2),
    currency VARCHAR(10) DEFAULT 'HKD',
    
    -- 【元數據欄位 Metadata Fields】
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_revenue_segment UNIQUE (company_id, year, segment_name, segment_type)
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_revenue_company_id ON revenue_breakdown(company_id);
CREATE INDEX IF NOT EXISTS idx_revenue_year ON revenue_breakdown(year);
CREATE INDEX IF NOT EXISTS idx_revenue_segment_type ON revenue_breakdown(segment_type);


-- ============================================================
-- 【表 13: key_personnel 關鍵人員表】
-- 【功能 Purpose】
-- 儲存公司的董事、高管等關鍵人員資訊
-- 
-- 【設計理念 Design Philosophy】
-- 關鍵人員資訊對於公司治理分析至關重要。此表記錄：
-- - 人員基本資訊（姓名、職位）
-- - 任職狀態（現任/離任）
-- - 董事會角色及委員會成員身份
-- - 資料來源追溯（來自哪份 PDF）
--
-- 【關聯 Relationships】
-- - 多對一關聯至 companies (company_id -> companies.id)
-- - 可選關聯至 documents (document_id -> documents.id)
--
-- 【關鍵欄位 Key Fields】
-- - name_en / name_zh: 英文/中文名稱
-- - position_title_en / position_title_zh: 職位名稱
-- - position_type: 職位類型（director, executive, secretary 等）
-- - role: 簡化版角色（Chairman, CEO, CFO 等）
-- - board_role: 董事會角色
-- - committee_membership: 委員會成員身份（JSONB 陣列）
-- - is_current: 是否現任
-- - source_page: 資料來源頁碼
-- ============================================================
CREATE TABLE IF NOT EXISTS key_personnel (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,  -- 溯源：邊份 PDF 抽到嘅
    
    -- 【年份欄位 Year Field】
    -- 對應 Qwen LLM 抽取出嚟嘅人物關係時間點
    year INTEGER,
    
    -- 【個人資訊欄位 Personal Information Fields】
    name_en VARCHAR(255),
    name_zh VARCHAR(255),
    
    -- 【職位資訊欄位 Position Information Fields】
    position_title_en VARCHAR(255),
    position_title_zh VARCHAR(255),
    position_type VARCHAR(50),  -- director, executive, secretary, etc.
    role VARCHAR(255),          -- 簡化版角色 (例如：Chairman, CEO)
    
    -- 【董事會相關欄位 Board-Related Fields】
    board_role VARCHAR(100),     -- chairman, ceo, cfo, independent_director, etc.
    committee_membership JSONB,  -- ['audit', 'remuneration', 'nomination']
    
    -- 【任職資訊欄位 Appointment Information Fields】
    appointment_date DATE,
    resignation_date DATE,
    is_current BOOLEAN DEFAULT TRUE,
    
    -- 【元數據欄位 Metadata Fields】
    biography TEXT,
    source_page INTEGER,         -- 記錄 OpenDataLoader 搵到嘅原圖/表格位置
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_personnel_company_id ON key_personnel(company_id);
CREATE INDEX IF NOT EXISTS idx_personnel_document_id ON key_personnel(document_id);
CREATE INDEX IF NOT EXISTS idx_personnel_year ON key_personnel(year);
CREATE INDEX IF NOT EXISTS idx_personnel_position_type ON key_personnel(position_type);
CREATE INDEX IF NOT EXISTS idx_personnel_board_role ON key_personnel(board_role);
CREATE INDEX IF NOT EXISTS idx_personnel_role ON key_personnel(role);
CREATE INDEX IF NOT EXISTS idx_personnel_is_current ON key_personnel(is_current);


-- ============================================================
-- 【表 14: shareholding_structure 股東結構表】
-- 【功能 Purpose】
-- 儲存公司的股東持股結構數據
-- 
-- 【設計理念 Design Philosophy】
-- 股東結構分析對於公司控制權研究至關重要。此表記錄：
-- - 股東基本資訊（名稱、類型）
-- - 信託資訊（信託名稱、受託人名稱）
-- - 持股數據（股數、百分比）
-- - 控制權標識（是否為控股股東、機構投資者）
--
-- 【關聯 Relationships】
-- - 多對一關聯至 companies (company_id -> companies.id)
-- - 可選關聯至 documents (source_document_id -> documents.id)
--
-- 【關鍵欄位 Key Fields】
-- - shareholder_name: 股東名稱
-- - shareholder_type: 股東類型（individual, corporation, government 等）
-- - trust_name / trustee_name: 信託/受託人名稱
-- - shares_held: 持股數量
-- - percentage: 持股比例
-- - is_controlling: 是否為控股股東
-- - is_institutional: 是否為機構投資者
-- ============================================================
CREATE TABLE IF NOT EXISTS shareholding_structure (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    
    -- 【股東資訊欄位 Shareholder Information Fields】
    shareholder_name VARCHAR(255),
    shareholder_type VARCHAR(50),  -- individual, corporation, government, etc.
    
    -- 【信託資訊欄位 Trust Information Fields】
    trust_name VARCHAR(255),       -- 信託名稱 (例如: The Li Ka-Shing Unity Trust)
    trustee_name VARCHAR(255),     -- 受託人名稱 (例如: Li Ka-Shing Unity Trustee Company Limited)
    
    -- 【持股資訊欄位 Shareholding Information Fields】
    shares_held NUMERIC(20, 2),
    percentage NUMERIC(6, 4),
    
    -- 【股東類型欄位 Shareholder Type Fields】
    is_controlling BOOLEAN DEFAULT FALSE,
    is_institutional BOOLEAN DEFAULT FALSE,
    
    -- 【元數據欄位 Metadata Fields】
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- v4.6: 移除 year 和 notes（冗餘欄位，可從 source_document_id -> documents.year 取得）
    CONSTRAINT unique_shareholder UNIQUE (company_id, shareholder_name, source_document_id)
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_shareholding_company_id ON shareholding_structure(company_id);
CREATE INDEX IF NOT EXISTS idx_shareholding_type ON shareholding_structure(shareholder_type);
CREATE INDEX IF NOT EXISTS idx_shareholding_trust_name ON shareholding_structure(trust_name);
CREATE INDEX IF NOT EXISTS idx_shareholding_trustee_name ON shareholding_structure(trustee_name);


-- ============================================================
-- 【表 15: raw_artifacts 原始提取結果表】
-- 【功能 Purpose】
-- 儲存 OpenDataLoader 提取的原始內容，支援完美溯源
-- 
-- 【設計理念 Design Philosophy】
-- 完美溯源機制：
-- - 記錄 OpenDataLoader 截取的圖片、Markdown 及位置資訊
-- - 如果 Qwen-VL 解析錯誤，可透過 artifact_id 找回原始內容對質
-- - 支援多種 artifact 類型：文字切片、表格、圖片截圖、圖表
--
-- 【關聯 Relationships】
-- - 多對一關聯至 documents (document_id -> documents.id)
--
-- 【關鍵欄位 Key Fields】
-- - artifact_id: 唯一識別碼
-- - artifact_type: 類型（text_chunk, table, image_screenshot, chart）
-- - content: Markdown 內容
-- - file_path: 圖片儲存路徑
-- - page_num / bbox: 頁碼及位置座標
-- - parsed_data: Qwen-VL 解析結果
-- - parsing_status: 解析狀態（pending, parsed, failed）
-- ============================================================
CREATE TABLE IF NOT EXISTS raw_artifacts (
    id SERIAL PRIMARY KEY,
    artifact_id VARCHAR(255) UNIQUE,  
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 【類型分類欄位 Type Classification Field】
    artifact_type VARCHAR(50),        -- 'text_chunk', 'table', 'image_screenshot', 'chart'
    
    -- 【內容欄位 Content Field】
    -- OpenDataLoader 輸出的 Markdown 內容
    content TEXT,
    
    -- 【檔案路徑欄位 File Path Field】
    -- OpenDataLoader 截圖的儲存路徑
    file_path VARCHAR(500),
    
    -- 【位置資訊欄位 Position Information Fields】
    page_num INTEGER,
    bbox JSONB,                       -- {x, y, width, height}
    
    -- 【解析結果欄位 Parsing Result Fields】
    parsed_data JSONB,                -- Qwen-VL 解析出的結構化數據
    parsing_status VARCHAR(50) DEFAULT 'pending',  -- pending, parsed, failed
    parsing_error TEXT,
    
    -- 【元數據欄位 Metadata Field】
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_ra_document_id ON raw_artifacts(document_id);
CREATE INDEX IF NOT EXISTS idx_ra_artifact_id ON raw_artifacts(artifact_id);
CREATE INDEX IF NOT EXISTS idx_ra_artifact_type ON raw_artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_ra_page_num ON raw_artifacts(page_num);
CREATE INDEX IF NOT EXISTS idx_ra_parsing_status ON raw_artifacts(parsing_status);
CREATE INDEX IF NOT EXISTS idx_ra_parsed_data ON raw_artifacts USING GIN (parsed_data);


-- ============================================================
-- 【表 16: entity_relations 實體關係抽取表】
-- 【功能 Purpose】
-- 儲存 LLM 抽取的實體關係，支援 Graph-based 查詢
-- 
-- 【設計理念 Design Philosophy】
-- 實體關係圖譜：
-- - 記錄人物、公司、事件、地點之間的關係
-- - 支援知識圖譜構建
-- - 支援複雜關係查詢（如：某人的所有董事會關聯）
-- 關係類型包括：任命、辭任、收購、子公司關係等
--
-- 【關聯 Relationships】
-- - 多對一關聯至 documents (document_id -> documents.id)
-- - 可選關聯至 raw_artifacts (source_artifact_id -> raw_artifacts.artifact_id)
--
-- 【關鍵欄位 Key Fields】
-- - source_entity_type: 源實體類型（person, company, event, location）
-- - source_entity_id: 源實體 ID（可關聯至 key_personnel 或 companies）
-- - source_entity_name: 源實體名稱
-- - target_entity_type: 目標實體類型
-- - target_entity_id: 目標實體 ID
-- - target_entity_name: 目標實體名稱
-- - relation_type: 關係類型（appointed, resigned, acquired, subsidiary_of 等）
-- - relation_strength: 關係強度/置信度
-- - event_date / event_year: 事件發生時間
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_relations (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 【源實體欄位 Source Entity Fields】
    source_entity_type VARCHAR(50),   -- 'person', 'company', 'event', 'location'
    source_entity_id INTEGER,         -- 可關聯到 key_personnel 或 companies
    source_entity_name VARCHAR(255),
    
    -- 【目標實體欄位 Target Entity Fields】
    target_entity_type VARCHAR(50),
    target_entity_id INTEGER,
    target_entity_name VARCHAR(255),
    
    -- 【關係類型欄位 Relation Type Fields】
    relation_type VARCHAR(100),       -- 'appointed', 'resigned', 'acquired', 'subsidiary_of'
    relation_strength FLOAT DEFAULT 1.0,  -- 關係強度/置信度
    
    -- 【時間資訊欄位 Time Information Fields】
    event_date DATE,
    event_year INTEGER,
    
    -- 【溯源欄位 Traceability Fields】
    source_page INTEGER,
    source_artifact_id VARCHAR(255) REFERENCES raw_artifacts(artifact_id) ON DELETE SET NULL,
    
    -- 【元數據欄位 Metadata Fields】
    metadata JSONB DEFAULT '{}'::jsonb,
    extraction_confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_er_document_id ON entity_relations(document_id);
CREATE INDEX IF NOT EXISTS idx_er_source_type ON entity_relations(source_entity_type);
CREATE INDEX IF NOT EXISTS idx_er_target_type ON entity_relations(target_entity_type);
CREATE INDEX IF NOT EXISTS idx_er_relation_type ON entity_relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_er_event_date ON entity_relations(event_date);
CREATE INDEX IF NOT EXISTS idx_er_event_year ON entity_relations(event_year);


-- ============================================================
-- 【表 17: artifact_relations 跨模態關聯表 (Cross-Modal Relations)】
-- 【功能 Purpose】
-- 解決「跨頁/跨文件」的圖文關聯斷裂問題，建立 SQL 版輕量級多模態圖譜。
-- 
-- 【設計理念 Design Philosophy】
-- 針對財務報告中「圖表在第 5 頁，解釋在第 50 頁」的痛點。
-- 透過此橋樑表，將 raw_artifacts 中的圖表 (chart/image) 
-- 與對應的文字段落 (text_chunk) 進行強關聯。
-- 
-- 【關聯 Relationships】
-- - 關聯至 raw_artifacts (source_artifact_id -> 圖表)
-- - 關聯至 raw_artifacts (target_artifact_id -> 解釋文字)
-- ============================================================
CREATE TABLE IF NOT EXISTS artifact_relations (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 【源實體：通常是圖表或圖片】
    source_artifact_id VARCHAR(255) NOT NULL REFERENCES raw_artifacts(artifact_id) ON DELETE CASCADE,
    
    -- 【目標實體：通常是解釋性的文字段落】
    target_artifact_id VARCHAR(255) NOT NULL REFERENCES raw_artifacts(artifact_id) ON DELETE CASCADE,
    
    -- 【關係屬性 Relation Attributes】
    relation_type VARCHAR(50) DEFAULT 'explained_by', -- explained_by, referenced_in
    confidence_score FLOAT DEFAULT 1.0, -- 關聯置信度 (如果是 LLM 估計的可以小於 1)
    extraction_method VARCHAR(50) DEFAULT 'regex', -- regex, llm_inferred, manual
    
    -- 【審計欄位 Audit Fields】
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 避免重複關聯
    CONSTRAINT unique_artifact_relation UNIQUE (source_artifact_id, target_artifact_id)
);

-- 【索引策略 Index Strategy】
CREATE INDEX IF NOT EXISTS idx_ar_document_id ON artifact_relations(document_id);
CREATE INDEX IF NOT EXISTS idx_ar_source_id ON artifact_relations(source_artifact_id);
CREATE INDEX IF NOT EXISTS idx_ar_target_id ON artifact_relations(target_artifact_id);


-- ============================================================
-- 【實用函數 Utility Functions】
-- ============================================================

-- ============================================================
-- 【函數: update_updated_at_column】
-- 【功能 Purpose】
-- 自動更新 updated_at 欄位的觸發器函數
-- 
-- 【設計理念 Design Philosophy】
-- 在任何 UPDATE 操作之前，自動將 updated_at 設為當前時間戳，
-- 確保記錄的更新時間始終正確。
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- ============================================================
-- 【觸發器 Triggers】
-- 為所有包含 updated_at 欄位的表建立自動更新觸發器
-- ============================================================

-- 【觸發器: companies 表更新時間】
DROP TRIGGER IF EXISTS update_companies_updated_at ON companies;
CREATE TRIGGER update_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 【觸發器: documents 表更新時間】
DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;
CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 【觸發器: review_queue 表更新時間】
DROP TRIGGER IF EXISTS update_review_queue_updated_at ON review_queue;
CREATE TRIGGER update_review_queue_updated_at
    BEFORE UPDATE ON review_queue
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 【觸發器: vanna_training_data 表更新時間】
DROP TRIGGER IF EXISTS update_vanna_training_data_updated_at ON vanna_training_data;
CREATE TRIGGER update_vanna_training_data_updated_at
    BEFORE UPDATE ON vanna_training_data
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 【觸發器: key_personnel 表更新時間】
DROP TRIGGER IF EXISTS update_key_personnel_updated_at ON key_personnel;
CREATE TRIGGER update_key_personnel_updated_at
    BEFORE UPDATE ON key_personnel
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
-- 【觸發器: artifact_relations 表更新時間】
DROP TRIGGER IF EXISTS update_artifact_relations_updated_at ON artifact_relations;
CREATE TRIGGER update_artifact_relations_updated_at
    BEFORE UPDATE ON artifact_relations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 【索引補充 Additional Indexes】
-- 重新建立正確的索引，確保查詢效能
-- ============================================================

-- 【文檔表索引 Document Table Indexes】
CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);
CREATE INDEX IF NOT EXISTS idx_documents_owner_id ON documents(owner_company_id);
CREATE INDEX IF NOT EXISTS idx_documents_dynamic_attributes ON documents USING GIN (dynamic_attributes);

-- 【橋樑表索引 Bridge Table Indexes】
CREATE INDEX IF NOT EXISTS idx_dc_document_id ON document_companies(document_id);
CREATE INDEX IF NOT EXISTS idx_dc_company_id ON document_companies(company_id);
CREATE INDEX IF NOT EXISTS idx_dc_relation_type ON document_companies(relation_type);
CREATE INDEX IF NOT EXISTS idx_dc_extracted_industries ON document_companies USING GIN (extracted_industries);

-- ============================================================
-- 【視圖 Views】
-- 為前端及後端提供預先定義的查詢視圖
-- ============================================================

-- ============================================================
-- 【視圖: document_summary 文檔摘要視圖】
-- 【功能 Purpose】
-- 提供文檔的摘要資訊，包括：
-- - 文檔基本資訊
-- - 母公司名稱
-- - 提及公司數量
-- - 從 JSONB 提取的動態屬性
-- 
-- 【用途 Use Cases】
-- - 前端文檔列表展示
-- - 文檔快速概覽
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
-- 【視圖: v_documents_for_vanna Vanna 專用文檔視圖】
-- 【功能 Purpose】
-- 為 Vanna Text-to-SQL 模型提供優化的文檔視圖
-- 
-- 【設計理念 Design Philosophy】
-- 扁平化結構便於 Vanna 理解和生成 SQL：
-- - 將 companies 表的資訊直接 JOIN 到視圖中
-- - 從 JSONB 中提取常用屬性作為獨立欄位
-- - 使用清晰的欄位別名
-- 
-- 【用途 Use Cases】
-- - Vanna 訓練數據生成
-- - 自然語言轉 SQL 查詢
-- ============================================================
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

-- ============================================================
-- 【視圖: v_companies_for_vanna Vanna 專用公司視圖】
-- 【功能 Purpose】
-- 為 Vanna Text-to-SQL 模型提供優化的公司視圖
-- 
-- 【設計理念 Design Philosophy】
-- 解決行業雙軌制的查詢複雜度：
-- - 如果有權威定義（confirmed_industry），使用權威定義
-- - 如果沒有權威定義，使用 AI 預測的第一個行業
-- - 透過 COALESCE 函數封裝此邏輯
-- 
-- 【用途 Use Cases】
-- - Vanna 訓練數據生成
-- - 自然語言轉 SQL 查詢
-- - 前端公司列表展示
-- ============================================================
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
-- 【視圖: v_tables_with_context_for_vanna 跨模態圖表視圖】
-- 【功能 Purpose】
-- 為 Vanna 提供「圖表數字 + 跨頁文字解釋」的統一視圖
-- 
-- 【設計理念 Design Philosophy】
-- 解決「圖表在第 5 頁，解釋在第 50 頁」的痛點：
-- - 預先將 document_tables 的精準數字
-- - 與 artifact_relations 關聯的解釋文字 JOIN
-- - Vanna 只需要簡單查詢，不需要寫複雜的多重 JOIN
-- 
-- 【用途 Use Cases】
-- - 用戶問：「圖 5 的營收為什麼跌？具體跌了多少？」
-- - Vanna 只需：SELECT table_data, related_explanation FROM v_tables_with_context_for_vanna WHERE table_title LIKE '%圖 5%'
-- ============================================================
CREATE OR REPLACE VIEW v_tables_with_context_for_vanna AS
SELECT 
    dt.id AS table_id,
    dt.document_id,
    dt.table_type,
    dt.title AS table_title,
    dt.rows AS table_data,           -- 圖表/表格的精準數字
    ra_text.content AS related_explanation,  -- 來自第 50 頁的跨頁文字解釋
    ra_chart.page_num AS chart_page_num,
    ra_text.page_num AS explanation_page_num,
    dt.metadata->>'image_path' AS original_image_path
FROM document_tables dt
-- 假設 document_tables 的 metadata 中記錄了 source_artifact_id
LEFT JOIN raw_artifacts ra_chart ON dt.metadata->>'source_artifact_id' = ra_chart.artifact_id
LEFT JOIN artifact_relations ar ON ra_chart.artifact_id = ar.source_artifact_id
LEFT JOIN raw_artifacts ra_text ON ar.target_artifact_id = ra_text.artifact_id
WHERE ar.relation_type = 'explained_by' OR ar.relation_type IS NULL;

-- ============================================================
-- 【初始化完成通知 Initialization Complete Notice】
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Nanobot Database Schema 初始化完成 (v2.3)';
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
    RAISE NOTICE '  - vanna_training_data (Vanna 訓練數據)';
    RAISE NOTICE '';
    RAISE NOTICE '【深度內容提取表 Deep Content Extraction Tables】';
    RAISE NOTICE '  - financial_metrics (財務指標 EAV)';
    RAISE NOTICE '  - market_data (市場數據)';
    RAISE NOTICE '  - revenue_breakdown (收入分解)';
    RAISE NOTICE '  - key_personnel (關鍵人員)';
    RAISE NOTICE '  - shareholding_structure (股東結構)';
    RAISE NOTICE '  - raw_artifacts (原始提取結果 - 完美溯源)';
    RAISE NOTICE '  - entity_relations (實體關係 - Graph)';
    RAISE NOTICE '  - artifact_relations (跨模態關聯 - 解決圖文跨頁斷裂)';
    RAISE NOTICE '';
    RAISE NOTICE '【視圖 Views】';
    RAISE NOTICE '  - document_summary (文檔摘要視圖)';
    RAISE NOTICE '  - v_documents_for_vanna (Vanna 文檔視圖)';
    RAISE NOTICE '  - v_companies_for_vanna (Vanna 公司視圖 - 雙軌制行業)';
    RAISE NOTICE '  - v_tables_with_context_for_vanna (跨模態圖表視圖 - 數字+解釋)';
    RAISE NOTICE '';
    RAISE NOTICE '【核心改進 Key Improvements】';
    RAISE NOTICE '  ✅ 文檔結構優化（移除冗餘欄位）';
    RAISE NOTICE '  ✅ JSONB 動態屬性支援';
    RAISE NOTICE '  ✅ Vanna 查詢優化視圖';
    RAISE NOTICE '  ✅ 行業雙軌制邏輯封裝於視圖中';
    RAISE NOTICE '  ✅ 向後兼容（保留舊版財務表）';
    RAISE NOTICE '  ✅ 完美溯源機制（raw_artifacts）';
    RAISE NOTICE '  ✅ Graph 抽取支援（entity_relations）';
    RAISE NOTICE '============================================================';
END $$;