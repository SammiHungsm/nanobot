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
    ]
}