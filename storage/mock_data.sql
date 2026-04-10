-- ============================================================
-- Mock Data for Nanobot Testing
-- ============================================================
-- 包含新舊兩種 Schema 的測試數據
-- 新 Schema: documents, document_companies
-- 舊 Schema: companies, financial_metrics (Vanna 向後兼容)
-- ============================================================

-- ===========================================
-- 舊版 Schema 數據 (Vanna SQL 訓練用)
-- ===========================================

-- 1. Companies - Complete BioTech List (30 stocks)
INSERT INTO companies (name_en, name_zh, stock_code, industry, sector, auditor, auditor_opinion, ultimate_controlling_shareholder, principal_banker) VALUES
-- BioTech Companies (30 stocks from user's list)
('HUTCHMED', '和黃醫藥', '0013', 'Pharmaceuticals', 'BioTech', 'PwC', 'Unqualified', 'Hutchison Whampoa Limited', 'HSBC, Bank of China'),
('ALI HEALTH', '阿里健康', '0241', 'Healthcare Technology', 'BioTech', 'KPMG', 'Unqualified', 'Alibaba Group Holding Limited', 'HSBC, Standard Chartered'),
('GRAND PHARMA', '遠大醫藥', '0512', 'Pharmaceuticals', 'BioTech', 'Deloitte', 'Unqualified', 'Grand Pharma (China) Co., Ltd.', 'HSBC'),
('MICROPORT', '微創醫療', '0853', 'Medical Devices', 'BioTech', 'KPMG', 'Unqualified', 'MicroPort Scientific Corporation', 'HSBC, Bank of China'),
('CMS', '康希諾生物', '0867', 'Biotechnology', 'BioTech', 'PwC', 'Unqualified', 'CanSino Biologics Inc.', 'HSBC'),
('WEIGAO GROUP', '威高股份', '1066', 'Medical Devices', 'BioTech', 'EY', 'Unqualified', 'Weigao Group Company Limited', 'HSBC, ICBC'),
('CSPC PHARMA', '石藥集團', '1093', 'Pharmaceuticals', 'BioTech', 'Deloitte', 'Unqualified', 'CSPC Pharmaceutical Group Limited', 'HSBC, ICBC'),
('SINOPHARM', '國藥控股', '1099', 'Pharmaceuticals', 'BioTech', 'KPMG', 'Unqualified', 'China National Pharmaceutical Group', 'Bank of China, HSBC'),
('SINO BIOPHARM', '中國生物製藥', '1177', 'Pharmaceuticals', 'BioTech', 'EY', 'Unqualified', 'Tida Investment Limited', 'Bank of China, HSBC'),
('3SBIO', '三生製藥', '1530', 'Biotechnology', 'BioTech', 'PwC', 'Qualified', '3SBIO Inc.', 'HSBC'),
('GENSCRIPT BIO', '金斯瑞生物科技', '1548', 'Biotechnology', 'BioTech', 'Deloitte', 'Unqualified', 'GenScript Biotech Corporation', 'HSBC'),
('INNOVENT BIO', '信達生物', '1801', 'Biotechnology', 'BioTech', 'PwC', 'Unqualified', 'Innovent Biologics, Inc.', 'HSBC'),
('EVEREST MED', '業聚醫療', '1952', 'Medical Devices', 'BioTech', 'KPMG', 'Unqualified', 'OrbusNeich Medical (Shenzhen) Co., Ltd.', 'HSBC'),
('SIMCERE PHARMA', '先聲藥業', '2096', 'Pharmaceuticals', 'BioTech', 'EY', 'Unqualified', 'Simcere Pharmaceutical Group', 'Bank of China, HSBC'),
('XTALPI', '晶泰科技', '2228', 'Healthcare Technology', 'BioTech', 'PwC', 'Unqualified', 'XtalPi Holdings Limited', 'HSBC'),
('MEDBOT-B', '微創機器人-B', '2252', 'Medical Devices', 'BioTech', 'KPMG', 'Unqualified', 'Shanghai MicroPort MedBot (Group) Co., Ltd.', 'HSBC'),
('WUXI XDC', '藥明合聯', '2268', 'Biotechnology', 'BioTech', 'Deloitte', 'Unqualified', 'WuXi XDC Cayman Inc.', 'HSBC'),
('WUXI BIO', '藥明生物', '2269', 'Biotechnology', 'BioTech', 'PwC', 'Unqualified', 'WuXi Biologics (Cayman) Inc.', 'HSBC'),
('WUXI APPTEC', '藥明康德', '2359', 'Biotechnology', 'BioTech', 'KPMG', 'Unqualified', 'WuXi AppTec Co., Ltd.', 'HSBC, Bank of China'),
('CHINARES PHARMA', '中國中藥', '3320', 'Pharmaceuticals', 'BioTech', 'EY', 'Unqualified', 'China Resources Pharmaceutical Group', 'Bank of China'),
('HANSOH PHARMA', '翰森製藥', '3692', 'Pharmaceuticals', 'BioTech', 'Deloitte', 'Unqualified', 'Hansoh Pharmaceutical Group Company Limited', 'HSBC'),
('UNITED LAB', '聯邦製藥', '3933', 'Pharmaceuticals', 'BioTech', 'KPMG', 'Unqualified', 'United Laboratories International Holdings', 'HSBC'),
('BEONE MEDICINES', '貝達藥業', '6160', 'Pharmaceuticals', 'BioTech', 'Deloitte', 'Unqualified', 'Beone Medicines Co., Ltd.', 'HSBC, China Merchants Bank'),
('JD HEALTH', '京東健康', '6618', 'Healthcare Technology', 'BioTech', 'PwC', 'Unqualified', 'JD Health International Inc.', 'HSBC'),
('ASCENTAGE-B', '康方生物-B', '6855', 'Biotechnology', 'BioTech', 'KPMG', 'Unqualified', 'Akeso, Inc.', 'HSBC'),
('SKB BIO-B', '科倫博泰生物-B', '6990', 'Biotechnology', 'BioTech', 'Deloitte', 'Unqualified', 'Sichuan Kelun-Biotech Biopharmaceutical Co., Ltd.', 'HSBC'),
('ZAI LAB', '再鼎醫藥', '9688', 'Biotechnology', 'BioTech', 'PwC', 'Unqualified', 'Zai Lab Limited', 'HSBC'),
('AKESO', '康方生物', '9926', 'Biotechnology', 'BioTech', 'KPMG', 'Unqualified', 'Akeso, Inc.', 'HSBC'),
('INNOCARE', '諾誠健華', '9969', 'Biotechnology', 'BioTech', 'PwC', 'Unqualified', 'InnoCare Pharma Limited', 'HSBC, Standard Chartered'),
-- SFC (Securities and Futures Commission)
('Securities and Futures Commission', '證券及期貨事務監察委員會', 'SFC', 'Regulator', 'Regulatory', 'Director of Audit', 'Unqualified', 'Hong Kong SAR Government', 'N/A'),
-- CK Hutchison (for sample questions)
('CK Hutchison Holdings', '長江和記實業', '0001', 'Conglomerate', 'Conglomerate', 'PwC', 'Unqualified', 'Li Ka-Shing', 'HSBC, Bank of East Asia')
ON CONFLICT (stock_code) DO NOTHING;

-- 2. Financial Metrics - For sample questions
INSERT INTO financial_metrics (company_id, year, fiscal_period, metric_name, metric_name_zh, value, standardized_value, unit, category, source_file, source_page) VALUES
-- INNOCARE (stock_code: 9969) - For cross-year queries
((SELECT id FROM companies WHERE stock_code = '9969'), 2023, 'FY', 'Total Revenue', '總收入', 850.6, 935.7, 'CNY', 'revenue', 'INNOCARE_2023_AR.pdf', 50),
((SELECT id FROM companies WHERE stock_code = '9969'), 2024, 'FY', 'Total Revenue', '總收入', 1023.5, 1125.9, 'CNY', 'revenue', 'INNOCARE_2024_AR.pdf', 55),
((SELECT id FROM companies WHERE stock_code = '9969'), 2024, 'FY', 'Total Liabilities', '總負債', 456.2, 501.8, 'CNY', 'liability', 'INNOCARE_2024_AR.pdf', 60),
((SELECT id FROM companies WHERE stock_code = '9969'), 2023, 'FY', 'Total Liabilities', '總負債', 398.7, 438.6, 'CNY', 'liability', 'INNOCARE_2023_AR.pdf', 58),
-- AKESO - Top liabilities
((SELECT id FROM companies WHERE stock_code = '9926'), 2024, 'FY', 'Total Revenue', '總收入', 1890.5, 2079.6, 'CNY', 'revenue', 'AKESO_2024_AR.pdf', 50),
((SELECT id FROM companies WHERE stock_code = '9926'), 2024, 'FY', 'Total Liabilities', '總負債', 892.3, 981.5, 'CNY', 'liability', 'AKESO_2024_AR.pdf', 60),
-- WUXI BIO - High liabilities
((SELECT id FROM companies WHERE stock_code = '2269'), 2024, 'FY', 'Total Liabilities', '總負債', 3500.8, 3850.9, 'CNY', 'liability', 'WUXI_BIO_2024_AR.pdf', 60),
-- WUXI APPTEC - Top liabilities
((SELECT id FROM companies WHERE stock_code = '2359'), 2024, 'FY', 'Total Liabilities', '總負債', 4200.5, 4620.6, 'CNY', 'liability', 'WUXI_APPTEC_2024_AR.pdf', 60),
-- 3SBIO - Qualified opinion example
((SELECT id FROM companies WHERE stock_code = '1530'), 2024, 'FY', 'Total Liabilities', '總負債', 567.8, 624.6, 'CNY', 'liability', '3SBIO_2024_AR.pdf', 60),
((SELECT id FROM companies WHERE stock_code = '1530'), 2024, 'FY', 'Total Revenue', '總收入', 890.2, 979.2, 'CNY', 'revenue', '3SBIO_2024_AR.pdf', 50),
-- BEONE MEDICINES - Same auditor query
((SELECT id FROM companies WHERE stock_code = '6160'), 2024, 'FY', 'Total Liabilities', '總負債', 234.5, 258.0, 'CNY', 'liability', 'BEONE_2024_AR.pdf', 58),
((SELECT id FROM companies WHERE stock_code = '6160'), 2024, 'FY', 'Total Revenue', '總收入', 456.7, 502.4, 'CNY', 'revenue', 'BEONE_2024_AR.pdf', 50),
-- HUTCHMED - USD currency
((SELECT id FROM companies WHERE stock_code = '0013'), 2024, 'FY', 'Total Liabilities', '總負債', 1250.6, 9754.7, 'USD', 'liability', 'HUTCHMED_2024_AR.pdf', 62),
-- CSPC PHARMA
((SELECT id FROM companies WHERE stock_code = '1093'), 2024, 'FY', 'Total Liabilities', '總負債', 1890.2, 2079.2, 'CNY', 'liability', 'CSPC_2024_AR.pdf', 60),
-- SINO BIOPHARM
((SELECT id FROM companies WHERE stock_code = '1177'), 2024, 'FY', 'Total Liabilities', '總負債', 2100.5, 2310.6, 'CNY', 'liability', 'SINO_BIOPHARM_2024_AR.pdf', 60),
-- CK Hutchison - Multi-year P&L
((SELECT id FROM companies WHERE stock_code = '0001'), 2019, 'FY', 'Total Revenue', '總收入', 436800, 436800, 'HKD', 'revenue', 'CKH_AR_2019.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2020, 'FY', 'Total Revenue', '總收入', 403800, 403800, 'HKD', 'revenue', 'CKH_AR_2020.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2021, 'FY', 'Total Revenue', '總收入', 445300, 445300, 'HKD', 'revenue', 'CKH_AR_2021.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2022, 'FY', 'Total Revenue', '總收入', 456200, 456200, 'HKD', 'revenue', 'CKH_AR_2022.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'FY', 'Total Revenue', '總收入', 461600, 461600, 'HKD', 'revenue', 'CKH_AR_2023.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2019, 'FY', 'Profit Attributable to Shareholders', '股東應佔溢利', 39500, 39500, 'HKD', 'profit', 'CKH_AR_2019.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2020, 'FY', 'Profit Attributable to Shareholders', '股東應佔溢利', 33800, 33800, 'HKD', 'profit', 'CKH_AR_2020.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2021, 'FY', 'Profit Attributable to Shareholders', '股東應佔溢利', 42300, 42300, 'HKD', 'profit', 'CKH_AR_2021.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2022, 'FY', 'Profit Attributable to Shareholders', '股東應佔溢利', 36200, 36200, 'HKD', 'profit', 'CKH_AR_2022.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'FY', 'Profit Attributable to Shareholders', '股東應佔溢利', 36700, 36700, 'HKD', 'profit', 'CKH_AR_2023.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2019, 'FY', 'Fixed Assets', '固定資產', 289500, 289500, 'HKD', 'asset', 'CKH_AR_2019.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2020, 'FY', 'Fixed Assets', '固定資產', 278600, 278600, 'HKD', 'asset', 'CKH_AR_2020.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2021, 'FY', 'Fixed Assets', '固定資產', 292300, 292300, 'HKD', 'asset', 'CKH_AR_2021.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2022, 'FY', 'Fixed Assets', '固定資產', 301200, 301200, 'HKD', 'asset', 'CKH_AR_2022.pdf', 273),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'FY', 'Fixed Assets', '固定資產', 315600, 315600, 'HKD', 'asset', 'CKH_AR_2023.pdf', 273),
-- SFC - Cash at bank
((SELECT id FROM companies WHERE stock_code = 'SFC'), 2024, 'FY', 'Cash at Bank and in Hand', '銀行及手頭現金', 156.8, 156.8, 'HKD', 'asset', 'SFC_AR_2023_24.pdf', 151)
ON CONFLICT (company_id, year, fiscal_period, metric_name) DO NOTHING;

-- 3. Market Data - For 2022 line chart and market cap queries
INSERT INTO market_data (company_id, trade_date, closing_price, issued_shares, trading_volume, source) VALUES
-- INNOCARE (09969) - 2022 daily data for line chart
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-01-03', 12.35, 1180000000, 5670000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-02-01', 11.89, 1180000000, 4520000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-03-01', 13.45, 1180000000, 7890000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-04-01', 12.80, 1180000000, 6230000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-05-01', 11.50, 1180000000, 5450000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-06-01', 10.56, 1180000000, 8230000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-07-01', 9.87, 1180000000, 6540000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-08-01', 10.23, 1180000000, 5670000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-09-01', 9.45, 1180000000, 7890000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-10-01', 10.12, 1180000000, 6120000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-11-01', 10.78, 1180000000, 5340000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-12-01', 11.23, 1180000000, 5120000, 'activex'),
-- AKESO (09926) - 2022 data
((SELECT id FROM companies WHERE stock_code = '9926'), '2022-01-03', 25.60, 850000000, 3450000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9926'), '2022-06-01', 22.30, 850000000, 4560000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9926'), '2022-12-01', 28.90, 850000000, 5120000, 'activex'),
-- All BioTech current prices for Market Cap calculation (2024-12-31)
((SELECT id FROM companies WHERE stock_code = '0013'), '2024-12-31', 18.56, 8750000000, 12300000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '0241'), '2024-12-31', 3.45, 13400000000, 45600000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '0512'), '2024-12-31', 5.80, 2800000000, 8900000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '0853'), '2024-12-31', 8.90, 1750000000, 5670000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '0867'), '2024-12-31', 15.60, 250000000, 2340000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1066'), '2024-12-31', 6.50, 4500000000, 12300000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1093'), '2024-12-31', 6.78, 8900000000, 23400000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1099'), '2024-12-31', 22.50, 3250000000, 8900000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1177'), '2024-12-31', 3.12, 12500000000, 34500000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1530'), '2024-12-31', 8.90, 670000000, 5670000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1548'), '2024-12-31', 12.30, 2100000000, 4560000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1801'), '2024-12-31', 42.50, 1450000000, 3450000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1952'), '2024-12-31', 9.80, 180000000, 1230000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '2096'), '2024-12-31', 7.20, 900000000, 2340000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '2228'), '2024-12-31', 5.60, 1500000000, 3450000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '2252'), '2024-12-31', 18.90, 450000000, 1230000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '2268'), '2024-12-31', 25.60, 320000000, 890000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '2269'), '2024-12-31', 28.50, 4200000000, 15600000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '2359'), '2024-12-31', 45.80, 2950000000, 12300000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '3320'), '2024-12-31', 4.20, 6500000000, 8900000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '3692'), '2024-12-31', 14.50, 750000000, 2340000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '3933'), '2024-12-31', 6.80, 1800000000, 4560000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '6160'), '2024-12-31', 45.60, 450000000, 2340000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '6618'), '2024-12-31', 22.30, 3150000000, 8900000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '6855'), '2024-12-31', 52.80, 185000000, 1560000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '6990'), '2024-12-31', 125.60, 210000000, 890000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9688'), '2024-12-31', 185.90, 105000000, 567000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9926'), '2024-12-31', 32.50, 850000000, 5670000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2024-12-31', 15.80, 1180000000, 6780000, 'activex')
ON CONFLICT (company_id, trade_date) DO NOTHING;

-- 4. Key Personnel - For sample questions
INSERT INTO key_personnel (company_id, year, person_name, person_name_zh, role, role_zh, committee, biography, source_file, source_page) VALUES
-- SFC - Lisa Chen
((SELECT id FROM companies WHERE stock_code = 'SFC'), 2024, 'Lisa Chen', '陳麗莎', 'Executive Director', '執行董事', 'Enforcement Committee', 
'Lisa Chen joined the SFC in 2015 and was appointed Executive Director in 2022. She has over 20 years of experience in securities regulation and enforcement. Prior to joining the SFC, she worked at a leading international law firm specializing in financial services regulation. She holds a Bachelor of Laws from the University of Hong Kong and a Master of Laws from Harvard Law School. She has been instrumental in strengthening Hong Kongs regulatory framework and leading high-profile enforcement actions against market misconduct.', 
'SFC_AR_2023_24.pdf', 108),
-- SFC - Securities Compensation Fund Committee members
((SELECT id FROM companies WHERE stock_code = 'SFC'), 2024, 'Michael Wong', '黃志光', 'Chairman', '主席', 'Securities Compensation Fund Committee', 
'Michael Wong has been the Chairman of the Securities Compensation Fund Committee since 2020. He is a seasoned financial services professional with extensive experience in investor protection.', 
'SFC_AR_2023_24.pdf', 193),
((SELECT id FROM companies WHERE stock_code = 'SFC'), 2024, 'Sarah Lee', '李美玲', 'Member', '成員', 'Securities Compensation Fund Committee', 
'Sarah Lee is a Member of the Securities Compensation Fund Committee. She has over 15 years of experience in fund management and investor compensation schemes.', 
'SFC_AR_2023_24.pdf', 193),
((SELECT id FROM companies WHERE stock_code = 'SFC'), 2024, 'David Cheung', '張大衛', 'Member', '成員', 'Securities Compensation Fund Committee', 
'David Cheung is a Member of the Securities Compensation Fund Committee with expertise in securities law and investor protection mechanisms.',
'SFC_AR_2023_24.pdf', 193),
((SELECT id FROM companies WHERE stock_code = 'SFC'), 2024, 'Jennifer Lam', '林珍妮', 'Member', '成員', 'Securities Compensation Fund Committee', 
'Jennifer Lam is a Member of the Securities Compensation Fund Committee, bringing her expertise in risk management and fund administration.',
'SFC_AR_2023_24.pdf', 193),
-- CK Hutchison - Executive Directors
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'Victor Li', '李澤鉅', 'Executive Director', '執行董事', 'Executive Committee',
'Victor Li is the Chairman and Executive Director of CK Hutchison Holdings. He is the elder son of Li Ka-Shing and has been leading the company since 2018.',
'CKH_AR_2023.pdf', 2),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'Canning Fok', '霍建寧', 'Executive Director', '執行董事', 'Executive Committee',
'Canning Fok is the Group Managing Director and Executive Director of CK Hutchison Holdings, overseeing the groups day-to-day operations.',
'CKH_AR_2023.pdf', 2)
ON CONFLICT DO NOTHING;

-- 5. Shareholdings - Li Ka-Shing Unity Trust
INSERT INTO shareholdings (company_id, year, shareholder_name, shareholder_name_zh, shareholder_type, percentage_held, trust_name, trustee_name, source_file, source_page) VALUES
-- CK Hutchison - Li Ka-Shing Unity Trust
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'Li Ka-Shing Unity Trustee Company Limited', '李嘉誠聯合受託人有限公司', 'Trust', 30.52, 
'The Li Ka-Shing Unity Trust', 'Li Ka-Shing Unity Trustee Company Limited', 'CKH_AR_2023.pdf', 94),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'Li Ka-Shing Unity Trust', '李嘉誠聯合信託', 'Trust', 30.52,
'The Li Ka-Shing Unity Trust', 'Li Ka-Shing Unity Trustee Company Limited', 'CKH_AR_2023.pdf', 94)
ON CONFLICT (company_id, year, shareholder_name) DO NOTHING;

-- 6. Specific Events - SFC events
INSERT INTO specific_events (company_id, event_category, event_title, event_detail, event_date, effective_date, metric_value, metric_unit, source_file, source_page) VALUES
-- SFC - Property Acquisition (OIE Office)
((SELECT id FROM companies WHERE stock_code = 'SFC'), 'Property Acquisition', 
'SFC Office Acquisition at OIE', 
'The Securities and Futures Commission purchased 8 floors at the OIE (Office and Industrial Estate) building for its new office premises. The acquisition provides modern office space to accommodate the growing regulatory needs and expanded workforce of the Commission.',
'2023-06-15', '2023-06-15', 8, 'floors', 'SFC_AR_2023_24.pdf', 142),
-- SFC - GEM Listing Reform
((SELECT id FROM companies WHERE stock_code = 'SFC'), 'Listing Reform',
'SEHK GEM Listing Reform',
'The Stock Exchange of Hong Kong (SEHK) GEM listing reform was implemented to enhance the quality of GEM listings and provide a clearer regulatory framework for growth companies. The reform includes new eligibility requirements and streamlined listing procedures.',
'2023-10-01', '2023-10-01', NULL, NULL, 'SFC_AR_2023_24.pdf', 47),
-- SFC - Share Buy-backs Consultation
((SELECT id FROM companies WHERE stock_code = 'SFC'), 'Consultation',
'Consultation on Share Buy-backs',
'The SFC conducted a consultation on share buy-backs to review and enhance the regulatory framework governing share repurchase activities by listed companies. The consultation concluded with recommendations to modernize the rules.',
'2023-07-15', NULL, NULL, NULL, 'SFC_AR_2023_24.pdf', 50),
-- SFC - RMB Counters
((SELECT id FROM companies WHERE stock_code = 'SFC'), 'Market Initiative',
'Launch of RMB Counters',
'The SFC supported the launch of RMB counters for Hong Kong stocks, enabling trading in Renminbi. 24 stocks were initially launched for the RMB counters program.',
'2023-06-19', '2023-06-19', 24, 'stocks', 'SFC_AR_2023_24.pdf', 37)
ON CONFLICT DO NOTHING;

-- 7. Revenue Breakdown - CK Hutchison geographic
INSERT INTO revenue_breakdown (company_id, year, category, category_type, percentage, amount, currency, sub_category, sub_percentage, source_file, source_page) VALUES
-- CK Hutchison - Geographic breakdown (page 6)
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'Canada', 'Region', 12.5, 58000, 'HKD', NULL, NULL, 'CKH_AR_2023.pdf', 6),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'Asia, Australia & Others', 'Region', 45.2, 209500, 'HKD', 'Retail', 32.5, 'CKH_AR_2023.pdf', 6),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'Asia', 'Region', 35.5, 164600, 'HKD', 'Retail', 28.7, 'CKH_AR_2023.pdf', 6),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'Australia', 'Region', 8.3, 38500, 'HKD', 'Retail', 18.7, 'CKH_AR_2023.pdf', 6),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'Others', 'Region', 5.8, 26900, 'HKD', NULL, NULL, 'CKH_AR_2023.pdf', 6),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 'Europe', 'Region', 28.2, 130800, 'HKD', NULL, NULL, 'CKH_AR_2023.pdf', 6)
ON CONFLICT (company_id, year, category, category_type) DO NOTHING;

-- 8. Debt Maturity - CK Hutchison
INSERT INTO debt_maturity (company_id, year, maturity_year, amount, currency, debt_type, source_file, source_page) VALUES
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 2024, 15000, 'HKD', 'Bank Loan', 'CKH_AR_2023.pdf', 9),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 2025, 22000, 'HKD', 'Bond', 'CKH_AR_2023.pdf', 9),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 2026, 18500, 'HKD', 'Bank Loan', 'CKH_AR_2023.pdf', 9),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 2027, 35000, 'HKD', 'Bond', 'CKH_AR_2023.pdf', 9),
((SELECT id FROM companies WHERE stock_code = '0001'), 2023, 2028, 28000, 'HKD', 'Bank Loan', 'CKH_AR_2023.pdf', 9)
ON CONFLICT DO NOTHING;

-- 9. Listing Applications - SFC macro data
INSERT INTO listing_applications (company_id, year, application_count, approved_count, rejected_count, source_file, source_page) VALUES
(NULL, 2023, 145, 128, 17, 'SFC_AR_2023_24.pdf', 49),
(NULL, 2022, 138, 121, 17, 'SFC_AR_2022_23.pdf', 48)
ON CONFLICT DO NOTHING;


-- ===========================================
-- 新版 Schema 數據 (Document-centric)
-- ===========================================

-- Documents
INSERT INTO documents (filename, report_type, is_index_report, parent_company, index_theme, confirmed_industry, dynamic_attributes, processing_status) VALUES
('CKH_AR_2023.pdf', 'annual_report', FALSE, 'CK Hutchison Holdings', NULL, 'Conglomerate', '{"fiscal_year": "2023", "currency": "HKD", "total_pages": 300}', 'completed'),
('SFC_AR_2023_24.pdf', 'annual_report', FALSE, 'SFC', NULL, 'Regulatory', '{"fiscal_year": "2023-24", "currency": "HKD", "total_pages": 220}', 'completed'),
('INNOCARE_2024_AR.pdf', 'annual_report', FALSE, 'INNOCARE', NULL, 'Biotechnology', '{"fiscal_year": "2024", "currency": "CNY", "total_pages": 165}', 'completed'),
('AKESO_2024_AR.pdf', 'annual_report', FALSE, 'AKESO', NULL, 'Biotechnology', '{"fiscal_year": "2024", "currency": "CNY", "total_pages": 180}', 'completed'),
('HS_Biotech_Index_2024.pdf', 'index_report', TRUE, NULL, 'Hang Seng Biotech Index', 'Biotechnology', '{"index_quarter": "Q4", "constituent_count": 30}', 'completed')
ON CONFLICT DO NOTHING;

-- Document Companies
INSERT INTO document_companies (document_id, company_name, stock_code, assigned_industry, industry_source, dynamic_attributes)
SELECT id, 'CK Hutchison Holdings', '0001.HK', 'Conglomerate', 'ai_extracted', '{"revenue_2023_hkd": 461600}' FROM documents WHERE filename = 'CKH_AR_2023.pdf'
UNION ALL
SELECT id, 'INNOCARE', '9969.HK', 'Biotechnology', 'ai_extracted', '{"revenue_2024_cny": 1023.5}' FROM documents WHERE filename = 'INNOCARE_2024_AR.pdf'
UNION ALL
SELECT id, 'AKESO', '9926.HK', 'Biotechnology', 'ai_extracted', '{"revenue_2024_cny": 1890.5}' FROM documents WHERE filename = 'AKESO_2024_AR.pdf'
ON CONFLICT DO NOTHING;


-- ===========================================
-- Verification Queries
-- ===========================================
SELECT 'Companies' as table_name, COUNT(*) as count FROM companies
UNION ALL SELECT 'Financial Metrics', COUNT(*) FROM financial_metrics
UNION ALL SELECT 'Market Data', COUNT(*) FROM market_data
UNION ALL SELECT 'Key Personnel', COUNT(*) FROM key_personnel
UNION ALL SELECT 'Shareholdings', COUNT(*) FROM shareholdings
UNION ALL SELECT 'Specific Events', COUNT(*) FROM specific_events
UNION ALL SELECT 'Revenue Breakdown', COUNT(*) FROM revenue_breakdown
UNION ALL SELECT 'Debt Maturity', COUNT(*) FROM debt_maturity
UNION ALL SELECT 'Documents', COUNT(*) FROM documents
UNION ALL SELECT 'Document Companies', COUNT(*) FROM document_companies;