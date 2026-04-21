"""
Vanna AI Text-to-SQL Integration (Microservice Client)

Architecture: Gateway (HTTP Client) → vanna-service:8082 (Vanna AI)

This module is a PURE HTTP CLIENT.
- No local vanna/chromadb imports
- All Vanna operations go through HTTP API calls
- Decouples Gateway from heavy ML dependencies

Key Features:
- Text-to-SQL via HTTP
- Dynamic Schema Injection for JSONB attributes
- PostgreSQL JSONB query syntax support (Schema v2.3)

Usage:
    from nanobot.agent.tools.vanna_tool import VannaQueryTool
    
    tool = VannaQueryTool()
    result = await tool.execute(question="Show Tencent's revenue for 2020-2023")
"""

from typing import Optional, Dict, Any, List
from loguru import logger
import os
import json
import httpx
from pathlib import Path

# Import base Tool class
from nanobot.agent.tools.base import Tool


class VannaServiceClient:
    """
    HTTP Client for Vanna Service
    
    All Vanna operations go through HTTP API calls to vanna-service:8082
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize Vanna Service Client
        
        Args:
            base_url: Vanna service URL (default: http://vanna-service:8082)
        """
        self.base_url = base_url or os.getenv(
            "VANNA_SERVICE_URL", 
            "http://vanna-service:8082"
        )
        self.timeout = httpx.Timeout(120.0, connect=10.0)  # 🌟 增加到 120 秒
        logger.info(f"🌐 VannaServiceClient initialized: {self.base_url}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Vanna service health"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Vanna health check failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def ask(
        self, 
        question: str, 
        include_sql: bool = True,
        include_summary: bool = False
    ) -> Dict[str, Any]:
        """
        Ask Vanna a question (generate SQL and execute)
        
        Args:
            question: Natural language question
            include_sql: Return SQL (default: true)
            include_summary: Return summary (default: false)
            
        Returns:
            Dict with question, sql, answer, data, status
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/ask",
                    json={
                        "question": question,
                        "include_sql": include_sql,
                        "include_summary": include_summary
                    }
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Vanna ask failed: {e}")
            return {
                "question": question,
                "error": str(e),
                "status": "error"
            }
    
    async def ask_with_dynamic_schema(
        self, 
        question: str,
        include_summary: bool = False
    ) -> Dict[str, Any]:
        """
        Ask Vanna with Just-in-Time Schema Injection
        
        🌟 原本在本地 VannaSQL.generate_sql_with_dynamic_schema()
        
        This method:
        1. First discovers all dynamic keys in the database
        2. Builds an enhanced prompt with JSONB query hints
        3. Passes the enhanced prompt to Vanna
        
        Args:
            question: Natural language question
            include_summary: Return summary (default: false)
            
        Returns:
            Dict with question, sql, answer, data, status, dynamic_keys_discovered
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/ask_with_dynamic_schema",
                    json={
                        "question": question,
                        "include_summary": include_summary
                    }
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Vanna ask_with_dynamic_schema failed: {e}")
            return {
                "question": question,
                "error": str(e),
                "status": "error"
            }
    
    async def discover_dynamic_keys(self) -> Dict[str, Any]:
        """
        Discover all dynamic keys stored in JSONB columns
        
        Returns:
            Dict with discovered_keys, sample_values, key_frequency, discovered_industries
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/discover_dynamic_keys"
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Discover dynamic keys failed: {e}")
            return {
                "discovered_keys": [],
                "status": "error",
                "error": str(e)
            }
    
    async def train(self, train_type: str = "schema", doc_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Trigger Vanna training
        
        Args:
            train_type: "schema" | "ddl" | "sql"
            doc_id: Optional document ID for document-specific training
            
        Returns:
            Training status
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/train",
                    json={
                        "train_type": train_type,
                        "doc_id": doc_id
                    }
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Vanna train failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def train_ddl(self, ddl: str) -> Dict[str, Any]:
        """Train Vanna with DDL statement"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/train_ddl",
                    params={"ddl": ddl}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ DDL training failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def train_sql(self, question: str, sql: str) -> Dict[str, Any]:
        """Train Vanna with question + SQL example"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/train_sql",
                    params={"question": question, "sql": sql}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ SQL training failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def get_column_changes(self) -> Dict[str, Any]:
        """Get Schema v2.3 column name changes"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/api/column_changes")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Get column changes failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def get_status(self) -> Dict[str, Any]:
        """Get Vanna service status"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/status")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Get status failed: {e}")
            return {"status": "error", "error": str(e)}


# Global client instance
_vanna_client: Optional[VannaServiceClient] = None


def get_vanna_client() -> VannaServiceClient:
    """Get global Vanna service client"""
    global _vanna_client
    if not _vanna_client:
        _vanna_client = VannaServiceClient()
    return _vanna_client


# ============================================================
# Agent Tool Wrapper
# ============================================================

class VannaQueryTool(Tool):
    """
    🌟 Agent Tool for querying financial data via Vanna AI
    
    Architecture: Gateway → HTTP → vanna-service:8082
    
    This tool is a PURE HTTP CLIENT.
    - No local vanna/chromadb imports
    - All SQL generation happens in vanna-service
    - Supports Schema v2.3 (JSONB dynamic attributes)
    
    Usage:
        Agent calls: vanna_query(question="Show Tencent revenue for 2023")
        Tool → HTTP POST to vanna-service:8082/api/ask
        Returns: SQL + Query Results
    """
    
    @property
    def name(self) -> str:
        return "vanna_query"
    
    @property
    def description(self) -> str:
        return (
            "🔥 CRITICAL: ALWAYS USE THIS TOOL FIRST when the user asks about "
            "financial data, revenue, profit, margins, shareholding, key personnel, "
            "or ANY company-specific numerical data. "
            "Use this tool to search the local PostgreSQL database ACROSS ALL DOCUMENTS, "
            "EVEN IF the user does NOT specify a document name or year. "
            "DO NOT use web_search until this tool returns no results or fails! "
            "\n\nExample questions that MUST use this tool:"
            "\n- 'What is the shareholding percentage of Li Ka-Shing?'"
            "\n- 'Show Tencent revenue for 2023'"
            "\n- 'Top 5 companies by profit'"
            "\n- 'Average revenue for Biotech companies in 2022'"
        )
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "用戶的自然語言查詢，例如 'Show Tencent revenue for 2023'"
                },
                "include_summary": {
                    "type": "boolean",
                    "description": "是否生成結果摘要 (默認: false)",
                    "default": False
                },
                "use_dynamic_schema": {
                    "type": "boolean",
                    "description": "是否使用 Just-in-Time Schema Injection (默認: true)",
                    "default": True
                }
            },
            "required": ["question"]
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(
        self,
        question: str,
        include_summary: bool = False,
        use_dynamic_schema: bool = True,
        **kwargs
    ) -> str:
        """
        Execute Text-to-SQL query via Vanna Service
        
        Args:
            question: Natural language question
            include_summary: Generate result summary (default: false)
            use_dynamic_schema: Use Just-in-Time Schema Injection (default: true)
            
        Returns:
            Formatted response with SQL and results
        """
        logger.info(f"🔍 VannaQueryTool: {question}")
        
        client = get_vanna_client()
        
        try:
            # 🌟 Choose API based on use_dynamic_schema
            if use_dynamic_schema:
                result = await client.ask_with_dynamic_schema(
                    question=question,
                    include_summary=include_summary
                )
            else:
                result = await client.ask(
                    question=question,
                    include_sql=True,
                    include_summary=include_summary
                )
            
            # Check if Vanna service returned success
            if result.get("status") == "error":
                return f"❌ 查詢失敗: {result.get('error', 'Unknown error')}"
            
            if result.get("status") == "failed":
                return f"❌ 無法生成 SQL: {result.get('error', 'Please rephrase your question')}"
            
            # Format successful response
            response_parts = [
                f"✅ 查詢成功！",
                f"",
                f"**使用的 SQL:**",
                f"```sql",
                result.get("sql", ""),
                f"```",
                f"",
            ]
            
            # Show data if available
            data = result.get("data")
            if data:
                response_parts.append(f"**結果數據** ({len(data)} 行):")
                
                # Show first 10 rows
                for i, row in enumerate(data[:10], 1):
                    response_parts.append(f"{i}. {row}")
                
                if len(data) > 10:
                    response_parts.append(f"... 還有 {len(data) - 10} 行")
            else:
                response_parts.append("**結果數據**: 無數據返回")
            
            # Show summary if requested
            answer = result.get("answer")
            if answer:
                response_parts.extend([
                    f"",
                    f"**摘要:**",
                    answer
                ])
            
            return "\n".join(response_parts)
            
        except Exception as e:
            logger.error(f"❌ VannaQueryTool 執行失敗: {e}")
            return f"❌ 查詢執行錯誤: {str(e)}"


# ============================================================
# Convenience Functions for Legacy Compatibility
# ============================================================

async def ask(question: str, use_dynamic_schema: bool = True) -> Dict:
    """
    Ask Vanna a question (legacy compatibility)
    
    Args:
        question: Natural language question
        use_dynamic_schema: Use Just-in-Time Schema Injection (default: true)
        
    Returns:
        Query result with SQL and data
    """
    client = get_vanna_client()
    if use_dynamic_schema:
        return await client.ask_with_dynamic_schema(question)
    else:
        return await client.ask(question)


async def train_schema() -> Dict:
    """
    Trigger schema training (legacy compatibility)
    
    Returns:
        Training status
    """
    client = get_vanna_client()
    return await client.train(train_type="schema")


async def discover_dynamic_keys() -> Dict:
    """
    Discover all dynamic keys in JSONB columns (legacy compatibility)
    
    Returns:
        Dict with discovered_keys, sample_values, key_frequency
    """
    client = get_vanna_client()
    return await client.discover_dynamic_keys()


# ============================================================
# For Testing
# ============================================================

if __name__ == "__main__":
    import asyncio
    
    async def test_vanna_client():
        print("Testing Vanna Service Client...\n")
        
        client = VannaServiceClient()
        
        # Test health check
        print("1. Health Check...")
        health = await client.health_check()
        print(f"   Status: {health}")
        print()
        
        # Test query
        print("2. Testing Query...")
        test_questions = [
            "Show me the top 5 companies by revenue",
            "What was Tencent's revenue in 2023?"
        ]
        
        for question in test_questions:
            print(f"\n   Question: {question}")
            result = await client.ask(question)
            
            if result.get("status") == "ready":
                print(f"   ✓ SQL: {result.get('sql', 'N/A')[:100]}...")
                data = result.get("data")
                if data:
                    print(f"   ✓ Rows: {len(data)}")
            else:
                print(f"   ✗ Error: {result.get('error')}")
        
        print("\n✅ Vanna Service Client test complete!")
    
    asyncio.run(test_vanna_client())
