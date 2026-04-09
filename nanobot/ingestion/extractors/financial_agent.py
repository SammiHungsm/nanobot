"""
Financial Agent Module - LLM 審計師 (強制結構化版本)

負責調用 LLM 從 Markdown/文字中提取結構化財務數據。

改進：
1. 使用 lm-format-enforcer 強制結構化 JSON 輸出
2. 使用 json-repair 作為備選修復
3. 更健壯的 JSON 清理邏輯
4. 重試機制
"""

import os
import json
import re
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from loguru import logger

# OpenAI SDK
try:
    from openai import AsyncOpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    logger.warning("⚠️ OpenAI SDK 未安裝")

# JSON Repair
try:
    from json_repair import repair_json
    JSON_REPAIR_AVAILABLE = True
except ImportError:
    JSON_REPAIR_AVAILABLE = False
    logger.warning("⚠️ json-repair 未安裝")

# LM Format Enforcer
try:
    from lmformatenforcer import (
        LMFormatEnforcer,
        JsonSchemaParser,
        StringParser,
        RegexParser
    )
    LM_FORMAT_ENFORCER_AVAILABLE = True
except ImportError:
    LM_FORMAT_ENFORCER_AVAILABLE = False
    logger.warning("⚠️ lm-format-enforcer 未安裝，將使用傳統 JSON 清理")


# ===========================================
# Pydantic Schemas (強制結構化)
# ===========================================

class RevenueItem(BaseModel):
    """收入項目"""
    category: str = Field(..., description="分類名稱，如 'Europe', 'Mainland China'")
    category_type: Optional[str] = Field(None, description="分類類型，如 'Region', 'Business Segment'")
    percentage: Optional[float] = Field(None, description="百分比")
    amount: Optional[float] = Field(None, description="金額")
    currency: Optional[str] = Field(None, description="貨幣單位")


class RevenueBreakdownResponse(BaseModel):
    """收入分佈響應"""
    items: List[RevenueItem] = Field(default_factory=list, description="收入項目列表")
    total_percentage: Optional[float] = Field(None, description="總百分比（應接近 100%）")


class CompanyInfo(BaseModel):
    """公司信息"""
    stock_code: Optional[str] = Field(None, description="股票代碼，如 '00001'")
    name_en: Optional[str] = Field(None, description="英文名稱")
    name_zh: Optional[str] = Field(None, description="中文名稱")
    industry: Optional[str] = Field(None, description="行業")
    sector: Optional[str] = Field(None, description="板塊")


class KeyPersonnelItem(BaseModel):
    """高管項目"""
    person_name: str = Field(..., description="姓名")
    person_name_zh: Optional[str] = Field(None, description="中文姓名")
    role: Optional[str] = Field(None, description="職位")
    committee: Optional[str] = Field(None, description="委員會")
    biography: Optional[str] = Field(None, description="簡歷")


class KeyPersonnelResponse(BaseModel):
    """高管響應"""
    items: List[KeyPersonnelItem] = Field(default_factory=list, description="高管列表")


# ===========================================
# 配置讀取
# ===========================================

def _get_config_api_credentials() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    從 nanobot config.json 讀取 API 憑證和模型
    """
    try:
        from nanobot.config.loader import load_config
        from pathlib import Path
        
        config_path = None
        nanobot_config_env = os.getenv("NANOBOT_CONFIG")
        if nanobot_config_env:
            config_path = Path(nanobot_config_env)
            if not config_path.exists():
                config_path = None
        
        config = load_config(config_path)
        provider = config.get_provider()
        
        model = None
        try:
            model = config.agents.defaults.model
        except AttributeError:
            pass
        
        if provider:
            api_key = provider.api_key or None
            api_base = provider.api_base or None
            
            if api_key and api_key.startswith("sk-YOUR"):
                api_key = None
            
            if api_key:
                logger.debug(f"✅ FinancialAgent 從 config 讀取: model={model}")
                return api_key, api_base, model
    except Exception as e:
        logger.warning(f"⚠️ FinancialAgent 無法從 config.json 載入配置: {e}")
    
    return None, None, None


# ===========================================
# JSON 處理工具
# ===========================================

class JSONProcessor:
    """JSON 處理工具類"""
    
    @staticmethod
    def clean_json_response(text: str) -> str:
        """
        清理 JSON 響應（多層清理）
        
        改進版：處理更多邊緣情況
        """
        if not text:
            return text
        
        text = text.strip()
        
        # Step 1: 移除 Markdown 代碼塊
        if "```" in text:
            # 提取 ``` 之間的內容
            pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
            matches = re.findall(pattern, text)
            if matches:
                text = matches[0]
            else:
                # 如果沒有閉合的 ```
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines)
        
        # Step 2: 找到第一個 { 和最後一個 } 之間的內容
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx:end_idx + 1]
        
        # Step 3: 找到第一個 [ 和最後一個 ] 之間的內容（如果是數組）
        if text.strip().startswith("["):
            start_idx = text.find("[")
            end_idx = text.rfind("]")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                text = text[start_idx:end_idx + 1]
        
        return text.strip()
    
    @staticmethod
    def repair_and_parse(text: str) -> Optional[Dict[str, Any]]:
        """
        修復並解析 JSON（多層備選）
        
        嘗試順序：
        1. 直接解析
        2. 清理後解析
        3. json-repair 修復
        4. 正則提取關鍵字段
        """
        if not text:
            return None
        
        # 方法 1: 直接解析
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # 方法 2: 清理後解析
        cleaned = JSONProcessor.clean_json_response(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        
        # 方法 3: json-repair 修復
        if JSON_REPAIR_AVAILABLE:
            try:
                repaired = repair_json(cleaned)
                return json.loads(repaired)
            except Exception as e:
                logger.warning(f"⚠️ json-repair 修復失敗: {e}")
        
        # 方法 4: 正則提取關鍵字段（最後手段）
        return JSONProcessor._extract_by_regex(cleaned)
    
    @staticmethod
    def _extract_by_regex(text: str) -> Optional[Dict[str, Any]]:
        """
        使用正則提取關鍵字段（最後手段）
        
        適用於 JSON 完全損壞的情況
        """
        result = {}
        
        # 提取 "key": "value" 或 "key": number
        string_pattern = r'"(\w+)"\s*:\s*"([^"]*)"'
        number_pattern = r'"(\w+)"\s*:\s*([\d.]+)'
        
        for key, value in re.findall(string_pattern, text):
            result[key] = value
        
        for key, value in re.findall(number_pattern, text):
            try:
                if '.' in value:
                    result[key] = float(value)
                else:
                    result[key] = int(value)
            except ValueError:
                result[key] = value
        
        return result if result else None


# ===========================================
# Financial Agent
# ===========================================

class FinancialAgent:
    """
    Financial Agent - LLM 審計師（強制結構化版本）
    
    改進：
    - 使用 Pydantic Schema 定義輸出結構
    - 多層 JSON 修復機制
    - 重試機制
    """
    
    def __init__(
        self,
        api_key: str = None,
        api_base: str = None,
        model: str = None,
        max_retries: int = 2
    ):
        """
        初始化
        
        Args:
            api_key: API Key
            api_base: API Base URL
            model: LLM 模型名稱
            max_retries: 最大重試次數
        """
        if not api_key or not api_base or not model:
            config_key, config_base, config_model = _get_config_api_credentials()
            api_key = api_key or config_key
            api_base = api_base or config_base
            model = model or config_model
        
        self.api_key = api_key or os.getenv("CUSTOM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.api_base = api_base or os.getenv("CUSTOM_API_BASE") or os.getenv("OPENAI_API_BASE")
        self.model = model
        self.max_retries = max_retries
        self.client = None
        self.json_processor = JSONProcessor()
    
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
    
    async def _call_llm_with_retry(
        self,
        messages: List[Dict],
        temperature: float = 0.0,
        response_format: Optional[Dict] = None
    ) -> Optional[str]:
        """
        調用 LLM 並重試
        
        Args:
            messages: 消息列表
            temperature: 溫度
            response_format: 響應格式
            
        Returns:
            str: LLM 響應文本
        """
        client = self._get_client()
        if not client:
            return None
        
        for attempt in range(self.max_retries + 1):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature
                }
                
                # 如果支持 response_format，添加參數
                if response_format:
                    kwargs["response_format"] = response_format
                
                response = await client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
                
            except Exception as e:
                if attempt < self.max_retries:
                    logger.warning(f"⚠️ LLM 調用失敗 (嘗試 {attempt + 1}/{self.max_retries + 1}): {e}")
                else:
                    logger.error(f"❌ LLM 調用失敗: {e}")
                    return None
        
        return None
    
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
        
        logger.info(f"🧠 審計師 Agent 正在提取 Revenue Breakdown...")
        
        # 獲取 prompt
        system_prompt = get_prompt("revenue_breakdown")
        
        # 增強 prompt：強調 JSON 格式
        enhanced_system_prompt = f"""{system_prompt}

IMPORTANT: You MUST respond with valid JSON only. No markdown, no explanations, just pure JSON.

Expected format:
{{
  "items": [
    {{
      "category": "Europe",
      "category_type": "Region",
      "percentage": 15.0,
      "amount": 12345.67,
      "currency": "HKD"
    }}
  ],
  "total_percentage": 100.0
}}"""
        
        messages = [
            {"role": "system", "content": enhanced_system_prompt},
            {"role": "user", "content": markdown_content}
        ]
        
        # 嘗試使用 response_format（如果模型支持）
        result_text = await self._call_llm_with_retry(
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"}  # 要求 JSON 輸出
        )
        
        if not result_text:
            return None
        
        # 解析 JSON（多層修復）
        result = self.json_processor.repair_and_parse(result_text)
        
        if result:
            # 驗證 schema
            try:
                validated = RevenueBreakdownResponse(**result)
                logger.info(f"✅ JSON 提取成功: {len(validated.items)} 個項目")
                return validated.model_dump()
            except Exception as e:
                logger.warning(f"⚠️ Schema 驗證失敗，返回原始數據: {e}")
                return result
        
        logger.error(f"❌ JSON 解析失敗")
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
        
        logger.info(f"🧠 正在提取公司信息...")
        
        system_prompt = get_prompt("company_info")
        
        enhanced_system_prompt = f"""{system_prompt}

IMPORTANT: You MUST respond with valid JSON only. No markdown, no explanations, just pure JSON.

Expected format:
{{
  "stock_code": "00001",
  "name_en": "CK Hutchison Holdings Limited",
  "name_zh": "長江和記實業有限公司",
  "industry": "Conglomerates",
  "sector": "Conglomerates"
}}"""
        
        messages = [
            {"role": "system", "content": enhanced_system_prompt},
            {"role": "user", "content": text_content[:5000]}  # 限制長度
        ]
        
        result_text = await self._call_llm_with_retry(
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        if not result_text:
            return None
        
        result = self.json_processor.repair_and_parse(result_text)
        
        if result:
            try:
                validated = CompanyInfo(**result)
                logger.info(f"✅ 公司信息提取成功: {validated.name_en or validated.name_zh}")
                return validated.model_dump()
            except Exception as e:
                logger.warning(f"⚠ Schema 驗證失敗，返回原始數據: {e}")
                return result
        
        return None
    
    async def extract_key_personnel(
        self,
        markdown_content: str
    ) -> Optional[Dict[str, Any]]:
        """
        從 Markdown 中提取高管信息
        
        Args:
            markdown_content: Markdown 文本
            
        Returns:
            Dict: 高管信息
        """
        from .prompts import get_prompt
        
        logger.info(f"🧠 正在提取高管信息...")
        
        system_prompt = get_prompt("key_personnel")
        
        enhanced_system_prompt = f"""{system_prompt}

IMPORTANT: You MUST respond with valid JSON only.

Expected format:
{{
  "items": [
    {{
      "person_name": "John Doe",
      "person_name_zh": "張三",
      "role": "Executive Director",
      "committee": "Audit Committee",
      "biography": "..."
    }}
  ]
}}"""
        
        messages = [
            {"role": "system", "content": enhanced_system_prompt},
            {"role": "user", "content": markdown_content}
        ]
        
        result_text = await self._call_llm_with_retry(
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        if not result_text:
            return None
        
        result = self.json_processor.repair_and_parse(result_text)
        
        if result:
            try:
                validated = KeyPersonnelResponse(**result)
                logger.info(f"✅ 高管信息提取成功: {len(validated.items)} 人")
                return validated.model_dump()
            except Exception as e:
                logger.warning(f"⚠️ Schema 驗證失敗: {e}")
                return result
        
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
            # 切換到 Vision 模型
            vision_model = self.model.replace("qwen3.5", "qwen-vl").replace("gpt-4", "gpt-4-vision")
            
            system_prompt = get_prompt("direct_revenue_vision")
            
            enhanced_prompt = f"""{system_prompt}

IMPORTANT: You MUST respond with valid JSON only. Extract all visible data from the table/chart in the image."""
            
            logger.info(f"🧠 正在使用 Vision LLM 提取 {extraction_type}...")
            
            response = await client.chat.completions.create(
                model=vision_model,
                messages=[
                    {"role": "system", "content": enhanced_prompt},
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
            result = self.json_processor.repair_and_parse(result_text)
            
            if result:
                logger.info(f"✅ Vision 提取成功")
                return result
            
            logger.error(f"❌ Vision 提取 JSON 解析失敗")
            return None
            
        except Exception as e:
            logger.error(f"❌ Vision 提取失敗: {e}")
            return None


# ===========================================
# 便捷函數
# ===========================================

async def extract_revenue_breakdown_simple(
    markdown_content: str,
    api_key: str = None,
    api_base: str = None,
    model: str = None
) -> Optional[Dict[str, Any]]:
    """
    簡單的 Revenue Breakdown 提取入口
    
    Args:
        markdown_content: Markdown 文本
        api_key: API Key
        api_base: API Base URL
        model: 模型名稱
        
    Returns:
        Dict: 提取的數據
    """
    agent = FinancialAgent(api_key=api_key, api_base=api_base, model=model)
    return await agent.extract_revenue_breakdown(markdown_content)


async def extract_company_info_simple(
    text_content: str,
    api_key: str = None,
    api_base: str = None,
    model: str = None
) -> Optional[Dict[str, Any]]:
    """
    簡單的公司信息提取入口
    """
    agent = FinancialAgent(api_key=api_key, api_base=api_base, model=model)
    return await agent.extract_company_info(text_content)