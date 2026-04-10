# Sample Questions Coverage Report

## ✅ CK Hutchison (0001) 2023 Annual Report Questions

| Question | SQL Pair ID | Status |
|----------|-------------|--------|
| What is the percentage of shareholding of Li Ka-Shing Unity Trustee Company Limited as trustee of The Li Ka-Shing Unity Trust? (p94) | `shareholding_001` | ✅ Covered |
| Can you list the executive directors? (p2) | `executive_directors_001` | ✅ Covered |
| What is the % of total revenue from Canada? (p6) | `revenue_canada_001` | ✅ Covered |
| What is the % and amount of total revenue from Asia, Australia & Others? (p6) | `revenue_asia_australia_001` | ✅ Covered |
| Within Asia, Australia & Others, what is the % of revenue for Retail Sector? (p6) | `revenue_asia_retail_001` | ✅ Covered |
| Please provide the profit and loss figures with 5 comparative periods? (p273) | `profit_loss_5years_001` | ✅ Covered |
| Please provide profit attributable to ordinary shareholders from 2019-2023? (p273) | `profit_attributable_001` | ✅ Covered |
| Please provide revenue figures from 2019-2023? (p273) | `revenue_5years_001` | ✅ Covered |
| Please provide fixed assets figures from 2019-2023? (p273) | `fixed_assets_5years_001` | ✅ Covered |
| What is the amount of total debt to be matured in 2027? (p9) | `debt_maturity_2027_001` | ✅ Covered |

## ✅ SFC Annual Report 2023-24 Questions

| Question | SQL Pair ID | Status |
|----------|-------------|--------|
| What is the amount of cash at bank and in hand for 2024? (p151) | `sfc_cash_001` | ✅ Covered |
| List all members of the Securities Compensation Fund Committee? (p193) | `sfc_committee_001` | ✅ Covered |
| How many floors did SFC purchase for the OIE office? (p142) | `sfc_office_floors_001` | ✅ Covered |
| Generate the bio of Lisa Chen? (p108) | `sfc_bio_001` | ✅ Covered |
| When was the effective date of the SEHK GEM listing reform? (p47) | `sfc_listing_reform_001` | ✅ Covered |
| How many listing applications were processed by SFC? (p49) | `sfc_listing_applications_001` | ✅ Covered |
| When was the consultation on share buy-backs conducted? (p50) | `sfc_share_buyback_001` | ✅ Covered |
| How many stocks were launched for the RMB counters? (p37) | `sfc_rmb_counters_001` | ✅ Covered |

## ✅ BioTech Sector Questions (Cross-Document)

| Question | SQL Pair ID | Status |
|----------|-------------|--------|
| Provide the Top 10 stock codes and names of market capital from BioTech Sector | `biotech_top10_marketcap_001` | ✅ Covered |
| Provide the Top 5 with highest total liabilities | `biotech_top5_liabilities_001` | ✅ Covered |
| List all BioTech stocks with same auditor as stock 6160 | `biotech_same_auditor_001` | ✅ Covered |
| Provide all ultimate controlling shareholders of each BioTech stock | `biotech_shareholders_001` | ✅ Covered |
| List all BioTech companies with Qualified Opinion | `biotech_qualified_opinion_001` | ✅ Covered |

## ✅ Cross-Year Integration Questions

| Question | SQL Pair ID | Status |
|----------|-------------|--------|
| Find Top 2 BioTech stocks with highest liabilities in 2024 and show 2022 price | `biotech_top2_liabilities_price_001` | ✅ Covered |
| Plot line chart of closing price and volume for stock 09969 in 2022 | `stock_price_volume_chart_001` | ✅ Covered |
| Total revenue of stock 09969 in 2023 & 2024 and avg volume in 2022 | `stock_revenue_avg_volume_001` | ✅ Covered |
| List BioTech stocks with HSBC as principal banker and their avg 2022 price | `biotech_hsbc_avg_price_001` | ✅ Covered |

---

## Database Tables Required

| Table | Purpose | Mock Data Status |
|-------|---------|------------------|
| `companies` | Company master data | ✅ 30 BioTech + SFC + CKH |
| `financial_metrics` | Financial KPIs (EAV model) | ✅ Multi-year data |
| `market_data` | Stock prices & volumes | ✅ 2022 + 2024 data |
| `key_personnel` | Directors & committees | ✅ Full bios |
| `shareholdings` | Major shareholders | ✅ Trust structures |
| `specific_events` | Events & initiatives | ✅ SFC events |
| `revenue_breakdown` | Geographic/segment revenue | ✅ CKH breakdown |
| `debt_maturity` | Debt schedule | ✅ Multi-year |
| `listing_applications` | SFC macro data | ✅ Annual stats |
| `documents` | Document-centric (new) | ✅ Sample docs |
| `document_companies` | Company associations | ✅ Linked |

---

## Vanna Training Data Summary

- **SQL Pairs**: 40+ examples covering all query patterns
- **Documentation**: 50+ critical definitions and examples
- **Key Concepts Covered**:
  - EAV model queries (`financial_metrics`)
  - JSONB dynamic attributes (`dynamic_attributes->>'key'`)
  - Market cap calculation (`closing_price * issued_shares`)
  - Standardized values for cross-company comparison
  - Rule A/B industry assignment logic
  - Cross-year JOIN queries

---

## BioTech Stocks Coverage (30 stocks)

| Stock Code | Company Name | Has Data |
|------------|--------------|----------|
| 0013 | HUTCHMED | ✅ |
| 0241 | ALI HEALTH | ✅ |
| 0512 | GRAND PHARMA | ✅ |
| 0853 | MICROPORT | ✅ |
| 0867 | CMS | ✅ |
| 1066 | WEIGAO GROUP | ✅ |
| 1093 | CSPC PHARMA | ✅ |
| 1099 | SINOPHARM | ✅ |
| 1177 | SINO BIOPHARM | ✅ |
| 1530 | 3SBIO | ✅ (Qualified Opinion) |
| 1548 | GENSCRIPT BIO | ✅ |
| 1801 | INNOVENT BIO | ✅ |
| 1952 | EVEREST MED | ✅ |
| 2096 | SIMCERE PHARMA | ✅ |
| 2228 | XTALPI | ✅ |
| 2252 | MEDBOT-B | ✅ |
| 2268 | WUXI XDC | ✅ |
| 2269 | WUXI BIO | ✅ |
| 2359 | WUXI APPTEC | ✅ |
| 3320 | CHINARES PHARMA | ✅ |
| 3692 | HANSOH PHARMA | ✅ |
| 3933 | UNITED LAB | ✅ |
| 6160 | BEONE MEDICINES | ✅ (Same auditor query) |
| 6618 | JD HEALTH | ✅ |
| 6855 | ASCENTAGE-B | ✅ |
| 6990 | SKB BIO-B | ✅ |
| 9688 | ZAI LAB | ✅ |
| 9926 | AKESO | ✅ |
| 9969 | INNOCARE | ✅ (Detailed 2022 data) |

---

## Key SQL Patterns for Vanna

### 1. Market Cap Calculation
```sql
SELECT c.stock_code, c.name_en, 
       (m.closing_price * m.issued_shares) as market_capital
FROM companies c JOIN market_data m ON c.id = m.company_id
WHERE c.sector = 'BioTech' AND m.trade_date = '2024-12-31'
ORDER BY market_capital DESC LIMIT 10;
```

### 2. Cross-Year Liabilities + Price
```sql
SELECT c.stock_code, fm.standardized_value as liabilities_2024,
       m.closing_price as price_2022
FROM companies c
JOIN financial_metrics fm ON c.id = fm.company_id
JOIN market_data m ON c.id = m.company_id
WHERE c.sector = 'BioTech' 
  AND fm.metric_name = 'Total Liabilities' AND fm.year = 2024
  AND m.trade_date BETWEEN '2022-01-01' AND '2022-12-31'
ORDER BY fm.standardized_value DESC;
```

### 3. JSONB Dynamic Attributes
```sql
SELECT filename, dynamic_attributes->>'index_quarter' as quarter
FROM documents 
WHERE dynamic_attributes->>'index_quarter' = 'Q3';
```

### 4. Rule A Industry (Index Reports)
```sql
SELECT d.filename, dc.company_name, dc.assigned_industry
FROM documents d 
JOIN document_companies dc ON d.id = dc.document_id
WHERE d.is_index_report = TRUE 
  AND dc.industry_source = 'confirmed';
```

---

**All sample questions are covered! ✅**