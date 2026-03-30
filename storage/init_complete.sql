-- SFC AI 財報分析系統 - 完整數據庫 Schema
-- PostgreSQL 16 + pgvector
-- 支持：結構化財務數據 + 非結構化知識圖譜 + 原始文檔追蹤

-- Enable pgvector extension for hybrid search (optional but recommended)
CREATE EXTENSION IF NOT EXISTS vector;

-- ===========================================
-- 1. Companies Master Table
-- ===========================================
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    name_en VARCHAR(255) NOT NULL,
    name_zh VARCHAR(255),
    stock_code VARCHAR(20) UNIQUE,
    industry VARCHAR(100),
    sector VARCHAR(100),
    listing_status VARCHAR(50) DEFAULT 'listed',  -- 'listed', 'delisted', 'private'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_company UNIQUE (name_en, name_zh)
);

CREATE INDEX idx_company_name ON companies USING btree (name_en, name_zh);
CREATE INDEX idx_company_stock ON companies USING btree (stock_code);
CREATE INDEX idx_company_industry ON companies USING btree (industry);

COMMENT ON TABLE companies IS 'Master table for companies covered in annual reports';

-- ===========================================
-- 2. Financial Metrics (結構化數字 - Vanna 專用)
-- ===========================================
CREATE TABLE IF NOT EXISTS financial_metrics (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    fiscal_period VARCHAR(10) NOT NULL,  -- 'FY', 'H1', 'Q1', etc.
    
    metric_name VARCHAR(100) NOT NULL,
    metric_name_zh VARCHAR(100) NOT NULL,
    
    value DOUBLE PRECISION NOT NULL,
    unit VARCHAR(20) NOT NULL,  -- 'CNY', 'USD', 'HKD', 'percentage', 'ratio'
    category VARCHAR(50),  -- 'revenue', 'profit', 'asset', 'liability', 'cash_flow', etc.
    
    -- Audit trail (100% 可追溯)
    source_file VARCHAR(500) NOT NULL,
    source_page INTEGER,
    source_table_id VARCHAR(100),
    extraction_confidence FLOAT DEFAULT 1.0,
    extraction_method VARCHAR(50),  -- 'manual', 'ocr', 'llm_extracted'
    
    -- Validation
    validated BOOLEAN DEFAULT FALSE,
    validated_by VARCHAR(100),
    validated_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_metric UNIQUE (company_id, year, fiscal_period, metric_name)
);

CREATE INDEX idx_metric_company ON financial_metrics USING btree (company_id);
CREATE INDEX idx_metric_year ON financial_metrics USING btree (year);
CREATE INDEX idx_metric_name ON financial_metrics USING btree (metric_name);
CREATE INDEX idx_metric_category ON financial_metrics USING btree (category);
CREATE INDEX idx_metric_lookup ON financial_metrics USING btree (company_id, year, metric_name);
CREATE INDEX idx_metric_period ON financial_metrics USING btree (fiscal_period);

COMMENT ON TABLE financial_metrics IS 'Financial metrics extracted from annual reports (Vanna SQL query target)';

-- ===========================================
-- 3. Knowledge Graph (實體與關係 - Qwen 抽取)
-- ===========================================
CREATE TABLE IF NOT EXISTS knowledge_graph (
    id SERIAL PRIMARY KEY,
    
    -- Entity type: 'person', 'event', 'organization', 'product', 'location', 'award'
    entity_type VARCHAR(50) NOT NULL,
    entity_name VARCHAR(255) NOT NULL,
    entity_name_zh VARCHAR(255),
    
    -- Attributes stored as JSONB (flexible schema)
    attributes JSONB DEFAULT '{}',
    -- Example attributes:
    -- Person: {title: 'Chairman', gender: 'M', age: 65}
    -- Event: {date: '2024-03-15', type: 'AGM', location: 'HK'}
    -- Organization: {type: 'subsidiary', ownership: '100%'}
    
    -- Relationships (stored as JSONB array)
    relations JSONB DEFAULT '[]',
    -- Example: [{"relation": "attended", "target_entity_id": 123, "context": "2023 AGM"}]
    
    -- Source tracking
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    source_file VARCHAR(500) NOT NULL,
    source_page INTEGER,
    extraction_confidence FLOAT DEFAULT 1.0,
    
    -- Metadata
    language VARCHAR(10) DEFAULT 'zh',
    verified BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_kg_entity_type ON knowledge_graph USING btree (entity_type);
CREATE INDEX idx_kg_entity_name ON knowledge_graph USING btree (entity_name, entity_name_zh);
CREATE INDEX idx_kg_company ON knowledge_graph USING btree (company_id);
CREATE INDEX idx_kg_attributes ON knowledge_graph USING gin (attributes);
CREATE INDEX idx_kg_relations ON knowledge_graph USING gin (relations);

-- Full-text search on entity names
CREATE INDEX idx_kg_entity_search ON knowledge_graph USING gin (
    to_tsvector('simple', entity_name || ' ' || COALESCE(entity_name_zh, ''))
);

COMMENT ON TABLE knowledge_graph IS 'Entities and relationships extracted from annual reports (people, events, organizations)';

-- ===========================================
-- 4. Document Chunks (非結構化文本 - JSONB 存儲)
-- ===========================================
CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(100) NOT NULL,  -- Unique document identifier
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    
    -- Chunk metadata
    chunk_index INTEGER NOT NULL,  -- Sequential order
    page_num INTEGER,
    section_title VARCHAR(500),
    chunk_type VARCHAR(50),  -- 'text', 'table', 'figure_caption', 'footer'
    
    -- Content
    content TEXT NOT NULL,  -- Extracted text content
    content_json JSONB,  -- Structured content (e.g., table as JSON)
    
    -- OpenDataLoader metadata (JSONB for flexibility)
    metadata JSONB DEFAULT '{}',
    -- Example metadata:
    -- {
    --   "bbox": [x1, y1, x2, y2],
    --   "font_size": 12,
    --   "is_header": false,
    --   "table_id": "table_001",
    --   "confidence": 0.98
    -- }
    
    -- Embedding (optional, for hybrid search)
    embedding vector(768),  -- Adjust dimension based on embedding model
    
    -- Source tracking
    source_file VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64),  -- SHA256 for deduplication
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chunks_doc ON document_chunks USING btree (doc_id);
CREATE INDEX idx_chunks_company ON document_chunks USING btree (company_id);
CREATE INDEX idx_chunks_page ON document_chunks USING btree (page_num);
CREATE INDEX idx_chunks_type ON document_chunks USING btree (chunk_type);
CREATE INDEX idx_chunks_metadata ON document_chunks USING gin (metadata);
CREATE INDEX idx_chunks_content ON document_chunks USING gin (to_tsvector('simple', content));
CREATE INDEX idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

COMMENT ON TABLE document_chunks IS 'Document text chunks with JSONB metadata (OpenDataLoader output)';

-- ===========================================
-- 5. Raw Artifacts (原始檔案追蹤)
-- ===========================================
CREATE TABLE IF NOT EXISTS raw_artifacts (
    id SERIAL PRIMARY KEY,
    artifact_id VARCHAR(100) UNIQUE NOT NULL,  -- Unique artifact identifier
    doc_id VARCHAR(100) NOT NULL,  -- Parent document
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    
    -- Artifact type: 'image', 'table_json', 'layered_pdf', 'chart', 'signature'
    file_type VARCHAR(50) NOT NULL,
    
    -- File location (IMPORTANT: store path only, NOT file content)
    file_path VARCHAR(500) NOT NULL,  -- Relative path in Docker volume
    file_size_bytes BIGINT,
    file_mime_type VARCHAR(100),
    
    -- Extracted metadata
    metadata JSONB DEFAULT '{}',
    -- Example:
    -- {
    --   "page_num": 5,
    --   "caption": "Figure 1: Revenue Growth",
    --   "table_rows": 15,
    --   "table_cols": 6,
    --   "ocr_confidence": 0.95
    -- }
    
    -- Link to processed data
    linked_chunk_id INTEGER REFERENCES document_chunks(id),
    linked_metric_id INTEGER REFERENCES financial_metrics(id),
    
    -- Source tracking
    source_file VARCHAR(500) NOT NULL,
    page_num INTEGER,
    extraction_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_artifacts_doc ON raw_artifacts USING btree (doc_id);
CREATE INDEX idx_artifacts_company ON raw_artifacts USING btree (company_id);
CREATE INDEX idx_artifacts_type ON raw_artifacts USING btree (file_type);
CREATE INDEX idx_artifacts_metadata ON raw_artifacts USING gin (metadata);
CREATE INDEX idx_artifacts_linked_chunk ON raw_artifacts USING btree (linked_chunk_id);
CREATE INDEX idx_artifacts_linked_metric ON raw_artifacts USING btree (linked_metric_id);

COMMENT ON TABLE raw_artifacts IS 'Raw artifacts (images, tables, PDFs) stored in Docker volume - DB stores paths only';

-- ===========================================
-- 6. Documents Master Table (文檔級別追蹤)
-- ===========================================
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(100) UNIQUE NOT NULL,  -- Unique document identifier
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    
    title VARCHAR(500) NOT NULL,
    title_zh VARCHAR(500),
    document_type VARCHAR(50),  -- 'annual_report', 'interim_report', 'prospectus', etc.
    year INTEGER,
    fiscal_period VARCHAR(10),
    
    -- File info
    file_path VARCHAR(500) UNIQUE NOT NULL,
    file_hash VARCHAR(64) UNIQUE,  -- SHA256 for deduplication
    file_size_bytes BIGINT,
    
    -- Processing status
    processing_status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP,
    processing_error TEXT,
    
    -- Statistics
    total_pages INTEGER,
    total_chunks INTEGER,
    total_artifacts INTEGER,
    
    -- Metadata
    metadata_json JSONB,
    
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_document_doc_id ON documents USING btree (doc_id);
CREATE INDEX idx_document_company ON documents USING btree (company_id);
CREATE INDEX idx_document_year ON documents USING btree (year);
CREATE INDEX idx_document_type ON documents USING btree (document_type);
CREATE INDEX idx_document_status ON documents USING btree (processing_status);

COMMENT ON TABLE documents IS 'Master document tracking table';

-- ===========================================
-- 7. Processing Queue (任務隊列)
-- ===========================================
CREATE TABLE IF NOT EXISTS processing_queue (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(100) REFERENCES documents(doc_id) ON DELETE CASCADE,
    
    task_type VARCHAR(50) NOT NULL,  -- 'parse', 'extract', 'train_vanna'
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed'
    priority INTEGER DEFAULT 0,
    
    payload JSONB,
    result JSONB,
    error_message TEXT,
    
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_queue_status ON processing_queue USING btree (status);
CREATE INDEX idx_queue_doc ON processing_queue USING btree (doc_id);
CREATE INDEX idx_queue_priority ON processing_queue USING btree (priority DESC);

COMMENT ON TABLE processing_queue IS 'Background processing queue';

-- ===========================================
-- 8. Views for Easy Querying
-- ===========================================

-- Financial metrics summary view
CREATE OR REPLACE VIEW v_metric_summary AS
SELECT 
    c.name_en AS company_en,
    c.name_zh AS company_zh,
    c.stock_code,
    c.industry,
    m.year,
    m.fiscal_period,
    m.metric_name,
    m.metric_name_zh,
    m.value,
    m.unit,
    m.category,
    m.source_file,
    m.source_page,
    m.extraction_confidence,
    m.validated
FROM financial_metrics m
JOIN companies c ON m.company_id = c.id
ORDER BY c.name_en, m.year DESC, m.fiscal_period;

-- Knowledge graph with relationships
CREATE OR REPLACE VIEW v_kg_entities AS
SELECT 
    kg.id,
    kg.entity_type,
    kg.entity_name,
    kg.entity_name_zh,
    kg.attributes,
    kg.relations,
    c.name_en AS company_en,
    c.stock_code,
    kg.source_file,
    kg.source_page,
    kg.created_at
FROM knowledge_graph kg
LEFT JOIN companies c ON kg.company_id = c.id
ORDER BY kg.entity_type, kg.entity_name;

-- Document artifacts with links
CREATE OR REPLACE VIEW v_document_artifacts AS
SELECT 
    d.doc_id,
    d.title,
    d.document_type,
    d.year,
    ra.artifact_id,
    ra.file_type,
    ra.file_path,
    ra.metadata,
    ra.page_num
FROM documents d
JOIN raw_artifacts ra ON d.doc_id = ra.doc_id
ORDER BY d.doc_id, ra.page_num, ra.file_type;

-- ===========================================
-- 9. Functions & Triggers
-- ===========================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_companies_updated_at BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_financial_metrics_updated_at BEFORE UPDATE ON financial_metrics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===========================================
-- 10. Sample Data (可選 - 測試用)
-- ===========================================
INSERT INTO companies (name_en, name_zh, stock_code, industry, sector) VALUES
    ('Tencent Holdings', '腾讯控股', '0700.HK', 'Technology', 'Internet'),
    ('Alibaba Group', '阿里巴巴集团', '9988.HK', 'E-commerce', 'Internet'),
    ('JD.com', '京东', '9618.HK', 'E-commerce', 'Internet'),
    ('Meituan', '美团', '3690.HK', 'Technology', 'Internet Services'),
    ('Xiaomi Corporation', '小米集团', '1810.HK', 'Consumer Electronics', 'Hardware')
ON CONFLICT (stock_code) DO NOTHING;

-- ===========================================
-- 11. Permissions
-- ===========================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

-- ===========================================
-- Schema Documentation
-- ===========================================
COMMENT ON SCHEMA public IS 'SFC AI 財報分析系統 - 企業級 PostgreSQL Schema (100% Auditability)';
