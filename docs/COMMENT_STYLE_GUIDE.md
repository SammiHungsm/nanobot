# Comment Style Guide

**Version:** 1.0  
**Effective Date:** 2026-04-18  
**Status:** Active

---

## Purpose

This guide establishes consistent commenting standards across the nanobot codebase to improve readability, maintainability, and collaboration.

---

## 1. Language Standard

### Rule: Use English for All Code Comments

**Rationale:** English is the universal language of programming and enables broader collaboration.

```python
# ❌ WRONG: Mixed languages
# 🌟 v4.3: Vision 必须成功，不使用 Filename Fallback
# Step 1: 检查 PyMuPDF 是否可用

# ✅ CORRECT: English only
# v4.3: Vision must succeed, no filename fallback
# Step 1: Check PyMuPDF availability
```

### Exception: User-Facing Strings

Keep user-facing strings (error messages, logs, prompts) in the project's target language (Chinese for this project):

```python
# ✅ CORRECT: English comment, Chinese user message
logger.error("❌ PDF not found")  # User-facing error in Chinese
raise FileNotFoundError(f"PDF not found: {pdf_path}")  # Exception in English
```

---

## 2. Comment Structure

### 2.1 File Headers

Every Python file should start with a module docstring:

```python
"""
Stage 0: Preprocessor and Company Metadata Extraction

Responsibilities:
- Run independently, does not wait for LlamaParse
- Extract company info from PDF cover using Vision LLM
- Register company in database immediately

v4.3 Changes:
- Vision must succeed, no filename fallback
- Uses PyMuPDF for high-DPI cover extraction
"""
```

### 2.2 Function Docstrings

Use Google-style docstrings with complete parameter documentation:

```python
async def extract_cover_metadata(
    pdf_path: str,
    doc_id: str = None,
    vision_model: str = None
) -> Dict[str, Any]:
    """
    Extract company metadata from PDF cover using Vision LLM
    
    Args:
        pdf_path: Path to PDF file
        doc_id: Document identifier (optional)
        vision_model: Vision model name (default: from llm_core)
        
    Returns:
        Dictionary containing:
        - stock_code: HK stock code (e.g., "00001")
        - year: Report year
        - name_en: Company English name
        - name_zh: Company Chinese name
        - company_id: Database ID (if registration successful)
        
    Raises:
        RuntimeError: If PyMuPDF is not installed
        FileNotFoundError: If PDF file does not exist
    """
```

### 2.3 Inline Comments

Use inline comments to explain WHY, not WHAT:

```python
# ❌ WRONG: Explains what (redundant)
company_id = result.get("company_id")  # Get company ID

# ✅ CORRECT: Explains why (valuable context)
company_id = result.get("company_id")  # Needed for Stage 4 data insertion
```

### 2.4 Section Markers

Use consistent section markers with minimal emojis:

```python
# ===== Database Operations =====  # ✅ Major section
# --- Validation ---  # ✅ Minor section
# TODO: Add retry logic  # ✅ Action items
# FIXME: Handle edge case  # ✅ Bugs to fix
```

Avoid excessive emoji use:

```python
# ❌ WRONG: Too many emojis
# 🌟 Step 1: Check PyMuPDF ✅
# 🚀 Step 2: Parse PDF 🔥
# 💾 Step 3: Save Results 💰
```

---

## 3. Comment Types

### 3.1 TODO Comments

Mark technical debt and future improvements:

```python
# TODO: Migrate to BaseIngestionPipeline
# See: nanobot/ingestion/REFACTOR_PLAN.md
# Priority: High
# Estimated effort: 2 days

# TODO(v2.4): Remove legacy support for old schema
# Timeline: Q3 2026
```

Format: `# TODO: [Optional context]`  
Include:
- What needs to be done
- Why it's needed (optional)
- Reference to planning docs (if applicable)
- Priority/effort estimate (for large tasks)

### 3.2 FIXME Comments

Mark bugs and issues:

```python
# FIXME: This fails for PDFs with >500 pages
# Root cause: Memory limit in PyMuPDF
# Workaround: Split into batches (see stage0_preprocessor.py)

# FIXME(issue#123): Race condition in concurrent writes
# Status: Investigating
```

Format: `# FIXME: [Issue description]`  
Include:
- What's broken
- Root cause (if known)
- Workaround (if available)
- Issue tracker reference (if applicable)

### 3.3 NOTE Comments

Add important context or warnings:

```python
# NOTE: This API call is rate-limited to 100 requests/minute
# Monitor: Check logs for "rate_limit_exceeded" errors

# NOTE: Schema v2.3 changed field names
# Old: trade_date, closing_price
# New: data_date, close_price
```

Format: `# NOTE: [Important information]`

### 3.4 WARNING Comments

Highlight potential pitfalls:

```python
# WARNING: Do not remove this sleep - Vanna needs time to initialize
# Removing this will cause "Vanna not ready" errors

# WARNING: This query is slow on large datasets (>10k rows)
# Consider adding index on company_id and year
```

Format: `# WARNING: [Risk description]`

---

## 4. Language-Specific Guidelines

### 4.1 Python

#### Class Docstrings

```python
class Stage0Preprocessor:
    """
    Stage 0: Cover preprocessing and company metadata extraction
    
    Responsibilities:
    - Extract cover image using PyMuPDF
    - Analyze cover with Vision LLM
    - Register company in database
    
    Dependencies:
    - PyMuPDF (fitz): PDF image extraction
    - llm_core: Vision model access
    - db_client: Database operations
    """
```

#### Type Hints

Always use type hints for function parameters and return values:

```python
# ❌ WRONG: No type hints
def parse_pdf(pdf_path, output_dir=None):
    ...

# ✅ CORRECT: Complete type hints
def parse_pdf(
    pdf_path: str,
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    ...
```

#### Magic Numbers

Replace magic numbers with named constants:

```python
# ❌ WRONG: Magic number
if len(pages) > 100:
    batch_size = 10

# ✅ CORRECT: Named constant
MAX_PAGES_BEFORE_BATCH = 100
BATCH_SIZE = 10

if len(pages) > MAX_PAGES_BEFORE_BATCH:
    batch_size = BATCH_SIZE
```

### 4.2 SQL

#### Comment Style

Use standard SQL comments with clear section markers:

```sql
-- ============================================================
-- Table: companies
-- Purpose: Store listed company basic information
-- ============================================================

-- Core fields
id SERIAL PRIMARY KEY,
stock_code VARCHAR(50) UNIQUE,  -- HK stock code format: 00001, 00700

-- Industry classification (dual-track system)
is_industry_confirmed BOOLEAN DEFAULT FALSE,  -- TRUE if from Index Report
confirmed_industry VARCHAR(100),  -- Rule A: Authoritative definition
ai_extracted_industries JSONB,  -- Rule B: AI-predicted industries
```

#### Index Documentation

Always explain WHY an index exists:

```sql
-- GIN index for JSONB queries: WHERE extracted_industries ? 'Biotech'
CREATE INDEX idx_companies_ai_industries 
ON companies USING GIN (ai_extracted_industries);

-- Composite index for common query pattern:
-- SELECT * FROM financial_metrics 
-- WHERE company_id = ? AND year = ? ORDER BY year DESC
CREATE INDEX idx_financial_metrics_company_year 
ON financial_metrics(company_id, year DESC);
```

---

## 5. Documentation Files

### 5.1 README.md

Keep README focused on:
- Project overview
- Quick start guide
- Key features
- Basic usage examples

### 5.2 Architecture Docs

Store detailed architecture in `docs/`:
- `docs/pipeline_architecture.md` - Stage flow and responsibilities
- `docs/schema_erd.md` - Database relationships
- `docs/api_reference.md` - API endpoint documentation

### 5.3 Code Review Reports

Store periodic reviews in `docs/`:
- `docs/CODE_REVIEW_YYYY-MM-DD.md` - Comprehensive code review
- Include action items and priorities
- Track improvements over time

---

## 6. Common Mistakes to Avoid

### ❌ Mistake 1: Commenting Obvious Code

```python
# ❌ BAD: Redundant comment
result = await db.insert(data)  # Insert data into database

# ✅ GOOD: No comment needed (code is self-explanatory)
result = await db.insert(data)
```

### ❌ Mistake 2: Outdated Comments

```python
# ❌ BAD: Comment doesn't match code
# Returns True on success, False on failure
def process_data(data):
    if not data:
        raise ValueError("Data cannot be empty")  # Actually raises exception
    return True

# ✅ GOOD: Update comment when code changes
# Returns True on success, raises ValueError on invalid input
def process_data(data):
    if not data:
        raise ValueError("Data cannot be empty")
    return True
```

### ❌ Mistake 3: Commented-Out Code

```python
# ❌ BAD: Left old code in comments
# old_result = legacy_process(data)
# if old_result:
#     return old_result
result = new_process(data)
return result

# ✅ GOOD: Remove commented code, use version control
result = new_process(data)
return result
```

### ❌ Mistake 4: Inconsistent Language

```python
# ❌ BAD: Mixed languages in same file
# 初始化数据库连接
# Initialize database connection
# 初始化完了就可以开始处理了
# Start processing after initialization

# ✅ GOOD: Consistent language
# Initialize database connection
# Start processing after initialization
```

---

## 7. Enforcement

### 7.1 Code Review Checklist

Reviewers should check:
- [ ] Comments are in English (except user-facing strings)
- [ ] Docstrings follow Google style
- [ ] Type hints are present
- [ ] No commented-out code
- [ ] TODOs/FIXMEs are properly formatted
- [ ] Comments explain WHY, not WHAT

### 7.2 Automated Checks

Consider adding to CI/CD:
- Pylint for docstring requirements
- Custom script to detect mixed languages
- TODO/FIXME aggregation report

---

## 8. Examples

### Complete Example: Well-Commented Function

```python
async def extract_cover_metadata(
    pdf_path: str,
    doc_id: str = None,
    vision_model: str = None,
    db_client: Any = None,
    is_index_report: bool = False
) -> Dict[str, Any]:
    """
    Extract company metadata from PDF cover using Vision LLM
    
    This is the first stage in the PDF processing pipeline. It runs
    independently (does not wait for LlamaParse) and extracts key
    information needed for downstream stages.
    
    Args:
        pdf_path: Path to PDF file
        doc_id: Document identifier (optional, defaults to PDF filename stem)
        vision_model: Vision model name (default: from llm_core.vision_model)
        db_client: Database client for company registration
        is_index_report: True if this is an index/industry report
        
    Returns:
        Dictionary containing extracted metadata:
        - stock_code: HK stock code (e.g., "00001", "00700")
        - year: Report year (e.g., 2023, 2024)
        - name_en: Company English name
        - name_zh: Company Chinese name
        - company_id: Database ID (if registration successful, else None)
        - vision_result: Raw Vision LLM response
        
    Raises:
        RuntimeError: If PyMuPDF is not installed
        FileNotFoundError: If PDF file does not exist
        ValueError: If Vision extraction fails
        
    Example:
        >>> result = await extract_cover_metadata("tencent_2023_ar.pdf")
        >>> print(result["stock_code"])
        '00700'
        
    Note:
        - Vision extraction MUST succeed (no fallback to filename parsing)
        - Company registration is attempted but failure is non-fatal
        - For index reports, stock_code and company names will be None
        
    TODO:
        - Add support for US stock codes (NYSE, NASDAQ)
        - Implement retry logic for Vision API failures
    """
    # Validate PDF exists
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    # Extract cover image using PyMuPDF
    cover_image_path = await _extract_cover_image(pdf_path, doc_id)
    if not cover_image_path:
        raise RuntimeError("Failed to extract cover image")
    
    # Extract company info using Vision LLM
    vision_result = await _vision_extract_company(
        cover_image_path=cover_image_path,
        vision_model=vision_model or llm_core.vision_model,
        is_index_report=is_index_report
    )
    
    # Register company in database (non-fatal if fails)
    company_id = None
    if db_client and vision_result.get("stock_code"):
        try:
            company_id = await db_client.upsert_company(
                stock_code=vision_result["stock_code"],
                name_en=vision_result["name_en"],
                name_zh=vision_result["name_zh"]
            )
        except Exception as e:
            logger.warning(f"Company registration failed: {e}")
    
    return {
        "stock_code": vision_result.get("stock_code"),
        "year": vision_result.get("year"),
        "name_en": vision_result.get("name_en"),
        "name_zh": vision_result.get("name_zh"),
        "company_id": company_id,
        "vision_result": vision_result
    }
```

---

## 9. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-18 | AI Agent | Initial version created from code review findings |

---

## 10. References

- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [PEP 257 - Docstring Conventions](https://peps.python.org/pep-0257/)
- [PEP 484 - Type Hints](https://peps.python.org/pep-0484/)
- [Clean Code by Robert C. Martin](https://www.amazon.com/Clean-Code-Handbook-Software-Craftsmanship/dp/0132350882)

---

**Approved by:** Project Maintainers  
**Next Review Date:** 2026-07-18 (Quarterly review recommended)
