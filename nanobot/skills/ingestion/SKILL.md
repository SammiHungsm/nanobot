---
name: ingestion
description: Intelligent document ingestion for PDF reports with industry assignment rules (Rule A/B).
metadata: {"nanobot":{"emoji":"📄","requires":{"tools":["smart_insert_document","get_db_schema","update_document_status"]}}}
---

# Ingestion Skill

Intelligent document ingestion for processing PDF reports with automatic industry assignment rules.

## Capabilities

- **Document Type Detection**: Automatically identify annual reports vs index reports
- **Industry Assignment Rules**: Apply Rule A (confirmed industry) or Rule B (AI extraction)
- **Entity Extraction**: Extract parent company, subsidiaries, stock codes
- **Dynamic Attributes**: Store flexible metadata in JSONB columns
- **Smart Database Insert**: Write documents and related companies atomically

---

## Rules

### Rule A (Index Reports - Confirmed Industry)

**Trigger**: Report explicitly defines a single industry theme (e.g., "Hang Seng Biotech Index")

**Behavior**:
1. Extract `confirmed_doc_industry` from report title/intro
2. Set `industry_assignment_rule = "A"`
3. Force ALL constituent companies to have the same industry
4. Do NOT generate multiple AI industry predictions

**Example**:
```
Report: "Hang Seng Biotech Index Q3 2024"
→ confirmed_industry = "Biotech"
→ All constituents: assigned_industry = "Biotech"
→ industry_source = "confirmed"
```

### Rule B (Annual Reports - AI Extraction)

**Trigger**: Annual report or comprehensive report without single industry theme

**Behavior**:
1. `confirmed_doc_industry = null`
2. Set `industry_assignment_rule = "B"`
3. AI extracts possible industries for each company
4. Store in `ai_suggested_industries` JSONB column

**Example**:
```
Report: "Tencent Holdings Annual Report 2023"
→ parent_company = "Tencent Holdings"
→ For each subsidiary: ai_suggested_industries = ["Technology", "Gaming", "Social Media"]
→ industry_source = "ai_extracted"
```

---

## Tools Required

### 1. `smart_insert_document`

**Use when**: After analyzing PDF first 1-2 pages

**Input**:
```json
{
  "filename": "hsi_biotech_q3_2024.pdf",
  "report_type": "index_report",
  "parent_company": null,
  "index_theme": "Hang Seng Biotech Index",
  "confirmed_doc_industry": "Biotech",
  "industry_assignment_rule": "A",
  "dynamic_data": {
    "index_quarter": "Q3",
    "report_year": "2024"
  },
  "sub_companies": [
    {"name": "Company A", "stock_code": "0001.HK"},
    {"name": "Company B", "stock_code": "0002.HK"}
  ]
}
```

**Output**:
```json
{
  "success": true,
  "document_id": 42,
  "companies_inserted": 2,
  "rule_applied": "A"
}
```

---

### 2. `get_db_schema`

**Use when**: Before inserting to understand current database structure

**Output**: Current tables, columns, and JSONB keys

---

### 3. `update_document_status`

**Use when**: After processing to update status

**Input**:
```json
{
  "document_id": 42,
  "status": "completed",
  "notes": "Successfully processed 2 constituent companies"
}
```

---

## Thinking Process

When analyzing a PDF document:

```
[PLAN]
Input: PDF first 1-2 pages content

1. Document Type Detection:
   - Check for "Index", "恒生指數", "HSI" keywords → Index Report
   - Check for single company name + "Annual Report" → Annual Report
   - Check for explicit industry theme in title

2. Industry Rule Selection:
   - Explicit industry theme? → Rule A
   - No single theme? → Rule B

3. Entity Extraction:
   - Extract parent company (if annual report)
   - Extract index theme (if index report)
   - Extract constituent companies + stock codes
   - Extract dynamic attributes (quarter, year, etc.)

4. Database Insert:
   - Call smart_insert_document with extracted data
   - Apply correct industry assignment rule

5. Status Update:
   - Call update_document_status with result
```

---

## Output Format

### For Index Report (Rule A):
```json
{
  "filename": "hsi_biotech_q3_2024.pdf",
  "report_type": "index_report",
  "parent_company": null,
  "index_theme": "Hang Seng Biotech Index",
  "confirmed_doc_industry": "Biotech",
  "industry_assignment_rule": "A",
  "dynamic_data": {
    "index_quarter": "Q3",
    "report_year": "2024",
    "base_date": "2024-09-30"
  },
  "sub_companies": [
    {"name": "Sino Biopharmaceutical", "stock_code": "1177.HK"},
    {"name": "Wuxi Biologics", "stock_code": "2269.HK"}
  ]
}
```

### For Annual Report (Rule B):
```json
{
  "filename": "tencent_2023_ar.pdf",
  "report_type": "annual_report",
  "parent_company": "Tencent Holdings Limited",
  "index_theme": null,
  "confirmed_doc_industry": null,
  "industry_assignment_rule": "B",
  "dynamic_data": {
    "report_year": "2023",
    "is_audited": true
  },
  "sub_companies": [
    {
      "name": "Tencent Music",
      "stock_code": "TME",
      "ai_industries": ["Technology", "Entertainment", "Streaming"]
    },
    {
      "name": "WeChat Pay",
      "stock_code": null,
      "ai_industries": ["FinTech", "Payments"]
    }
  ]
}
```

---

## Database Schema Reference (v2.3)

### documents table (v2.3):
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key (Integer) |
| doc_id | VARCHAR(255) | Unique string ID |
| owner_company_id | INTEGER | FK to companies (for annual reports) |
| filename | VARCHAR(500) | File name |
| report_type | VARCHAR(50) | 'annual_report' or 'index_report' |
| processing_status | VARCHAR(50) | 'pending', 'processing', 'completed', 'failed' |
| year | INTEGER | Report year |

**Note**: `parent_company`, `index_theme`, `confirmed_industry`, `dynamic_attributes` are DELETED in v2.3.

### companies table (v2.3):
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| stock_code | VARCHAR(50) | Stock code (e.g., 0700.HK) |
| name_en | VARCHAR(255) | Company name (English) |
| name_zh | VARCHAR(255) | Company name (Chinese) |
| confirmed_industry | VARCHAR(100) | Confirmed industry (Rule A) |
| is_industry_confirmed | BOOLEAN | TRUE if industry is confirmed |
| ai_extracted_industries | JSONB | AI extracted industries (Rule B) |
| extra_data | JSONB | Flexible metadata & dynamic attributes |

### document_companies table (v2.3):
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| document_id | INTEGER | FK to documents(id) |
| company_id | INTEGER | FK to companies(id) |
| relation_type | VARCHAR(50) | 'mentioned', 'subsidiary', 'owner' |
| extracted_industries | JSONB | AI extracted industries (Rule B) |
| extraction_source | VARCHAR(50) | 'confirmed' or 'ai_predict' |

---

## JSONB Query Examples (Schema v2.3)

```sql
-- Extract dynamic attribute (companies.extra_data)
SELECT extra_data->>'index_quarter' FROM companies;

-- Query by dynamic attribute (companies)
SELECT c.name_en, c.extra_data->>'index_theme' 
FROM companies c
WHERE c.extra_data->>'index_quarter' = 'Q3';

-- Check if industry exists in JSON array (document_companies)
SELECT dc.document_id, c.name_en 
FROM document_companies dc
JOIN companies c ON dc.company_id = c.id
WHERE dc.extracted_industries ? 'Biotech';

-- Check if key exists (companies.extra_data)
SELECT * FROM companies 
WHERE extra_data ? 'base_date';

-- Join documents with companies (v2.3)
SELECT d.filename, c.name_en, c.confirmed_industry
FROM documents d
JOIN companies c ON d.owner_company_id = c.id;

-- Multi-company query (document_companies bridge table)
SELECT d.filename, c.name_en, dc.extraction_source
FROM documents d
JOIN document_companies dc ON dc.document_id = d.id
JOIN companies c ON dc.company_id = c.id;
```

---

## Error Handling

If processing fails:
1. Call `update_document_status` with status="failed"
2. Include error details in notes
3. Document will appear in `data_review_queue` for manual review