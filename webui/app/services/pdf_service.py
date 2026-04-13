"""
PDF Service - Handles document parsing with OpenDataLoader

🎯 v2.0: 使用統一的 pdf_core 封裝
- 所有底层 API 调用统一在 nanobot.core.pdf_core
- 自动处理 Docker 网络问题
- 统一 format 参数格式
- 统一 JSON 输出结构
"""

from pathlib import Path
from typing import Dict
from loguru import logger

# 🌟 使用统一的核心模块
from nanobot.core.pdf_core import parse_pdf_async, PDFParseResult


async def process_pdf_async(input_path: str, output_path: str, enable_hybrid: bool = False) -> Dict:
    """
    Process PDF file asynchronously using unified PDF Core.
    
    🌟 v2.0: 一行代码搞定
    
    Args:
        input_path: Path to input PDF
        output_path: Path for JSON output
        enable_hybrid: 是否启用 Hybrid AI 视觉模式
        
    Returns:
        Metadata from processed file
    """
    logger.info(f"📄 异步解析 PDF: {input_path}")
    
    # 🌟 直接調用統一核心的非同步方法
    result: PDFParseResult = await parse_pdf_async(input_path, enable_hybrid=enable_hybrid)
    
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
                "total_pages": result.total_pages
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 已保存 JSON: {output_path}")
    
    # 🌟 回傳給前端需要的 metadata
    return {
        "metadata": result.metadata,
        "total_pages": result.total_pages,
        "tables_count": len(result.tables),
        "images_count": len(result.images),
        "artifacts_count": len(result.artifacts)
    }