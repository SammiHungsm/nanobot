"""
Parsers Module - PDF 解析層

負責將 PDF 轉換為結構化數據（文字、Markdown 等）。
"""

import os
import re
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


def _get_config_api_credentials() -> tuple[Optional[str], Optional[str]]:
    """
    從 nanobot config.json 讀取 API 憑證
    
    Returns:
        tuple: (api_key, api_base)
    """
    try:
        from nanobot.config.loader import load_config
        from pathlib import Path
        import os
        
        # 優先使用 NANOBOT_CONFIG 環境變數指定的路徑
        config_path = None
        nanobot_config_env = os.getenv("NANOBOT_CONFIG")
        if nanobot_config_env:
            config_path = Path(nanobot_config_env)
            if not config_path.exists():
                config_path = None
        
        config = load_config(config_path)
        provider = config.get_provider()
        
        if provider:
            api_key = provider.api_key or None
            api_base = provider.api_base or None
            
            # 檢查是否為佔位符
            if api_key and api_key.startswith("sk-YOUR"):
                api_key = None
            
            if api_key:
                logger.debug(f"✅ 從 config.json 載入 API Key: {api_key[:10]}...")
                return api_key, api_base
    except Exception as e:
        logger.warning(f"⚠️ 無法從 config.json 載入 API 憑證: {e}")
    
    return None, None


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
            api_key: API Key (優先使用參數，其次從 config.json 讀取)
            api_base: API Base URL
            model: Vision 模型名稱
        """
        # 優先順序：參數 > config.json > 環境變數
        if not api_key or not api_base:
            config_key, config_base = _get_config_api_credentials()
            api_key = api_key or config_key
            api_base = api_base or config_base
        
        # 最後嘗試環境變數作為 fallback
        self.api_key = api_key or os.getenv("CUSTOM_API_KEY") or os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.api_base = api_base or os.getenv("CUSTOM_API_BASE") or os.getenv("OPENAI_API_BASE")
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
    def is_candidate_page(page, keywords: List[str]) -> bool:
        """
        🚀 企業級掃描器：結合文字正規化與視覺特徵的多維度特徵掃描
        
        Args:
            page: PyMuPDF Page 對象
            keywords: 關鍵字列表
            
        Returns:
            bool: 是否為候選頁面
        """
        # ==========================================
        # 策略 1: 正規化模糊搜尋 (Normalized Text Search)
        # ==========================================
        raw_text = page.get_text("text")
        
        # 將所有換行、多餘空格、標點符號全部剷除，變成純小寫字母
        # 例如 "Revenue \n Breakdown" 會變成 "revenuebreakdown"
        normalized_text = re.sub(r'[\s\W_]+', '', raw_text.lower())
        
        for kw in keywords:
            # 將 keyword 也做同樣的正規化
            norm_kw = re.sub(r'[\s\W_]+', '', kw.lower())
            if norm_kw in normalized_text:
                logger.debug(f"🔍 模糊搜尋命中 Keyword: {kw}")
                return True

        # ==========================================
        # 策略 2: 視覺特徵偵測 (Visual Feature Detection - 針對圖表)
        # ==========================================
        # 如果文字找不到，但這頁有大量的向量繪圖 (通常是 Pie Chart / Bar Chart)
        try:
            drawings = page.get_drawings()
            if len(drawings) > 15:  # 財報圖表通常由數十條 path 組成
                logger.debug("📊 偵測到大量向量繪圖，疑似複雜圖表頁面")
                # 檢查附近有沒有 "%" 符號 - 財務圖表通常有百分比
                if "%" in raw_text:
                    logger.debug("   ✅ 同時偵測到 % 符號，標記為候選")
                    return True
        except Exception as e:
            logger.debug(f"   ⚠️ 向量繪圖檢測失敗: {e}")

        # ==========================================
        # 策略 3: 表格特徵偵測 (Table Feature Detection)
        # ==========================================
        # 即使找不到 Keyword，但這頁如果有大型表格結構，也交給 LLM 判斷
        try:
            tables = page.find_tables()
            if tables and len(tables.tables) > 0:
                # 檢查表格內容是否包含地區或數字
                for table in tables.tables:
                    table_content = table.extract()
                    if table_content:
                        table_text = "\n".join([str(cell) for row in table_content for cell in row if cell])
                        # 檢查是否包含財務特徵
                        financial_indicators = ["HK$", "RMB", "US$", "Total", "total", 
                                                  "revenue", "turnover", "sales", "income",
                                                  "Europe", "China", "Asia", "Canada", "Hong Kong",
                                                  "地區", "地", "區域", "地理"]
                        for indicator in financial_indicators:
                            if indicator in table_text:
                                logger.debug(f"📑 偵測到包含財務特徵的表格 ({indicator})，標記為候選")
                                return True
        except Exception as e:
            logger.debug(f"   ⚠️ 表格檢測失敗: {e}")

        return False

    @staticmethod
    def scan_for_keywords(
        pdf_path: str,
        keywords: List[str]
    ) -> List[int]:
        """
        掃描 PDF 找出包含關鍵字或財務特徵的頁面 (企業級多維度掃描)
        
        Args:
            pdf_path: PDF 檔案路徑
            keywords: 關鍵字列表
            
        Returns:
            List[int]: 包含關鍵字的頁碼列表 (1-indexed)
        """
        if not PYMUPDF_AVAILABLE:
            logger.warning("⚠️ PyMuPDF 未安裝，無法進行掃描")
            return []
        
        candidate_pages = []
        
        try:
            doc = fitz.open(pdf_path)
            logger.info(f"   📄 開始掃描 {len(doc)} 頁...")
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                if FastParser.is_candidate_page(page, keywords):
                    candidate_pages.append(page_num + 1)  # 1-indexed
            
            doc.close()
            
            logger.info(f"   🎯 掃描完成：找到 {len(candidate_pages)} 個候選頁面: {candidate_pages[:10]}{'...' if len(candidate_pages) > 10 else ''}")
            return sorted(set(candidate_pages))
            
        except Exception as e:
            logger.error(f"❌ 關鍵字掃描失敗: {e}")
            return []