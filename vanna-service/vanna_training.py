"""
Vanna Training Data - Complete Training for Annual Report Analysis
包含：DDL、Documentation、SQL Examples (基於所有 Sample Questions)
"""

# ===========================================
# 1. DDL Training - 資料庫結構
# ===========================================

DDL_TRAINING = [
    # Companies 表
    """
    CREATE TABLE companies (
        id SERIAL PRIMARY KEY,
        name_en VARCHAR(255) NOT NULL,
        name_zh VARCHAR(255),
        stock_code VARCHAR(20) UNIQUE,
        industry VARCHAR(100),
        sector VARCHAR(100),
        auditor VARCHAR(200),
        auditor_opinion VARCHAR(50),
        ultimate_controlling_shareholder VARCHAR(255),
        principal_banker VARCHAR(255),
        listing_status VARCHAR(50) DEFAULT 'listed',
        listing_date DATE
    );
    """,
    
    # Financial Metrics 表
    """
    CREATE TABLE financial_metrics (
        id SERIAL PRIMARY KEY,
        company_id INTEGER NOT NULL REFERENCES companies(id),
        year INTEGER NOT NULL,
        fiscal_period VARCHAR(10) NOT NULL,
        metric_name VARCHAR(100) NOT NULL,
        metric_name_zh VARCHAR(100) NOT NULL,
        value DOUBLE PRECISION NOT NULL,
        unit VARCHAR(20) NOT NULL,
        category VARCHAR(50),
        source_file VARCHAR(500),
        source_page INTEGER
    );
    """,
    
    # Market Data 表
    """
    CREATE TABLE market_data (
        id SERIAL PRIMARY KEY,
        company_id INTEGER NOT NULL REFERENCES companies(id),
        trade_date DATE NOT NULL,
        closing_price DECIMAL(18, 6),
        opening_price DECIMAL(18, 6),
        high_price DECIMAL(18, 6),
        low_price DECIMAL(18, 6),
        issued_shares BIGINT,
        trading_volume BIGINT,
        market_cap DECIMAL(20, 2)
    );
    """,
    
    # Key Personnel 表
    """
    CREATE TABLE key_personnel (
        id SERIAL PRIMARY KEY,
        company_id INTEGER REFERENCES companies(id),
        year INTEGER NOT NULL,
        person_name VARCHAR(200) NOT NULL,
        person_name_zh VARCHAR(200),
        role VARCHAR(100),
        role_zh VARCHAR(100),
        committee VARCHAR(200),
        committee_position VARCHAR(100),
        biography TEXT,
        biography_zh TEXT,
        age INTEGER,
        source_file VARCHAR(500),
        source_page INTEGER
    );
    """,
    
    # Shareholdings 表
    """
    CREATE TABLE shareholdings (
        id SERIAL PRIMARY KEY,
        company_id INTEGER NOT NULL REFERENCES companies(id),
        year INTEGER NOT NULL,
        shareholder_name VARCHAR(255) NOT NULL,
        shareholder_name_zh VARCHAR(255),
        shareholder_type VARCHAR(50),
        percentage_held DECIMAL(10, 4),
        shares_held BIGINT,
        trust_name VARCHAR(255),
        trustee_name VARCHAR(255),
        source_file VARCHAR(500),
        source_page INTEGER
    );
    """,
    
    # Specific Events 表
    """
    CREATE TABLE specific_events (
        id SERIAL PRIMARY KEY,
        company_id INTEGER REFERENCES companies(id),
        doc_id VARCHAR(100),
        event_category VARCHAR(100) NOT NULL,
        event_type VARCHAR(100),
        event_title VARCHAR(500),
        event_detail TEXT,
        event_date DATE,
        effective_date DATE,
        metric_value DECIMAL(20, 2),
        metric_unit VARCHAR(50),
        source_file VARCHAR(500),
        source_page INTEGER
    );
    """,
    
    # Revenue Breakdown 表
    """
    CREATE TABLE revenue_breakdown (
        id SERIAL PRIMARY KEY,
        company_id INTEGER NOT NULL REFERENCES companies(id),
        year INTEGER NOT NULL,
        category VARCHAR(100) NOT NULL,
        category_type VARCHAR(50),
        percentage DECIMAL(10, 4),
        amount DECIMAL(20, 2),
        currency VARCHAR(10),
        sub_category VARCHAR(100),
        sub_percentage DECIMAL(10, 4),
        source_file VARCHAR(500),
        source_page INTEGER
    );
    """,
    
    # Debt Maturity 表
    """
    CREATE TABLE debt_maturity (
        id SERIAL PRIMARY KEY,
        company_id INTEGER NOT NULL REFERENCES companies(id),
        year INTEGER NOT NULL,
        maturity_year INTEGER NOT NULL,
        maturity_date DATE,
        amount DECIMAL(20, 2),
        currency VARCHAR(10) DEFAULT 'HKD',
        debt_type VARCHAR(100),
        source_file VARCHAR(500),
        source_page INTEGER
    );
    """,
    
    # Listing Applications 表
    """
    CREATE TABLE listing_applications (
        id SERIAL PRIMARY KEY,
        company_id INTEGER REFERENCES companies(id),
        doc_id VARCHAR(100),
        year INTEGER NOT NULL,
        application_count INTEGER,
        approved_count INTEGER,
        rejected_count INTEGER,
        source_file VARCHAR(500),
        source_page INTEGER
    );
    """,
]

# ===========================================
# 2. Documentation Training - 商業邏輯
# ===========================================

DOCUMENTATION_TRAINING = [
    # Market Cap 計算
    "Market Capital is calculated by multiplying the closing price by the issued shares. Formula: Market Capital = closing_price * issued_shares",
    
    # BioTech Sector
    "The BioTech list is flexible. Always query the companies table where sector = 'BioTech' instead of using a hardcoded list of stock codes.",
    "BioTech sector includes pharmaceutical companies, biotechnology firms, medical device manufacturers, and healthcare technology companies.",
    
    # Auditor Opinion
    "Auditor opinion types include: 'Unqualified' (clean opinion), 'Qualified' (with reservations), 'Disclaimer' (unable to express opinion), 'Adverse' (material misstatements).",
    "A 'Qualified Opinion' indicates that the auditor has reservations about certain aspects of the financial statements.",
    
    # Financial Periods
    "Fiscal periods: 'FY' = Full Year, 'H1' = First Half, 'H2' = Second Half, 'Q1/Q2/Q3/Q4' = Quarters.",
    
    # Stock Codes
    "Hong Kong stock codes are typically 4-5 digits, e.g., '00001' for CK Hutchison, '00700' for Tencent.",
    "Stock codes in the database do NOT include the '.HK' suffix.",
    
    # Revenue Categories
    "Revenue breakdown categories can be by region (e.g., 'Canada', 'Asia', 'Australia') or by business segment (e.g., 'Retail', 'Wholesale').",
    
    # Shareholding
    "Trust holdings are recorded with both the trust name and the trustee name. For example, 'Li Ka-Shing Unity Trust' with trustee 'Li Ka-Shing Unity Trustee Company Limited'.",
    
    # Principal Banker
    "Principal banker refers to the main bank or banks that provide significant banking services to the company.",
    
    # Ultimate Controlling Shareholder
    "Ultimate controlling shareholder is the person or entity that has ultimate control over the company, which may be different from the direct shareholders.",
]

# ===========================================
# 3. SQL Training - Sample Questions
# ===========================================

SQL_TRAINING = [
    # ===========================================
    # Stock 00001 (CK Hutchison) 2023 Questions
    # ===========================================
    
    # Q: What is the percentage of shareholding of Li Ka-Shing Unity Trustee Company Limited ("TUT1") as trustee of The Li Ka-Shing Unity Trust ("UT1")?
    {
        "question": "What is the percentage of shareholding of Li Ka-Shing Unity Trustee Company Limited as trustee of The Li Ka-Shing Unity Trust in CK Hutchison?",
        "sql": """
            SELECT shareholder_name, trust_name, percentage_held 
            FROM shareholdings 
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
            AND trustee_name LIKE '%Li Ka-Shing Unity Trustee%'
            AND trust_name LIKE '%Li Ka-Shing Unity Trust%';
        """
    },
    
    # Q: Can you list the executive directors?
    {
        "question": "List all executive directors of CK Hutchison",
        "sql": """
            SELECT person_name, role, committee 
            FROM key_personnel 
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
            AND role LIKE '%Executive Director%'
            ORDER BY person_name;
        """
    },
    
    # Q: What is the % of total revenue from Canada based on the chart?
    {
        "question": "What is the percentage of total revenue from Canada for CK Hutchison?",
        "sql": """
            SELECT category, percentage, amount 
            FROM revenue_breakdown 
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
            AND year = 2023 
            AND category = 'Canada'
            AND category_type = 'Region';
        """
    },
    
    # Q: What is the % and amount of total revenue from Asia, Australia & Others?
    {
        "question": "What is the percentage and amount of total revenue from Asia, Australia and Others for CK Hutchison?",
        "sql": """
            SELECT category, percentage, amount 
            FROM revenue_breakdown 
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
            AND year = 2023 
            AND category IN ('Asia', 'Australia', 'Others')
            AND category_type = 'Region';
        """
    },
    
    # Q: Within Asia, Australia & Others, what is the % of revenue for Retail Sector?
    {
        "question": "Within Asia Australia and Others, what is the percentage of revenue for Retail Sector for CK Hutchison?",
        "sql": """
            SELECT category, sub_category, sub_percentage 
            FROM revenue_breakdown 
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
            AND year = 2023 
            AND category IN ('Asia', 'Australia', 'Others')
            AND sub_category LIKE '%Retail%';
        """
    },
    
    # Q: Please provide the profit and loss figures with 5 comparative periods?
    {
        "question": "Provide profit and loss figures for CK Hutchison for the last 5 years",
        "sql": """
            SELECT year, metric_name, value, unit 
            FROM financial_metrics 
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
            AND category IN ('revenue', 'profit', 'loss')
            AND fiscal_period = 'FY'
            ORDER BY year DESC, metric_name
            LIMIT 25;
        """
    },
    
    # Q: Please provide profit attributable to ordinary shareholders from 2019 – 2023?
    {
        "question": "Provide profit attributable to ordinary shareholders for CK Hutchison from 2019 to 2023",
        "sql": """
            SELECT year, value, unit 
            FROM financial_metrics 
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
            AND metric_name LIKE '%profit attributable%shareholder%'
            AND year BETWEEN 2019 AND 2023
            AND fiscal_period = 'FY'
            ORDER BY year;
        """
    },
    
    # Q: Please provide revenue figures from 2019 – 2023?
    {
        "question": "Provide revenue figures for CK Hutchison from 2019 to 2023",
        "sql": """
            SELECT year, value, unit 
            FROM financial_metrics 
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
            AND metric_name LIKE '%revenue%'
            AND year BETWEEN 2019 AND 2023
            AND fiscal_period = 'FY'
            ORDER BY year;
        """
    },
    
    # Q: Please provide fixed assets figures from 2019 – 2023?
    {
        "question": "Provide fixed assets figures for CK Hutchison from 2019 to 2023",
        "sql": """
            SELECT year, value, unit 
            FROM financial_metrics 
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
            AND metric_name LIKE '%fixed asset%'
            AND year BETWEEN 2019 AND 2023
            AND fiscal_period = 'FY'
            ORDER BY year;
        """
    },
    
    # Q: What is the amount of total debt to be matured in 2027?
    {
        "question": "What is the amount of total debt to be matured in 2027 for CK Hutchison?",
        "sql": """
            SELECT maturity_year, SUM(amount) as total_amount, currency 
            FROM debt_maturity 
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
            AND maturity_year = 2027
            GROUP BY maturity_year, currency;
        """
    },
    
    # ===========================================
    # SFC Annual Report 2023-24 Questions
    # ===========================================
    
    # Q: What is the amount of cash at bank and in hand for the year 2024?
    {
        "question": "What is the amount of cash at bank and in hand for SFC in 2024?",
        "sql": """
            SELECT year, value, unit 
            FROM financial_metrics 
            WHERE company_id = (SELECT id FROM companies WHERE name_en LIKE '%Securities and Futures Commission%' OR name_en LIKE '%SFC%') 
            AND metric_name LIKE '%cash at bank%'
            AND year = 2024;
        """
    },
    
    # Q: List all members of the Securities Compensation Fund Committee?
    {
        "question": "List all members of the Securities Compensation Fund Committee mentioned in SFC Annual Report",
        "sql": """
            SELECT person_name, committee_position 
            FROM key_personnel 
            WHERE company_id = (SELECT id FROM companies WHERE name_en LIKE '%Securities and Futures Commission%' OR name_en LIKE '%SFC%') 
            AND committee LIKE '%Securities Compensation Fund%'
            ORDER BY person_name;
        """
    },
    
    # Q: How many floors did SFC purchase for the OIE office?
    {
        "question": "How many floors did SFC purchase for the OIE office?",
        "sql": """
            SELECT event_title, metric_value, metric_unit, event_detail 
            FROM specific_events 
            WHERE company_id = (SELECT id FROM companies WHERE name_en LIKE '%Securities and Futures Commission%' OR name_en LIKE '%SFC%') 
            AND event_category = 'Property Acquisition'
            AND event_detail LIKE '%OIE%';
        """
    },
    
    # Q: Generate the bio of Lisa Chen?
    {
        "question": "Generate the bio of Lisa Chen mentioned in SFC Annual Report",
        "sql": """
            SELECT person_name, biography, role 
            FROM key_personnel 
            WHERE company_id = (SELECT id FROM companies WHERE name_en LIKE '%Securities and Futures Commission%' OR name_en LIKE '%SFC%') 
            AND person_name LIKE '%Lisa Chen%';
        """
    },
    
    # Q: When was the effective date of the SEHK GEM listing reform?
    {
        "question": "When was the effective date of the SEHK GEM listing reform mentioned in SFC Annual Report?",
        "sql": """
            SELECT event_title, effective_date, event_detail 
            FROM specific_events 
            WHERE company_id = (SELECT id FROM companies WHERE name_en LIKE '%Securities and Futures Commission%' OR name_en LIKE '%SFC%') 
            AND event_category LIKE '%Listing Reform%'
            AND event_detail LIKE '%GEM%';
        """
    },
    
    # Q: How many listing applications were processed by SFC?
    {
        "question": "How many listing applications were processed by SFC?",
        "sql": """
            SELECT year, application_count, approved_count, rejected_count 
            FROM listing_applications 
            WHERE company_id = (SELECT id FROM companies WHERE name_en LIKE '%Securities and Futures Commission%' OR name_en LIKE '%SFC%')
            ORDER BY year DESC;
        """
    },
    
    # Q: When was the consultation on share buy-backs conducted?
    {
        "question": "When was the consultation on share buy-backs conducted by SFC?",
        "sql": """
            SELECT event_title, event_date, announcement_date, event_detail 
            FROM specific_events 
            WHERE company_id = (SELECT id FROM companies WHERE name_en LIKE '%Securities and Futures Commission%' OR name_en LIKE '%SFC%') 
            AND event_category = 'Consultation'
            AND event_detail LIKE '%share buy-back%';
        """
    },
    
    # Q: How many stocks were launched for the RMB counters?
    {
        "question": "How many stocks were launched for the RMB counters mentioned in SFC Annual Report?",
        "sql": """
            SELECT event_title, metric_value, event_detail 
            FROM specific_events 
            WHERE company_id = (SELECT id FROM companies WHERE name_en LIKE '%Securities and Futures Commission%' OR name_en LIKE '%SFC%') 
            AND event_detail LIKE '%RMB counter%';
        """
    },
    
    # ===========================================
    # BioTech Sector Questions
    # ===========================================
    
    # Q: Provide the Top 10 stock codes and names of the market capital from the BioTech Sector
    {
        "question": "Provide the Top 10 stock codes and names of the market capital from the BioTech Sector",
        "sql": """
            SELECT c.stock_code, c.name_en as company_name, 
                   (m.closing_price * m.issued_shares) as market_capital
            FROM companies c
            JOIN market_data m ON c.id = m.company_id
            WHERE c.sector = 'BioTech'
            AND m.trade_date = (SELECT MAX(trade_date) FROM market_data)
            ORDER BY market_capital DESC
            LIMIT 10;
        """
    },
    
    # Q: Provide the Top 5 stock codes and names with the highest total liabilities?
    {
        "question": "Provide the Top 5 stock codes and names with the highest total liabilities in BioTech sector",
        "sql": """
            SELECT c.stock_code, c.name_en as company_name, fm.value as total_liabilities
            FROM companies c
            JOIN financial_metrics fm ON c.id = fm.company_id
            WHERE c.sector = 'BioTech'
            AND fm.metric_name LIKE '%total liabilit%'
            AND fm.year = 2024
            AND fm.fiscal_period = 'FY'
            ORDER BY fm.value DESC
            LIMIT 5;
        """
    },
    
    # Q: List all BioTech stocks which has the same auditor as stock 6160 Beone Medicines?
    {
        "question": "List all BioTech stocks which has the same auditor as stock 6160 Beone Medicines",
        "sql": """
            SELECT c.stock_code, c.name_en, c.auditor
            FROM companies c
            WHERE c.sector = 'BioTech'
            AND c.auditor = (
                SELECT auditor FROM companies WHERE stock_code = '6160'
            )
            ORDER BY c.stock_code;
        """
    },
    
    # Q: Please provide all the ultimate controlling shareholders of each BioTech stocks
    {
        "question": "Provide all the ultimate controlling shareholders of each BioTech stock",
        "sql": """
            SELECT stock_code, name_en, ultimate_controlling_shareholder
            FROM companies
            WHERE sector = 'BioTech'
            AND ultimate_controlling_shareholder IS NOT NULL
            ORDER BY stock_code;
        """
    },
    
    # Q: List all BioTech companies which has a Qualified Opinion from auditor's opinion?
    {
        "question": "List all BioTech companies which has a Qualified Opinion from auditor's opinion",
        "sql": """
            SELECT stock_code, name_en, auditor, auditor_opinion
            FROM companies
            WHERE sector = 'BioTech'
            AND auditor_opinion = 'Qualified'
            ORDER BY stock_code;
        """
    },
    
    # ===========================================
    # Integrated with Structured Database Questions
    # ===========================================
    
    # Q: Find the Top 2 BioTech stocks with the highest total liabilities in 2024 and plot a line chart showing these 2 stocks closing price in 2022
    {
        "question": "Find the Top 2 BioTech stocks with the highest total liabilities in 2024",
        "sql": """
            SELECT c.stock_code, c.name_en, fm.value as total_liabilities
            FROM companies c
            JOIN financial_metrics fm ON c.id = fm.company_id
            WHERE c.sector = 'BioTech'
            AND fm.metric_name LIKE '%total liabilit%'
            AND fm.year = 2024
            ORDER BY fm.value DESC
            LIMIT 2;
        """
    },
    
    {
        "question": "Show closing prices for specific BioTech stocks in 2022",
        "sql": """
            SELECT c.stock_code, c.name_en, m.trade_date, m.closing_price
            FROM companies c
            JOIN market_data m ON c.id = m.company_id
            WHERE c.stock_code IN ('09969', '09926')  -- Example stocks
            AND m.trade_date BETWEEN '2022-01-01' AND '2022-12-31'
            ORDER BY c.stock_code, m.trade_date;
        """
    },
    
    # Q: Plot the line chart of the closing price and transaction volume for stock 09969 in 2022
    {
        "question": "Show closing price and trading volume for stock 09969 in 2022",
        "sql": """
            SELECT trade_date, closing_price, trading_volume
            FROM market_data
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '09969')
            AND trade_date BETWEEN '2022-01-01' AND '2022-12-31'
            ORDER BY trade_date;
        """
    },
    
    # Q: What is the total revenue of stock 09969 in 2023 & 2024 and what is the average trading volume in 2022?
    {
        "question": "What is the total revenue of stock 09969 in 2023 and 2024",
        "sql": """
            SELECT year, value as total_revenue, unit
            FROM financial_metrics
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '09969')
            AND metric_name LIKE '%total revenue%'
            AND year IN (2023, 2024)
            AND fiscal_period = 'FY'
            ORDER BY year;
        """
    },
    
    {
        "question": "What is the average trading volume for stock 09969 in 2022",
        "sql": """
            SELECT AVG(trading_volume) as avg_volume
            FROM market_data
            WHERE company_id = (SELECT id FROM companies WHERE stock_code = '09969')
            AND trade_date BETWEEN '2022-01-01' AND '2022-12-31';
        """
    },
    
    # Q: List all BioTech Stocks in 2024 which principal bankers are HSBC and their average closing price in 2022
    {
        "question": "List all BioTech stocks in 2024 which principal bankers are HSBC",
        "sql": """
            SELECT stock_code, name_en, principal_banker
            FROM companies
            WHERE sector = 'BioTech'
            AND principal_banker LIKE '%HSBC%';
        """
    },
    
    {
        "question": "Show average closing price for BioTech stocks with HSBC as principal banker in 2022",
        "sql": """
            SELECT c.stock_code, c.name_en, AVG(m.closing_price) as avg_closing_price
            FROM companies c
            JOIN market_data m ON c.id = m.company_id
            WHERE c.sector = 'BioTech'
            AND c.principal_banker LIKE '%HSBC%'
            AND m.trade_date BETWEEN '2022-01-01' AND '2022-12-31'
            GROUP BY c.stock_code, c.name_en
            ORDER BY avg_closing_price DESC;
        """
    },
]


def get_all_training_data():
    """返回所有训练数据"""
    return {
        "ddl": DDL_TRAINING,
        "documentation": DOCUMENTATION_TRAINING,
        "sql_examples": SQL_TRAINING
    }


def train_vanna(vn):
    """
    使用所有训练数据训练 Vanna
    
    Args:
        vn: Vanna 实例
    """
    print("🧠 開始訓練 Vanna...")
    
    # 1. 訓練 DDL
    print("\n📝 訓練 DDL...")
    for ddl in DDL_TRAINING:
        try:
            vn.train(ddl=ddl)
            print(f"   ✅ DDL trained")
        except Exception as e:
            print(f"   ⚠️ DDL training error: {e}")
    
    # 2. 訓練 Documentation
    print("\n📚 訓練 Documentation...")
    for doc in DOCUMENTATION_TRAINING:
        try:
            vn.train(documentation=doc)
            print(f"   ✅ Documentation trained")
        except Exception as e:
            print(f"   ⚠️ Documentation training error: {e}")
    
    # 3. 訓練 SQL Examples
    print("\n💾 訓練 SQL Examples...")
    for example in SQL_TRAINING:
        try:
            vn.train(
                question=example["question"],
                sql=example["sql"]
            )
            print(f"   ✅ SQL trained: {example['question'][:50]}...")
        except Exception as e:
            print(f"   ⚠️ SQL training error: {e}")
    
    print("\n✅ Vanna 訓練完成！")


if __name__ == "__main__":
    # 測試用
    print("Vanna Training Data Module")
    print(f"DDL: {len(DDL_TRAINING)} items")
    print(f"Documentation: {len(DOCUMENTATION_TRAINING)} items")
    print(f"SQL Examples: {len(SQL_TRAINING)} items")