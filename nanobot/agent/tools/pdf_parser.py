"""
OpenDataLoader-PDF Wrapper for Nanobot

High-accuracy PDF parsing with bounding boxes for citations.

🎯 v2.0: 使用統一的 pdf_core 封裝
- 所有底层 API 调用统一在 nanobot.core.pdf_core
- 自动处理 Docker 网络问题
- 统一 format 参数格式
- 统一 JSON 输出结构

Supports:
- Markdown extraction
- JSON with coordinates
- Table structure preservation
- OCR for scanned documents (hybrid mode)
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from loguru import logger

# 🌟 使用统一的核心模块
from nanobot.core.pdf_core import OpenDataLoaderCore


# ===========================================
# 保留原本的 Dataclass（讓 Agent 其他地方不報錯）
# ===========================================

@dataclass
class BoundingBox:
    """Bounding box coordinates for an element"""
    x: float
    y: float
    width: float
    height: float
    page: int


@dataclass
class ExtractedElement:
    """Extracted element with type and bounding box"""
    element_type: str  # 'heading', 'paragraph', 'table', 'image', 'list'
    content: str
    bbox: BoundingBox
    level: Optional[int] = None  # For headings (h1, h2, etc.)
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ParsedPDF:
    """Complete parsed PDF document"""
    file_path: str
    total_pages: int
    markdown: str
    elements: List[ExtractedElement]
    tables: List[Dict[str, Any]]
    images: List[Dict[str, Any]]
    metadata: Dict[str, Any]


# ===========================================
# OpenDataLoaderPDF - 薄薄的适配层
# ===========================================

class OpenDataLoaderPDF:
    """
    OpenDataLoader-PDF wrapper for high-accuracy PDF parsing.
    
    🌟 v2.0: 现在只是薄薄的适配层，核心逻辑全在 pdf_core
    
    Example:
        parser = OpenDataLoaderPDF()
        result = parser.parse("annual_report.pdf")
        print(result.markdown)
        for table in result.tables:
            print(f"Table on page {table['page']}: {table['data']}")
    """
    
    def __init__(self, hybrid_mode: bool = False, hybrid_url: str = None):
        """
        Initialize OpenDataLoader-PDF.
        
        Args:
            hybrid_mode: Use AI hybrid mode for complex PDFs (requires server)
            hybrid_url: URL of hybrid mode server (默认从环境变量获取)
        """
        self.hybrid_mode = hybrid_mode
        # 🌟 直接包裹新的 Core
        self.core = OpenDataLoaderCore(enable_hybrid=hybrid_mode, hybrid_url=hybrid_url)
        logger.info(f"OpenDataLoaderPDF initialized (hybrid_mode={hybrid_mode})")
    
    def parse(self, pdf_path: str, output_dir: str = None, save_raw: bool = True) -> ParsedPDF:
        """
        Parse a PDF file.
        
        🌟 v2.0: 一行代码搞定
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Directory to save output (default: data/parsed_outputs)
            save_raw: If True, save raw output files for inspection
        
        Returns:
            ParsedPDF object with extracted content
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        logger.info(f"Parsing PDF: {pdf_path}")
        
        # 🌟 設定輸出目錄
        if output_dir is None:
            output_dir = Path("data/parsed_outputs") / pdf_path.stem
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # 🌟 呼叫核心解析
        result = self.core.parse(str(pdf_path), str(output_dir))
        
        # 🌟 轉換為相容 Agent 的 ParsedPDF 格式
        parsed_pdf = self.core.to_parsed_pdf(result)
        
        if save_raw:
            logger.info(f"Raw output saved to: {output_dir}")
        
        logger.info(f"✅ Successfully parsed: {parsed_pdf.total_pages} pages, {len(parsed_pdf.tables)} tables")
        return parsed_pdf
    
    def extract_tables(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract only tables from PDF.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            List of table dictionaries with structure preserved
        """
        parsed = self.parse(pdf_path)
        return parsed.tables
    
    def extract_with_citations(self, pdf_path: str) -> tuple:
        """
        Extract text with citation information.
        
        Returns:
            Tuple of (markdown_text, citations_list)
            Each citation: {'text': str, 'page': int, 'bbox': dict}
        """
        parsed = self.parse(pdf_path)
        
        citations = [
            {
                'text': elem.content[:100],
                'page': elem.bbox.page,
                'bbox': {'x': elem.bbox.x, 'y': elem.bbox.y, 'width': elem.bbox.width, 'height': elem.bbox.height},
                'type': elem.element_type
            }
            for elem in parsed.elements
        ]
        
        return parsed.markdown, citations


# ===========================================
# 便捷函数
# ===========================================

def parse_pdf(pdf_path: str, **kwargs) -> ParsedPDF:
    """Quick PDF parsing"""
    parser = OpenDataLoaderPDF(**kwargs)
    return parser.parse(pdf_path)


def extract_tables_from_pdf(pdf_path: str, **kwargs) -> List[Dict]:
    """Quick table extraction"""
    parser = OpenDataLoaderPDF(**kwargs)
    return parser.extract_tables(pdf_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        pdf_file = sys.argv[1]
        parser = OpenDataLoaderPDF()
        result = parser.parse(pdf_file)
        
        print(f"Pages: {result.total_pages}")
        print(f"Tables: {len(result.tables)}")
        print(f"Images: {len(result.images)}")
        print(f"\nFirst 500 chars of markdown:\n{result.markdown[:500]}")
    else:
        print("Usage: python pdf_parser.py <pdf_file>")