#!/usr/bin/env python3
"""
Test script for OpenDataLoader PDF extraction.
Usage: python test_opendataloader.py <pdf_path> [pages]
"""

import sys
import json
import tempfile
from pathlib import Path

def test_opendataloader(pdf_path: str, pages: str = "1"):
    """Test OpenDataLoader with a PDF file."""
    print(f"📄 Testing OpenDataLoader with: {pdf_path}")
    print(f"📖 Pages: {pages}")
    print("-" * 60)
    
    # Check if file exists
    if not Path(pdf_path).exists():
        print(f"❌ File not found: {pdf_path}")
        return
    
    file_size = Path(pdf_path).stat().st_size
    print(f"📊 File size: {file_size / 1024 / 1024:.2f} MB")
    print()
    
    # Import OpenDataLoader
    try:
        from opendataloader_pdf import convert
        print("✅ opendataloader_pdf imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import opendataloader_pdf: {e}")
        return
    
    # Create temp directory for output
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "output.json"
        
        print(f"\n🔧 Converting PDF...")
        print(f"   Output path: {output_path}")
        
        try:
            # Try with keyword arguments
            convert(
                pdf_path,
                output_path=str(output_path),
                output_format="json",
                pages=pages
            )
            print("✅ Conversion completed (keyword args)")
        except TypeError as e:
            print(f"⚠️ Keyword args failed: {e}")
            print("   Trying positional args...")
            try:
                convert(pdf_path, str(output_path))
                print("✅ Conversion completed (positional args)")
            except Exception as e2:
                print(f"❌ Conversion failed: {e2}")
                return
        except Exception as e:
            print(f"❌ Conversion failed: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # Check output
        print(f"\n📂 Checking output...")
        
        if output_path.exists():
            if output_path.is_dir():
                print(f"   Output is a directory")
                json_files = list(output_path.glob("*.json"))
                print(f"   Found {len(json_files)} JSON files:")
                for jf in json_files:
                    print(f"     - {jf.name}")
                
                if json_files:
                    output_path = json_files[0]
                else:
                    print("❌ No JSON files found in output directory")
                    return
            else:
                print(f"   Output is a file")
                print(f"   Size: {output_path.stat().st_size} bytes")
            
            # Read and parse JSON
            print(f"\n📖 Reading output...")
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                
                print(f"   Type: {type(result).__name__}")
                
                if isinstance(result, list):
                    print(f"   Length: {len(result)} items")
                    content_blocks = result
                elif isinstance(result, dict):
                    print(f"   Keys: {list(result.keys())}")
                    
                    # 檢查內容欄位
                    if "kids" in result:
                        content_blocks = result["kids"]
                        print(f"   ✅ Found 'kids' with {len(content_blocks)} items")
                    elif "content" in result:
                        content_blocks = result["content"]
                        print(f"   ✅ Found 'content' with {len(content_blocks)} items")
                    else:
                        content_blocks = []
                        print(f"   ⚠️ No content field found")
                    
                    # 顯示元數據
                    if "number of pages" in result:
                        print(f"   📄 Number of pages: {result['number of pages']}")
                    if "file name" in result:
                        print(f"   📁 File name: {result['file name']}")
                else:
                    content_blocks = []
                
                # 統計各類型
                if content_blocks:
                    type_counts = {}
                    for block in content_blocks:
                        if isinstance(block, dict):
                            block_type = block.get("type", "unknown")
                            type_counts[block_type] = type_counts.get(block_type, 0) + 1
                    print(f"\n📊 Content type counts: {type_counts}")
                    
                    # 顯示每種類型的示例
                    print(f"\n📝 Sample items by type:")
                    shown_types = set()
                    for block in content_blocks[:20]:  # 只看前 20 個
                        if isinstance(block, dict):
                            block_type = block.get("type", "unknown")
                            if block_type not in shown_types:
                                shown_types.add(block_type)
                                print(f"\n   === {block_type} ===")
                                print(f"   {json.dumps(block, indent=2, ensure_ascii=False)[:500]}")
                else:
                    print("\n⚠️ No content blocks found")
                    print("   This could mean:")
                    print("   - PDF is scanned images (needs OCR)")
                    print("   - PDF has no extractable text")
                    print("   - OpenDataLoader needs OCR enabled")
                        
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse JSON: {e}")
                with open(output_path, 'r') as f:
                    print(f"   Raw content (first 500 chars):")
                    print(f.read()[:500])
        else:
            print(f"❌ Output path does not exist: {output_path}")
            # List temp_dir contents
            print(f"\n📂 Temp directory contents:")
            for item in Path(temp_dir).iterdir():
                print(f"   {item.name}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_opendataloader.py <pdf_path> [pages]")
        print("Example: python test_opendataloader.py document.pdf 1")
        print("         python test_opendataloader.py document.pdf 1-5")
        print("         python test_opendataloader.py document.pdf all")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    pages = sys.argv[2] if len(sys.argv) > 2 else "1"
    
    test_opendataloader(pdf_path, pages)


if __name__ == "__main__":
    main()