// ============================================================
// Neo4j Schema Initialization - Auto-run on Container Start
// ============================================================
// 
// Neo4j 會喺容器啟動時自動執行呢個檔案入面嘅 Cypher 命令。
// 必須要有的：Constraints 和 Indexes
// ============================================================

// ============================================================
// 1. Drop existing constraints/indexes (for re-run)
// ============================================================
DROP CONSTRAINT person_name IF EXISTS;
DROP CONSTRAINT person_name_zh IF EXISTS;
DROP CONSTRAINT company_name IF EXISTS;
DROP CONSTRAINT company_stock_code IF EXISTS;
DROP CONSTRAINT trust_name IF EXISTS;

// ============================================================
// 2. Create Constraints (Unique + Existence)
// ============================================================

// Person constraints
CREATE CONSTRAINT person_name IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT person_name_zh IF NOT EXISTS FOR (p:Person) REQUIRE p.name_zh IS UNIQUE;

// Company constraints
CREATE CONSTRAINT company_name IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT company_stock_code IF NOT EXISTS FOR (c:Company) REQUIRE c.stock_code IS UNIQUE;

// Trust constraint
CREATE CONSTRAINT trust_name IF NOT EXISTS FOR (t:Trust) REQUIRE t.name IS UNIQUE;

// ============================================================
// 3. Create Indexes (Performance)
// ============================================================

// Person indexes
CREATE INDEX person_type IF NOT EXISTS FOR (p:Person) ON (p.person_type);

// Company indexes
CREATE INDEX company_sector IF NOT EXISTS FOR (c:Company) ON (c.sector);
CREATE INDEX company_is_industry_confirmed IF NOT EXISTS FOR (c:Company) ON (c.is_industry_confirmed);

// Relationship indexes (for fast traversal)
CREATE INDEX HOLDS_SHARE_percentage IF NOT EXISTS FOR ()-[r:HOLDS_SHARE]-() ON (r.percentage);
CREATE INDEX CONTROLS_depth IF NOT EXISTS FOR ()-[r:CONTROLS]-() ON (r.depth);
CREATE INDEX APPOINTED_AS_role IF NOT EXISTS FOR ()-[r:APPOINTED_AS]-() ON (r.role);

// ============================================================
// 4. Create Initial Node Labels (Optional)
// ============================================================

// These are optional but help with type checking
// The constraints above will auto-create the labels

PRINT "✅ Neo4j Schema initialized successfully";
