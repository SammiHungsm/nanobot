-- ============================================================
-- Migration: Remove Vanna References (2026-04-25)
-- ============================================================
-- Reason: Replaced by DirectSQLTool + Apache AGE
-- - No more Vanna pre-training needed
-- - Agent writes SQL directly using schema
-- - Graph queries use Apache AGE Cypher

-- Step 1: Drop Vanna-related views
DROP VIEW IF EXISTS v_documents_for_vanna;
DROP VIEW IF EXISTS v_companies_for_vanna;
DROP VIEW IF EXISTS v_tables_with_context_for_vanna;

-- Step 2: Drop vanna_training_data table (if exists from old schema)
DROP TABLE IF EXISTS vanna_training_data;

-- Step 3: Create replacement views for DirectSQLTool
-- These views help Agent understand the schema when writing SQL

-- Document summary view (replaces v_documents_for_vanna)
CREATE OR REPLACE VIEW v_documents_summary AS
SELECT 
    d.id,
    d.doc_id,
    d.filename,
    d.report_type,
    d.year,
    d.processing_status,
    d.uploaded_at,
    d.dynamic_attributes->>'index_theme' AS index_theme,
    c.name_en AS owner_company_name,
    COUNT(dc.id) AS mentioned_companies_count
FROM documents d
LEFT JOIN companies c ON d.owner_company_id = c.id
LEFT JOIN document_companies dc ON d.id = dc.document_id
GROUP BY d.id, c.name_en;

-- Company summary view (replaces v_companies_for_vanna)
CREATE OR REPLACE VIEW v_companies_summary AS
SELECT 
    id,
    name_en,
    name_zh,
    stock_code,
    sector,
    is_industry_confirmed,
    COALESCE(
        confirmed_industry, 
        (ai_extracted_industries->>0)
    ) AS primary_industry,
    extra_data,
    created_at
FROM companies;

-- Financial metrics summary view
CREATE OR REPLACE VIEW v_financial_metrics_summary AS
SELECT 
    fm.id,
    fm.company_id,
    c.name_en AS company_name,
    fm.year,
    fm.fiscal_period,
    fm.metric_name,
    fm.metric_name_zh,
    fm.value,
    fm.unit,
    fm.standardized_value,
    fm.standardized_currency,
    fm.category
FROM financial_metrics fm
LEFT JOIN companies c ON fm.company_id = c.id;

-- Revenue breakdown summary view
CREATE OR REPLACE VIEW v_revenue_breakdown_summary AS
SELECT 
    rb.id,
    rb.company_id,
    c.name_en AS company_name,
    rb.year,
    rb.segment_name,
    rb.segment_type,
    rb.revenue_percentage,
    rb.revenue_amount,
    rb.currency
FROM revenue_breakdown rb
LEFT JOIN companies c ON rb.company_id = c.id;

-- Key personnel summary view
CREATE OR REPLACE VIEW v_key_personnel_summary AS
SELECT 
    kp.id,
    kp.company_id,
    c.name_en AS company_name,
    kp.year,
    kp.name_en,
    kp.name_zh,
    kp.position_title_en,
    kp.role,
    kp.board_role
FROM key_personnel kp
LEFT JOIN companies c ON kp.company_id = c.id;

RAISE NOTICE '✅ Vanna references removed, DirectSQLTool views created';