"""
OpenDataLoader-PDF Wrapper for Nanobot

High-accuracy PDF parsing with bounding boxes for citations.
Supports:
- Markdown extraction
- JSON with coordinates
- Table structure preservation
- OCR for scanned documents (hybrid mode)

Installation:
    pip install -U opendataloader-pdf
    # For hybrid mode (scanned PDFs, complex tables):
    pip install "opendataloader-pdf[hybrid]"
"""

from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
import json
from loguru import logger


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


class OpenDataLoaderPDF:
    """
    OpenDataLoader-PDF wrapper for high-accuracy PDF parsing.
    
    Example:
        parser = OpenDataLoaderPDF()
        result = parser.parse("annual_report.pdf")
        print(result.markdown)
        for table in result.tables:
            print(f"Table on page {table['page']}: {table['data']}")
    """
    
    def __init__(self, hybrid_mode: bool = False, hybrid_url: str = "http://localhost:5002"):
        """
        Initialize OpenDataLoader-PDF.
        
        Args:
            hybrid_mode: Use AI hybrid mode for complex PDFs (requires server)
            hybrid_url: URL of hybrid mode server
        """
        self.hybrid_mode = hybrid_mode
        self.hybrid_url = hybrid_url
        self._check_installation()
        logger.info(f"OpenDataLoaderPDF initialized (hybrid_mode={hybrid_mode})")
    
    def _check_installation(self):
        """Check if opendataloader_pdf is installed"""
        try:
            import opendataloader_pdf
            self.module = opendataloader_pdf
        except ImportError:
            logger.error("opendataloader_pdf not installed. Run: pip install opendataloader-pdf")
            raise
    
    def parse(self, pdf_path: str, output_dir: Optional[str] = None, save_raw: bool = True) -> ParsedPDF:
        """
        Parse a PDF file.
        
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
        
        # Use configured output directory or default
        if output_dir is None:
            output_dir = Path("data/parsed_outputs") / pdf_path.stem
            output_dir.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Build convert() parameters
            convert_kwargs = {
                'input_path': str(pdf_path),
                'output_dir': str(output_dir),
                'format': ['markdown', 'json'],  # Get both formats
                'quiet': False,  # Show progress
            }
            
            # Add hybrid mode if enabled
            if self.hybrid_mode:
                convert_kwargs['hybrid'] = 'full'
                if self.hybrid_url:
                    convert_kwargs['hybrid_url'] = self.hybrid_url
            
            # Use OpenDataLoader-PDF to parse (writes files to output_dir)
            logger.info(f"Saving raw output to: {output_dir}")
            self.module.convert(**convert_kwargs)
            
            # Read the generated files
            parsed = self._read_output_files(output_dir, str(pdf_path))
            logger.info(f"Successfully parsed {pdf_path}: {parsed.total_pages} pages, {len(parsed.tables)} tables")
            
            if save_raw:
                logger.info(f"Raw output saved to: {output_dir}")
            
            return parsed
            
        except Exception as e:
            logger.error(f"Failed to parse PDF {pdf_path}: {e}")
            raise
    
    def _read_output_files(self, output_dir: Path, pdf_path: str) -> ParsedPDF:
        """Read parsed output files from output directory"""
        import json
        
        # Find generated files
        md_files = list(output_dir.glob("*.md"))
        json_files = list(output_dir.glob("*.json"))
        
        # Read markdown
        markdown = ""
        if md_files:
            # Concatenate all markdown files
            for md_file in sorted(md_files):
                markdown += md_file.read_text(encoding='utf-8') + "\n\n"
        
        # Read JSON for structured data
        tables = []
        images = []
        elements = []
        metadata = {}
        total_pages = 0
        
        if json_files:
            for json_file in sorted(json_files):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Extract tables
                    if 'tables' in data:
                        tables.extend(data['tables'])
                    
                    # Extract images
                    if 'images' in data:
                        images.extend(data['images'])
                    
                    # Extract elements
                    if 'elements' in data:
                        elements.extend(data['elements'])
                    
                    # Get page count
                    if 'total_pages' in data:
                        total_pages = max(total_pages, data['total_pages'])
                    
                    # Metadata
                    if 'metadata' in data:
                        metadata.update(data['metadata'])
                        
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to read {json_file}: {e}")
        
        return ParsedPDF(
            file_path=pdf_path,
            total_pages=total_pages,
            markdown=markdown.strip(),
            elements=self._parse_elements(elements),
            tables=tables,
            images=images,
            metadata=metadata
        )
    
    def _parse_elements(self, elements: List[Dict]) -> List[ExtractedElement]:
        """Convert raw element dicts to ExtractedElement objects"""
        parsed = []
        
        for item in elements:
            try:
                bbox_data = item.get('bbox', {})
                bbox = BoundingBox(
                    x=bbox_data.get('x', 0),
                    y=bbox_data.get('y', 0),
                    width=bbox_data.get('width', 0),
                    height=bbox_data.get('height', 0),
                    page=bbox_data.get('page', 1)
                )
                
                element = ExtractedElement(
                    element_type=item.get('type', 'paragraph'),
                    content=item.get('content', ''),
                    bbox=bbox,
                    level=item.get('level'),
                    metadata=item.get('metadata')
                )
                parsed.append(element)
            except (KeyError, TypeError) as e:
                logger.debug(f"Failed to parse element: {e}")
        
        return parsed
    
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
    
    def extract_with_citations(self, pdf_path: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Extract text with citation information.
        
        Returns:
            Tuple of (markdown_text, citations_list)
            Each citation: {'text': str, 'page': int, 'bbox': dict}
        """
        parsed = self.parse(pdf_path)
        
        citations = []
        for element in parsed.elements:
            citations.append({
                'text': element.content[:100],  # First 100 chars
                'page': element.bbox.page,
                'bbox': asdict(element.bbox),
                'type': element.element_type
            })
        
        return parsed.markdown, citations


class TableExtractor:
    """
    Specialized table extractor with structure preservation.
    
    Uses OpenDataLoader-PDF's table detection + post-processing
    for complex financial tables.
    """
    
    def __init__(self, parser: Optional[OpenDataLoaderPDF] = None):
        """
        Args:
            parser: OpenDataLoaderPDF instance (creates one if not provided)
        """
        self.parser = parser or OpenDataLoaderPDF()
    
    def extract_financial_tables(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract tables specifically optimized for financial data.
        
        Returns:
            List of tables with:
            - headers: List of column headers
            - rows: List of row data
            - page: Page number
            - bbox: Bounding box
            - confidence: Extraction confidence
        """
        tables = self.parser.extract_tables(pdf_path)
        
        # Post-process for financial tables
        processed = []
        for table in tables:
            # Detect if this looks like a financial table
            if self._is_financial_table(table):
                processed.append(self._process_financial_table(table))
        
        return processed
    
    def _is_financial_table(self, table: Dict) -> bool:
        """Check if table looks like financial data"""
        # Check for common financial keywords
        financial_keywords = [
            'revenue', 'income', 'profit', 'asset', 'liability',
            'equity', 'cash', 'flow', 'earnings', 'expense'
        ]
        
        headers = table.get('headers', [])
        headers_text = ' '.join(headers).lower()
        
        return any(kw in headers_text for kw in financial_keywords)
    
    def _process_financial_table(self, table: Dict) -> Dict:
        """Process financial table for better structure"""
        # Implement table structure analysis
        # - Detect multi-level headers
        # - Identify metric names vs values
        # - Handle merged cells
        
        processed = {
            'headers': table.get('headers', []),
            'rows': table.get('rows', []),
            'page': table.get('page', 1),
            'bbox': table.get('bbox', {}),
            'confidence': table.get('confidence', 1.0),
            'structure': 'flat'  # or 'hierarchical' if multi-level
        }
        
        return processed


# Convenience functions
def parse_pdf(pdf_path: str, **kwargs) -> ParsedPDF:
    """Quick PDF parsing"""
    parser = OpenDataLoaderPDF(**kwargs)
    return parser.parse(pdf_path)


def extract_tables_from_pdf(pdf_path: str, **kwargs) -> List[Dict]:
    """Quick table extraction"""
    extractor = TableExtractor(OpenDataLoaderPDF(**kwargs))
    return extractor.extract_financial_tables(pdf_path)


if __name__ == "__main__":
    # Example usage
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
