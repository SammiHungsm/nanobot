"""
統一工具註冊模組

將所有分散的工具集中註冊到 Agent 的 Tool Registry。

Usage:
    from nanobot.agent.tools.register_all import register_all_tools
    register_all_tools(agent_loop.tools)
"""

from __future__ import annotations

from loguru import logger


def register_all_tools(registry) -> None:
    """
    註冊所有可用工具
    
    Args:
        registry: Agent 的 Tool Registry (通常來自 AgentLoop.tools)
    """
    
    # 1. 註冊攝入工具 (智能寫入)
    try:
        from nanobot.agent.tools.db_ingestion_tools import register_ingestion_tools
        register_ingestion_tools(registry)
    except ImportError as e:
        logger.warning(f"⚠️ Failed to import db_ingestion_tools: {e}")
    
    # 2. 註冊動態 Schema 工具 (Just-in-Time Schema Injection)
    try:
        from nanobot.agent.tools.dynamic_schema_tools import register_dynamic_schema_tools
        register_dynamic_schema_tools(registry)
    except ImportError as e:
        logger.warning(f"⚠️ Failed to import dynamic_schema_tools: {e}")
    
    # 3. 註冊 Vanna 工具 (Text-to-SQL)
    try:
        from nanobot.agent.tools.vanna_tool import VannaSQLTool
        registry.register(VannaSQLTool())
        logger.info("✅ Registered VannaSQLTool")
    except ImportError as e:
        logger.warning(f"⚠️ Failed to import vanna_tool: {e}")
    
    # 4. 註内其他常用工具
    try:
        from nanobot.agent.tools.base import register_base_tools
        register_base_tools(registry)
    except ImportError:
        logger.debug("No base tools to register")
    
    # 5. 註冊文件處理工具
    try:
        from nanobot.agent.tools.document_tools import (
            ParsePDFTool,
            ExtractTablesTool,
            SearchChunksTool
        )
        registry.register(ParsePDFTool())
        registry.register(ExtractTablesTool())
        registry.register(SearchChunksTool())
        logger.info("✅ Registered document processing tools")
    except ImportError as e:
        logger.warning(f"⚠️ Failed to import document_tools: {e}")
    
    # 6. 註冊多模態 RAG 工具 (跨模態圖文關聯)
    try:
        from nanobot.agent.tools.multimodal_rag import MultimodalRAGTools
        from nanobot.agent.tools.base import Tool
        
        # 創建 Tool Wrapper
        class GetChartContextTool(Tool):
            """獲取圖表的跨頁解釋文字"""
            
            @property
            def name(self) -> str:
                return "get_chart_context"
            
            @property
            def description(self) -> str:
                return """
🎯 Runtime SQL JOIN - 解決「圖表在第 5 頁，解釋在第 50 頁」的跨頁斷裂問題

當用戶問「圖 3 的營收為什麼下跌？」時，使用此工具：
1. 先調用 find_chart_by_figure_number 獲取圖表的 artifact_id
2. 再調用此工具獲取跨頁解釋文字

Args:
    image_artifact_id: 圖表的 Artifact ID
    
Returns:
    str: 合併後的跨頁解釋文字
"""
            
            @property
            def parameters(self) -> dict:
                return {
                    "type": "object",
                    "properties": {
                        "image_artifact_id": {
                            "type": "string",
                            "description": "圖表的 Artifact ID"
                        }
                    },
                    "required": ["image_artifact_id"]
                }
            
            async def execute(self, image_artifact_id: str) -> str:
                from nanobot.agent.tools.multimodal_rag import get_chart_context
                return await get_chart_context(image_artifact_id)
        
        class FindChartByFigureNumberTool(Tool):
            """根據圖表編號查找 Artifact ID"""
            
            @property
            def name(self) -> str:
                return "find_chart_by_figure_number"
            
            @property
            def description(self) -> str:
                return """
根據圖表編號（如 "3", "5A"）查找對應的 Artifact ID

用於將用戶口中的「圖 3」轉換為具體的 artifact_id

Args:
    document_id: 文檔 ID
    figure_number: 圖表編號（例如："3", "5A", "12B"）
    
Returns:
    str: Artifact ID，或 None
"""
            
            @property
            def parameters(self) -> dict:
                return {
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "integer",
                            "description": "文檔 ID"
                        },
                        "figure_number": {
                            "type": "string",
                            "description": "圖表編號（例如：3, 5A, 12B）"
                        }
                    },
                    "required": ["document_id", "figure_number"]
                }
            
            async def execute(self, document_id: int, figure_number: str) -> str:
                from nanobot.agent.tools.multimodal_rag import find_chart_by_figure_number
                result = await find_chart_by_figure_number(document_id, figure_number)
                return result or "未找到對應的圖表"
        
        class AssembleMultimodalPromptTool(Tool):
            """組裝多模態 Prompt"""
            
            @property
            def name(self) -> str:
                return "assemble_multimodal_prompt"
            
            @property
            def description(self) -> str:
                return """
將圖片描述 + 跨頁文字 + 用戶問題組裝成完整 Prompt

Args:
    image_description: 圖表的描述
    context_text: 跨頁解釋文字
    user_question: 用戶的問題
    
Returns:
    str: 組裝好的完整 Prompt
"""
            
            @property
            def parameters(self) -> dict:
                return {
                    "type": "object",
                    "properties": {
                        "image_description": {
                            "type": "string",
                            "description": "圖表的描述"
                        },
                        "context_text": {
                            "type": "string",
                            "description": "跨頁解釋文字"
                        },
                        "user_question": {
                            "type": "string",
                            "description": "用戶的問題"
                        }
                    },
                    "required": ["image_description", "context_text", "user_question"]
                }
            
            async def execute(
                self,
                image_description: str,
                context_text: str,
                user_question: str
            ) -> str:
                from nanobot.agent.tools.multimodal_rag import assemble_multimodal_prompt
                return assemble_multimodal_prompt(image_description, context_text, user_question)
        
        registry.register(GetChartContextTool())
        registry.register(FindChartByFigureNumberTool())
        registry.register(AssembleMultimodalPromptTool())
        
        logger.info("✅ Registered multimodal RAG tools (cross-modal retrieval)")
        
    except ImportError as e:
        logger.warning(f"⚠️ Failed to import multimodal_rag: {e}")
    
    # 統計已註冊的工具
    total_tools = len(registry.list_tools())
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
        for tool in registry.list_tools()
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
        "vanna_sql",
        "search_chunks"
    ],
    "document": [
        "parse_pdf",
        "extract_tables"
    ],
    "multimodal_rag": [
        "get_chart_context",
        "find_chart_by_figure_number",
        "assemble_multimodal_prompt"
    ]
}