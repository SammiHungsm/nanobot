"""
Page Classifier - LLM 智能頁面路由器

使用 LLM 進行語義分析，自動找出含有目標數據的頁碼。
完全不需要 hardcode keywords 或貨幣符號！

架構：Two-Stage LLM Pipeline
1. Stage 1 (便宜 & 快速): LLM 語義分類
2. Stage 2 (昂貴 & 精準): Vision LLM 只處理相關頁面
"""

import os
import json
import logging
from typing import Dict, List, Optional
from loguru import logger

# 導入統一的 LLM 客戶端
# 🌟 使用统一的 llm_core
from nanobot.core.llm_core import llm_core


class PageClassifier:
    """
    LLM 智能頁面路由器
    
    使用 LLM 進行語義分析，自動識別包含目標數據的頁面。
    完全消除 hardcode keywords 的需求。
    """
    
    def __init__(self):
        """
        初始化
        
        使用統一的 LLM 客戶端，不再手動管理 API Key。
        """
        self._client = None
        self._model = None
        logger.info(f"✅ PageClassifier 初始化完成")
    
    def _get_client(self):
        """獲取 OpenAI 客戶端（延遲載入）"""
        # 🌟 使用統一的 llm_core
        if self._client is None:
            self._client = llm_core
        return self._client
    
    def _get_model(self) -> str:
        """獲取 LLM 模型名稱"""
        # 🌟 使用統一的 llm_core
        if self._model is None:
            self._model = llm_core.default_model
        return self._model
    
    async def find_candidate_pages(
        self,
        pages_text_dict: Dict[int, str],
        target_data_types: List[str] = None
    ) -> Dict[str, List[int]]:
        """
        使用 LLM 進行語義分析，自動找出含有目標數據的頁碼。
        完全不需要 hardcode keywords 或貨幣符號！
        
        Args:
            pages_text_dict: dict 格式為 {page_num: "該頁的原始粗糙文字..."}
            target_data_types: 目標數據類型列表，默認為 ["revenue_breakdown", "key_personnel"]
            
        Returns:
            Dict[str, List[int]]: {"revenue_breakdown": [6, 15], "key_personnel": [32, 33]}
        """
        if target_data_types is None:
            target_data_types = ["revenue_breakdown", "key_personnel"]
        
        logger.info(f"🧠 啟動 LLM 智能頁面路由 (Smart Routing)...")
        logger.info(f"   📄 總頁數: {len(pages_text_dict)}")
        logger.info(f"   🎯 目標數據類型: {target_data_types}")
        
        client = self._get_client()
        if not client:
            logger.error("❌ 無法初始化 LLM 客戶端")
            return {dt: [] for dt in target_data_types}
        
        # 為了節省 Token，將多頁的文字壓縮
        compressed_context = self._compress_pages(pages_text_dict)
        
        if not compressed_context:
            logger.warning("⚠️ 壓縮後的上下文為空，無法進行分類")
            return {dt: [] for dt in target_data_types}
        
        system_prompt = self._build_system_prompt(target_data_types)
        
        try:
            # 🌟 使用 llm_core.chat() 方法
            result_text = await client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": compressed_context}
                ],
                model=self._get_model(),
                temperature=0.0
            )
            
            result = json.loads(result_text)
            
            # 確保所有目標類型都有結果
            for dt in target_data_types:
                if dt not in result:
                    result[dt] = []
            
            logger.info(f"🎯 LLM 路由結果: {result}")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ LLM 返回非 JSON 格式: {e}")
            return {dt: [] for dt in target_data_types}
        except Exception as e:
            logger.error(f"❌ LLM 頁面分類失敗: {e}")
            return {dt: [] for dt in target_data_types}
    
    def _compress_pages(
        self,
        pages_text_dict: Dict[int, str],
        preview_chars: int = 400
    ) -> str:
        """
        壓縮頁面文字以節省 Token
        
        Args:
            pages_text_dict: 頁面文字字典
            preview_chars: 每頁預覽字符數
            
        Returns:
            str: 壓縮後的上下文
        """
        compressed_parts = []
        
        for page_num in sorted(pages_text_dict.keys()):
            text = pages_text_dict[page_num]
            
            # 取每頁的開頭，這通常包含了標題和關鍵內容
            preview = text[:preview_chars].replace('\n', ' ').strip()
            
            if len(preview) > 10:  # 過濾掉空白頁
                compressed_parts.append(f"--- [Page {page_num}] ---\n{preview}\n")
        
        return "\n".join(compressed_parts)
    
    def _build_system_prompt(self, target_data_types: List[str]) -> str:
        """
        構建系統提示詞
        
        Args:
            target_data_types: 目標數據類型列表
            
        Returns:
            str: 系統提示詞
        """
        # 數據類型描述
        data_type_descriptions = {
            "revenue_breakdown": "地區性收入分佈、營業額地理分析、Geographical segment/revenue/turnover by region",
            "key_personnel": "董事局成員簡歷、高管個人介紹、Biography of Directors/Senior Management",
            "financial_metrics": "財務指標表格、損益表、資產負債表、Financial Statements",
            "shareholdings": "股權結構、主要股東、Shareholding structure、Major shareholders",
            "esg_metrics": "ESG 數據、碳排放、可持續發展指標、ESG metrics、Carbon emission"
        }
        
        # 構建目標數據描述
        target_descriptions = []
        for i, dt in enumerate(target_data_types, 1):
            desc = data_type_descriptions.get(dt, dt)
            target_descriptions.append(f"{i}. {dt}: {desc}")
        
        targets_text = "\n".join(target_descriptions)
        
        # 構建輸出格式範例
        example_output = {dt: [] for dt in target_data_types}
        example_output[target_data_types[0]] = [6, 15]
        if len(target_data_types) > 1:
            example_output[target_data_types[1]] = [32, 33]
        
        return f"""你是一個頂尖的金融數據分析大腦。
我會提供一份財務報告中各頁的部分文字預覽（已標註頁碼）。
請根據語義理解，判斷哪些頁面「最可能」包含以下結構化數據。

目標數據：
{targets_text}

請注意：
- 不要依賴特定的關鍵字，請理解語義
- 同義詞也應識別（例如 "Turnover" = "Revenue" = "Sales"）
- 如果某頁看起來像表格數據頁，即使沒有明確標題，也應該標記
- 最多返回每種數據類型的前 5 個最相關頁面

請以嚴格的 JSON 格式輸出，返回最有可能包含該數據的頁碼列表（整數）。如果沒有，請返回空列表。

輸出範例：
{json.dumps(example_output, indent=2)}"""

    async def classify_single_page(
        self,
        page_text: str,
        page_num: int
    ) -> Dict[str, bool]:
        """
        對單一頁面進行分類
        
        Args:
            page_text: 頁面文字
            page_num: 頁碼
            
        Returns:
            Dict[str, bool]: {"revenue_breakdown": True, "key_personnel": False}
        """
        result = await self.find_candidate_pages({page_num: page_text})
        return {k: page_num in v for k, v in result.items()}


# ===========================================
# 便捷函數
# ===========================================

async def find_revenue_breakdown_pages(
    pdf_path: str
) -> List[int]:
    """
    便捷函數：找出包含 Revenue Breakdown 的頁面
    
    Args:
        pdf_path: PDF 路徑
        
    Returns:
        List[int]: 頁碼列表
    """
    import fitz
    
    # 提取所有頁面文字
    pages_text = {}
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pages_text[page_num + 1] = page.get_text("text")
    doc.close()
    
    # 使用 PageClassifier 進行分類
    classifier = PageClassifier()
    result = await classifier.find_candidate_pages(pages_text, ["revenue_breakdown"])
    
    return result.get("revenue_breakdown", [])