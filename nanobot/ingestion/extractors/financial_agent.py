"""
Financial Agent Module - LLM 審計師 (強制結構化版本)

負責調用 LLM 從 Markdown/文字中提取結構化財務數據。

改進：
1. 使用 lm-format-enforcer 強制結構化 JSON 輸出
2. 使用 json-repair 作為備選修復
3. 更健壯的 JSON 清理邏輯
4. 重試機制
5. 使用統一的 LLM 客戶端
"""

import os
import json
import re
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from loguru import logger

# 導入統一的 LLM 客戶端
from ..utils.llm_client import get_llm_client, get_llm_model

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
    """收入項目 (Schema v2.3)"""
    segment_name: str = Field(..., description="分類名稱，如 'Europe', 'Mainland China'")
    segment_type: Optional[str] = Field(None, description="分類類型，如 'geography', 'business'")
    revenue_percentage: Optional[float] = Field(None, description="百分比")
    revenue_amount: Optional[float] = Field(None, description="金額")
    currency: Optional[str] = Field(None, description="貨幣單位")


class RevenueBreakdownResponse(BaseModel):
    """收入分佈響應 (Schema v2.3)"""
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
    """高管項目 (Schema v2.3)"""
    name_en: str = Field(..., description="英文姓名")
    name_zh: Optional[str] = Field(None, description="中文姓名")
    position_title_en: Optional[str] = Field(None, description="職位名稱")
    role: Optional[str] = Field(None, description="簡化版角色，如 Chairman, CEO")
    board_role: Optional[str] = Field(None, description="董事角色，如 chairman, ceo, independent_director")
    committee_membership: Optional[List[str]] = Field(None, description="所屬委員會列表，如 ['audit', 'remuneration']")
    biography: Optional[str] = Field(None, description="簡歷")


class KeyPersonnelResponse(BaseModel):
    """高管響應"""
    items: List[KeyPersonnelItem] = Field(default_factory=list, description="高管列表")


# ===========================================
# 配置讀取
# ===========================================

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
    
    def __init__(self, max_retries: int = 2):
        """
        初始化
        
        Args:
            max_retries: 最大重試次數
        """
        # 使用統一的 LLM 客戶端
        self._client = None
        self._model = None
        self.max_retries = max_retries
        self.json_processor = JSONProcessor()
    
    def _get_client(self):
        """獲取 OpenAI 客戶端（延遲載入）"""
        if self._client is None:
            self._client = get_llm_client()
        return self._client
    
    def _get_model(self) -> str:
        """獲取 LLM 模型名稱"""
        if self._model is None:
            self._model = get_llm_model()
        return self._model
    
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
                    "model": self._get_model(),
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
        
        # 增強 prompt：強調 JSON 格式 (Schema v2.3)
        enhanced_system_prompt = f"""{system_prompt}

IMPORTANT: You MUST respond with valid JSON only. No markdown, no explanations, just pure JSON.

Expected format (Schema v2.3):
{{
  "items": [
    {{
      "segment_name": "Europe",
      "segment_type": "geography",
      "revenue_percentage": 15.0,
      "revenue_amount": 12345.67,
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
            # 🌟 檢查是否有新發現的關鍵字（持續學習）
            discovered_keyword = result.get("discovered_keyword")
            if discovered_keyword and isinstance(discovered_keyword, dict):
                keyword = discovered_keyword.get("keyword")
                reasoning = discovered_keyword.get("reasoning", "")
                
                if keyword:
                    # 🧠 註冊新關鍵字到知識庫
                    from ..utils.keyword_manager import KeywordManager
                    km = KeywordManager()
                    register_result = km.add_keyword(
                        category="revenue_breakdown",
                        keyword=keyword,
                        source="agent",
                        confidence="bronze",  # Agent 發現的關鍵字需要審核
                        reasoning=reasoning
                    )
                    
                    if register_result.get("success"):
                        logger.info(f"🧠 Agent 發現新關鍵字: '{keyword}' 已加入知識庫")
                    else:
                        logger.debug(f"   關鍵字 '{keyword}' 未加入: {register_result.get('reason')}")
            
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
        
        🔧 優化：專注於前兩頁文本，提高準確率
        
        Args:
            text_content: 文本內容（最好是前 1-2 頁的封面文本）
            
        Returns:
            Dict: 公司信息
        """
        from .prompts import get_prompt
        
        logger.info(f"🧠 正在從封面提取公司元數據...")
        
        system_prompt = get_prompt("company_info")
        
        # 🎯 優化後的 Prompt：強調這是封面文本，精準提取
        enhanced_system_prompt = f"""{system_prompt}

🎯 這是一份港股年報的封面與目錄頁文本。請精準提取以下 4 個核心資訊：

1. **stock_code**: 股票代碼（通常是 4-5 位數字，如 01093, 02359）
   - 必須是純數字，不要包含任何符號
   - 範例：00001, 00700, 02359

2. **year**: 這份財報的年份（如 2023, 2024）
   - 通常是財務年度結束年份

3. **name_en**: 公司英文名稱
   - 如果找不到，請填 null，不要猜測

4. **name_zh**: 公司中文名稱
   - 如果找不到，請填 null，不要猜測

⚠️ CRITICAL RULES:
- 如果找不到任何資訊，請填 null
- 不要從內容中「推測」或「聯想」
- stock_code 必須是純數字字符串

Expected JSON format:
{{
  "stock_code": "02359",
  "name_en": "Pharmaron Beijing Co., Ltd.",
  "name_zh": "康龍化成（北京）新藥技術股份有限公司",
  "industry": "Pharmaceuticals",
  "sector": "BioTech"
}}"""
        
        messages = [
            {"role": "system", "content": enhanced_system_prompt},
            {"role": "user", "content": text_content[:3000]}  # 🎯 縮小範圍：前兩頁通常 <3000 字
        ]
        
        result_text = await self._call_llm_with_retry(
            messages=messages,
            temperature=0.0,  # 🎯 零溫度：最高精確度
            response_format={"type": "json_object"}
        )
        
        if not result_text:
            return None
        
        result = self.json_processor.repair_and_parse(result_text)
        
        if result:
            try:
                validated = CompanyInfo(**result)
                logger.info(f"✅ 公司元數據提取成功: Stock={validated.stock_code}, Name={validated.name_en or validated.name_zh}")
                return validated.model_dump()
            except Exception as e:
                logger.warning(f"⚠ Schema 驗證失敗，返回原始數據: {e}")
                return result
        
        return None
    
    async def extract_company_metadata_from_cover(
        self,
        front_pages_text: str
    ) -> Optional[Dict[str, Any]]:
        """
        🎯 新增：專門從封面提取核心 Metadata（stock_code, year, names）
        
        這是精準版本，只處理封面文本，確保最高準確率。
        
        Args:
            front_pages_text: 前 1-2 頁的文本內容
            
        Returns:
            Dict: {stock_code, year, name_en, name_zh}
        """
        logger.info(f"🎯 從封面精準提取核心 Metadata...")
        
        # 🚀 添加调试：打印提取的文本长度和前 500 字符
        text_preview = front_pages_text[:500] if front_pages_text else "EMPTY"
        logger.debug(f"   📄 封面文本长度: {len(front_pages_text) if front_pages_text else 0}")
        logger.debug(f"   📄 封面文本预览: {text_preview}")
        
        # 🚀 添加调试：打印完整文本（帮助诊断问题）
        logger.info(f"   📄 完整封面文本:\n{front_pages_text}")
        
        prompt = """你是一個精準的文檔解析器。請從以下港股年報封面文本中提取 4 個核心資訊。

⚠️ 嚴格規則：
1. stock_code: 股票代碼（4-5 位純數字，如 02359）
2. year: 財報年份（如 2024）
3. name_en: 公司英文名（找不到填 null）
4. name_zh: 公司中文名（找不到填 null）

封面文本：
""" + front_pages_text[:3000] + """

只回傳 JSON，不要解釋：
{""" 
        
        messages = [
            {"role": "user", "content": prompt}
        ]
        
        result_text = await self._call_llm_with_retry(
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        # 🚀 添加调试：打印 LLM 原始响应
        logger.debug(f"   🤖 LLM 原始响应: {result_text[:500] if result_text else 'None'}")
        
        if not result_text:
            logger.warning("⚠️ 封面元數據提取失敗：LLM 未返回结果")
            return None
        
        result = self.json_processor.repair_and_parse(result_text)
        
        if result:
            stock_code = result.get("stock_code")
            year = result.get("year")
            
            # 🎯 驗證：stock_code 必須是純數字
            if stock_code:
                # 清理：移除非數字字符
                stock_code = re.sub(r'[^\d]', '', str(stock_code))
                if len(stock_code) < 4:
                    logger.warning(f"⚠️ 股票代碼格式異常: {stock_code}")
                    result["stock_code"] = None
                else:
                    # 標準化：補零至 5 位
                    result["stock_code"] = stock_code.zfill(5)
            
            # 🎯 驗證：year 必須是合理的年份
            if year:
                try:
                    year_int = int(year)
                    if 2000 <= year_int <= 2030:
                        result["year"] = year_int
                    else:
                        logger.warning(f"⚠️ 年份格式異常: {year}")
                        result["year"] = None
                except:
                    result["year"] = None
            
            logger.info(f"✅ 封面元數據: Stock={result.get('stock_code')}, Year={result.get('year')}")
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

Expected format (Schema v2.3):
{{
  "items": [
    {{
      "name_en": "John Doe",
      "name_zh": "張三",
      "position_title_en": "Executive Director",
      "role": "CEO",
      "board_role": "ceo",
      "committee_membership": ["audit", "remuneration"],
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
            # ✅ 正确写法：使用 _get_model() 方法
            vision_model = self._get_model().replace("qwen3.5", "qwen-vl").replace("gpt-4", "gpt-4-vision")
            
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
    
    async def extract_company_metadata_with_vision(
        self,
        base64_image: str
    ) -> Optional[Dict[str, Any]]:
        """
        🎯 專門從封面圖片提取 Metadata（Vision 版本）
        
        這是替代 FastParser 的核心方法：
        - 直接將 PDF 封面轉成圖片
        - 使用 Vision LLM 同時執行 OCR + 語義提取
        - 適用於港股年報封面（文字常被向量化或嵌入圖片）
        
        Args:
            base64_image: Base64 編碼的封面圖片
            
        Returns:
            Dict: {stock_code, year, name_en, name_zh}
        """
        client = self._get_client()
        if not client:
            return None
        
        try:
            # 🔧 Vision 模型映射（根據不同 provider 切換）
            # 常見的映射規則：
            # - qwen3.5 → qwen-vl-max 或 qwen-vl-plus
            # - gpt-4 → gpt-4-vision-preview 或 gpt-4o
            # - glm-4 → glm-4v
            vision_model = self._get_model()
            
            # 嘗試映射到 Vision 模型
            if "qwen" in vision_model.lower():
                # Qwen 系列：嘗試切換到 VL 模型
                if "qwen3" in vision_model.lower():
                    vision_model = vision_model.replace("qwen3", "qwen-vl")
                elif "qwen2" in vision_model.lower():
                    vision_model = vision_model.replace("qwen2", "qwen-vl")
                else:
                    vision_model = "qwen-vl-max"
            elif "gpt-4" in vision_model.lower() and "vision" not in vision_model.lower():
                # OpenAI GPT-4 系列
                if "gpt-4o-mini" in vision_model.lower():
                    vision_model = "gpt-4o"  # mini 不支持 vision，切換到 4o
                elif "gpt-4-turbo" in vision_model.lower():
                    vision_model = "gpt-4-turbo"  # turbo 本身支持 vision
                else:
                    vision_model = "gpt-4-vision-preview"
            elif "glm" in vision_model.lower():
                # GLM 系列
                if "glm-4" in vision_model.lower():
                    vision_model = "glm-4v"
            
            logger.info(f"👁️ 正在使用 Vision LLM ({vision_model}) 扫描封面...")
            
            prompt = """你是一個精準的財報數據提取專家。請從這張港股年報封面圖片中提取 4 個核心資訊。

⚠️ 嚴格規則：
1. stock_code: 股票代碼（通常是 4-5 位純數字，例如 02359, 00001。不要包含多餘文字）
2. year: 財報年份（如 2023, 2024）
3. name_en: 公司英文名（找不到填 null）
4. name_zh: 公司中文名（找不到填 null）

請僅回傳 JSON 格式，不要包含任何其他解釋：
{
  "stock_code": "00001",
  "year": 2023,
  "name_en": "CK Hutchison Holdings Limited",
  "name_zh": "長和"
}"""
            
            response = await client.chat.completions.create(
                model=vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.0
            )
            
            result_text = response.choices[0].message.content
            logger.debug(f"   🤖 Vision LLM 原始響應: {result_text[:300] if result_text else 'None'}...")
            
            result = self.json_processor.repair_and_parse(result_text)
            
            if result:
                stock_code = result.get("stock_code")
                year = result.get("year")
                
                # 🎯 驗證：stock_code 必須是純數字
                if stock_code:
                    stock_code = re.sub(r'[^\d]', '', str(stock_code))
                    if len(stock_code) < 4:
                        logger.warning(f"⚠️ 股票代碼格式異常: {stock_code}")
                        result["stock_code"] = None
                    else:
                        result["stock_code"] = stock_code.zfill(5)
                
                # 🎯 驗證：year 必須是合理的年份
                if year:
                    try:
                        year_int = int(year)
                        if 2000 <= year_int <= 2030:
                            result["year"] = year_int
                        else:
                            logger.warning(f"⚠️ 年份格式異常: {year}")
                            result["year"] = None
                    except:
                        result["year"] = None
                
                logger.info(f"✅ 封面 Vision 提取成功: Stock={result.get('stock_code')}, Year={result.get('year')}")
                return result
            
            logger.error("❌ 封面 Vision 提取失敗：JSON 解析失敗")
            return None
            
        except Exception as e:
            logger.error(f"❌ 封面 Vision 提取失敗: {e}")
            return None


# ===========================================
# 便捷函數
# ===========================================

async def extract_revenue_breakdown_simple(
    markdown_content: str,
) -> Optional[Dict[str, Any]]:
    """
    簡單的 Revenue Breakdown 提取入口
    
    🌟 重构后：FinancialAgent 使用统一的 get_llm_client()，不再需要传入 API 参数
    
    Args:
        markdown_content: Markdown 文本
        
    Returns:
        Dict: 提取的數據
    """
    agent = FinancialAgent()
    return await agent.extract_revenue_breakdown(markdown_content)


async def extract_company_info_simple(
    text_content: str,
) -> Optional[Dict[str, Any]]:
    """
    簡單的公司信息提取入口
    
    🌟 重构后：FinancialAgent 使用统一的 get_llm_client()，不再需要传入 API 参数
    """
    agent = FinancialAgent()
    return await agent.extract_company_info(text_content)