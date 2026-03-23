"""LiteParse tool for financial report parsing with spatial awareness.

This tool wraps the LiteParse CLI to provide accurate parsing of financial documents
with preserved table structures, bounding boxes, and spatial relationships.

Usage:
    from nanobot.agent.tools.liteparse import LiteParseTool
    
    tool = LiteParseTool()
    result = await tool.execute(pdf_path="path/to/report.pdf")
"""

import asyncio
import json
import os
import shutil
import subprocess
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool


class LiteParseTool(Tool):
    """Parse PDF documents using LiteParse with spatial awareness.
    
    LiteParse excels at parsing financial reports with:
    - Dual-column layouts
    - Complex tables (balance sheets, income statements)
    - Preserved indentation and spatial structure
    - Bounding box coordinates for all elements
    
    This tool invokes the LiteParse CLI via subprocess and returns
    structured JSON with spatial metadata.
    """

    @property
    def name(self) -> str:
        return "liteparse_parse"

    @property
    def description(self) -> str:
        return (
            "Parse PDF documents using LiteParse for accurate financial report extraction. "
            "Preserves table structures, indentation, and spatial relationships. "
            "Returns JSON with bounding boxes and structured content. "
            "Ideal for balance sheets, income statements, and complex financial tables."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the PDF file to parse",
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format: 'json' (default) or 'markdown'",
                    "enum": ["json", "markdown"],
                    "default": "json",
                },
                "pages": {
                    "type": "string",
                    "description": "Optional page range to parse (e.g., '1-5', '10', '1-3,5,7-9'). "
                    "If not specified, parses all pages.",
                },
                "include_screenshots": {
                    "type": "boolean",
                    "description": "Whether to generate screenshots of parsed pages (default: false)",
                    "default": False,
                },
            },
            "required": ["pdf_path"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        """Execute LiteParse on a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            output_format: 'json' or 'markdown'
            pages: Optional page range specification
            include_screenshots: Whether to generate screenshots
            
        Returns:
            Parsed content with spatial metadata, or error message
        """
        pdf_path = kwargs.get("pdf_path")
        output_format = kwargs.get("output_format", "json")
        pages = kwargs.get("pages")
        include_screenshots = kwargs.get("include_screenshots", False)

        if not pdf_path:
            return {"error": "pdf_path is required"}

        # Validate PDF exists
        if not os.path.exists(pdf_path):
            return {"error": f"PDF file not found: {pdf_path}"}

        if not pdf_path.lower().endswith(".pdf"):
            return {"error": f"File must be a PDF: {pdf_path}"}

        try:
            # Check if LiteParse CLI is available
            lit_path = await self._find_lit_cli()
            if not lit_path:
                return {
                    "error": "LiteParse CLI not found. Install with: npm install -g @llamaindex/liteparse",
                    "installation_hint": "npm install -g @llamaindex/liteparse",
                }

            # Build command
            cmd = [lit_path, "parse", pdf_path, "--format", output_format]
            
            if pages:
                cmd.extend(["--pages", pages])

            logger.info(f"Executing LiteParse: {' '.join(cmd)}")

            # Execute with timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=300.0,  # 5 minute timeout for large PDFs
                )
            except asyncio.TimeoutError:
                process.kill()
                return {
                    "error": "LiteParse timed out after 5 minutes",
                    "hint": "Try parsing specific pages using the 'pages' parameter",
                }

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                return {"error": f"LiteParse failed: {error_msg}"}

            # Parse output
            if output_format == "json":
                try:
                    result = json.loads(stdout.decode("utf-8"))
                    
                    # Add metadata
                    result["_liteparse_metadata"] = {
                        "pdf_path": pdf_path,
                        "pages_parsed": pages or "all",
                        "element_count": len(result.get("elements", [])),
                        "has_tables": any(
                            elem.get("type") == "table" 
                            for elem in result.get("elements", [])
                        ),
                    }
                    
                    # Generate screenshots if requested
                    if include_screenshots:
                        screenshots = await self._generate_screenshots(pdf_path, pages)
                        result["_screenshots"] = screenshots

                    return result
                except json.JSONDecodeError as e:
                    return {
                        "error": f"Failed to parse LiteParse JSON output: {str(e)}",
                        "raw_output": stdout.decode("utf-8", errors="replace")[:500],
                    }
            else:
                # Markdown output
                return {
                    "content": stdout.decode("utf-8", errors="replace"),
                    "format": "markdown",
                }

        except Exception as e:
            logger.exception(f"LiteParse execution failed: {e}")
            return {"error": f"LiteParse execution failed: {str(e)}"}

    async def _find_lit_cli(self) -> str | None:
        """Find the LiteParse CLI executable.
        
        Searches in:
        1. System PATH
        2. Common npm global install locations
        3. Local node_modules/.bin
        """
        # Try PATH first
        lit_path = shutil.which("lit")
        if lit_path:
            return lit_path

        # Try common locations
        common_paths = [
            # Windows global npm
            os.path.expandvars(r"%APPDATA%\npm\lit.cmd"),
            os.path.expandvars(r"%APPDATA%\npm\lit"),
            # macOS/Linux global npm
            "/usr/local/bin/lit",
            "/opt/homebrew/bin/lit",
            # Local project
            os.path.join(os.getcwd(), "node_modules", ".bin", "lit"),
            os.path.join(os.getcwd(), "node_modules", ".bin", "lit.cmd"),
        ]

        for path in common_paths:
            if os.path.exists(path):
                return path

        return None

    async def _generate_screenshots(self, pdf_path: str, pages: str | None = None) -> list[dict[str, Any]]:
        """Generate screenshots of PDF pages using LiteParse.
        
        Args:
            pdf_path: Path to PDF file
            pages: Optional page range
            
        Returns:
            List of screenshot metadata with paths
        """
        lit_path = await self._find_lit_cli()
        if not lit_path:
            return []

        try:
            cmd = [lit_path, "screenshot", pdf_path]
            
            if pages:
                cmd.extend(["--target-pages", pages])
            
            # Create output directory
            output_dir = os.path.join(
                os.path.dirname(pdf_path),
                "_liteparse_screenshots"
            )
            os.makedirs(output_dir, exist_ok=True)
            cmd.extend(["--output-dir", output_dir])

            logger.info(f"Generating screenshots: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120.0,
            )

            if process.returncode != 0:
                logger.warning(f"Screenshot generation failed: {stderr.decode()}")
                return []

            # List generated screenshots
            screenshots = []
            if os.path.exists(output_dir):
                for filename in sorted(os.listdir(output_dir)):
                    if filename.endswith((".png", ".jpg", ".jpeg")):
                        screenshots.append({
                            "filename": filename,
                            "path": os.path.join(output_dir, filename),
                            "relative_path": os.path.relpath(
                                os.path.join(output_dir, filename),
                                os.path.dirname(pdf_path)
                            ),
                        })

            return screenshots

        except Exception as e:
            logger.warning(f"Failed to generate screenshots: {e}")
            return []


class LiteParseDebuggerTool(Tool):
    """Debug and visualize LiteParse parsing results.
    
    Provides tools for:
    - Visualizing bounding boxes on PDF pages
    - Comparing parsing results
    - Performance profiling
    """

    @property
    def name(self) -> str:
        return "liteparse_debug"

    @property
    def description(self) -> str:
        return (
            "Debug and analyze LiteParse parsing results. "
            "Visualize bounding boxes, check element counts, and validate parsing quality. "
            "Useful for testing and optimizing financial report parsing."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": "Path to the PDF file to analyze",
                },
                "action": {
                    "type": "string",
                    "description": "Debug action to perform",
                    "enum": ["summary", "validate", "stats"],
                    "default": "summary",
                },
            },
            "required": ["pdf_path"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        """Execute LiteParse debugging.
        
        Args:
            pdf_path: Path to PDF file
            action: Debug action (summary, validate, stats)
            
        Returns:
            Debug information and analysis
        """
        pdf_path = kwargs.get("pdf_path")
        action = kwargs.get("action", "summary")

        if not pdf_path:
            return {"error": "pdf_path is required"}

        if not os.path.exists(pdf_path):
            return {"error": f"PDF file not found: {pdf_path}"}

        # First parse the document
        parse_tool = LiteParseTool()
        result = await parse_tool.execute(pdf_path=pdf_path, output_format="json")

        if "error" in result:
            return result

        if action == "summary":
            return self._generate_summary(result, pdf_path)
        elif action == "validate":
            return self._validate_parsing(result)
        elif action == "stats":
            return self._generate_statistics(result)
        else:
            return {"error": f"Unknown action: {action}"}

    def _generate_summary(self, result: dict, pdf_path: str) -> dict:
        """Generate a summary of parsing results."""
        elements = result.get("elements", [])
        
        # Count by type
        type_counts = {}
        for elem in elements:
            elem_type = elem.get("type", "unknown")
            type_counts[elem_type] = type_counts.get(elem_type, 0) + 1

        # Check for tables
        tables = [e for e in elements if e.get("type") == "table"]
        
        return {
            "pdf_path": pdf_path,
            "total_elements": len(elements),
            "element_types": type_counts,
            "table_count": len(tables),
            "has_financial_tables": any(
                "balance" in str(t.get("text", "")).lower() or
                "income" in str(t.get("text", "")).lower() or
                "cash flow" in str(t.get("text", "")).lower()
                for t in tables
            ),
            "pages": result.get("_liteparse_metadata", {}).get("pages_parsed", "unknown"),
        }

    def _validate_parsing(self, result: dict) -> dict:
        """Validate parsing quality."""
        elements = result.get("elements", [])
        issues = []
        warnings = []

        # Check for elements without bounding boxes
        missing_bbox = sum(1 for e in elements if "bbox" not in e and "bounding_box" not in e)
        if missing_bbox > 0:
            warnings.append(f"{missing_bbox} elements missing bounding boxes")

        # Check for empty text elements
        empty_text = sum(1 for e in elements if not e.get("text", "").strip())
        if empty_text > 0:
            warnings.append(f"{empty_text} elements with empty text")

        # Check table structure
        tables = [e for e in elements if e.get("type") == "table"]
        for i, table in enumerate(tables):
            if not table.get("rows"):
                issues.append(f"Table {i+1} has no row structure")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "total_elements": len(elements),
            "tables_validated": len(tables),
        }

    def _generate_statistics(self, result: dict) -> dict:
        """Generate detailed statistics."""
        elements = result.get("elements", [])
        
        # Text length distribution
        text_lengths = [len(e.get("text", "")) for e in elements if e.get("text")]
        
        # Bounding box sizes
        bbox_areas = []
        for e in elements:
            bbox = e.get("bbox") or e.get("bounding_box")
            if bbox:
                if isinstance(bbox, dict):
                    w = bbox.get("width", 0)
                    h = bbox.get("height", 0)
                    bbox_areas.append(w * h)

        return {
            "total_elements": len(elements),
            "avg_text_length": sum(text_lengths) / len(text_lengths) if text_lengths else 0,
            "max_text_length": max(text_lengths) if text_lengths else 0,
            "avg_bbox_area": sum(bbox_areas) / len(bbox_areas) if bbox_areas else 0,
            "element_type_distribution": self._count_types(elements),
        }

    def _count_types(self, elements: list) -> dict[str, int]:
        """Count elements by type."""
        counts = {}
        for e in elements:
            t = e.get("type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts
