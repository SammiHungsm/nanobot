"""
Stage 1: OpenDataLoader 基础解析

职责：
- 调用 OpenDataLoader Hybrid (CUDA GPU) 解析 PDF
- 返回 raw_artifacts (tables, images, text_chunks)
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from nanobot.core.pdf_core import OpenDataLoaderCore


class Stage1Parser:
    """Stage 1: OpenDataLoader 基础解析"""
    
    @staticmethod
    async def parse_pdf(
        pdf_path: str,
        output_dir: str,
        enable_hybrid: bool = True,  # 🌟 总是启用 Hybrid（GPU 或 CPU 自动检测）
        batch_size: int = 10,
        batch_delay: int = 15
    ) -> Dict[str, Any]:
        """
        解析 PDF，返回 artifacts
        
        🌟 总是使用 Hybrid 模式（GPU/CPU 自动检测）
        - 有 GPU → CUDA Docling
        - 无 GPU → CPU Docling
        - 无 Java only mode
        
        Args:
            pdf_path: PDF 文件路径
            output_dir: 输出目录
            enable_hybrid: 总是 True（由 Hybrid 服务自动检测 GPU/CPU）
            batch_size: 分批大小（大 PDF 时使用）
            batch_delay: 批次间延迟
            
        Returns:
            Dict: {"artifacts": List, "total_pages": int, "output_json": str}
        """
        logger.info(f"📄 Stage 1: 开始 Hybrid 解析...")
        logger.info(f"   Hybrid 模式: 总是启用（GPU/CPU 自动检测）")
        
        # 🌟 总是使用 Hybrid（设备由 start_hybrid.sh 自动检测）
        core = OpenDataLoaderCore(enable_hybrid=True)
        
        result = core.parse(
            pdf_path=pdf_path,
            output_dir=output_dir,
            enable_hybrid=True  # 🌟 使用正确的参数名
        )
        
        logger.info(f"   ✅ 解析完成: {result.total_pages} 页, {len(result.artifacts)} artifacts")
        
        return {
            "artifacts": result.artifacts,
            "total_pages": result.total_pages,
            "tables": result.tables,
            "images": result.images,
            "markdown": result.markdown,
            "output_dir": output_dir,
            "hybrid_enabled": True,
            "hybrid_device": result.hybrid_device  # cuda 或 cpu
        }