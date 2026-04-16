"""
LlamaParse Wrapper for Nanobot (v3.2)

High-accuracy PDF parsing with bounding boxes for citations.

🎯 v3.2: 使用 LlamaParse Cloud API
- 替代 OpenDataLoader Hybrid
- 支持 130+ 格式
- 自动保存完整 raw output
- 图片下载到本地

Supports:
- Markdown extraction
- JSON with coordinates
- Table structure preservation
- Image extraction with presigned URLs
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from loguru import logger

# 🌟 使用 LlamaParse 封装
from nanobot.core.pdf_core import PDFParser, PDFParseResult


# ===========================================
# Dataclasses
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
    bbox: Optional[BoundingBox] = None
    level: Optional[int] = None
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
# LlamaParsePDF
# ===========================================

class LlamaParsePDF:
    """
    LlamaParse wrapper for high-accuracy PDF parsing.
    
    Example:
        parser = LlamaParsePDF()
        result = parser.parse("annual_report.pdf")
    """
    
    def __init__(self, tier: str = "agentic", download_images: bool = True):
        self.tier = tier
        self.download_images = download_images
        self.parser = PDFParser(tier=tier, download_images=download_images)
        logger.info(f"LlamaParsePDF initialized (tier={tier})")
    
    def parse(self, pdf_path: str, output_dir: str = None, save_raw: bool = True) -> ParsedPDF:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        logger.info(f"Parsing PDF: {pdf_path}")
        result: PDFParseResult = self.parser.parse(str(pdf_path))
        parsed_pdf = self._convert_to_parsed_pdf(result, str(pdf_path))
        
        logger.info(f"✅ Parsed: {parsed_pdf.total_pages} pages, {len(parsed_pdf.tables)} tables")
        return parsed_pdf
    
    def parse_url(self, url: str) -> ParsedPDF:
        result: PDFParseResult = self.parser.parse_url(url)
        return self._convert_to_parsed_pdf(result, url)
    
    async def parse_async(self, pdf_path: str) -> ParsedPDF:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        result: PDFParseResult = await self.parser.parse_async(str(pdf_path))
        return self._convert_to_parsed_pdf(result, str(pdf_path))
    
    def extract_tables(self, pdf_path: str) -> List[Dict[str, Any]]:
        parsed = self.parse(pdf_path)
        return parsed.tables
    
    def extract_images(self, pdf_path: str) -> List[Dict[str, Any]]:
        parsed = self.parse(pdf_path)
        return parsed.images
    
    def load_from_raw_output(self, pdf_filename: str, job_id: str = None) -> ParsedPDF:
        result: PDFParseResult = self.parser.load_from_raw_output(pdf_filename, job_id)
        return self._convert_to_parsed_pdf(result, pdf_filename)
    
    def _convert_to_parsed_pdf(self, result: PDFParseResult, file_path: str) -> ParsedPDF:
        elements = []
        for artifact in result.artifacts:
            elem = ExtractedElement(
                element_type=artifact.get('type', 'text'),
                content=artifact.get('content', ''),
                bbox=None,
                metadata={'page': artifact.get('page', 0)}
            )
            elements.append(elem)
        
        for table in result.tables:
            elem = ExtractedElement(
                element_type='table',
                content=str(table.get('content', '')),
                bbox=None,
                metadata={'page': table.get('page', 0)}
            )
            elements.append(elem)
        
        for img in result.images:
            elem = ExtractedElement(
                element_type='image',
                content=img.get('filename', ''),
                bbox=None,
                metadata={
                    'page': img.get('page', 0),
                    'local_path': img.get('local_path', ''),
                    'url': img.get('url', ''),
                    'category': img.get('category', '')
                }
            )
            elements.append(elem)
        
        return ParsedPDF(
            file_path=file_path,
            total_pages=result.total_pages,
            markdown=result.markdown,
            elements=elements,
            tables=result.tables,
            images=result.images,
            metadata={
                'parser': 'llamaparse',
                'tier': result.tier,
                'job_id': result.job_id,
                'raw_output_dir': result.raw_output_dir
            }
        )


# ===========================================
# 便捷函数
# ===========================================

def parse_pdf(pdf_path: str, **kwargs) -> ParsedPDF:
    parser = LlamaParsePDF(**kwargs)
    return parser.parse(pdf_path)

async def parse_pdf_async(pdf_path: str, **kwargs) -> ParsedPDF:
    parser = LlamaParsePDF(**kwargs)
    return await parser.parse_async(pdf_path)

def extract_tables_from_pdf(pdf_path: str, **kwargs) -> List[Dict]:
    parser = LlamaParsePDF(**kwargs)
    return parser.extract_tables(pdf_path)

def extract_images_from_pdf(pdf_path: str, **kwargs) -> List[Dict]:
    parser = LlamaParsePDF(**kwargs)
    return parser.extract_images(pdf_path)

def load_from_raw_output(pdf_filename: str, job_id: str = None) -> ParsedPDF:
    parser = LlamaParsePDF()
    return parser.load_from_raw_output(pdf_filename, job_id)