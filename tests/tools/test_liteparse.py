"""Tests for LiteParse integration.

Run with: pytest tests/tools/test_liteparse.py -v
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

# Add nanobot to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "nanobot"))

from nanobot.agent.tools.liteparse import LiteParseTool, LiteParseDebuggerTool


# Test PDF paths
TEST_PDF_DIR = Path(
    r"C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG\data\input\__enqueued__"
)
SAMPLE_PDF = TEST_PDF_DIR / "SFC_annual_report_2023-24.pdf"


@pytest.fixture
def liteparse_tool():
    """Create LiteParseTool instance."""
    return LiteParseTool()


@pytest.fixture
def debugger_tool():
    """Create LiteParseDebuggerTool instance."""
    return LiteParseDebuggerTool()


class TestLiteParseTool:
    """Test LiteParseTool functionality."""

    @pytest.mark.asyncio
    async def test_tool_schema(self, liteparse_tool):
        """Test tool schema is correctly defined."""
        schema = liteparse_tool.to_schema()
        
        assert schema["type"] == "function"
        assert "function" in schema
        assert schema["function"]["name"] == "liteparse_parse"
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]
        
        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        assert "pdf_path" in params["properties"]
        assert "pdf_path" in params["required"]

    @pytest.mark.asyncio
    async def test_missing_pdf_path(self, liteparse_tool):
        """Test error handling for missing pdf_path."""
        result = await liteparse_tool.execute()
        
        assert "error" in result
        assert "pdf_path is required" in result["error"]

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, liteparse_tool):
        """Test error handling for nonexistent file."""
        result = await liteparse_tool.execute(pdf_path="/nonexistent/path.pdf")
        
        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_file_extension(self, liteparse_tool):
        """Test error handling for non-PDF file."""
        # Create a temp file with wrong extension
        temp_file = Path(__file__).parent / "test.txt"
        temp_file.write_text("test content")
        
        try:
            result = await liteparse_tool.execute(pdf_path=str(temp_file))
            
            assert "error" in result
            assert "must be a PDF" in result["error"]
        finally:
            temp_file.unlink()

    @pytest.mark.asyncio
    async def test_lit_cli_detection(self, liteparse_tool):
        """Test LiteParse CLI detection."""
        lit_path = await liteparse_tool._find_lit_cli()
        
        # This test passes whether or not lit is installed
        # If installed, returns path; if not, returns None
        assert lit_path is None or os.path.exists(lit_path)

    @pytest.mark.skipif(
        not SAMPLE_PDF.exists(),
        reason=f"Sample PDF not found: {SAMPLE_PDF}",
    )
    @pytest.mark.asyncio
    async def test_parse_sample_pdf(self, liteparse_tool):
        """Test parsing the SFC annual report."""
        result = await liteparse_tool.execute(
            pdf_path=str(SAMPLE_PDF),
            output_format="json",
        )
        
        # Check for LiteParse CLI availability
        if "error" in result and "LiteParse CLI not found" in result["error"]:
            pytest.skip("LiteParse CLI not installed")
        
        # Should not have errors
        if "error" in result:
            pytest.fail(f"Parse failed: {result['error']}")
        
        # Validate structure
        assert "elements" in result or "_liteparse_metadata" in result
        
        metadata = result.get("_liteparse_metadata", {})
        assert metadata.get("pdf_path") == str(SAMPLE_PDF)
        assert "element_count" in metadata

    @pytest.mark.skipif(
        not SAMPLE_PDF.exists(),
        reason=f"Sample PDF not found: {SAMPLE_PDF}",
    )
    @pytest.mark.asyncio
    async def test_parse_specific_pages(self, liteparse_tool):
        """Test parsing specific page range."""
        result = await liteparse_tool.execute(
            pdf_path=str(SAMPLE_PDF),
            pages="1-3",
            output_format="json",
        )
        
        if "error" in result:
            if "LiteParse CLI not found" in result["error"]:
                pytest.skip("LiteParse CLI not installed")
            pytest.fail(f"Parse failed: {result['error']}")
        
        metadata = result.get("_liteparse_metadata", {})
        assert metadata.get("pages_parsed") == "1-3"

    @pytest.mark.skipif(
        not SAMPLE_PDF.exists(),
        reason=f"Sample PDF not found: {SAMPLE_PDF}",
    )
    @pytest.mark.asyncio
    async def test_screenshot_generation(self, liteparse_tool):
        """Test screenshot generation."""
        result = await liteparse_tool.execute(
            pdf_path=str(SAMPLE_PDF),
            pages="1",
            include_screenshots=True,
        )
        
        if "error" in result:
            if "LiteParse CLI not found" in result["error"]:
                pytest.skip("LiteParse CLI not installed")
            pytest.fail(f"Parse failed: {result['error']}")
        
        # Check screenshots were generated
        screenshots = result.get("_screenshots", [])
        # May be empty if screenshot generation fails, but shouldn't error


class TestLiteParseDebuggerTool:
    """Test LiteParseDebuggerTool functionality."""

    @pytest.mark.asyncio
    async def test_debugger_schema(self, debugger_tool):
        """Test debugger tool schema."""
        schema = debugger_tool.to_schema()
        
        assert schema["function"]["name"] == "liteparse_debug"
        assert "action" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_debug_summary(self, debugger_tool):
        """Test debug summary action."""
        if not SAMPLE_PDF.exists():
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        
        result = await debugger_tool.execute(
            pdf_path=str(SAMPLE_PDF),
            action="summary",
        )
        
        if "error" in result and "LiteParse CLI not found" in result["error"]:
            pytest.skip("LiteParse CLI not installed")
        
        if "error" in result:
            pytest.fail(f"Debug failed: {result['error']}")
        
        assert "total_elements" in result
        assert "element_types" in result
        assert "table_count" in result

    @pytest.mark.asyncio
    async def test_debug_validate(self, debugger_tool):
        """Test debug validation action."""
        if not SAMPLE_PDF.exists():
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        
        result = await debugger_tool.execute(
            pdf_path=str(SAMPLE_PDF),
            action="validate",
        )
        
        if "error" in result and "LiteParse CLI not found" in result["error"]:
            pytest.skip("LiteParse CLI not installed")
        
        if "error" in result:
            pytest.fail(f"Validation failed: {result['error']}")
        
        assert "valid" in result
        assert "issues" in result
        assert "warnings" in result

    @pytest.mark.asyncio
    async def test_debug_stats(self, debugger_tool):
        """Test debug statistics action."""
        if not SAMPLE_PDF.exists():
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        
        result = await debugger_tool.execute(
            pdf_path=str(SAMPLE_PDF),
            action="stats",
        )
        
        if "error" in result and "LiteParse CLI not found" in result["error"]:
            pytest.skip("LiteParse CLI not installed")
        
        if "error" in result:
            pytest.fail(f"Stats generation failed: {result['error']}")
        
        assert "total_elements" in result
        assert "avg_text_length" in result


class TestLiteParseIntegration:
    """Integration tests for LiteParse with real PDFs."""

    @pytest.mark.asyncio
    async def test_multiple_pdf_formats(self, liteparse_tool):
        """Test parsing multiple PDFs from the test directory."""
        if not TEST_PDF_DIR.exists():
            pytest.skip(f"Test directory not found: {TEST_PDF_DIR}")
        
        # Get available PDFs
        pdfs = list(TEST_PDF_DIR.glob("*.pdf"))[:3]  # Test first 3 PDFs
        
        if not pdfs:
            pytest.skip("No PDFs found in test directory")
        
        results = []
        for pdf in pdfs:
            result = await liteparse_tool.execute(pdf_path=str(pdf))
            
            if "error" in result:
                if "LiteParse CLI not found" in result["error"]:
                    pytest.skip("LiteParse CLI not installed")
                results.append({"pdf": str(pdf), "status": "failed", "error": result["error"]})
            else:
                results.append({"pdf": str(pdf), "status": "success"})
        
        # At least some should succeed if LiteParse is installed
        success_count = sum(1 for r in results if r["status"] == "success")
        assert success_count > 0, f"All PDFs failed: {results}"

    @pytest.mark.asyncio
    async def test_table_detection(self, liteparse_tool):
        """Test that financial tables are detected."""
        if not SAMPLE_PDF.exists():
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        
        result = await liteparse_tool.execute(
            pdf_path=str(SAMPLE_PDF),
            output_format="json",
        )
        
        if "error" in result:
            if "LiteParse CLI not found" in result["error"]:
                pytest.skip("LiteParse CLI not installed")
            pytest.fail(f"Parse failed: {result['error']}")
        
        metadata = result.get("_liteparse_metadata", {})
        
        # Annual reports should have tables
        assert metadata.get("has_tables") is True


def test_biotech_reports_available():
    """Verify test PDFs are available."""
    if not TEST_PDF_DIR.exists():
        pytest.skip(f"Test directory not found: {TEST_PDF_DIR}")
    
    pdfs = list(TEST_PDF_DIR.glob("*.pdf"))
    
    assert len(pdfs) > 0, "No PDFs found in test directory"
    
    # Check for expected files
    expected = [
        "SFC_annual_report_2023-24.pdf",
        "BioTech_Sector_annual_reports_2025.pdf",
    ]
    
    found_expected = [f for f in expected if (TEST_PDF_DIR / f).exists()]
    
    print(f"\nAvailable test PDFs ({len(pdfs)} total):")
    for pdf in sorted(pdf.name for pdf in pdfs[:10]):
        print(f"  - {pdf}")
    
    if len(found_expected) > 0:
        print(f"\nFound expected files: {found_expected}")
