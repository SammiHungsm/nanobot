"""
PDF Service - Handles document parsing with LlamaParse

🎯 v3.0: 简化架构，只使用 LlamaParse
- 移除 OpenDataLoader/Docling/Hybrid
- 所有 PDF 解析通过 LlamaParse Cloud API
- 支持 130+ 格式 + 本地文件上传
"""

from pathlib import Path
from typing import Dict
from loguru import logger

# 🌟 使用统一的核心模块
from nanobot.core.pdf_core import PDFParser, PDFParseResult


async def process_pdf_async(input_path: str, output_path: str = None) -> Dict:
    """
    Process PDF file asynchronously using LlamaParse.
    
    Args:
        input_path: Path to input PDF
        output_path: Path for JSON output (optional)
        
    Returns:
        Metadata from processed file
    """
    logger.info(f"📄 LlamaParse 解析 PDF: {input_path}")
    
    # 🌟 使用 LlamaParse 解析
    parser = PDFParser()
    result: PDFParseResult = await parser.parse_async(input_path)
    
    # 🌟 保存 JSON（如果需要）
    if output_path:
        import json
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "metadata": result.metadata,
                "artifacts": result.artifacts,
                "tables": result.tables,
                "images": result.images,
                "total_pages": result.total_pages,
                "job_id": result.job_id  # 🌟 保存 job_id 避免重复扣费
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 已保存 JSON: {output_path}")
    
    # 🌟 回傳給前端需要的 metadata
    return {
        "metadata": result.metadata,
        "total_pages": result.total_pages,
        "tables_count": len(result.tables),
        "images_count": len(result.images),
        "artifacts_count": len(result.artifacts),
        "job_id": result.job_id  # 🌟 返回 job_id 供前端保存
    }