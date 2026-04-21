"""
統一工具註冊模組 (修復版)

修復內容：
1. 添加 VannaSQLTool Wrapper
2. 移除不存在的 document_tools 导入
3. 确保所有工具正确注册

Usage:
    from nanobot.agent.tools.register_all_fixed import register_all_tools
    register_all_tools(agent_loop.tools)
"""

from __future__ import annotations

from loguru import logger
from typing import Any


def register_all_tools(registry) -> None:
    """
    註冊所有可用工具
    
    Args:
        registry: Agent 的 Tool Registry (通常來自 AgentLoop.tools)
    """
    
    # ============================================================
    # 1. 註冊攝入工具 (智能寫入)
    # ============================================================
    try:
        from nanobot.agent.tools.db_ingestion_tools import (
            GetDBSchemaTool,
            SmartInsertDocumentTool,
            UpdateDocumentStatusTool,
            UpdateDynamicAttributesTool,
            CreateReviewRecordTool
        )
        registry.register(GetDBSchemaTool())
        registry.register(SmartInsertDocumentTool())
        registry.register(UpdateDocumentStatusTool())
        registry.register(UpdateDynamicAttributesTool())
        registry.register(CreateReviewRecordTool())
        logger.info("✅ Registered ingestion tools")
    except ImportError as e:
        logger.warning(f"⚠️ Failed to import db_ingestion_tools: {e}")
    
    # ============================================================
    # 2. 註冊動態 Schema 工具 (Just-in-Time Schema Injection)
    # ============================================================
    try:
        from nanobot.agent.tools.dynamic_schema_tools import (
            GetDynamicKeysTool,
            GetJSONBSchemaTool,
            PrepareVannaPromptTool
        )
        registry.register(GetDynamicKeysTool())
        registry.register(GetJSONBSchemaTool())
        registry.register(PrepareVannaPromptTool())
        logger.info("✅ Registered dynamic schema tools")
    except ImportError as e:
        logger.warning(f"⚠️ Failed to import dynamic_schema_tools: {e}")
    
    # ============================================================
    # 3. 註冊 Vanna 工具 (Text-to-SQL) 🌟 使用新的 Tool Wrapper
    # ============================================================
    try:
        from nanobot.agent.tools.vanna_tool import VannaQueryTool
        registry.register(VannaQueryTool())
        logger.info("✅ Registered VannaQueryTool")
        
    except ImportError as e:
        logger.warning(f"⚠️ Failed to import vanna_tool: {e}")
    
    # ============================================================
    # 4. 註冊多模態 RAG 工具 (跨模態圖文關聯) 🌟 使用新的 Tool Wrapper
    # ============================================================
    try:
        from nanobot.agent.tools.multimodal_rag import (
            GetChartContextTool,
            FindChartByFigureNumberTool,
            AssembleMultimodalPromptTool
        )
        registry.register(GetChartContextTool())
        registry.register(FindChartByFigureNumberTool())
        registry.register(AssembleMultimodalPromptTool())
        
        logger.info("✅ Registered multimodal RAG tools (cross-modal retrieval)")
        
    except ImportError as e:
        logger.warning(f"⚠️ Failed to import multimodal_rag: {e}")
    
    # ============================================================
    # 5. 註冊財務分析工具 (移除不存在的 document_tools)
    # ============================================================
    try:
        from nanobot.agent.tools.base import Tool
        
        class QueryFinancialDatabaseTool(Tool):
            """
            [Tool] 執行 SQL 查詢獲取精確數據
            """
            
            @property
            def name(self) -> str:
                return "query_financial_database"
            
            @property
            def description(self) -> str:
                return (
                    "Execute SQL queries against the financial database for exact numbers. "
                    "Use for: exact values, rankings, trends, math operations. "
                    "NEVER approximate - database gives exact values."
                )
            
            @property
            def parameters(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "SQL query string"
                        }
                    },
                    "required": ["sql"]
                }
            
            @property
            def read_only(self) -> bool:
                return True
            
            async def execute(self, sql: str) -> str:
                import json
                from nanobot.agent.tools.financial import FinancialTools
                
                tools = FinancialTools()
                result = tools.query_database(sql)
                
                if result.success:
                    response = {
                        "row_count": len(result.data),
                        "results": result.data[:20],
                        "citations": result.citations
                    }
                else:
                    response = {"error": result.message}
                
                return json.dumps(response, ensure_ascii=False, indent=2)
        
        class SearchDocumentsTool(Tool):
            """
            [Tool] 搜索文檔內容
            """
            
            @property
            def name(self) -> str:
                return "search_documents"
            
            @property
            def description(self) -> str:
                return (
                    "Search documents by text. "
                    "Use for: policies, strategies, commentary, explanations."
                )
            
            @property
            def parameters(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "company_name": {
                            "type": "string",
                            "description": "Optional company filter"
                        },
                        "year": {
                            "type": "integer",
                            "description": "Optional year filter"
                        }
                    },
                    "required": ["query"]
                }
            
            @property
            def read_only(self) -> bool:
                return True
            
            async def execute(
                self,
                query: str,
                company_name: str = None,
                year: int = None
            ) -> str:
                import json
                from nanobot.agent.tools.financial import FinancialTools
                
                tools = FinancialTools()
                result = tools.search_documents(query, company_name, year)
                
                if result.success:
                    response = {
                        "count": len(result.data),
                        "results": result.data[:10],
                        "citations": result.citations
                    }
                else:
                    response = {"error": result.message}
                
                return json.dumps(response, ensure_ascii=False, indent=2)
        
        class ResolveEntityTool(Tool):
            """
            [Tool] 解析公司名稱
            """
            
            @property
            def name(self) -> str:
                return "resolve_entity"
            
            @property
            def description(self) -> str:
                return (
                    "Resolve company name variations (CN/EN) to standard entity. "
                    "Use this before querying to handle name variations like '腾讯' vs 'Tencent'."
                )
            
            @property
            def parameters(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Company name (any language/variant)"
                        }
                    },
                    "required": ["name"]
                }
            
            @property
            def read_only(self) -> bool:
                return True
            
            async def execute(self, name: str) -> str:
                import json
                from nanobot.agent.tools.financial import FinancialTools
                
                tools = FinancialTools()
                result = tools.resolve_entity(name)
                
                if result.success:
                    return json.dumps(result.data, ensure_ascii=False, indent=2)
                else:
                    return f"Company not found: {name}"
        
        registry.register(QueryFinancialDatabaseTool())
        registry.register(SearchDocumentsTool())
        registry.register(ResolveEntityTool())
        
        logger.info("✅ Registered financial analysis tools")
        
    except ImportError as e:
        logger.warning(f"⚠️ Failed to import financial: {e}")
    
    # ============================================================
    # 6. 註冊基礎工具
    # ============================================================
    try:
        from nanobot.agent.tools.base import register_base_tools
        register_base_tools(registry)
        logger.info("✅ Registered base tools")
    except ImportError:
        logger.debug("No base tools to register")
    
    # ============================================================
    # 統計已註冊的工具
    # ============================================================
    total_tools = len(registry)
    logger.info(f"📊 Total registered tools: {total_tools}")
    
    return registry


def list_all_tools() -> dict:
    """
    列出所有可用工具的描述
    
    Returns:
        Dict of tool_name -> description
    """
    from nanobot.agent.tools.registry import ToolRegistry
    
    registry = ToolRegistry()
    register_all_tools(registry)
    
    return {
        tool.name: tool.description
        for tool in registry._tools.values()
    }


# ============================================================
# Quick Reference
# ============================================================

TOOL_CATEGORIES = {
    "ingestion": [
        "get_db_schema",
        "smart_insert_document",
        "update_document_status",
        "update_dynamic_attributes",
        "create_review_record"
    ],
    "dynamic_schema": [
        "get_dynamic_keys",
        "get_jsonb_schema",
        "prepare_vanna_prompt"
    ],
    "query": [
        "vanna_sql",  # 🌟 主要查詢工具
        "query_financial_database",
        "search_documents"
    ],
    "entity_resolution": [
        "resolve_entity"
    ],
    "multimodal_rag": [
        "get_chart_context",
        "find_chart_by_figure_number",
        "assemble_multimodal_prompt"
    ]
}


if __name__ == "__main__":
    print("Testing Tool Registration...\n")
    
    from nanobot.agent.tools.registry import ToolRegistry
    registry = ToolRegistry()
    register_all_tools(registry)
    
    print(f"Total tools: {len(registry)}")
    print("\nRegistered tools:")
    for name in sorted(registry.tool_names):
        print(f"  - {name}")
