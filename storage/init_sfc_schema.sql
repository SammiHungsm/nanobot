-- ============================================================
-- SFC BioTech RAG Schema Extension
-- ============================================================
--
-- 【用途】SFC 監管科技 PoC - 生物科技板塊查詢
--
-- 【設計理念】
-- 1. 保留原有 nanobot schema (companies, documents 等)
-- 2. 新增 SFC 專用表 (annual_financials, daily_market_data)
-- 3. 支援 Text-to-SQL 查詢場景
--
-- 【版本】v1.0 - 2026-04-26
-- ============================================================

-- ============================================================
-- 【表 1: annual_financials 年度財務及合規數據表】
-- 【功能 Purpose】
-- 記錄各公司不同年度的財務指標與合規審計資訊
-- 對應年報數據，支援 SFC Sample Questions
-- ============================================================
CREATE TABLE IF NOT EXISTS annual_financials (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    fiscal_year INT NOT NULL,

    -- 【財務指標】(對應 Q1.6 - Q1.9, Q4.3)
    total_revenue NUMERIC(20, 2),           -- 總收入
    profit_attributable NUMERIC(20, 2),     -- 歸屬於普通股股東利潤
    fixed_assets NUMERIC(20, 2),            -- 固定資產
    total_liabilities NUMERIC(20, 2),       -- 總負債 (對應 Q3.2)
    cash_at_bank NUMERIC(20, 2),            -- 銀行及現金結餘 (對應 Q2.1)
    total_equity NUMERIC(20, 2),            -- 股東權益
    total_assets NUMERIC(20, 2),            -- 總資產

    -- 【企業管治與合規資訊】(對應 Q3.3, Q3.4, Q3.5, Q4.4)
    auditor VARCHAR(150),                   -- 核數師/審計師
    auditor_opinion VARCHAR(100),           -- 審計意見 (Unqualified, Qualified Opinion)
    principal_banker VARCHAR(150),          -- 主要往來銀行
    controlling_shareholder VARCHAR(255),   -- 最終控股股東
    company_secretary VARCHAR(150),         -- 公司秘書

    -- 【其他重要資訊】
    listing_date DATE,                      -- 上市日期
    financial_year_end DATE,                -- 財年結束日期
    audit_fee NUMERIC(20, 2),               -- 審計費用

    -- 【元數據】
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (stock_code, fiscal_year)
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_annual_financials_stock_code ON annual_financials(stock_code);
CREATE INDEX IF NOT EXISTS idx_annual_financials_year ON annual_financials(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_annual_financials_auditor ON annual_financials(auditor);
CREATE INDEX IF NOT EXISTS idx_annual_financials_opinion ON annual_financials(auditor_opinion);
CREATE INDEX IF NOT EXISTS idx_annual_financials_banker ON annual_financials(principal_banker);

-- 【外鍵關聯到 companies 表】
ALTER TABLE annual_financials
ADD CONSTRAINT fk_annual_financials_company
FOREIGN KEY (stock_code) REFERENCES companies(stock_code) ON DELETE CASCADE;

-- ============================================================
-- 【表 2: debt_maturities 債務到期明細表】
-- 【功能 Purpose】
-- 處理「2027 年到期債務總額」等問題 (Q1.10)
-- ============================================================
CREATE TABLE IF NOT EXISTS debt_maturities (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    report_year INT NOT NULL,               -- 報告年份
    maturity_year INT NOT NULL,             -- 到期年份
    debt_amount NUMERIC(20, 2),             -- 債務金額
    debt_type VARCHAR(100),                 -- 債務類型 (bank_loan, bond, etc.)
    currency VARCHAR(10) DEFAULT 'HKD',     -- 貨幣單位

    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_debt_maturities_stock ON debt_maturities(stock_code);
CREATE INDEX IF NOT EXISTS idx_debt_maturities_maturity_year ON debt_maturities(maturity_year);
CREATE INDEX IF NOT EXISTS idx_debt_maturities_report_year ON debt_maturities(report_year);

-- 【外鍵】
ALTER TABLE debt_maturities
ADD CONSTRAINT fk_debt_maturities_company
FOREIGN KEY (stock_code) REFERENCES companies(stock_code) ON DELETE CASCADE;

-- ============================================================
-- 【表 3: daily_market_data 每日市場交易數據表】
-- 【功能 Purpose】
-- 處理 2022 年歷史交易數據庫整合
-- 支援 Top 10 市值計算、交易圖表等 (Part 4 所有問題)
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_market_data (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_code VARCHAR(10) NOT NULL,

    -- 【價格數據】
    opening_price NUMERIC(10, 3),           -- 開盤價
    closing_price NUMERIC(10, 3),           -- 收盤價
    high_price NUMERIC(10, 3),              -- 最高價
    low_price NUMERIC(10, 3),               -- 最低價

    -- 【交易數據】
    transaction_volume BIGINT,              -- 交易量
    transaction_value NUMERIC(20, 2),       -- 交易金額
    number_of_trades INTEGER,               -- 交易筆數

    -- 【股本數據】(用於計算市值)
    issued_shares BIGINT,                   -- 發行股數
    market_cap NUMERIC(20, 2),              -- 市值 (收盤價 × 發行股數)

    -- 【元數據】
    data_source VARCHAR(50),                -- 數據來源
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (trade_date, stock_code)
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_daily_market_date ON daily_market_data(trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_market_stock ON daily_market_data(stock_code);
CREATE INDEX IF NOT EXISTS idx_daily_market_stock_date ON daily_market_data(stock_code, trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_market_year ON daily_market_data(EXTRACT(YEAR FROM trade_date));

-- 【外鍵】
ALTER TABLE daily_market_data
ADD CONSTRAINT fk_daily_market_company
FOREIGN KEY (stock_code) REFERENCES companies(stock_code) ON DELETE CASCADE;

-- ============================================================
-- 【表 4: biotech_companies 生物科技公司專用表】
-- 【功能 Purpose】
-- 存儲生物科技板塊特有資訊
-- ============================================================
CREATE TABLE IF NOT EXISTS biotech_companies (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL UNIQUE,

    -- 【研發資訊】
    r_and_d_expense NUMERIC(20, 2),         -- 研發開支
    r_and_d_percentage NUMERIC(10, 4),      -- 研發佔收入比例
    clinical_trials INTEGER,                -- 臨床試驗數量
    patents_count INTEGER,                  -- 專利數量

    -- 【產品管線】
    pipeline_stage VARCHAR(50),             -- 產品管線階段 (pre-clinical, Phase I, II, III)
    key_products JSONB,                     -- 主要產品列表

    -- 【融資資訊】
    last_funding_round VARCHAR(50),         -- 最近融資輪次
    last_funding_amount NUMERIC(20, 2),     -- 最近融資金額

    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 【索引】
CREATE INDEX IF NOT EXISTS idx_biotech_stock ON biotech_companies(stock_code);
CREATE INDEX IF NOT EXISTS idx_biotech_pipeline ON biotech_companies(pipeline_stage);

-- 【外鍵】
ALTER TABLE biotech_companies
ADD CONSTRAINT fk_biotech_company
FOREIGN KEY (stock_code) REFERENCES companies(stock_code) ON DELETE CASCADE;

-- ============================================================
-- 【視圖 Views】
-- ============================================================

-- 【視圖: v_annual_financials_summary - 年度財務摘要】
CREATE OR REPLACE VIEW v_annual_financials_summary AS
SELECT
    af.id,
    af.stock_code,
    c.name_en AS company_name,
    c.name_zh AS company_name_zh,
    af.fiscal_year,
    af.total_revenue,
    af.profit_attributable,
    af.total_liabilities,
    af.cash_at_bank,
    af.auditor,
    af.auditor_opinion,
    af.principal_banker,
    af.controlling_shareholder
FROM annual_financials af
LEFT JOIN companies c ON af.stock_code = c.stock_code;

-- 【視圖: v_market_cap_ranking - 市值排名】
CREATE OR REPLACE VIEW v_market_cap_ranking AS
SELECT
    dm.stock_code,
    c.name_en AS company_name,
    dm.trade_date,
    dm.closing_price,
    dm.issued_shares,
    dm.market_cap,
    RANK() OVER (ORDER BY dm.market_cap DESC) AS market_cap_rank
FROM daily_market_data dm
LEFT JOIN companies c ON dm.stock_code = c.stock_code
WHERE dm.trade_date = (SELECT MAX(trade_date) FROM daily_market_data);

-- 【視圖: v_biotech_summary - 生物科技公司摘要】
CREATE OR REPLACE VIEW v_biotech_summary AS
SELECT
    bc.id,
    bc.stock_code,
    c.name_en AS company_name,
    c.name_zh AS company_name_zh,
    c.sector,
    bc.r_and_d_expense,
    bc.r_and_d_percentage,
    bc.pipeline_stage,
    af.total_revenue,
    af.auditor,
    af.auditor_opinion
FROM biotech_companies bc
LEFT JOIN companies c ON bc.stock_code = c.stock_code
LEFT JOIN annual_financials af ON bc.stock_code = af.stock_code
    AND af.fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE) - 1;

-- ============================================================
-- 【觸發器 Triggers】
-- ============================================================

-- 【觸發器: 自動計算市值】
CREATE OR REPLACE FUNCTION calculate_market_cap()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.closing_price IS NOT NULL AND NEW.issued_shares IS NOT NULL THEN
        NEW.market_cap := NEW.closing_price * NEW.issued_shares;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_calculate_market_cap ON daily_market_data;
CREATE TRIGGER trg_calculate_market_cap
    BEFORE INSERT OR UPDATE ON daily_market_data
    FOR EACH ROW
    EXECUTE FUNCTION calculate_market_cap();

-- 【觸發器: 更新 updated_at 時間戳】
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_annual_financials_updated_at ON annual_financials;
CREATE TRIGGER trg_annual_financials_updated_at
    BEFORE UPDATE ON annual_financials
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_biotech_companies_updated_at ON biotech_companies;
CREATE TRIGGER trg_biotech_companies_updated_at
    BEFORE UPDATE ON biotech_companies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- 【初始化完成通知】
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'SFC BioTech RAG Schema 擴展完成 (v1.0)';
    RAISE NOTICE '============================================================';
    RAISE NOTICE '';
    RAISE NOTICE '【新增表 New Tables】';
    RAISE NOTICE '  - annual_financials (年度財務及合規數據)';
    RAISE NOTICE '  - debt_maturities (債務到期明細)';
    RAISE NOTICE '  - daily_market_data (每日市場交易數據)';
    RAISE NOTICE '  - biotech_companies (生物科技公司專用)';
    RAISE NOTICE '';
    RAISE NOTICE '【新增視圖 New Views】';
    RAISE NOTICE '  - v_annual_financials_summary (年度財務摘要)';
    RAISE NOTICE '  - v_market_cap_ranking (市值排名)';
    RAISE NOTICE '  - v_biotech_summary (生物科技公司摘要)';
    RAISE NOTICE '';
    RAISE NOTICE '【支援查詢場景 Supported Query Scenarios】';
    RAISE NOTICE '  - 5 年財務數據比較';
    RAISE NOTICE '  - Top 10 市值計算';
    RAISE NOTICE '  - 特定年份每日交易圖表';
    RAISE NOTICE '  - 核數師篩選';
    RAISE NOTICE '  - 保留意見 (Qualified Opinion) 篩選';
    RAISE NOTICE '============================================================';
END $$;
