"""
Financial Agent Module - LLM 審計師

負責調用 LLM 從 Markdown/文字中提取結構化財務數據。
"""

import os
import json
from typing import Optional, Dict, Any
from loguru import logger

# OpenAI SDK
try:
    from openai import AsyncOpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    logger.warning("⚠️ OpenAI SDK 未安裝")


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


class FinancialAgent:
    """
    Financial Agent - LLM 審計師
    
    負責從非結構化文本中提取結構化財務數據。
    """
    
    def __init__(
        self,
        api_key: str = None,
        api_base: str = None,
        model: str = "qwen3.5-plus"
    ):
        """
        初始化
        
        Args:
            api_key: API Key (優先使用參數，其次從 config.json 讀取)
            api_base: API Base URL
            model: LLM 模型名稱
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
    
    async def extract_revenue_breakdown(
        self,
        markdown_content: str
    ) -> Optional[Dict[str, Any]]:
        """
        從 Markdown 中提取 Revenue Breakdown 數據
        
        Args:
            markdown_content: Markdown 文本
            
        Returns:
            Dict: 提取的結構化數據
        """
        from .prompts import get_prompt
        
        client = self._get_client()
        if not client:
            return None
        
        try:
            logger.info(f"🧠 審計師 Agent 正在提取 Revenue Breakdown...")
            
            system_prompt = get_prompt("revenue_breakdown")
            
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": markdown_content}
                ],
                temperature=0.0
            )
            
            result_text = response.choices[0].message.content
            
            # 清理可能的 Markdown 標記
            result_text = self._clean_json_response(result_text)
            
            # 解析 JSON
            try:
                result_json = json.loads(result_text.strip())
                logger.info(f"✅ JSON 提取成功: {list(result_json.keys())}")
                return result_json
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 解析失敗: {e}")
                logger.error(f"   原始返回: {result_text[:500]}")
                return None
            
        except Exception as e:
            logger.error(f"❌ LLM 提取失敗: {e}")
            return None
    
    async def extract_company_info(
        self,
        text_content: str
    ) -> Optional[Dict[str, Any]]:
        """
        從文本中提取公司信息
        
        Args:
            text_content: 文本內容
            
        Returns:
            Dict: 公司信息
        """
        from .prompts import get_prompt
        
        client = self._get_client()
        if not client:
            return None
        
        try:
            logger.info(f"🧠 正在提取公司信息...")
            
            system_prompt = get_prompt("company_info")
            
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text_content}
                ],
                temperature=0.0
            )
            
            result_text = response.choices[0].message.content
            result_text = self._clean_json_response(result_text)
            
            try:
                result_json = json.loads(result_text.strip())
                logger.info(f"✅ 公司信息提取成功: {result_json.get('name_en', 'N/A')}")
                return result_json
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 解析失敗: {e}")
                return None
            
        except Exception as e:
            logger.error(f"❌ 公司信息提取失敗: {e}")
            return None
    
    async def extract_with_vision(
        self,
        base64_image: str,
        extraction_type: str = "revenue_breakdown"
    ) -> Optional[Dict[str, Any]]:
        """
        直接從圖片中提取數據（一步到位）
        
        Args:
            base64_image: Base64 編碼的圖片
            extraction_type: 提取類型
            
        Returns:
            Dict: 提取的數據
        """
        from .prompts import get_prompt
        
        client = self._get_client()
        if not client:
            return None
        
        try:
            prompt_key = f"direct_{extraction_type}_vision" if extraction_type == "revenue" else "financial_table"
            system_prompt = get_prompt(prompt_key) or get_prompt("direct_revenue_vision")
            
            logger.info(f"🧠 正在使用 Vision LLM 提取 {extraction_type}...")
            
            response = await client.chat.completions.create(
                model=self.model.replace("qwen3.5", "qwen-vl"),  # 切換到 Vision 模型
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
                                "text": f"請提取這張圖片中的 {extraction_type} 數據。"
                            }
                        ]
                    }
                ],
                temperature=0.0
            )
            
            result_text = response.choices[0].message.content
            result_text = self._clean_json_response(result_text)
            
            try:
                return json.loads(result_text.strip())
            except json.JSONDecodeError:
                logger.error(f"❌ JSON 解析失敗")
                return None
            
        except Exception as e:
            logger.error(f"❌ Vision 提取失敗: {e}")
            return None
    
    @staticmethod
    def _clean_json_response(text: str) -> str:
        """清理 JSON 響應中的 Markdown 標記"""
        if not text:
            return text
        
        text = text.strip()
        
        # 移除 Markdown 代碼塊標記
        if text.startswith("```"):
            lines = text.split("\n")
            # 移除第一行的 ```json 或 ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            # 移除最後一行的 ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        
        return text.strip()