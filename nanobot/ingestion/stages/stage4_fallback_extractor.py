"""
Stage 4 Fallback Extractor - 終極包底提取器

當 Stage 4 Agentic Extractor 未能提取數據時，
使用專門的 LLM Prompt 直接提取並寫入數據庫。

功能：
1. extract_revenue_breakdown - 提取收入分解（按地區/業務）
2. extract_shareholding - 提取股東結構
"""

import json
import re
from typing import Dict, Any, List
from loguru import logger

from nanobot.core.llm_core import llm_core


class Stage4FallbackExtractor:
    """終極包底提取器 - 當 Agent 未能提取時的最後防線"""
    
    @classmethod
    async def extract_revenue_breakdown(
        cls,
        artifacts: List[Dict[str, Any]],
        company_id: int,
        document_id: int,
        year: int,
        db_client
    ) -> Dict[str, Any]:
        """
        提取收入分解數據
        
        Args:
            artifacts: 所有 artifacts
            company_id: 公司 ID
            document_id: 文檔 ID
            year: 年份
            db_client: 數據庫客戶端
        
        Returns:
            {"status": "success/failed", "extracted_count": int, ...}
        """
        logger.info(f"🔄 Fallback: 提取 Revenue Breakdown (doc={document_id})")
        
        # 1. 準備內容（只取包含收入相關關鍵詞的 artifacts）
        relevant_content = []
        revenue_keywords = [
            'revenue', '收入', '營收', 'sales', '营业额',
            'geography', 'region', '地區', '亞太', '歐洲', '美洲',
            'segment', '業務', '分部', '零售', '港口'
        ]
        
        for artifact in artifacts:
            content = artifact.get("content", "") or ""
            if len(content) < 100:
                continue
            
            # 檢查是否包含收入相關關鍵詞
            content_lower = content.lower()
            if any(kw.lower() in content_lower for kw in revenue_keywords):
                relevant_content.append({
                    "page": artifact.get("page", artifact.get("page_num", "N/A")),
                    "type": artifact.get("type", "text"),
                    "content": content[:2000]  # 限制長度
                })
        
        if not relevant_content:
            logger.info("   ⚠️ Fallback: 沒有找到包含收入關鍵詞的內容")
            return {"status": "success", "extracted_count": 0, "reason": "no_relevant_content"}
        
        logger.info(f"   📝 找到 {len(relevant_content)} 個相關 artifacts")
        
        # 2. 構建 LLM Prompt
        content_text = "\n\n".join([
            f"=== Page {c['page']} ===\n{c['content']}"
            for c in relevant_content[:10]  # 限制 10 個區塊
        ])
        
        system_prompt = f"""你是一個財務數據提取專家。

任務：從以下文本中提取收入分解數據。

公司 ID: {company_id}
年份: {year}

收入分解是指：
- 按地區劃分（香港、歐洲、亞太、美洲等）
- 按業務劃分（零售、港口、基建等）

請返回 JSON 格式：
```json
{{
  "segments": [
    {{
      "segment_name": "Europe",
      "segment_type": "geography",
      "revenue_amount": 123456,
      "revenue_percentage": 25.5,
      "currency": "HKD"
    }}
  ]
}}
```

⚠️ 重要：
- segment_type 只可以是 'geography' 或 'business'
- 如果有金額和百分比，都必須填寫
- 如果有多個年份的數據，只提取 {year} 年的
"""
        
        user_message = f"請從以下內容提取收入分解數據：\n\n{content_text[:8000]}"
        
        # 3. 調用 LLM
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            response = await llm_core.chat(messages=messages)
            
            # 4. 解析響應
            segments = cls._parse_json_response(response)
            
            if not segments:
                logger.info("   ⚠️ Fallback: LLM 未返回有效數據")
                return {"status": "success", "extracted_count": 0, "reason": "no_parse_result"}
            
            # 5. 寫入數據庫
            inserted_count = await cls._insert_revenue_breakdown(
                db_client=db_client,
                company_id=company_id,
                year=year,
                document_id=document_id,
                segments=segments
            )
            
            logger.info(f"   ✅ Fallback: 成功寫入 {inserted_count} 條 revenue_breakdown")
            
            return {
                "status": "success",
                "extracted_count": inserted_count,
                "segments_found": len(segments)
            }
            
        except Exception as e:
            logger.warning(f"   ⚠️ Fallback Revenue Breakdown 失敗: {e}")
            return {"status": "failed", "error": str(e), "extracted_count": 0}
    
    @classmethod
    async def extract_shareholding(
        cls,
        artifacts: List[Dict[str, Any]],
        company_id: int,
        document_id: int,
        year: int,
        db_client
    ) -> Dict[str, Any]:
        """
        提取股東結構數據
        
        Args:
            artifacts: 所有 artifacts
            company_id: 公司 ID
            document_id: 文檔 ID
            year: 年份
            db_client: 數據庫客戶端
        
        Returns:
            {"status": "success/failed", "extracted_count": int, ...}
        """
        logger.info(f"🔄 Fallback: 提取 Shareholding (doc={document_id})")
        
        # 1. 準備內容（只取包含股東相關關鍵詞的 artifacts）
        relevant_content = []
        shareholder_keywords = [
            'shareholder', '股東', '持股', 'shares', '股份',
            'beneficial', '實益', 'trust', '信託', 'trustee',
            'controlling', '主要股東', 'substantial'
        ]
        
        for artifact in artifacts:
            content = artifact.get("content", "") or ""
            if len(content) < 100:
                continue
            
            content_lower = content.lower()
            if any(kw.lower() in content_lower for kw in shareholder_keywords):
                relevant_content.append({
                    "page": artifact.get("page", artifact.get("page_num", "N/A")),
                    "type": artifact.get("type", "text"),
                    "content": content[:2000]
                })
        
        if not relevant_content:
            logger.info("   ⚠️ Fallback: 沒有找到包含股東關鍵詞的內容")
            return {"status": "success", "extracted_count": 0, "reason": "no_relevant_content"}
        
        logger.info(f"   📝 找到 {len(relevant_content)} 個相關 artifacts")
        
        # 2. 構建 LLM Prompt
        content_text = "\n\n".join([
            f"=== Page {c['page']} ===\n{c['content']}"
            for c in relevant_content[:10]
        ])
        
        system_prompt = f"""你是一個財務數據提取專家。

任務：從以下文本中提取股東結構數據。

公司 ID: {company_id}
年份: {year}

股東結構包括：
- 主要股東名稱和持股比例
- 信託/託管人信息
- 機構投資者
- 控制權股東

請返回 JSON 格式：
```json
{{
  "shareholders": [
    {{
      "shareholder_name": "CKP Holdings",
      "shareholder_type": "corporate",
      "percentage": 25.5,
      "is_controlling": true,
      "is_institutional": false,
      "trust_name": null,
      "trustee_name": null
    }}
  ]
}}
```

⚠️ 重要：
- percentage 是持股百分比（如 25.5 代表 25.5%）
- shareholder_type 可以是 'individual', 'corporate', 'institutional'
- is_controlling 表示是否為控股股東
"""
        
        user_message = f"請從以下內容提取股東結構數據：\n\n{content_text[:8000]}"
        
        # 3. 調用 LLM
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            response = await llm_core.chat(messages=messages)
            
            # 4. 解析響應
            shareholders = cls._parse_json_response(response)
            
            if not shareholders:
                logger.info("   ⚠️ Fallback: LLM 未返回有效數據")
                return {"status": "success", "extracted_count": 0, "reason": "no_parse_result"}
            
            # 5. 寫入數據庫
            inserted_count = await cls._insert_shareholding(
                db_client=db_client,
                company_id=company_id,
                document_id=document_id,
                shareholders=shareholders
            )
            
            logger.info(f"   ✅ Fallback: 成功寫入 {inserted_count} 條 shareholding")
            
            return {
                "status": "success",
                "extracted_count": inserted_count,
                "shareholders_found": len(shareholders)
            }
            
        except Exception as e:
            logger.warning(f"   ⚠️ Fallback Shareholding 失敗: {e}")
            return {"status": "failed", "error": str(e), "extracted_count": 0}
    
    @staticmethod
    def _parse_json_response(response: str) -> List[Dict]:
        """解析 LLM 返回的 JSON"""
        try:
            # 嘗試從代碼塊中提取 JSON
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 嘗試直接解析整個響應
                json_str = response
            
            data = json.loads(json_str)
            
            # 檢查常見的包裝結構
            if isinstance(data, dict):
                for key in ['segments', 'shareholders', 'data', 'result']:
                    if key in data:
                        return data[key]
                # 如果是單一對象，包裝成列表
                return [data]
            
            if isinstance(data, list):
                return data
            
            return []
            
        except json.JSONDecodeError as e:
            logger.warning(f"   ⚠️ JSON 解析失敗: {e}")
            return []
    
    @staticmethod
    async def _insert_revenue_breakdown(
        db_client,
        company_id: int,
        year: int,
        document_id: int,
        segments: List[Dict]
    ) -> int:
        """寫入 revenue_breakdown 表"""
        inserted_count = 0
        
        async with db_client.connection() as conn:
            for seg in segments:
                try:
                    await conn.execute(
                        '''
                        INSERT INTO revenue_breakdown 
                        (company_id, year, segment_name, segment_type, revenue_amount, 
                         revenue_percentage, currency, source_document_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (company_id, year, segment_name, segment_type)
                        DO UPDATE SET 
                            revenue_amount = $5,
                            revenue_percentage = $6,
                            source_document_id = $8
                        ''',
                        company_id,
                        year,
                        seg.get("segment_name"),
                        seg.get("segment_type", "geography"),
                        seg.get("revenue_amount"),
                        seg.get("revenue_percentage"),
                        seg.get("currency", "HKD"),
                        document_id
                    )
                    inserted_count += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ 寫入 revenue_breakdown 失敗: {e}")
        
        return inserted_count
    
    @staticmethod
    async def _insert_shareholding(
        db_client,
        company_id: int,
        document_id: int,
        shareholders: List[Dict]
    ) -> int:
        """寫入 shareholding_structure 表 (v4.6: 移除 year 欄位)"""
        inserted_count = 0
        
        async with db_client.connection() as conn:
            for sh in shareholders:
                try:
                    await conn.execute(
                        '''
                        INSERT INTO shareholding_structure 
                        (company_id, shareholder_name, shareholder_type, 
                         shares_held, percentage, is_controlling, is_institutional,
                         trust_name, trustee_name, source_document_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (company_id, shareholder_name, source_document_id)
                        DO UPDATE SET 
                            percentage = $5,
                            is_controlling = $6,
                            shares_held = $4
                        ''',
                        company_id,
                        sh.get("shareholder_name"),
                        sh.get("shareholder_type", "corporate"),
                        sh.get("shares_held"),
                        sh.get("percentage"),
                        sh.get("is_controlling", False),
                        sh.get("is_institutional", False),
                        sh.get("trust_name"),
                        sh.get("trustee_name"),
                        document_id
                    )
                    inserted_count += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ 寫入 shareholding_structure 失敗: {e}")
        
        return inserted_count
