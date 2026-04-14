"""
OpenDataLoader Parser - 純 Parser 層

職責：
- 將 PDF 解析為 Artifacts（文字、表格、圖片）
- 不涉及資料庫操作
- 不涉及 LLM 提取

🎯 v2.0: 使用統一的 pdf_core 封裝
- 所有底层 API 调用统一在 nanobot.core.pdf_core
- 自动处理 Docker 网络问题
- 统一 format 参数格式
- 统一 JSON 输出结构
"""

from typing import List, Dict, Any
from loguru import logger

# 🌟 使用统一的核心模块
from nanobot.core.pdf_core import OpenDataLoaderCore


class OpenDataLoaderParser:
    """
    OpenDataLoader 解析器
    
    🌟 v2.0: 所有核心逻辑由 pdf_core 处理，这里只是薄薄的适配层
    
    純 Parser：輸入 PDF，輸出 Artifacts。
    不碰資料庫，不碰 LLM。
    """
    
    def __init__(self, enable_hybrid: bool = True):
        """
        初始化
        
        Args:
            enable_hybrid: 是否启用 Hybrid AI 视觉模式（默认 True = 启用 GPU 加速 + 图片处理）
        """
        self.core = OpenDataLoaderCore(enable_hybrid=enable_hybrid)
        logger.info(f"✅ OpenDataLoaderParser 初始化完成 (hybrid={enable_hybrid})")
    
    def parse(self, pdf_path: str, doc_id: str = None) -> List[Dict[str, Any]]:
        """
        解析 PDF 文件
        
        Args:
            pdf_path: PDF 文件路徑
            doc_id: 文檔 ID（可選，用於調試）
            
        Returns:
            List[Dict]: Artifacts 列表
        """
        logger.info(f"📖 OpenDataLoader 正在解析：{pdf_path}")
        
        # 🌟 呼叫核心解析
        result = self.core.parse(pdf_path)
        
        # 🌟 直接使用核心提供的轉換工具
        artifacts = result.artifacts
        
        logger.info(f"✅ 解析完成：{len(artifacts)} 個 artifacts")
        return artifacts
    
    def parse_pages(self, pdf_path: str, pages: List[int], doc_id: str = None, enable_hybrid: bool = False) -> List[Dict[str, Any]]:
        """
        🌟 只解析 PDF 的特定页面（用于快速提取封面信息）
        
        Args:
            pdf_path: PDF 文件路径
            pages: 要解析的页码列表（如 [1, 2]）
            doc_id: 文档 ID
            enable_hybrid: 是否启用 Hybrid 模式（默认 False = 纯 Java，节省 GPU）
            
        Returns:
            List[Dict]: Artifacts 列表
        """
        logger.info(f"📖 快速解析 Page {pages}：{pdf_path} (enable_hybrid={enable_hybrid})")
        
        # 🌟 支援特定頁面快速解析，可选择启用/禁用 Hybrid
        result = self.core.parse(pdf_path, pages=pages, use_hybrid=enable_hybrid)
        
        logger.info(f"✅ Page {pages} 解析完成：{len(result.artifacts)} 個 artifacts")
        return result.artifacts
    
    async def parse_async(self, pdf_path: str, doc_id: str = None, enable_hybrid: bool = True) -> List[Dict[str, Any]]:
        """
        異步解析 PDF
        
        Args:
            pdf_path: PDF 文件路徑
            doc_id: 文檔 ID
            enable_hybrid: 是否启用 Hybrid 模式（默认 True）
            
        Returns:
            List[Dict]: Artifacts 列表
        """
        logger.info(f"📖 異步解析：{pdf_path} (enable_hybrid={enable_hybrid})")
        
        # 🌟 呼叫核心的非同步方法，传入 enable_hybrid
        result = await self.core.parse_async(pdf_path, enable_hybrid=enable_hybrid)
        
        logger.info(f"✅ 解析完成：{len(result.artifacts)} 個 artifacts")
        return result.artifacts