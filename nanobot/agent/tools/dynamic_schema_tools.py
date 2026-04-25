"""
Dynamic Schema Tools - Just-in-Time Schema Discovery

這些 Tools 讓 Agent 能夠：
1. 動態發現 JSONB 欄位中的所有 Keys
2. 將隱藏屬性注入到查詢 Prompt 中
3. 支持 PostgreSQL JSONB 查詢語法

設計理念：
- 不再需要人工維護 JSON Key 清單
- Agent 在查詢前自動掃描資料庫
- 實現真正的全動態閉環

用於：
- DirectSQLTool 的 Schema 發現
- SemanticSearchTool 的內容檢索
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from loguru import logger

from nanobot.agent.tools.base import Tool


class GetDynamicKeysTool(Tool):
    """
    [Tool] 獲取所有 JSONB 動態屬性的 Keys
    
    🌟 Schema v2.3: 动态属性存储在 companies.extra_data
    
    功能：
    - 扫描 companies 表的 extra_data 欄位
    - 返回所有出現過的 Key
    - 用于 Just-in-Time Schema Injection
    """
    
    @property
    def name(self) -> str:
        return "get_dynamic_keys"
    
    @property
    def description(self) -> str:
        return (
            "Discover all dynamic attribute keys stored in JSONB columns. "
            "Use this before generating SQL queries that might need to access hidden attributes. "
            "🌟 Schema v2.3: Dynamic attributes are stored in companies.extra_data."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Table to scan for JSONB keys (default: 'companies')",
                    "default": "companies"
                },
                "column_name": {
                    "type": "string", 
                    "description": "JSONB column to scan (default: 'extra_data')",
                    "default": "extra_data"
                }
            }
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(
        self,
        table_name: str = "companies",  # 🌟 Schema v2.3: 改為 companies
        column_name: str = "extra_data"  # 🌟 Schema v2.3: 改為 extra_data
    ) -> str:
        """執行動態 Key 發現"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 方法 1: 使用 jsonb_object_keys 獲取所有 Keys
                keys_rows = await conn.fetch(
                    f"""
                    SELECT DISTINCT jsonb_object_keys({column_name}) AS key
                    FROM {table_name}
                    WHERE {column_name} IS NOT NULL 
                    AND {column_name} != '{{}}'::jsonb
                    ORDER BY key
                    """
                )
                
                discovered_keys = [row["key"] for row in keys_rows]
                
                # 方法 2: 獲取每個 Key 的樣本值（用於理解數據類型）
                sample_values = {}
                for key in discovered_keys[:10]:  # 只取前 10 個作為樣本
                    sample = await conn.fetchrow(
                        f"""
                        SELECT {column_name}->>'{key}' AS sample_value
                        FROM {table_name}
                        WHERE {column_name}->>'{key}' IS NOT NULL
                        LIMIT 1
                        """
                    )
                    if sample:
                        sample_values[key] = sample["sample_value"]
                
                # 方法 3: 獲取使用頻率
                frequency_rows = await conn.fetch(
                    f"""
                    SELECT jsonb_object_keys({column_name}) AS key, COUNT(*) as count
                    FROM {table_name}
                    WHERE {column_name} IS NOT NULL
                    GROUP BY jsonb_object_keys({column_name})
                    ORDER BY count DESC
                    LIMIT 20
                    """
                )
                
                key_frequency = {row["key"]: row["count"] for row in frequency_rows}
                
                result = {
                    "discovered_keys": discovered_keys,
                    "total_keys": len(discovered_keys),
                    "sample_values": sample_values,
                    "key_frequency": key_frequency,
                    "query_hint": f"""
📌 SQL Query Hint (Schema v2.3):
當查詢動態屬性時，請使用 PostgreSQL JSONB 語法：

-- 提取單一值 (companies.extra_data)
SELECT extra_data->>'{discovered_keys[0] if discovered_keys else 'key_name'}' 
FROM companies;

-- 查询关联公司（JOIN documents）
SELECT c.name_en, c.extra_data->>'index_theme' 
FROM companies c
JOIN documents d ON d.owner_company_id = c.id;

-- 檢查 Key 是否存在
SELECT * FROM companies 
WHERE extra_data ? 'key_name';
"""
                }
                
                logger.info(f"🔍 發現 {len(discovered_keys)} 個動態屬性 Keys")
                
                return json.dumps(result, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"❌ 獲取動態 Keys 失敗: {e}")
            return json.dumps({"error": str(e), "discovered_keys": []})
        finally:
            await db.close()


class GetJSONBSchemaTool(Tool):
    """
    [Tool] 獲取完整的 JSONB Schema 信息
    
    功能：
    - 掃描所有 JSONB 欄位
    - 分析數據類型
    - 生成 Vanna 可用的 Schema 信息
    """
    
    @property
    def name(self) -> str:
        return "get_jsonb_schema"
    
    @property
    def description(self) -> str:
        return (
            "Get complete schema information for all JSONB columns. "
            "This includes data types, sample values, and usage statistics. "
            "Use this to understand what hidden attributes are available for querying."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_samples": {
                    "type": "boolean",
                    "description": "Include sample values for each key",
                    "default": True
                }
            }
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(self, include_samples: bool = True) -> str:
        """執行完整的 JSONB Schema 分析"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 獲取所有 JSONB 欄位
                jsonb_columns = await conn.fetch(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE data_type = 'jsonb'
                    AND table_schema = 'public'
                    """
                )
                
                schema_info = {}
                
                for col in jsonb_columns:
                    table = col["table_name"]
                    column = col["column_name"]
                    
                    # 獲取 Keys
                    keys_rows = await conn.fetch(
                        f"""
                        SELECT DISTINCT jsonb_object_keys({column}) AS key
                        FROM {table}
                        WHERE {column} IS NOT NULL
                        """
                    )
                    
                    keys = [row["key"] for row in keys_rows]
                    
                    schema_info[f"{table}.{column}"] = {
                        "keys": keys,
                        "key_count": len(keys)
                    }
                    
                    if include_samples and keys:
                        # 獲取樣本數據
                        sample = await conn.fetchrow(
                            f"""
                            SELECT {column} as sample
                            FROM {table}
                            WHERE {column} IS NOT NULL
                            LIMIT 1
                            """
                        )
                        if sample:
                            schema_info[f"{table}.{column}"]["sample_data"] = sample["sample"]
                
                return json.dumps(schema_info, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"❌ JSONB Schema 分析失敗: {e}")
            return json.dumps({"error": str(e)})
        finally:
            await db.close()


class PrepareVannaPromptTool(Tool):
    """
    [⚠️ DEPRECATED 廢棄工具] 準備帶有動態 Schema 信息的 Prompt
    
    功能：
    - 自動注入動態 Keys 到 Prompt
    - 添加 JSONB 查詢語法提示
    
    ⚠️ 注意：已被 DirectSQLTool 取代，不再需要 Vanna 預訓練
    """
    
    @property
    def name(self) -> str:
        return "prepare_vanna_prompt"
    
    @property
    def description(self) -> str:
        return (
            "[DEPRECATED] Prepare a prompt with dynamic schema information. "
            "⚠️ This tool is deprecated. Use DirectSQLTool with get_dynamic_keys instead. "
            "Agent can write SQL directly without Vanna pre-training."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_question": {
                    "type": "string",
                    "description": "[DEPRECATED] The user's natural language question"
                },
                "additional_context": {
                    "type": "string", 
                    "description": "[DEPRECATED] Additional context to include"
                }
            },
            "required": ["user_question"]
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    @property
    def deprecated(self) -> bool:
        return True  # 🌟 標記為廢棄
    
    async def execute(
        self,
        user_question: str,
        additional_context: str = ""
    ) -> str:
        """準備帶有動態 Schema 的 Vanna Prompt"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 🌟 Schema v2.3: 获取 companies.extra_data 的动态 Keys
                keys_rows = await conn.fetch(
                    """
                    SELECT DISTINCT jsonb_object_keys(extra_data) AS key
                    FROM companies
                    WHERE extra_data IS NOT NULL
                    """
                )
                
                dynamic_keys = [row["key"] for row in keys_rows]
                
                # 🌟 Schema v2.3: 获取 ai_extracted_industries 的樣本 (document_companies)
                industry_samples = await conn.fetch(
                    """
                    SELECT DISTINCT jsonb_array_elements_text(extracted_industries) AS industry
                    FROM document_companies
                    WHERE extracted_industries IS NOT NULL
                    LIMIT 20
                    """
                )
                
                industries = [row["industry"] for row in industry_samples]
                
                # 構建增強 Prompt (Schema v2.3)
                enhanced_prompt = f"""
用戶問題: {user_question}

📌 重要：資料庫 Schema v2.3 (動態屬性存儲在 JSONB 欄位中):

**companies 表動態屬性 (extra_data):**
{json.dumps(dynamic_keys, indent=2, ensure_ascii=False)}

**document_companies 表 AI 提取行業 (extracted_industries):**
{json.dumps(industries, indent=2, ensure_ascii=False)}

**PostgreSQL JSONB 查詢語法提示 (Schema v2.3):**
```sql
-- 提取動態屬性值 (companies.extra_data)
SELECT extra_data->>'key_name' FROM companies;

-- 查询关联公司（JOIN documents）
SELECT c.name_en, c.extra_data->>'index_theme', d.filename
FROM companies c
JOIN documents d ON d.owner_company_id = c.id;

-- 查询 JSON 数组中的行业值 (document_companies)
SELECT * FROM document_companies 
WHERE extracted_industries ? 'Biotech';

-- 檢查 Key 是否存在
SELECT * FROM companies WHERE extra_data ? 'key_name';
```

{additional_context}

請根據以上信息生成正確的 SQL 查詢。
"""
                
                return enhanced_prompt
                
        except Exception as e:
            logger.error(f"❌ 準備 Vanna Prompt 失敗: {e}")
            return f"用戶問題: {user_question}\n\n(無法獲取動態 Schema 信息)"
        finally:
            await db.close()


# ============================================================
# Tool 註冊函數
# ============================================================

def register_dynamic_schema_tools(registry) -> None:
    """
    註冊所有動態 Schema Tools
    
    Usage:
        from nanobot.agent.tools.dynamic_schema_tools import register_dynamic_schema_tools
        register_dynamic_schema_tools(agent_loop.tools)
    """
    registry.register(GetDynamicKeysTool())
    registry.register(GetJSONBSchemaTool())
    registry.register(PrepareVannaPromptTool())
    
    logger.info("✅ Registered 3 dynamic schema tools: get_dynamic_keys, get_jsonb_schema, prepare_vanna_prompt")