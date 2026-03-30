"""
Phase 1 Setup Verification Script

Tests:
1. Docker containers running (PostgreSQL + MongoDB)
2. Database connections
3. OpenDataLoader-PDF installation and parsing
4. Sample PDF parsing quality check

Usage:
    python test_phase1_setup.py
"""

import sys
import json
from pathlib import Path
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>")

# Test colors
class Colors:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"

def print_header(text: str):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BLUE}{text:^60}{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")

def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")

# ============================================================================
# TEST 1: Check Docker Containers
# ============================================================================

def test_docker_containers():
    """Check if PostgreSQL and MongoDB containers are running"""
    print_header("TEST 1: Docker Containers Status")
    
    try:
        import subprocess
        
        # Check PostgreSQL
        logger.info("Checking PostgreSQL container...")
        result = subprocess.run(
            ["docker", "exec", "postgres-financial", "pg_isready", "-U", "postgres"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print_success("PostgreSQL container is running and accepting connections")
        else:
            print_error("PostgreSQL container is NOT running")
            print_warning("Try: docker-compose -f docker-compose-financial.yml up -d postgres-financial")
            return False
        
        # Check MongoDB
        logger.info("Checking MongoDB container...")
        result = subprocess.run(
            ["docker", "exec", "mongodb-docs", "mongosh", "--eval", "db.adminCommand('ping')"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if "ok" in result.stdout.lower():
            print_success("MongoDB container is running and accepting connections")
        else:
            print_error("MongoDB container is NOT running")
            print_warning("Try: docker-compose -f docker-compose-financial.yml up -d mongodb-docs")
            return False
        
        return True
        
    except subprocess.TimeoutExpired:
        print_error("Docker command timed out")
        return False
    except FileNotFoundError:
        print_error("Docker not found. Is Docker Desktop running?")
        return False
    except Exception as e:
        print_error(f"Docker check failed: {e}")
        return False

# ============================================================================
# TEST 2: PostgreSQL Connection & Schema
# ============================================================================

def test_postgresql_connection():
    """Test PostgreSQL connection and check schema"""
    print_header("TEST 2: PostgreSQL Connection & Schema")
    
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        # Connection parameters (matching docker-compose-financial.yml)
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="annual_reports",
            user="postgres",
            password="postgres_password_change_me"
        )
        
        print_success("Successfully connected to PostgreSQL (localhost:5433)")
        
        # Check if tables exist
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT table_name, table_schema 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
            
            tables = cur.fetchall()
            
            if tables:
                print_success(f"Found {len(tables)} tables in 'public' schema:")
                for table in tables:
                    print(f"  - {table['table_name']}")
            else:
                print_warning("No tables found. Run init.sql to create schema.")
        
        # Check if pgvector extension is installed
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pg_extension WHERE extname = 'vector'")
            if cur.fetchone():
                print_success("pgvector extension is installed")
            else:
                print_warning("pgvector extension NOT found (optional for hybrid search)")
        
        # Test query with sample data
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) as count FROM companies")
            result = cur.fetchone()
            if result and result['count'] > 0:
                print_success(f"Database has {result['count']} companies loaded")
            else:
                print_warning("No companies in database yet")
        
        conn.close()
        print_success("PostgreSQL connection test PASSED")
        return True
        
    except ImportError:
        print_error("psycopg2 not installed. Run: pip install psycopg2-binary")
        return False
    except psycopg2.OperationalError as e:
        print_error(f"Cannot connect to PostgreSQL: {e}")
        print_warning("Make sure PostgreSQL container is running: docker-compose -f docker-compose-financial.yml up -d postgres-financial")
        return False
    except Exception as e:
        print_error(f"PostgreSQL test failed: {e}")
        return False

# ============================================================================
# TEST 3: MongoDB Connection
# ============================================================================

def test_mongodb_connection():
    """Test MongoDB connection"""
    print_header("TEST 3: MongoDB Connection")
    
    try:
        from pymongo import MongoClient
        
        # Connection string (matching docker-compose-financial.yml)
        client = MongoClient(
            "mongodb://mongo:mongo_password_change_me@localhost:27018/",
            serverSelectionTimeoutMS=5000
        )
        
        # Test connection
        client.admin.command('ping')
        print_success("Successfully connected to MongoDB (localhost:27018)")
        
        # List databases
        dbs = client.list_database_names()
        if "annual_reports" in dbs:
            print_success("annual_reports database exists")
        else:
            print_warning("annual_reports database not created yet (will be created on first write)")
        
        # Show collections
        db = client["annual_reports"]
        collections = db.list_collection_names()
        if collections:
            print_success(f"Found {len(collections)} collections:")
            for col in collections:
                print(f"  - {col}")
        else:
            print_warning("No collections yet (empty database)")
        
        client.close()
        print_success("MongoDB connection test PASSED")
        return True
        
    except ImportError:
        print_error("pymongo not installed. Run: pip install pymongo")
        return False
    except Exception as e:
        print_error(f"MongoDB connection failed: {e}")
        print_warning("Make sure MongoDB container is running: docker-compose -f docker-compose-financial.yml up -d mongodb-docs")
        return False

# ============================================================================
# TEST 4: OpenDataLoader-PDF Installation
# ============================================================================

def test_opendataloader_installation():
    """Test if OpenDataLoader-PDF is installed"""
    print_header("TEST 4: OpenDataLoader-PDF Installation")
    
    try:
        import opendataloader_pdf
        print_success("opendataloader_pdf is installed")
        
        # Check version
        if hasattr(opendataloader_pdf, '__version__'):
            print(f"  Version: {opendataloader_pdf.__version__}")
        
        # Check if hybrid mode is available
        try:
            from opendataloader_pdf import HybridClient
            print_success("Hybrid mode is available (for scanned PDFs)")
        except ImportError:
            print_warning("Hybrid mode NOT available (install with: pip install 'opendataloader-pdf[hybrid]')")
        
        return True
        
    except ImportError:
        print_error("opendataloader_pdf is NOT installed")
        print_warning("Install with: pip install -U opendataloader-pdf")
        print_warning("For scanned PDFs: pip install 'opendataloader-pdf[hybrid]'")
        return False

# ============================================================================
# TEST 5: OpenDataLoader-PDF Parsing Test
# ============================================================================

def test_opendataloader_parsing(pdf_path: str = None):
    """Test PDF parsing with OpenDataLoader-PDF"""
    print_header("TEST 5: OpenDataLoader-PDF Parsing Quality")
    
    # Find a test PDF
    if not pdf_path:
        # Try common locations
        test_paths = [
            "C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/LightRAG/data/input/__enqueued__/ar_2025_full_en.pdf",
            "C:/Users/sammi_hung/AnnualReportPoC/data/raw/ar_2025_full_en.pdf",
            "C:/Users/sammi_hung/lobsterai/project/test.pdf",
        ]
        
        for path in test_paths:
            if Path(path).exists():
                pdf_path = path
                break
    
    if not pdf_path or not Path(pdf_path).exists():
        print_warning("No test PDF found. Skipping parsing test.")
        print("Place a PDF at one of these locations:")
        for path in test_paths:
            print(f"  - {path}")
        return None
    
    print(f"Testing with: {pdf_path}\n")
    
    try:
        from nanobot.agent.tools.pdf_parser import OpenDataLoaderPDF
        
        # Initialize parser
        parser = OpenDataLoaderPDF(hybrid_mode=False)
        print_success("OpenDataLoaderPDF initialized")
        
        # Parse the PDF
        logger.info("Parsing PDF... (this may take a moment)")
        import time
        start_time = time.time()
        
        result = parser.parse(pdf_path)
        
        elapsed = time.time() - start_time
        print_success(f"PDF parsed successfully in {elapsed:.2f} seconds")
        
        # Show results
        print(f"\n📊 Parsing Results:")
        print(f"  Total pages: {result.total_pages}")
        print(f"  Markdown length: {len(result.markdown):,} characters")
        print(f"  Tables found: {len(result.tables)}")
        print(f"  Images found: {len(result.images)}")
        print(f"  Elements extracted: {len(result.elements)}")
        
        # Show first table if available
        if result.tables:
            print(f"\n📋 First Table Preview:")
            first_table = result.tables[0]
            print(f"  Page: {first_table.get('page', 'N/A')}")
            if 'headers' in first_table:
                print(f"  Headers: {first_table['headers'][:5]}...")  # First 5 headers
            if 'rows' in first_table and first_table['rows']:
                print(f"  First row: {first_table['rows'][0][:3]}...")  # First 3 cells
        
        # Show sample of markdown
        print(f"\n📝 Markdown Sample (first 300 chars):")
        print(f"  {result.markdown[:300]}...")
        
        # Quality check
        print(f"\n✅ Quality Check:")
        if result.total_pages > 0:
            print_success("✓ Pages extracted")
        else:
            print_error("✗ No pages extracted")
        
        if len(result.markdown) > 1000:
            print_success("✓ Substantial text content")
        else:
            print_warning("⚠ Very little text extracted")
        
        if result.tables:
            print_success("✓ Tables detected (critical for financial data)")
        else:
            print_warning("⚠ No tables detected (may need hybrid mode for complex PDFs)")
        
        if result.elements:
            print_success("✓ Structured elements with bounding boxes")
        else:
            print_warning("⚠ No structured elements (may need to check output format)")
        
        print_success("\n🎉 OpenDataLoader-PDF parsing test PASSED")
        return True
        
    except ImportError as e:
        print_error(f"Import failed: {e}")
        print_warning("Check if pdf_parser.py is in the correct location")
        return False
    except Exception as e:
        print_error(f"Parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# MAIN: Run All Tests
# ============================================================================

def main():
    """Run all Phase 1 tests"""
    print_header("🧪 PHASE 1 SETUP VERIFICATION")
    print("Testing: Docker, PostgreSQL, MongoDB, OpenDataLoader-PDF\n")
    
    results = {
        "Docker Containers": test_docker_containers(),
        "PostgreSQL": test_postgresql_connection(),
        "MongoDB": test_mongodb_connection(),
        "OpenDataLoader Install": test_opendataloader_installation(),
        "PDF Parsing": test_opendataloader_parsing(),
    }
    
    # Summary
    print_header("📊 TEST SUMMARY")
    
    passed = sum(1 for v in results.values() if v in [True, None])  # None = skipped but OK
    failed = sum(1 for v in results.values() if v is False)
    total = len(results)
    
    for test_name, result in results.items():
        if result is True:
            print_success(f"{test_name}: PASSED")
        elif result is False:
            print_error(f"{test_name}: FAILED")
        else:
            print_warning(f"{test_name}: SKIPPED (OK)")
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if failed == 0:
        print_success("\n🎉 ALL TESTS PASSED! Ready for Phase 2!")
        print("\nNext steps:")
        print("1. Migrate storage layer (postgres_storage.py, mongo_storage.py)")
        print("2. Implement financial tools (financial.py)")
        print("3. Migrate entity resolver")
        print("4. Test end-to-end queries")
        return 0
    else:
        print_error(f"\n⚠ {failed} test(s) failed. Please fix the issues above before proceeding to Phase 2.")
        print("\nCommon fixes:")
        print("- Docker not running: Start Docker Desktop")
        print("- Containers not running: docker-compose -f docker-compose-financial.yml up -d")
        print("- Missing Python packages: pip install psycopg2-binary pymongo opendataloader-pdf")
        return 1

if __name__ == "__main__":
    sys.exit(main())
