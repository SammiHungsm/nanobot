-- ==============================================================================
-- SFC AI 財報分析系統 - 終極乾淨版 Schema (No RAG, Pure Vanna Text-to-SQL)
-- ==============================================================================

-- 1. 建立 ENUM 類型 (防止 LLM 亂作字眼)
CREATE TYPE auditor_opinion_type AS ENUM ('Unqualified', 'Qualified', 'Disclaimer', 'Adverse', 'Not Applicable');
CREATE TYPE event_category_type AS ENUM ('Property Acquisition', 'Listing Reform', 'Consultation', 'Share Buy-back', 'Product Launch');
CREATE TYPE category_type_enum AS ENUM ('Region', 'Business', 'Product', 'Segment');

-- ===========================================
-- ZONE 1: 業務與財務數據區 (Vanna 專用大腦)
-- ===========================================

-- 1. Companies (公司主檔 - 漸進式資料充實架構)
-- 🔧 支援多源名稱：恆指報表 (index) + PDF 擷取 (extracted)
CREATE TABLE public.companies (
 id serial4 NOT NULL PRIMARY KEY,
 
 -- 🎯 多源名稱欄位 (Progressive Data Enrichment)
 -- 優先順序：index > extracted，透過 v_companies_resolved View 統一存取
 name_en_index varchar(255) NULL,             -- 來自恆指報表（絕對準確）
 name_en_extracted varchar(255) NULL,         -- 從年報 PDF 擷取的英文名
 name_zh_extracted varchar(255) NULL,         -- 從年報 PDF 擷取的中文名
 
 -- 舊欄位保留（向後兼容，逐步遷移）
 name_en varchar(255) NULL,                   -- 已放寬 NOT NULL，改由 View 計算
 name_zh varchar(255) NULL,
 
 stock_code varchar(20) NULL UNIQUE,
 industry varchar(100) NULL,
 sector varchar(100) NULL,
 listing_status varchar(50) DEFAULT 'listed',
 auditor varchar(200) NULL,
 auditor_opinion auditor_opinion_type NULL,
 ultimate_controlling_shareholder varchar(255) NULL,
 principal_banker varchar(255) NULL,
 listing_date date NULL,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP,
 updated_at timestamp DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_company_sector ON public.companies USING btree (sector);
CREATE INDEX idx_company_stock ON public.companies USING btree (stock_code);

-- 🎯 公司名稱解析視圖 (Vanna 查詢專用)
-- 邏輯：優先使用 index 的名字，沒有的話再用 extracted 的英文名
CREATE OR REPLACE VIEW v_companies_resolved AS
SELECT 
    id,
    stock_code,
    COALESCE(name_en_index, name_en_extracted, name_en) AS display_name_en,
    COALESCE(name_zh_extracted, name_zh) AS display_name_zh,
    industry,
    sector,
    auditor,
    auditor_opinion,
    ultimate_controlling_shareholder,
    principal_banker,
    listing_status,
    listing_date
FROM companies;

-- 註解說明
COMMENT ON COLUMN public.companies.name_en_index IS '來自恆指報表的公司英文名（權威來源）';
COMMENT ON COLUMN public.companies.name_en_extracted IS '從年報 PDF 擷取的英文名（可能不準確）';
COMMENT ON COLUMN public.companies.name_zh_extracted IS '從年報 PDF 擷取的中文名';
COMMENT ON VIEW v_companies_resolved IS 'Vanna 專用視圖：自動選取最佳公司名稱（index > extracted）';

-- 2. Market Data (市場數據)
CREATE TABLE public.market_data (
 id serial4 NOT NULL PRIMARY KEY,
 company_id int4 NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 trade_date date NOT NULL,
 closing_price numeric(18, 6) NULL,
 opening_price numeric(18, 6) NULL,
 high_price numeric(18, 6) NULL,
 low_price numeric(18, 6) NULL,
 issued_shares int8 NULL,
 trading_volume int8 NULL,
 source_file varchar(500) NULL,
 source varchar(50) DEFAULT 'activex',
 created_at timestamp DEFAULT CURRENT_TIMESTAMP,
 updated_at timestamp DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT unique_market_data UNIQUE (company_id, trade_date)
);

-- 3. Financial Metrics (通用財務指標)
-- 🔧 修正：新增標準化欄位，解決跨公司比較的「數學災難」
CREATE TABLE public.financial_metrics (
 id serial4 NOT NULL PRIMARY KEY,
 company_id int4 NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 year int4 NOT NULL,
 fiscal_period varchar(10) NOT NULL,
 metric_name varchar(100) NOT NULL,           -- 標準化後的指標名稱（由 EntityResolver 產生）
 metric_name_zh varchar(100) NOT NULL,        -- 標準化後的中文名稱
 original_metric_name varchar(200) NULL,      -- 財報上的原始名稱（供溯源）
 value float8 NOT NULL,                       -- 原始數值
 unit varchar(20) NOT NULL,                   -- 原始單位（如 'RMB '000', 'HKD Million'）
 standardized_value numeric(20,2) NOT NULL,   -- 🔧 標準化後的絕對數值（統一為最小單位，如元）
 standardized_currency varchar(10) NOT NULL DEFAULT 'HKD', -- 🔧 統一幣別（預設港幣）
 category varchar(50) NULL,
 source_file varchar(500) NOT NULL,
 source_page int4 NULL,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP,
 updated_at timestamp DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT unique_metric UNIQUE (company_id, year, fiscal_period, metric_name)
);
CREATE INDEX idx_financial_metrics_name ON public.financial_metrics USING btree (metric_name);
CREATE INDEX idx_financial_metrics_standardized ON public.financial_metrics USING btree (standardized_value);

-- 4. Key Personnel (關鍵人物)
CREATE TABLE public.key_personnel (
 id serial4 NOT NULL PRIMARY KEY,
 company_id int4 NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 year int4 NOT NULL,
 person_name varchar(200) NOT NULL,
 person_name_zh varchar(200) NULL,
 role varchar(100) NULL,
 committee varchar(200) NULL,
 biography text NULL,
 source_file varchar(500) NOT NULL,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP,
 updated_at timestamp DEFAULT CURRENT_TIMESTAMP
);

-- 5. Shareholdings (股權架構)
CREATE TABLE public.shareholdings (
 id serial4 NOT NULL PRIMARY KEY,
 company_id int4 NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 year int4 NOT NULL,
 shareholder_name varchar(255) NOT NULL,
 shareholder_type varchar(50) NULL,
 percentage_held numeric(10, 4) NULL,
 shares_held int8 NULL,
 trust_name varchar(255) NULL,
 trustee_name varchar(255) NULL,
 source_file varchar(500) NOT NULL,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP
);

-- 6. Specific Events (特定事件)
CREATE TABLE public.specific_events (
 id serial4 NOT NULL PRIMARY KEY,
 company_id int4 NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 doc_id varchar(100) NULL,
 event_category event_category_type NOT NULL,
 event_title varchar(500) NULL,
 event_detail text NULL,
 metric_value numeric(20, 2) NULL,
 metric_unit varchar(50) NULL,
 source_file varchar(500) NOT NULL,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP
);

-- 7. Revenue Breakdown (收入分佈)
CREATE TABLE public.revenue_breakdown (
 id serial4 NOT NULL PRIMARY KEY,
 company_id int4 NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 year int4 NOT NULL,
 category varchar(100) NOT NULL,
 category_type category_type_enum NULL,
 percentage numeric(10, 4) NULL,
 amount numeric(20, 2) NULL,
 currency varchar(10) NULL,
 source_file varchar(500) NOT NULL,
 source_page int4 NULL,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT unique_revenue_breakdown UNIQUE (company_id, year, category, category_type)
);
CREATE INDEX idx_revenue_company ON public.revenue_breakdown USING btree (company_id);
CREATE INDEX idx_revenue_year ON public.revenue_breakdown USING btree (year);
CREATE INDEX idx_revenue_category ON public.revenue_breakdown USING btree (category);

-- 8. Debt Maturity (債務到期)
CREATE TABLE public.debt_maturity (
 id serial4 NOT NULL PRIMARY KEY,
 company_id int4 NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 year int4 NOT NULL,
 maturity_year int4 NOT NULL,
 amount numeric(20, 2) NULL,
 currency varchar(10) DEFAULT 'HKD',
 debt_type varchar(100) NULL,
 source_file varchar(500) NOT NULL,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP
);

-- 9. Listing Applications (上市申請)
CREATE TABLE public.listing_applications (
 id serial4 NOT NULL PRIMARY KEY,
 company_id int4 NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 doc_id varchar(100) NULL,
 year int4 NOT NULL,
 application_count int4 NULL,
 approved_count int4 NULL,
 rejected_count int4 NULL,
 source_file varchar(500) NOT NULL,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================
-- ZONE 2: 檔案與任務管理區 (OpenDataLoader 後台)
-- ===========================================

CREATE TABLE public.documents (
 id serial4 NOT NULL PRIMARY KEY,
 doc_id varchar(100) NOT NULL UNIQUE,
 company_id int4 NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 title varchar(500) NOT NULL,
 document_type varchar(50) NULL,
 year int4 NULL,
 file_path varchar(500) NOT NULL UNIQUE,
 file_hash varchar(64) NULL,
 file_size_bytes int4 NULL,
 processing_status varchar(50) DEFAULT 'pending',
 processing_error text NULL,
 processing_completed_at timestamp NULL,
 total_chunks int4 NULL,
 total_artifacts int4 NULL,
 uploaded_at timestamp DEFAULT CURRENT_TIMESTAMP,
 updated_at timestamp DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE public.processing_queue (
 id serial4 NOT NULL PRIMARY KEY,
 doc_id varchar(100) NULL REFERENCES public.documents(doc_id) ON DELETE CASCADE,
 task_type varchar(50) NOT NULL,
 status varchar(50) DEFAULT 'pending',
 priority int4 DEFAULT 0,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP
);

-- 🚨 注意：已經安全移除 linked_chunk_id，解除咗 RAG 綁定危機 🚨
CREATE TABLE public.raw_artifacts (
 id serial4 NOT NULL PRIMARY KEY,
 artifact_id varchar(100) NOT NULL UNIQUE,
 doc_id varchar(100) NOT NULL,
 company_id int4 NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 file_type varchar(50) NOT NULL,
 file_path varchar(500) NOT NULL,
 linked_metric_id int4 NULL REFERENCES public.financial_metrics(id),
 source_file varchar(500) NOT NULL,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP
);

-- 10. Document Pages (PDF 頁面兜底表)
CREATE TABLE public.document_pages (
 id serial4 NOT NULL PRIMARY KEY,
 company_id int4 NULL REFERENCES public.companies(id) ON DELETE CASCADE,
 doc_id varchar(100) NULL,
 year int4 NULL,
 page_num int4 NOT NULL,
 markdown_content text NULL,
 content_type varchar(50) DEFAULT 'markdown',
 has_images bool DEFAULT FALSE,
 has_charts bool DEFAULT FALSE,
 source_file varchar(500) NULL,
 created_at timestamp DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT unique_document_page UNIQUE (company_id, year, page_num, source_file)
);
CREATE INDEX idx_document_pages_doc_id ON public.document_pages USING btree (doc_id);
CREATE INDEX idx_document_pages_company_year ON public.document_pages USING btree (company_id, year);

-- ===========================================
-- ZONE 3: Views (方便 Vanna 查詢)
-- ===========================================

CREATE OR REPLACE VIEW v_biotech_market_cap AS
SELECT 
 c.stock_code,
 c.name_en AS company_name,
 m.closing_price,
 m.issued_shares,
 (m.closing_price * m.issued_shares) AS market_cap,
 m.trade_date
FROM companies c
JOIN market_data m ON c.id = m.company_id
WHERE c.sector = 'BioTech'
ORDER BY market_cap DESC;

CREATE OR REPLACE VIEW v_biotech_financials AS
SELECT 
 c.stock_code,
 c.name_en AS company_name,
 c.auditor,
 c.auditor_opinion,
 fm.year,
 fm.metric_name,
 fm.value,
 fm.unit
FROM companies c
JOIN financial_metrics fm ON c.id = fm.company_id
WHERE c.sector = 'BioTech'
ORDER BY c.stock_code, fm.year DESC;