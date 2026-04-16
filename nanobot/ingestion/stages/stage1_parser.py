"""
Stage 1: LlamaParse 基础解析 (v3.2)

职责：
- 调用 LlamaParse Cloud API 解析 PDF
- 返回 raw_artifacts (tables, images, text_chunks)
- 自动保存 raw results（省钱，可复用）

🌟 v3.2: 完全移除 OpenDataLoader
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from nanobot.core.pdf_core import PDFParser, PDFParseResult


class Stage1Parser:
    """Stage 1: LlamaParse 基础解析"""
    
    @staticmethod
    async def parse_pdf(
        pdf_path: str,
        output_dir: str = None,
        doc_id: str = None,
        tier: str = "agentic",
        save_result: bool = True,
        skip_if_saved: bool = True
    ) -> Dict[str, Any]:
        """
        解析 PDF，返回 artifacts
        
        Args:
            pdf_path: PDF 文件路径
            output_dir: 输出目录（默认 data/raw/llamaparse/{pdf_filename}）
            doc_id: 文档 ID（可选）
            tier: LlamaParse 解析层级（agentic/cost_effective/fast）
            save_result: 是否自动保存结果
            skip_if_saved: 如果已保存，是否跳过解析
            
        Returns:
            Dict[str, Any]: 解析结果
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        pdf_filename = pdf_path.name
        
        # 🌟 检查是否已有保存的结果
        parser = PDFParser(tier=tier)
        
        if skip_if_saved:
            try:
                logger.info(f"📂 检查已保存结果: {pdf_filename}")
                result = parser.load_from_raw_output(pdf_filename)
                logger.info(f"✅ 使用已保存结果（不扣费）")
                return Stage1Parser._convert_result(result, doc_id)
            except FileNotFoundError:
                logger.info(f"   未找到已保存结果，开始新解析")
        
        # 🌟 调用 LlamaParse
        logger.info(f"🚀 LlamaParse 解析: {pdf_path}")
        result: PDFParseResult = await parser.parse_async(str(pdf_path))
        
        # 🌟 保存结果
        if save_result:
            logger.info(f"💾 Raw output 已保存到: {result.raw_output_dir}")
        
        return Stage1Parser._convert_result(result, doc_id)
    
    @staticmethod
    def _convert_result(result: PDFParseResult, doc_id: str = None) -> Dict[str, Any]:
        """
        将 PDFParseResult 转换为 Stage 1 输出格式
        
        Args:
            result: LlamaParse 结果
            doc_id: 文档 ID
            
        Returns:
            Dict[str, Any]: Stage 1 输出
        """
        return {
            "success": True,
            "doc_id": doc_id,
            "job_id": result.job_id,
            "total_pages": result.total_pages,
            "markdown": result.markdown,
            "tables": result.tables,
            "images": result.images,
            "artifacts": result.artifacts,
            "metadata": {
                "parser": "llamaparse",
                "tier": result.tier,
                "raw_output_dir": result.raw_output_dir,
                "char_count": len(result.markdown),
                "table_count": len(result.tables),
                "image_count": len(result.images)
            }
        }
    
    @staticmethod
    async def parse_pdf_url(
        url: str,
        doc_id: str = None,
        tier: str = "agentic"
    ) -> Dict[str, Any]:
        """
        解析 URL PDF
        
        Args:
            url: PDF URL
            doc_id: 文档 ID
            tier: 解析层级
            
        Returns:
            Dict[str, Any]: 解析结果
        """
        parser = PDFParser(tier=tier)
        result: PDFParseResult = await parser.parse_url_async(url)
        
        return Stage1Parser._convert_result(result, doc_id)
    
    @staticmethod
    def load_saved_result(pdf_filename: str, job_id: str = None) -> Dict[str, Any]:
        """
        加载已保存的结果（不扣费）
        
        Args:
            pdf_filename: PDF 文件名
            job_id: 任务 ID（可选）
            
        Returns:
            Dict[str, Any]: 解析结果
        """
        parser = PDFParser()
        result: PDFParseResult = parser.load_from_raw_output(pdf_filename, job_id)
        
        return Stage1Parser._convert_result(result)