"""
PDF Service - Handles document parsing with OpenDataLoader
"""
import asyncio
import json
from pathlib import Path
from typing import Optional
from loguru import logger


def run_opendataloader(input_path: str, output_path: str):
    """
    Run OpenDataLoader PDF conversion.
    This is a blocking operation, should be run in a thread pool.
    
    Args:
        input_path: Path to input PDF file
        output_path: Path to save JSON output
    """
    try:
        # Try to use OpenDataLoader with proper parameters
        try:
            from opendataloader import convert
            
            convert(
                input_path, 
                output_path=output_path, 
                output_format="json", 
                pages="all"
            )
        except ImportError:
            logger.warning("OpenDataLoader not available, using mock result")
            # Create a mock result for testing
            mock_result = {
                "metadata": {
                    "filename": Path(input_path).name,
                    "page_count": 0,
                    "status": "mock"
                },
                "content": []
            }
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(mock_result, f, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"OpenDataLoader conversion failed: {e}")
        raise


async def process_pdf_async(input_path: str, output_path: str) -> dict:
    """
    Process PDF file asynchronously using thread pool.
    
    Args:
        input_path: Path to input PDF
        output_path: Path for JSON output
        
    Returns:
        Metadata from processed file
    """
    loop = asyncio.get_event_loop()
    
    # Run blocking operation in thread pool
    await loop.run_in_executor(
        None,
        run_opendataloader,
        input_path,
        output_path
    )
    
    # Read and return metadata
    if Path(output_path).exists():
        with open(output_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    return {}
