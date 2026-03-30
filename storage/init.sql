-- Annual Report PoC Database Initialization
-- Creates schema for financial metrics storage

-- Enable pgvector extension for hybrid search (optional)
CREATE EXTENSION IF NOT EXISTS vector;

-- Companies master table
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    name_en VARCHAR(255) NOT NULL,
    name_zh VARCHAR(255),
    stock_code VARCHAR(20) UNIQUE,
    industry VARCHAR(100),
    sector VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_company UNIQUE (name_en, name_zh)
);

CREATE INDEX idx_company_name ON companies USING btree (name_en, name_zh);
CREATE INDEX idx_company_stock ON companies USING btree (stock_code);
CREATE INDEX idx_company_industry ON companies USING btree (industry);

-- Financial metrics records
CREATE TABLE IF NOT EXISTS metric_records (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    fiscal_period VARCHAR(10) NOT NULL,  -- 'FY', 'H1', 'Q1', etc.
    
    metric_name VARCHAR(100) NOT NULL,
    metric_name_zh VARCHAR(100) NOT NULL,
    
    value DOUBLE PRECISION NOT NULL,
    unit VARCHAR(20) NOT NULL,  -- 'CNY', 'USD', 'percentage'
    category VARCHAR(50),  -- 'revenue', 'profit', 'asset', etc.
    
    -- Audit trail
    source_file VARCHAR(500) NOT NULL,
    source_page INTEGER,
    source_table_id VARCHAR(100),
    extraction_confidence FLOAT DEFAULT 1.0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_metric UNIQUE (company_id, year, fiscal_period, metric_name)
);

CREATE INDEX idx_metric_company ON metric_records USING btree (company_id);
CREATE INDEX idx_metric_year ON metric_records USING btree (year);
CREATE INDEX idx_metric_name ON metric_records USING btree (metric_name);
CREATE INDEX idx_metric_category ON metric_records USING btree (category);
CREATE INDEX idx_metric_lookup ON metric_records USING btree (company_id, year, metric_name);

-- Documents table for MongoDB-style storage in PostgreSQL (optional)
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    
    title VARCHAR(500) NOT NULL,
    document_type VARCHAR(50),  -- 'annual_report', 'interim_report', etc.
    year INTEGER,
    fiscal_period VARCHAR(10),
    
    file_path VARCHAR(500) UNIQUE NOT NULL,
    file_hash VARCHAR(64) UNIQUE,  -- SHA256 for deduplication
    
    parsed_text TEXT,  -- Full parsed text for search
    metadata_json JSONB,  -- Additional metadata
    
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

CREATE INDEX idx_document_company ON documents USING btree (company_id);
CREATE INDEX idx_document_year ON documents USING btree (year);
CREATE INDEX idx_document_type ON documents USING btree (document_type);
CREATE INDEX idx_document_text ON documents USING gin (to_tsvector('english', parsed_text));

-- Insert sample companies (can be removed if not needed)
INSERT INTO companies (name_en, name_zh, stock_code, industry) VALUES
    ('Tencent Holdings', '腾讯控股', '0700.HK', 'Technology'),
    ('Alibaba Group', '阿里巴巴集团', '9988.HK', 'E-commerce'),
    ('JD.com', '京东', '9618.HK', 'E-commerce'),
    ('Meituan', '美团', '3690.HK', 'Technology'),
    ('Xiaomi Corporation', '小米集团', '1810.HK', 'Consumer Electronics')
ON CONFLICT (stock_code) DO NOTHING;

-- Create view for easy metric lookup
CREATE OR REPLACE VIEW v_metric_summary AS
SELECT 
    c.name_en,
    c.name_zh,
    c.stock_code,
    m.year,
    m.fiscal_period,
    m.metric_name,
    m.value,
    m.unit,
    m.source_file,
    m.source_page
FROM metric_records m
JOIN companies c ON m.company_id = c.id
ORDER BY c.name_en, m.year DESC;

-- Grant permissions (adjust as needed)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

COMMENT ON TABLE companies IS 'Master table for companies covered in annual reports';
COMMENT ON TABLE metric_records IS 'Financial metrics extracted from annual reports';
COMMENT ON TABLE documents IS 'Document metadata and parsed content';
