"""LiteParse Data Cleaner for Financial Reports.

This module processes raw LiteParse output to:
1. Filter out noise (headers, footers, decorative elements)
2. Extract and format financial tables as Markdown
3. Prioritize balance sheets, income statements, cash flow statements
4. Reduce context window usage while preserving critical data

Usage:
    from liteparse_data_cleaner import FinancialDataCleaner
    
    cleaner = FinancialDataCleaner()
    cleaned = cleaner.clean(raw_liteparse_output)
    markdown = cleaner.to_markdown(cleaned['tables'])
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CleanedTable:
    """Represents a cleaned financial table."""
    table_id: str
    page_number: int
    table_type: str  # 'balance_sheet', 'income_statement', 'cash_flow', 'other'
    markdown: str
    row_count: int
    col_count: int
    confidence: float  # How confident we are this is a real financial table
    bbox: dict | None = None
    notes: list[str] = field(default_factory=list)


class FinancialDataCleaner:
    """Clean and format LiteParse output for financial analysis."""

    # Keywords to identify table types
    TABLE_TYPE_KEYWORDS = {
        'balance_sheet': [
            '資產負債表', 'balance sheet', 'statement of financial position',
            'total assets', 'total liabilities', 'equity',
            '資產', '負債', '股東權益'
        ],
        'income_statement': [
            '利潤表', 'income statement', 'profit and loss', 'profit & loss',
            'revenue', 'gross profit', 'net profit', 'operating profit',
            '收入', '利潤', '毛利', '淨利', '溢利'
        ],
        'cash_flow': [
            '現金流量表', 'cash flow statement',
            'operating activities', 'investing activities', 'financing activities',
            '經營活動', '投資活動', '融資活動', '現金流'
        ],
        'notes_to_financials': [
            '財務報表附註', 'notes to financial statements',
            'accounting policies', 'significant accounting'
        ]
    }

    # Noise patterns to filter out
    NOISE_PATTERNS = [
        r'^\d+\s*of\s*\d+$',  # Page numbers "1 of 50"
        r'^www\.\S+$',  # URLs
        r'^\S+@\S+\.\S+$',  # Email addresses
        r'^(報告日期 |Date| 報告編號):',  # Report metadata headers
        r'^©\s*\d{4}',  # Copyright notices
        r'^All rights reserved',  # Rights statements
        r'^Confidential',  # Confidentiality markers
    ]

    def __init__(self, min_table_rows: int = 3, min_confidence: float = 0.5):
        """Initialize cleaner.
        
        Args:
            min_table_rows: Minimum rows for a table to be included
            min_confidence: Minimum confidence score to include table
        """
        self.min_table_rows = min_table_rows
        self.min_confidence = min_confidence

    def clean(self, liteparse_output: dict) -> dict[str, Any]:
        """Clean raw LiteParse output.
        
        Args:
            liteparse_output: Raw JSON from LiteParse
            
        Returns:
            Dictionary with cleaned tables, metadata, and statistics
        """
        elements = liteparse_output.get('elements', [])
        
        # Extract tables
        raw_tables = [
            e for e in elements 
            if e.get('type') == 'table' or e.get('type') == 'financial_table'
        ]
        
        # Process each table
        cleaned_tables = []
        for table_elem in raw_tables:
            cleaned = self._process_table(table_elem)
            if cleaned and cleaned.confidence >= self.min_confidence:
                cleaned_tables.append(cleaned)
        
        # Sort by confidence and page number
        cleaned_tables.sort(key=lambda t: (-t.confidence, t.page_number))
        
        # Extract text elements with financial context
        financial_text = self._extract_financial_text(elements)
        
        return {
            'tables': cleaned_tables,
            'financial_text': financial_text,
            'statistics': {
                'total_elements': len(elements),
                'raw_tables_found': len(raw_tables),
                'tables_after_cleaning': len(cleaned_tables),
                'table_types': self._count_table_types(cleaned_tables),
            }
        }

    def _process_table(self, table_elem: dict) -> CleanedTable | None:
        """Process a single table element."""
        # Extract table data
        table_data = table_elem.get('table', {})
        rows = table_data.get('rows', [])
        
        if len(rows) < self.min_table_rows:
            return None
        
        # Determine table type
        table_type, confidence = self._classify_table(rows)
        
        # Convert to Markdown
        markdown = self._rows_to_markdown(rows)
        
        # Get bounding box
        bbox = table_elem.get('bbox') or table_elem.get('bounding_box')
        
        # Generate table ID
        table_id = f"table_{table_type}_{table_elem.get('page', 0)}"
        
        # Create cleaned table
        cleaned = CleanedTable(
            table_id=table_id,
            page_number=table_elem.get('page', 0),
            table_type=table_type,
            markdown=markdown,
            row_count=len(rows),
            col_count=max(len(row.get('cells', [])) for row in rows) if rows else 0,
            confidence=confidence,
            bbox=bbox,
        )
        
        # Add notes for low-confidence tables
        if confidence < 0.7:
            cleaned.notes.append(f"Low confidence ({confidence:.2f}) - may contain noise")
        
        return cleaned

    def _classify_table(self, rows: list[dict]) -> tuple[str, float]:
        """Classify table type based on content.
        
        Returns:
            Tuple of (table_type, confidence_score)
        """
        # Extract all text from rows
        all_text = ' '.join(
            cell.get('text', '') 
            for row in rows 
            for cell in row.get('cells', [])
        ).lower()
        
        scores = {}
        for table_type, keywords in self.TABLE_TYPE_KEYWORDS.items():
            match_count = sum(1 for kw in keywords if kw.lower() in all_text)
            scores[table_type] = match_count
        
        # Find best match
        if not scores or max(scores.values()) == 0:
            return 'other', 0.3
        
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        
        # Calculate confidence based on keyword matches
        if best_score >= 3:
            confidence = 0.9
        elif best_score == 2:
            confidence = 0.7
        elif best_score == 1:
            confidence = 0.5
        else:
            confidence = 0.3
        
        return best_type, confidence

    def _rows_to_markdown(self, rows: list[dict]) -> str:
        """Convert table rows to Markdown format.
        
        Handles:
        - Header row detection
        - Column alignment
        - Empty cells
        - Number formatting
        """
        if not rows:
            return ""
        
        # Extract all cells
        grid = []
        for row in rows:
            cells = row.get('cells', [])
            grid.append([cell.get('text', '') for cell in cells])
        
        if not grid:
            return ""
        
        # Normalize row lengths
        max_cols = max(len(row) for row in grid)
        for row in grid:
            while len(row) < max_cols:
                row.append('')
        
        # Build Markdown
        lines = []
        
        # Header row
        header = grid[0]
        lines.append('| ' + ' | '.join(self._escape_md(h) for h in header) + ' |')
        
        # Separator
        lines.append('| ' + ' | '.join(['---'] * max_cols) + ' |')
        
        # Data rows
        for row in grid[1:]:
            lines.append('| ' + ' | '.join(self._escape_md(cell) for cell in row) + ' |')
        
        return '\n'.join(lines)

    def _escape_md(self, text: str) -> str:
        """Escape Markdown special characters."""
        if not text:
            return ''
        # Escape pipe characters
        text = text.replace('|', '\\|')
        # Escape newlines
        text = text.replace('\n', ' ')
        # Truncate very long cells
        if len(text) > 200:
            text = text[:197] + '...'
        return text

    def _extract_financial_text(self, elements: list[dict]) -> list[dict]:
        """Extract non-table financial text elements.
        
        Focuses on:
        - Section headers
        - Financial metrics mentioned in text
        - Key figures and percentages
        """
        financial_text = []
        
        for elem in elements:
            if elem.get('type') not in ['text', 'header', 'paragraph']:
                continue
            
            text = elem.get('text', '')
            
            # Skip noise
            if self._is_noise(text):
                continue
            
            # Look for financial patterns
            if self._contains_financial_data(text):
                financial_text.append({
                    'text': text,
                    'type': elem.get('type', 'text'),
                    'page': elem.get('page', 0),
                    'bbox': elem.get('bbox') or elem.get('bounding_box'),
                })
        
        return financial_text

    def _is_noise(self, text: str) -> bool:
        """Check if text is noise (headers, footers, etc.)."""
        if not text or len(text.strip()) < 5:
            return True
        
        text_lower = text.lower().strip()
        
        for pattern in self.NOISE_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        
        return False

    def _contains_financial_data(self, text: str) -> bool:
        """Check if text contains financial data."""
        financial_patterns = [
            r'\d+\.?\d*\s*%/',  # Percentages
            r'\$\s*\d+',  # Dollar amounts
            r'HK\$\s*\d+',  # HKD amounts
            r'RMB\s*\d+',  # RMB amounts
            r'\d+\s*million',  # Millions
            r'\d+\s*billion',  # Billions
            r'同比增長', r'year-over-year', r'YoY',  # Growth
            r'毛利率', r'gross margin',  # Margins
            r'淨利率', r'net margin',
        ]
        
        return any(re.search(p, text, re.IGNORECASE) for p in financial_patterns)

    def _count_table_types(self, tables: list[CleanedTable]) -> dict[str, int]:
        """Count tables by type."""
        counts = {}
        for table in tables:
            counts[table.table_type] = counts.get(table.table_type, 0) + 1
        return counts

    def to_context_string(self, cleaned_data: dict, max_tables: int = 10) -> str:
        """Convert cleaned data to context string for LLM.
        
        Args:
            cleaned_data: Output from clean()
            max_tables: Maximum number of tables to include
            
        Returns:
            Formatted string ready for LLM context
        """
        tables = cleaned_data.get('tables', [])[:max_tables]
        financial_text = cleaned_data.get('financial_text', [])[:50]  # Limit text snippets
        
        lines = [
            "# 財務報表數據 (Financial Report Data)",
            "",
            f"共找到 {len(tables)} 個財務表格",
            ""
        ]
        
        # Add tables by type priority
        priority_order = ['balance_sheet', 'income_statement', 'cash_flow', 'notes_to_financials', 'other']
        
        table_counter = 1
        for table_type in priority_order:
            type_tables = [t for t in tables if t.table_type == table_type]
            
            for table in type_tables:
                type_name_cn = {
                    'balance_sheet': '資產負債表',
                    'income_statement': '利潤表',
                    'cash_flow': '現金流量表',
                    'notes_to_financials': '財務報表附註',
                    'other': '其他表格'
                }.get(table.table_type, '表格')
                
                lines.append(f"## 表格 {table_counter}: {type_name_cn} (第 {table.page_number} 頁)")
                lines.append(f"置信度：{table.confidence:.2f}")
                lines.append("")
                lines.append(table.markdown)
                lines.append("")
                
                if table.notes:
                    lines.append("備註：", ', '.join(table.notes))
                    lines.append("")
                
                table_counter += 1
        
        # Add financial text snippets
        if financial_text:
            lines.append("# 重要財務數據片段 (Key Financial Data)")
            lines.append("")
            
            for i, snippet in enumerate(financial_text[:20], 1):
                lines.append(f"{i}. [第 {snippet.get('page', 0)} 頁] {snippet['text']}")
        
        return '\n'.join(lines)


def clean_for_llm(liteparse_output: dict, max_tables: int = 10) -> str:
    """Convenience function to clean LiteParse output for LLM consumption.
    
    Args:
        liteparse_output: Raw JSON from LiteParse
        max_tables: Maximum tables to include
        
    Returns:
        Formatted context string
    """
    cleaner = FinancialDataCleaner()
    cleaned = cleaner.clean(liteparse_output)
    return cleaner.to_context_string(cleaned, max_tables=max_tables)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean LiteParse output for LLM consumption")
    parser.add_argument(
        "--input-json",
        type=str,
        help="JSON string of LiteParse output (for MCP mode)",
    )
    parser.add_argument(
        "--input-file",
        type=str,
        help="Path to JSON file with LiteParse output",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["markdown", "context", "stats"],
        default="context",
        help="Output mode",
    )
    parser.add_argument(
        "--max-tables",
        type=int,
        default=10,
        help="Maximum tables to include",
    )
    
    args = parser.parse_args()
    
    # Load input
    if args.input_json:
        liteparse_output = json.loads(args.input_json)
    elif args.input_file:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            liteparse_output = json.load(f)
    else:
        # Use sample
        liteparse_output = {
            'elements': [
                {
                    'type': 'table',
                    'page': 10,
                    'table': {
                        'rows': [
                            {'cells': [{'text': '項目'}, {'text': '2023'}, {'text': '2022'}]},
                            {'cells': [{'text': '收入'}, {'text': '1,000,000'}, {'text': '900,000'}]},
                            {'cells': [{'text': '毛利'}, {'text': '500,000'}, {'text': '450,000'}]},
                            {'cells': [{'text': '淨利'}, {'text': '200,000'}, {'text': '180,000'}]},
                        ]
                    },
                    'bbox': {'x': 100, 'y': 200, 'width': 400, 'height': 300}
                }
            ]
        }
    
    # Process
    cleaner = FinancialDataCleaner()
    cleaned = cleaner.clean(liteparse_output)
    
    if args.mode == "stats":
        print(json.dumps(cleaned['statistics'], indent=2, ensure_ascii=False))
    else:
        context_str = cleaner.to_context_string(cleaned, max_tables=args.max_tables)
        print(context_str)
