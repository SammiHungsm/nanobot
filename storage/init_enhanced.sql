-- SFC AI 財報分析系統 - 增強版 Schema
-- 新增表格以支援 Sample Questions

-- ===========================================
-- 0. ENUM Types for Categorical Fields (避免 LLM 猜測錯誤)
-- ===========================================
CREATE TYPE event_category_type AS ENUM (
    'Property Acquisition',
    'Listing Reform',
    'Consultation',
    'Regulatory Action',
    'Market Initiative',
    'Enforcement',
    'Other'
);

CREATE TYPE auditor_opinion_type AS ENUM (
    'Unqualified',
    'Qualified',
    'Disclaimer',
    'Adverse',
    'Not Applicable'
);

CREATE TYPE category_type_enum AS ENUM (
    'Region',
    'Business',
    'Product',
    'Segment'
);

-- ===========================================
-- 1. 更新 Companies 表 - 新增欄位
-- ===========================================
ALTER TABLE companies ADD COLUMN IF NOT EXISTS auditor VARCHAR(200);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS auditor_opinion auditor_opinion_type;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS ultimate_controlling_shareholder VARCHAR(255);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS principal_banker VARCHAR(255);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS listing_date DATE;

CREATE INDEX IF NOT EXISTS idx_company_auditor ON companies USING btree (auditor);
CREATE INDEX IF NOT EXISTS idx_company_sector ON companies USING btree (sector);

-- ===========================================
-- 2. Market Data 表 - 股價、股數、成交量
-- ===========================================
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    trade_date DATE NOT NULL,
    
    -- 價格數據
    closing_price DECIMAL(18, 6),  -- 收市價
    opening_price DECIMAL(18, 6),  -- 開市價
    high_price DECIMAL(18, 6),     -- 最高價
    low_price DECIMAL(18, 6),      -- 最低價
    
    -- 股份數據
    issued_shares BIGINT,          -- 已發行股份
    trading_volume BIGINT,         -- 成交量
    
    -- 注意：market_cap 不存儲，由 View 動態計算 (closing_price * issued_shares)
    
    -- 來源追蹤
    source_file VARCHAR(500),
    source VARCHAR(50) DEFAULT 'activex',  -- 'activex', 'annual_report', 'hkex'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_market_data UNIQUE (company_id, trade_date)
);

CREATE INDEX idx_market_company ON market_data USING btree (company_id);
CREATE INDEX idx_market_date ON market_data USING btree (trade_date);
CREATE INDEX idx_market_company_date ON market_data USING btree (company_id, trade_date);

COMMENT ON TABLE market_data IS '股價、股數、成交量數據 (用於計算 Market Cap)';

-- ===========================================
-- 3. Key Personnel 表 - 高層、委員會成員
-- ===========================================
CREATE TABLE IF NOT EXISTS key_personnel (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    
    -- 人物資料
    person_name VARCHAR(200) NOT NULL,
    person_name_zh VARCHAR(200),
    
    -- 職位
    role VARCHAR(100),              -- 'Executive Director', 'Independent Director', 'Chairman', etc.
    role_zh VARCHAR(100),
    committee VARCHAR(200),          -- 所屬委員會
    committee_position VARCHAR(100), -- 委員會職位
    
    -- 個人資料
    biography TEXT,                  -- 人物簡介 (Bio)
    biography_zh TEXT,
    age INTEGER,
    gender CHAR(1),
    nationality VARCHAR(100),
    
    -- 來源追蹤
    source_file VARCHAR(500) NOT NULL,
    source_page INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_personnel_company ON key_personnel USING btree (company_id);
CREATE INDEX idx_personnel_year ON key_personnel USING btree (year);
CREATE INDEX idx_personnel_name ON key_personnel USING btree (person_name);
CREATE INDEX idx_personnel_role ON key_personnel USING btree (role);
CREATE INDEX idx_personnel_committee ON key_personnel USING btree (committee);

COMMENT ON TABLE key_personnel IS '高層人員、董事、委員會成員資料';

-- ===========================================
-- 4. Shareholdings 表 - 持股比例
-- ===========================================
CREATE TABLE IF NOT EXISTS shareholdings (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    
    -- 股東資料
    shareholder_name VARCHAR(255) NOT NULL,
    shareholder_name_zh VARCHAR(255),
    shareholder_type VARCHAR(50),     -- 'Individual', 'Trust', 'Corporation', 'Government'
    
    -- 持股資料
    percentage_held DECIMAL(10, 4),  -- 持股百分比
    shares_held BIGINT,              -- 持股數量
    
    -- 信託資料
    trust_name VARCHAR(255),         -- 信託名稱 (如適用)
    trustee_name VARCHAR(255),       -- 受託人名稱
    
    -- 來源追蹤
    source_file VARCHAR(500) NOT NULL,
    source_page INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_shareholding UNIQUE (company_id, year, shareholder_name)
);

CREATE INDEX idx_shareholdings_company ON shareholdings USING btree (company_id);
CREATE INDEX idx_shareholdings_year ON shareholdings USING btree (year);
CREATE INDEX idx_shareholdings_name ON shareholdings USING btree (shareholder_name);

COMMENT ON TABLE shareholdings IS '主要股東持股比例';

-- ===========================================
-- 5. Specific Events 表 - 特定事件
-- ===========================================
CREATE TABLE IF NOT EXISTS specific_events (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    doc_id VARCHAR(100),             -- 關聯文檔
    
    -- 事件類別 (使用 ENUM 避免自由文本混亂)
    event_category event_category_type NOT NULL,
    event_type VARCHAR(100),
    
    -- 事件內容
    event_title VARCHAR(500),
    event_detail TEXT,               -- 詳細描述
    
    -- 日期
    event_date DATE,
    effective_date DATE,
    announcement_date DATE,
    
    -- 數值
    metric_value DECIMAL(20, 2),     -- 相關數值 (如樓層數)
    metric_unit VARCHAR(50),         -- 單位
    
    -- 來源追蹤
    source_file VARCHAR(500) NOT NULL,
    source_page INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_company ON specific_events USING btree (company_id);
CREATE INDEX idx_events_category ON specific_events USING btree (event_category);
CREATE INDEX idx_events_date ON specific_events USING btree (event_date);

COMMENT ON TABLE specific_events IS '特定事件記錄 (買Office、Listing Reform、Consultation等)';

-- ===========================================
-- 6. Revenue Breakdown 表 - 收入分佈
-- ===========================================
CREATE TABLE IF NOT EXISTS revenue_breakdown (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    
    -- 地區/業務分佈
    category VARCHAR(100) NOT NULL,  -- 地區: 'Canada', 'Asia', 'Australia' / 業務: 'Retail', 'Wholesale'
    category_type category_type_enum,  -- 使用 ENUM: 'Region', 'Business', 'Product', 'Segment'
    
    -- 數值
    percentage DECIMAL(10, 4),       -- 百分比
    amount DECIMAL(20, 2),           -- 金額
    currency VARCHAR(10),            -- 貨幣 (重要：加總時必須 GROUP BY currency)
    
    -- 子分類 (如 Asia 內的 Retail Sector)
    sub_category VARCHAR(100),
    sub_percentage DECIMAL(10, 4),
    
    -- 來源追蹤
    source_file VARCHAR(500) NOT NULL,
    source_page INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_revenue_breakdown UNIQUE (company_id, year, category, category_type)
);

CREATE INDEX idx_revenue_company ON revenue_breakdown USING btree (company_id);
CREATE INDEX idx_revenue_year ON revenue_breakdown USING btree (year);
CREATE INDEX idx_revenue_category ON revenue_breakdown USING btree (category);

COMMENT ON TABLE revenue_breakdown IS '收入分佈 (地區、業務)';

-- ===========================================
-- 7. Debt Maturity 表 - 債務到期
-- ===========================================
CREATE TABLE IF NOT EXISTS debt_maturity (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    
    maturity_year INTEGER NOT NULL,  -- 到期年份
    maturity_date DATE,              -- 到期日期
    
    amount DECIMAL(20, 2),           -- 金額
    currency VARCHAR(10) DEFAULT 'HKD',
    debt_type VARCHAR(100),          -- 'Bank Loan', 'Bond', 'Note'
    
    -- 來源追蹤
    source_file VARCHAR(500) NOT NULL,
    source_page INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_debt_company ON debt_maturity USING btree (company_id);
CREATE INDEX idx_debt_year ON debt_maturity USING btree (year);
CREATE INDEX idx_debt_maturity ON debt_maturity USING btree (maturity_year);

COMMENT ON TABLE debt_maturity IS '債務到期時間表';

-- ===========================================
-- 8. Listing Applications 表 - 上市申請 (宏觀市場數據)
-- ===========================================
CREATE TABLE IF NOT EXISTS listing_applications (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,  -- 可為 NULL (宏觀數據不屬於特定公司)
    doc_id VARCHAR(100),
    
    year INTEGER NOT NULL,
    application_count INTEGER,       -- 申請數量
    approved_count INTEGER,          -- 批准數量
    rejected_count INTEGER,          -- 拒絕數量
    
    -- 來源追蹤
    source_file VARCHAR(500) NOT NULL,
    source_page INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE listing_applications IS '上市申請統計 (company_id 可為 NULL 表示宏觀市場數據)';

CREATE INDEX idx_listing_year ON listing_applications USING btree (year);

COMMENT ON TABLE listing_applications IS '上市申請統計';

-- ===========================================
-- 9. Views for Vanna 查詢
-- ===========================================

-- BioTech 公司視圖 (Market Cap 計算)
CREATE OR REPLACE VIEW v_biotech_market_cap AS
SELECT 
    c.stock_code,
    c.name_en AS company_name,
    c.name_zh AS company_name_zh,
    m.closing_price,
    m.issued_shares,
    (m.closing_price * m.issued_shares) AS market_cap,
    m.trade_date
FROM companies c
JOIN market_data m ON c.id = m.company_id
WHERE c.sector = 'BioTech'
ORDER BY market_cap DESC;

-- BioTech 財務視圖
CREATE OR REPLACE VIEW v_biotech_financials AS
SELECT 
    c.stock_code,
    c.name_en AS company_name,
    c.sector,
    c.auditor,
    c.auditor_opinion,
    c.ultimate_controlling_shareholder,
    c.principal_banker,
    fm.year,
    fm.metric_name,
    fm.value,
    fm.unit
FROM companies c
JOIN financial_metrics fm ON c.id = fm.company_id
WHERE c.sector = 'BioTech'
ORDER BY c.stock_code, fm.year DESC;

-- ===========================================
-- 10. Trigger for updated_at
-- ===========================================
CREATE TRIGGER update_market_data_updated_at BEFORE UPDATE ON market_data
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_personnel_updated_at BEFORE UPDATE ON key_personnel
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===========================================
-- Schema Version
-- ===========================================
CREATE TABLE IF NOT EXISTS schema_version (
    version VARCHAR(20) PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT INTO schema_version (version, description) VALUES 
    ('2.0.0', 'Enhanced schema for Vanna Text-to-SQL with market_data, key_personnel, shareholdings, specific_events')
ON CONFLICT (version) DO NOTHING;

COMMENT ON SCHEMA public IS 'SFC AI 財報分析系統 - 增強版 Schema v2.0.0 (支援 Vanna Text-to-SQL)';