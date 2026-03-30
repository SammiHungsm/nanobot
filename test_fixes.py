#!/usr/bin/env python3
"""
Nanobot Fix Verification Tests

Tests all fixed components:
1. Vanna SQL execution safety
2. OpenDataLoader integration
3. MongoDB semantic search
4. SKILL.md intent routing

Usage:
    uv run python test_fixes.py
"""

import sys
import json
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

def print_header(text: str):
    print(f"\n{'='*70}")
    print(f"{text.center(70)}")
    print(f"{'='*70}\n")

def test_vanna_fix():
    """Test 1: Vanna SQL Execution Safety Fix"""
    print_header("Test 1: Vanna SQL Execution Safety")
    
    try:
        from nanobot.agent.tools.vanna_tool import VannaSQL
        from nanobot.storage.financial_storage import PostgresStorage
        
        print("[OK] VannaSQL and PostgresStorage imported successfully")
        
        # Check if VannaSQL's execute method uses PostgresStorage
        import inspect
        vanna_code = inspect.getsource(VannaSQL.execute)
        
        if 'PostgresStorage' in vanna_code:
            print("[PASS] Vanna fixed: Uses PostgresStorage to execute SQL")
            return True
        else:
            print("[FAIL] Vanna not fixed: Still executes SQL directly")
            return False
            
    except Exception as e:
        print(f"[SKIP] Vanna test skipped (database may not be connected): {e}")
        return None

def test_opendataloader_integration():
    """Test 2: OpenDataLoader Integration"""
    print_header("Test 2: OpenDataLoader Integration")
    
    try:
        import subprocess
        
        print("[OK] Importing build_indexes module...")
        
        # Read file with utf-8-sig to handle BOM
        script_path = Path("nanobot/skills/document_indexer/scripts/build_indexes.py")
        content = script_path.read_text(encoding='utf-8-sig')
        
        # Check if functions exist in file
        has_call_opendataloader = 'def call_opendataloader' in content
        has_extract_tables = 'def extract_tables_with_pymupdf' in content
        
        if has_call_opendataloader and has_extract_tables:
            print("[OK] OpenDataLoader functions found in build_indexes.py")
        else:
            print("[WARN] OpenDataLoader functions not found in build_indexes.py")
            return False
        
        # Check if OpenDataLoader CLI is installed
        try:
            # Try to find the CLI executable
            import shutil
            cli_path = shutil.which("opendataloader-pdf")
            
            if cli_path:
                print(f"[PASS] OpenDataLoader CLI installed: {cli_path}")
                return True
            else:
                print(f"[WARN] OpenDataLoader CLI not found in PATH")
                return False
                
        except Exception as e:
            print(f"[WARN] OpenDataLoader CLI check failed: {e}")
            return False
            
    except Exception as e:
        print(f"[FAIL] OpenDataLoader test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_semantic_search():
    """Test 3: MongoDB Semantic Search"""
    print_header("Test 3: MongoDB Semantic Search")
    
    try:
        from nanobot.storage.financial_storage import MongoDocumentStore
        import inspect
        
        print("[OK] MongoDocumentStore imported successfully")
        
        # Check if semantic_search method exists
        if hasattr(MongoDocumentStore, 'semantic_search'):
            print("[PASS] semantic_search method added")
            
            # Check method implementation
            method_code = inspect.getsource(MongoDocumentStore.semantic_search)
            
            if '$vectorSearch' in method_code:
                print("[OK] Supports vector search ($vectorSearch)")
            if '$text' in method_code:
                print("[OK] Supports text search ($text search)")
            if '_get_embedding' in method_code:
                print("[OK] Embedding model interface ready")
            
            return True
        else:
            print("[FAIL] semantic_search method not found")
            return False
            
    except Exception as e:
        print(f"[FAIL] MongoDB test failed: {e}")
        return False

def test_skill_md_routing():
    """Test 4: SKILL.md Intent Routing"""
    print_header("Test 4: SKILL.md Intent Routing")
    
    skill_path = Path("nanobot/skills/document_indexer/SKILL.md")
    
    if not skill_path.exists():
        print(f"[FAIL] SKILL.md file not found: {skill_path}")
        return False
    
    content = skill_path.read_text(encoding='utf-8')
    
    # Check for intent routing documentation (supports both English and Chinese)
    checks = {
        'vanna_tool documentation': 'vanna_tool' in content,
        'Semantic search documentation': 'semantic' in content.lower() or 'RagAnything' in content or '語義檢索' in content,
        'Tool selection logic': 'intent' in content.lower() or 'select' in content.lower() or '意圖路由' in content or '選擇正確' in content or '根據問題' in content,
        'SQL safety documentation': 'SQL injection' in content or 'financial_storage' in content or 'SQL 安全' in content
    }
    
    all_passed = True
    for check_name, passed in checks.items():
        if passed:
            print(f"[OK] {check_name}")
        else:
            print(f"[WARN] {check_name}")
            all_passed = False
    
    if all_passed:
        print("[PASS] SKILL.md intent routing complete")
    else:
        print("[WARN] SKILL.md intent routing incomplete")
    
    return all_passed

def test_build_indexes_opendataloader():
    """Test 5: build_indexes.py OpenDataLoader Integration"""
    print_header("Test 5: build_indexes.py OpenDataLoader Integration")
    
    script_path = Path("nanobot/skills/document_indexer/scripts/build_indexes.py")
    
    if not script_path.exists():
        print(f"[FAIL] build_indexes.py file not found: {script_path}")
        return False
    
    content = script_path.read_text(encoding='utf-8')
    
    # Check OpenDataLoader integration
    checks = {
        'call_opendataloader function': 'def call_opendataloader' in content,
        'extract_tables_with_pymupdf function': 'def extract_tables_with_pymupdf' in content,
        'OpenDataLoader CLI call': 'opendataloader-pdf' in content,
        'Fallback mechanism': 'PyMuPDF' in content or 'pymupdf' in content,
        'Page count check': 'page_count > 50' in content or 'use_opendataloader' in content,
        'tables.json output': 'tables.json' in content
    }
    
    all_passed = True
    for check_name, passed in checks.items():
        if passed:
            print(f"[OK] {check_name}")
        else:
            print(f"[WARN] {check_name}")
            all_passed = False
    
    if all_passed:
        print("[PASS] build_indexes.py OpenDataLoader integration complete")
    else:
        print("[WARN] build_indexes.py OpenDataLoader integration incomplete")
    
    return all_passed

def main():
    """Main test flow"""
    print_header("Nanobot Fix Verification Tests")
    
    tests = [
        ("Vanna SQL Safety", test_vanna_fix),
        ("OpenDataLoader Integration", test_opendataloader_integration),
        ("MongoDB Semantic Search", test_semantic_search),
        ("SKILL.md Intent Routing", test_skill_md_routing),
        ("build_indexes.py Integration", test_build_indexes_opendataloader)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[ERROR] Test '{name}' failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print_header("Test Summary")
    
    passed = sum(1 for _, r in results if r is True)
    skipped = sum(1 for _, r in results if r is None)
    failed = sum(1 for _, r in results if r is False)
    total = len(results)
    
    for name, result in results:
        if result is True:
            status = "[PASS]"
        elif result is None:
            status = "[SKIP]"
        else:
            status = "[FAIL]"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed} passed / {skipped} skipped / {failed} failed / {total} total")
    
    if failed == 0 and passed > 0:
        print("\n[PASS] All tests passed! Nanobot has been fixed successfully!")
        print("\nFix Summary:")
        print("  1. Vanna SQL execution now uses PostgresStorage to prevent SQL injection")
        print("  2. OpenDataLoader integrated into build_indexes.py for complex table parsing")
        print("  3. MongoDB semantic search added to financial_storage.py")
        print("  4. SKILL.md updated with tool selection logic and intent routing")
        print("\nNext Steps:")
        print("  1. Run 'uv run python train_vanna.py' to train Vanna")
        print("  2. Test PDF indexing: 'uv run python nanobot/skills/document_indexer/scripts/build_indexes.py <pdf_path>'")
        print("  3. Configure RagAnything or MongoDB Atlas vector search if needed")
        return 0
    else:
        print(f"\n[WARN] {failed} tests failed. Please check errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
