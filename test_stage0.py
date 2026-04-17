"""Test Stage 0 Vision extraction"""
import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from nanobot.core.pdf_core import PDFParser


async def test_load_from_raw():
    """Test load_from_raw_output"""
    print(f"\n🚀 Testing load_from_raw_output...")
    
    parser = PDFParser()
    result = parser.load_from_raw_output("20260417_071207_stock_00001_2023.pdf")
    
    print(f"\n✅ Load Result:")
    print(f"   Job ID: {result.job_id}")
    print(f"   Pages: {result.total_pages}")
    print(f"   Images: {len(result.images)}")
    print(f"   Tables: {len(result.tables)}")
    print(f"   Raw output dir: {result.raw_output_dir}")
    
    # 🌟 Check images
    if result.images:
        print(f"\n📸 First 5 images:")
        for img in result.images[:5]:
            print(f"   - {img.get('filename')}: {img.get('local_path', 'N/A')}")
    
    # 🌟 Check if markdown files exist
    raw_dir = Path(result.raw_output_dir) if result.raw_output_dir else None
    if raw_dir and raw_dir.exists():
        print(f"\n📂 Raw output directory: {raw_dir}")
        
        # 🌟 Check markdown files
        md_files = list(raw_dir.glob("markdown_page*.md"))
        if md_files:
            print(f"\n📝 Markdown files ({len(md_files)}):")
            for md_file in md_files[:3]:
                content = md_file.read_text(encoding='utf-8')
                # 🌟 Check if image paths are corrected
                has_images_dir = "images/" in content
                print(f"   - {md_file.name}: images/ prefix = {has_images_dir}")
                if "page_1" in content:
                    print(f"      Preview: {content[:100]}...")


if __name__ == "__main__":
    asyncio.run(test_load_from_raw())