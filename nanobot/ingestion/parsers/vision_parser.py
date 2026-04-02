"""
Parsers Module - PDF 解析層

負責將 PDF 轉換為結構化數據（文字、Markdown 等）。
"""

import os
import base64
import json
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from loguru import logger

# PyMuPDF for PDF processing
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("⚠️ PyMuPDF 未安裝，PDF 處理功能將受限")

# OpenAI SDK for Vision API
try:
    from openai import AsyncOpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    logger.warning("⚠️ OpenAI SDK 未安裝，Vision 功能將不可用")


class VisionParser:
    """
    Vision Parser - 使用 Vision LLM 將 PDF 頁面轉換為 Markdown
    
    適用於包含圖表、複雜排版的頁面。
    """
    
    def __init__(
        self,
        api_key: str = None,
        api_base: str = None,
        model: str = "qwen-vl-max"
    ):
        """
        初始化
        
        Args:
            api_key: API Key (默認從環境變數讀取)
            api_base: API Base URL
            model: Vision 模型名稱
        """
        self.api_key = api_key or os.getenv("CUSTOM_API_KEY", os.getenv("OPENAI_API_KEY"))
        self.api_base = api_base or os.getenv(
            "CUSTOM_API_BASE", 
            os.getenv("OPENAI_API_BASE", "https://coding.dashscope.aliyuncs.com/v1")
        )
        self.model = model
        self.client = None
    
    def _get_client(self) -> Optional[AsyncOpenAI]:
        """獲取 OpenAI 客戶端"""
        if not OPENAI_SDK_AVAILABLE:
            logger.error("❌ OpenAI SDK 未安裝")
            return None
        
        if not self.api_key or self.api_key.startswith("sk-YOUR"):
            logger.error("❌ 未配置有效的 API Key")
            return None
        
        if not self.client:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_base
            )
        
        return self.client
    
    @staticmethod
    def is_complex_page(page: "fitz.Page") -> bool:
        """
        判斷該頁是否需要動用 Vision 解析
        
        Args:
            page: PyMuPDF 的 Page 對象
            
        Returns:
            bool: True 表示需要 Vision 解析
        """
        if not PYMUPDF_AVAILABLE:
            return False
        
        try:
            # 條件 1: 頁面內有圖片/圖表
            image_list = page.get_images(full=True)
            if len(image_list) > 0:
                return True
            
            # 條件 2: 頁面內包含大量向量繪圖
            drawings = page.get_drawings()
            if len(drawings) > 10:
                return True
            
            # 條件 3: 包含特定的財務關鍵字
            text = page.get_text("text").lower()
            complex_keywords = [
                "revenue breakdown", "geographical", "chart", "pie chart",
                "收入分佈", "地區收入", "業務分佈", "breakdown by"
            ]
            for keyword in complex_keywords:
                if keyword in text:
                    return True
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ 檢測頁面複雜度失敗: {e}")
            return False
    
    def convert_page_to_image_base64(
        self,
        pdf_path: str,
        page_num: int,
        zoom: float = 2.0
    ) -> Optional[str]:
        """
        將 PDF 特定頁面轉換為高品質 PNG 圖片並返回 Base64 字串
        
        Args:
            pdf_path: PDF 檔案路徑
            page_num: 頁碼 (1-indexed)
            zoom: 放大倍數
            
        Returns:
            str: Base64 編碼的 PNG 圖片
        """
        if not PYMUPDF_AVAILABLE:
            logger.error("❌ PyMuPDF 未安裝")
            return None
        
        try:
            logger.info(f"👁️ 正在將 PDF 第 {page_num} 頁轉換為圖片...")
            
            doc = fitz.open(pdf_path)
            
            if page_num < 1 or page_num > len(doc):
                logger.error(f"❌ 頁碼 {page_num} 無效")
                doc.close()
                return None
            
            page = doc.load_page(page_num - 1)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            img_bytes = pix.tobytes("png")
            base64_image = base64.b64encode(img_bytes).decode('utf-8')
            
            doc.close()
            
            logger.info(f"✅ PDF 頁面已轉換為 Base64 圖片 ({len(base64_image)} chars)")
            return base64_image
            
        except Exception as e:
            logger.error(f"❌ PDF 轉圖片失敗: {e}")
            return None
    
    async def to_markdown(
        self,
        pdf_path: str,
        page_num: int,
        save_debug_path: str = None
    ) -> Optional[str]:
        """
        🌟 核心方法：將 PDF 頁面轉換為 Markdown
        
        Args:
            pdf_path: PDF 檔案路徑
            page_num: 頁碼 (1-indexed)
            save_debug_path: 保存 Markdown 中間產物的路徑（用於調試）
            
        Returns:
            str: Markdown 文本
        """
        # 導入 Prompt
        from ..extractors.prompts import get_prompt
        
        client = self._get_client()
        if not client:
            return None
        
        # Step 1: 轉換為圖片
        base64_image = self.convert_page_to_image_base64(pdf_path, page_num)
        if not base64_image:
            return None
        
        # Step 2: 調用 Vision API
        try:
            system_prompt = get_prompt("vision_to_markdown")
            
            logger.info(f"👁️ RAG-Anything 視覺模式：轉換圖片為 Markdown...")
            
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            },
                            {
                                "type": "text",
                                "text": "請將此頁面精確轉換為 Markdown："
                            }
                        ]
                    }
                ],
                temperature=0.0
            )
            
            markdown_result = response.choices[0].message.content
            logger.info(f"✅ Markdown 轉換完成 ({len(markdown_result)} chars)")
            
            # 保存中間產物供調試
            if save_debug_path:
                Path(save_debug_path).parent.mkdir(parents=True, exist_ok=True)
                with open(save_debug_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_result)
                logger.info(f"💾 Markdown 已保存: {save_debug_path}")
            
            return markdown_result
            
        except Exception as e:
            logger.error(f"❌ Vision Markdown 轉換失敗: {e}")
            return None


class FastParser:
    """
    Fast Parser - 使用 PyMuPDF 快速提取純文字
    
    適用於純文字頁面，速度極快。
    """
    
    @staticmethod
    def extract_text(pdf_path: str, page_num: int) -> Optional[str]:
        """
        快速提取 PDF 頁面文字
        
        Args:
            pdf_path: PDF 檔案路徑
            page_num: 頁碼 (1-indexed)
            
        Returns:
            str: 頁面文字
        """
        if not PYMUPDF_AVAILABLE:
            logger.error("❌ PyMuPDF 未安裝")
            return None
        
        try:
            doc = fitz.open(pdf_path)
            
            if page_num < 1 or page_num > len(doc):
                logger.error(f"❌ 頁碼 {page_num} 無效")
                doc.close()
                return None
            
            page = doc.load_page(page_num - 1)
            text = page.get_text("text")
            doc.close()
            
            logger.info(f"✅ 快速文字提取完成: {len(text)} chars")
            return text
            
        except Exception as e:
            logger.error(f"❌ 快速文字提取失敗: {e}")
            return None
    
    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        """獲取 PDF 頁數"""
        if not PYMUPDF_AVAILABLE:
            return 0
        
        try:
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except:
            return 0
    
    @staticmethod
    def scan_for_keywords(
        pdf_path: str,
        keywords: List[str]
    ) -> List[int]:
        """
        掃描 PDF 找出包含關鍵字的頁面
        
        Args:
            pdf_path: PDF 檔案路徑
            keywords: 關鍵字列表
            
        Returns:
            List[int]: 包含關鍵字的頁碼列表 (1-indexed)
        """
        if not PYMUPDF_AVAILABLE:
            return []
        
        candidate_pages = []
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_num in range(1, len(doc) + 1):
                page = doc.load_page(page_num - 1)
                text = page.get_text("text").lower()
                
                for keyword in keywords:
                    if keyword.lower() in text:
                        candidate_pages.append(page_num)
                        break
            
            doc.close()
            return sorted(set(candidate_pages))
            
        except Exception as e:
            logger.error(f"❌ 關鍵字掃描失敗: {e}")
            return []