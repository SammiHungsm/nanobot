-- Mock Data for Vanna Testing
-- 測試數據：用於驗證 Vanna 能否正確回答 Sample Questions

-- ===========================================
-- 1. Companies (BioTech + SFC)
-- ===========================================
INSERT INTO companies (name_en, name_zh, stock_code, industry, sector, auditor, auditor_opinion, ultimate_controlling_shareholder, principal_banker) VALUES
-- BioTech Companies
('HUTCHMED', '和黃醫藥', '0013', 'Pharmaceuticals', 'BioTech', 'PwC', 'Unqualified', 'Hutchison Whampoa Limited', 'HSBC, Bank of China'),
('ALI HEALTH', '阿里健康', '0241', 'Healthcare Technology', 'BioTech', 'KPMG', 'Unqualified', 'Alibaba Group Holding Limited', 'HSBC, Standard Chartered'),
('CSPC PHARMA', '石藥集團', '1093', 'Pharmaceuticals', 'BioTech', 'Deloitte', 'Unqualified', 'CSPC Pharmaceutical Group Limited', 'HSBC, ICBC'),
('SINO BIOPHARM', '中國生物製藥', '1177', 'Pharmaceuticals', 'BioTech', 'EY', 'Unqualified', 'Tida Investment Limited', 'Bank of China, HSBC'),
('3SBIO', '三生製藥', '1530', 'Biotechnology', 'BioTech', 'PwC', 'Qualified', '3SBIO Inc.', 'HSBC'),
('BEONE MEDICINES', '貝達藥業', '6160', 'Pharmaceuticals', 'BioTech', 'Deloitte', 'Unqualified', 'Beone Medicines Co., Ltd.', 'HSBC, China Merchants Bank'),
('AKESO', '康方生物', '9926', 'Biotechnology', 'BioTech', 'KPMG', 'Unqualified', 'Akeso, Inc.', 'HSBC'),
('INNOCARE', '諾誠健華', '9969', 'Biotechnology', 'BioTech', 'PwC', 'Unqualified', 'InnoCare Pharma Limited', 'HSBC, Standard Chartered'),
-- SFC (Securities and Futures Commission)
('Securities and Futures Commission', '證券及期貨事務監察委員會', 'SFC', 'Regulator', 'Regulatory', 'Director of Audit', 'Unqualified', 'Hong Kong SAR Government', 'N/A'),
-- CK Hutchison (for sample questions)
('CK Hutchison Holdings', '長江和記實業', '00001', 'Conglomerate', 'Conglomerate', 'PwC', 'Unqualified', 'Li Ka-Shing', 'HSBC, Bank of East Asia')
ON CONFLICT (stock_code) DO NOTHING;

-- ===========================================
-- 2. Financial Metrics (2023-2024)
-- ===========================================
INSERT INTO financial_metrics (company_id, year, fiscal_period, metric_name, metric_name_zh, value, unit, category, source_file, source_page) VALUES
-- INNOCARE (stock_code: 09969)
((SELECT id FROM companies WHERE stock_code = '9969'), 2023, 'FY', 'Total Revenue', '總收入', 850.6, 'CNY', 'revenue', 'INNOCARE_2023_AR.pdf', 50),
((SELECT id FROM companies WHERE stock_code = '9969'), 2024, 'FY', 'Total Revenue', '總收入', 1023.5, 'CNY', 'revenue', 'INNOCARE_2024_AR.pdf', 55),
((SELECT id FROM companies WHERE stock_code = '9969'), 2024, 'FY', 'Total Liabilities', '總負債', 456.2, 'CNY', 'liability', 'INNOCARE_2024_AR.pdf', 60),
((SELECT id FROM companies WHERE stock_code = '9969'), 2023, 'FY', 'Total Liabilities', '總負債', 398.7, 'CNY', 'liability', 'INNOCARE_2023_AR.pdf', 58),
((SELECT id FROM companies WHERE stock_code = '9969'), 2023, 'FY', 'Cash at Bank', '銀行現金', 1250.3, 'CNY', 'asset', 'INNOCARE_2023_AR.pdf', 65),
((SELECT id FROM companies WHERE stock_code = '9969'), 2024, 'FY', 'Cash at Bank', '銀行現金', 1456.8, 'CNY', 'asset', 'INNOCARE_2024_AR.pdf', 68),
-- AKESO (stock_code: 09926)
((SELECT id FROM companies WHERE stock_code = '9926'), 2024, 'FY', 'Total Revenue', '總收入', 1890.5, 'CNY', 'revenue', 'AKESO_2024_AR.pdf', 50),
((SELECT id FROM companies WHERE stock_code = '9926'), 2024, 'FY', 'Total Liabilities', '總負債', 892.3, 'CNY', 'liability', 'AKESO_2024_AR.pdf', 60),
-- 3SBIO
((SELECT id FROM companies WHERE stock_code = '1530'), 2024, 'FY', 'Total Liabilities', '總負債', 567.8, 'CNY', 'liability', '3SBIO_2024_AR.pdf', 60),
-- BEONE MEDICINES
((SELECT id FROM companies WHERE stock_code = '6160'), 2024, 'FY', 'Total Liabilities', '總負債', 234.5, 'CNY', 'liability', 'BEONE_2024_AR.pdf', 58),
-- HUTCHMED
((SELECT id FROM companies WHERE stock_code = '0013'), 2024, 'FY', 'Total Liabilities', '總負債', 1250.6, 'USD', 'liability', 'HUTCHMED_2024_AR.pdf', 62),
-- CSPC PHARMA
((SELECT id FROM companies WHERE stock_code = '1093'), 2024, 'FY', 'Total Liabilities', '總負債', 1890.2, 'CNY', 'liability', 'CSPC_2024_AR.pdf', 60),
-- SFC
((SELECT id FROM companies WHERE stock_code = 'SFC'), 2024, 'FY', 'Cash at Bank and in Hand', '銀行及手頭現金', 156.8, 'HKD', 'asset', 'SFC_AR_2023_24.pdf', 151)
ON CONFLICT (company_id, year, fiscal_period, metric_name) DO NOTHING;

-- ===========================================
-- 3. Market Data (2022 and current for Market Cap calculation)
-- ===========================================
INSERT INTO market_data (company_id, trade_date, closing_price, issued_shares, trading_volume, source) VALUES
-- INNOCARE (09969) - 2022 data for line chart
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-01-03', 12.35, 1180000000, 5670000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-02-01', 11.89, 1180000000, 4520000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-03-01', 13.45, 1180000000, 7890000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-06-01', 10.56, 1180000000, 8230000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-09-01', 9.87, 1180000000, 6540000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2022-12-01', 11.23, 1180000000, 5120000, 'activex'),
-- AKESO (09926) - 2022 data
((SELECT id FROM companies WHERE stock_code = '9926'), '2022-01-03', 25.60, 850000000, 3450000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9926'), '2022-06-01', 22.30, 850000000, 4560000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9926'), '2022-12-01', 28.90, 850000000, 5120000, 'activex'),
-- BioTech current prices for Market Cap
((SELECT id FROM companies WHERE stock_code = '0013'), '2024-12-31', 18.56, 8750000000, 12300000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '0241'), '2024-12-31', 3.45, 13400000000, 45600000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1093'), '2024-12-31', 6.78, 8900000000, 23400000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1177'), '2024-12-31', 3.12, 12500000000, 34500000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '1530'), '2024-12-31', 8.90, 670000000, 5670000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '6160'), '2024-12-31', 45.60, 450000000, 2340000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9926'), '2024-12-31', 32.50, 850000000, 5670000, 'activex'),
((SELECT id FROM companies WHERE stock_code = '9969'), '2024-12-31', 15.80, 1180000000, 6780000, 'activex')
ON CONFLICT (company_id, trade_date) DO NOTHING;

-- ===========================================
-- 4. Key Personnel (including Lisa Chen's bio)
-- ===========================================
INSERT INTO key_personnel (company_id, year, person_name, person_name_zh, role, role_zh, committee, biography, source_file, source_page) VALUES
-- SFC - Lisa Chen
((SELECT id FROM companies WHERE stock_code = 'SFC'), 2024, 'Lisa Chen', '陳麗莎', 'Executive Director', '執行董事', 'Enforcement Committee', 
'Lisa Chen joined the SFC in 2015 and was appointed Executive Director in 2022. She has over 20 years of experience in securities regulation and enforcement. Prior to joining the SFC, she worked at a leading international law firm specializing in financial services regulation. She holds a Bachelor of Laws from the University of Hong Kong and a Master of Laws from Harvard Law School. She has been instrumental in strengthening Hong Kong''s regulatory framework and leading high-profile enforcement actions against market misconduct.',
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
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 'Victor Li', '李澤鉅', 'Executive Director', '執行董事', 'Executive Committee',
'Victor Li is the Chairman and Executive Director of CK Hutchison Holdings. He is the elder son of Li Ka-Shing and has been leading the company since 2018.',
'CKH_AR_2023.pdf', 2),
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 'Canning Fok', '霍建寧', 'Executive Director', '執行董事', 'Executive Committee',
'Canning Fok is the Group Managing Director and Executive Director of CK Hutchison Holdings, overseeing the groups day-to-day operations.',
'CKH_AR_2023.pdf', 2)
ON CONFLICT DO NOTHING;

-- ===========================================
-- 5. Shareholdings (Li Ka-Shing Trust)
-- ===========================================
INSERT INTO shareholdings (company_id, year, shareholder_name, shareholder_name_zh, shareholder_type, percentage_held, trust_name, trustee_name, source_file, source_page) VALUES
-- CK Hutchison - Li Ka-Shing Unity Trust
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 'Li Ka-Shing Unity Trustee Company Limited', '李嘉誠聯合受託人有限公司', 'Trust', 30.52, 
'The Li Ka-Shing Unity Trust', 'Li Ka-Shing Unity Trustee Company Limited', 'CKH_AR_2023.pdf', 94),
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 'Li Ka-Shing Unity Trust', '李嘉誠聯合信託', 'Trust', 30.52,
'The Li Ka-Shing Unity Trust', 'Li Ka-Shing Unity Trustee Company Limited', 'CKH_AR_2023.pdf', 94),
-- INNOCARE major shareholders
((SELECT id FROM companies WHERE stock_code = '9969'), 2024, 'InnoCare Pharma Limited', '諾誠健華藥業有限公司', 'Corporation', 25.6, NULL, NULL, 'INNOCARE_2024_AR.pdf', 100)
ON CONFLICT (company_id, year, shareholder_name) DO NOTHING;

-- ===========================================
-- 6. Specific Events
-- ===========================================
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

-- ===========================================
-- 7. Revenue Breakdown (CK Hutchison)
-- ===========================================
INSERT INTO revenue_breakdown (company_id, year, category, category_type, percentage, amount, currency, sub_category, sub_percentage, source_file, source_page) VALUES
-- CK Hutchison - Geographic breakdown
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 'Canada', 'Region', 12.5, 58000, 'HKD', NULL, NULL, 'CKH_AR_2023.pdf', 6),
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 'Asia', 'Region', 45.2, 209500, 'HKD', 'Retail', 32.5, 'CKH_AR_2023.pdf', 6),
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 'Australia', 'Region', 8.3, 38500, 'HKD', 'Retail', 18.7, 'CKH_AR_2023.pdf', 6),
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 'Others', 'Region', 5.8, 26900, 'HKD', NULL, NULL, 'CKH_AR_2023.pdf', 6),
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 'Europe', 'Region', 28.2, 130800, 'HKD', NULL, NULL, 'CKH_AR_2023.pdf', 6)
ON CONFLICT (company_id, year, category, category_type) DO NOTHING;

-- ===========================================
-- 8. Debt Maturity (CK Hutchison)
-- ===========================================
INSERT INTO debt_maturity (company_id, year, maturity_year, amount, currency, debt_type, source_file, source_page) VALUES
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 2024, 15000, 'HKD', 'Bank Loan', 'CKH_AR_2023.pdf', 9),
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 2025, 22000, 'HKD', 'Bond', 'CKH_AR_2023.pdf', 9),
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 2026, 18500, 'HKD', 'Bank Loan', 'CKH_AR_2023.pdf', 9),
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 2027, 35000, 'HKD', 'Bond', 'CKH_AR_2023.pdf', 9),
((SELECT id FROM companies WHERE stock_code = '00001'), 2023, 2028, 28000, 'HKD', 'Bank Loan', 'CKH_AR_2023.pdf', 9)
ON CONFLICT DO NOTHING;

-- ===========================================
-- 9. Listing Applications (SFC Macro Data)
-- ===========================================
INSERT INTO listing_applications (company_id, year, application_count, approved_count, rejected_count, source_file, source_page) VALUES
-- company_id is NULL for macro-level SFC data
(NULL, 2023, 145, 128, 17, 'SFC_AR_2023_24.pdf', 49),
(NULL, 2022, 138, 121, 17, 'SFC_AR_2022_23.pdf', 48)
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
UNION ALL SELECT 'Listing Applications', COUNT(*) FROM listing_applications;