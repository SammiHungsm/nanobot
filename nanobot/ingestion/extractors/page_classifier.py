"""
Page Classifier - LLM 智能頁面路由器

使用 gpt-4o-mini 進行語義分析，自動找出含有目標數據的頁碼。
完全不需要 hardcode keywords 或貨幣符號！

架構：Two-Stage LLM Pipeline
1. Stage 1 (便宜 & 快速): gpt-4o-mini 語義分類
2. Stage 2 (昂貴 & 精準): gpt-4o Vision 只處理相關頁面
"""

import os
import json
import logging
from typing import Dict, List, Optional
from loguru import logger

# OpenAI SDK
try:
    from openai import AsyncOpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    logger.warning("⚠️ OpenAI SDK 未安裝，PageClassifier 將無法使用")


def _get_config_api_credentials() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    從 nanobot config.json 讀取 API 憑證和模型
    
    Returns:
        tuple: (api_key, api_base, model)
    """
    try:
        from nanobot.config.loader import load_config
        from pathlib import Path
        
        # 優先使用 NANOBOT_CONFIG 環境變數指定的路徑
        config_path = None
        nanobot_config_env = os.getenv("NANOBOT_CONFIG")
        if nanobot_config_env:
            config_path = Path(nanobot_config_env)
            if not config_path.exists():
                config_path = None
        
        config = load_config(config_path)
        provider = config.get_provider()
        
        # 從 agents.defaults 讀取模型
        model = None
        try:
            model = config.agents.defaults.model
        except AttributeError:
            pass
        
        if provider:
            api_key = provider.api_key or None
            api_base = provider.api_base or None
            
            # 檢查是否為佔位符
            if api_key and api_key.startswith("sk-YOUR"):
                api_key = None
            
            if api_key:
                logger.debug(f"✅ PageClassifier 從 config 讀取: model={model}")
                return api_key, api_base, model
    except Exception as e:
        logger.warning(f"⚠️ PageClassifier 無法從 config.json 載入配置: {e}")
    
    return None, None, None


class PageClassifier:
    """
    LLM 智能頁面路由器
    
    使用 gpt-4o-mini 進行語義分析，自動識別包含目標數據的頁面。
    完全消除 hardcode keywords 的需求。
    """
    
    def __init__(
        self,
        api_key: str = None,
        api_base: str = None,
        model: str = None
    ):
        """
        初始化
        
        Args:
            api_key: API Key (優先使用參數，其次從 config.json 讀取)
            api_base: API Base URL
            model: LLM 模型名稱 (優先使用參數，其次從 config.json 讀取)
        """
        # 優先順序：參數 > config.json
        if not api_key or not api_base or not model:
            config_key, config_base, config_model = _get_config_api_credentials()
            api_key = api_key or config_key
            api_base = api_base or config_base
            model = model or config_model
        
        # 最後嘗試環境變數作為 fallback
        self.api_key = api_key or os.getenv("CUSTOM_API_KEY") or os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.api_base = api_base or os.getenv("CUSTOM_API_BASE") or os.getenv("OPENAI_API_BASE")
        self.model = model  # 不使用硬編碼 fallback
        self.client = None
        
        if not self.api_key:
            logger.warning("⚠️ PageClassifier: 未配置有效的 API Key")
        if not self.model:
            raise ValueError("❌ PageClassifier: model 未配置！請在 config.json 的 provider 中設定 model")
        
        logger.info(f"✅ PageClassifier 初始化: model={self.model}")
    
    def _get_client(self) -> Optional[AsyncOpenAI]:
        """獲取 OpenAI 客戶端"""
        if not OPENAI_SDK_AVAILABLE:
            logger.error("❌ OpenAI SDK 未安裝")
            return None
        
        if not self.api_key or self.api_key.startswith("sk-YOUR"):
            logger.error("❌ PageClassifier: 未配置有效的 API Key")
            return None
        
        if not self.client:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_base
            )
        
        return self.client
    
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
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": compressed_context}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # 確保所有目標類型都有結果
            for dt in target_data_types:
                if dt not in result:
                    result[dt] = []
            
            logger.info(f"🎯 LLM 路由結果: {result}")
            
            # 記錄 Token 使用情況
            if hasattr(response, 'usage') and response.usage:
                logger.debug(f"   Token 使用: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}")
            
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
    pdf_path: str,
    api_key: str = None,
    api_base: str = None
) -> List[int]:
    """
    便捷函數：找出包含 Revenue Breakdown 的頁面
    
    Args:
        pdf_path: PDF 路徑
        api_key: API Key
        api_base: API Base URL
        
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
    classifier = PageClassifier(api_key=api_key, api_base=api_base)
    result = await classifier.find_candidate_pages(pages_text, ["revenue_breakdown"])
    
    return result.get("revenue_breakdown", [])