-- ============================================================
-- Apache AGE Extension Initialization
-- ============================================================

-- Load AGE extension
CREATE EXTENSION IF NOT EXISTS age;

-- Load pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Set up AGE search path for the database
SET search_path = ag_catalog, "$user", public;

-- Create graph for annual report entity relationships
SELECT create_graph('annual_report_graph');

-- Create graph for company ownership network
SELECT create_graph('ownership_graph');

-- ============================================================
-- Graph Schema Definitions (using Cypher via AGE)
-- ============================================================

-- Create label for Company vertices
SELECT create_vlabel('annual_report_graph', 'Company');

-- Create label for Person vertices  
SELECT create_vlabel('annual_report_graph', 'Person');

-- Create label for Document vertices
SELECT create_vlabel('annual_report_graph', 'Document');

-- Create label for Shareholding edges
SELECT create_elabel('annual_report_graph', 'OWNS_SHARES');

-- Create label for Management edges
SELECT create_elabel('annual_report_graph', 'MANAGES');

-- Create label for Subsidiary edges
SELECT create_elabel('annual_report_graph', 'SUBSIDIARY_OF');

-- Create label for Director edges
SELECT create_elabel('annual_report_graph', 'DIRECTOR_OF');

-- ============================================================
-- Example: Hybrid Query (SQL + Graph)
-- This demonstrates the power of AGE - joining relational and graph data
-- ============================================================

-- Example: Find all people who manage companies in a specific sector
-- This joins our relational tables with our graph data
-- (This is a placeholder query - actual usage would join with companies table)
