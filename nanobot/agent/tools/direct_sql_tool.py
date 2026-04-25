"""
Direct SQL Tool - Agent Query Bypass (Replace Vanna)

🌟 No Pre-Training Required
- Agent sees DB schema via GetDBSchemaTool
- Agent writes SQL directly
- Execute SQL via this tool

Why This is Better:
- Vanna 需要 pre-train (學 DDL + example SQLs)
- Agent 直接寫 SQL，零預訓練成本
- 減少依赖：刪除 vanna-service 微服務
"""

from typing import Any, Dict, List
from loguru import logger

from nanobot.agent.tools.base import Tool


class DirectSQLTool(Tool):
    """
    [Tool] 直接執行 SQL 查詢（无需预训练）
    
    Agent 看到 schema 自己會判斷用咩 SQL，根本不需要 Vanna。
    
    使用場景：
    - "Show Tencent revenue for 2023" → 直接寫 SQL
    - "What is the shareholding percentage of Li Ka-Shing?" → 直接寫 SQL
    - "Top 5 companies by profit" → 直接寫 SQL
    """
    
    @property
    def name(self) -> str:
        return "direct_sql"
    
    @property
    def description(self) -> str:
        return (
            "Execute a raw SQL query directly against the PostgreSQL database. "
            "Use this to answer financial data questions when you know the schema. "
            "🌟 No pre-training required - just write SQL based on the schema."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SQL query to execute (e.g., 'SELECT * FROM companies LIMIT 5')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return",
                    "default": 20
                }
            },
            "required": ["sql"]
        }
    
    @property
    def read_only(self) -> bool:
        return True  # Read-only for safety
    
    async def execute(self, sql: str, limit: int = 20, context: dict = None) -> str:
        """
        直接執行 SQL
        
        Args:
            sql: SQL 查詢語句
            limit: 返回行數限制
            context: 執行上下文（包含 db_client）
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        # 🌟 v4.16: 使用 Singleton
        db = DBClient.get_instance()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 🌟 自動加上 LIMIT
                if "limit" not in sql.lower():
                    sql = sql.rstrip(";") + f" LIMIT {limit}"
                
                logger.info(f"🔍 DirectSQL: {sql}")
                rows = await conn.fetch(sql)
                
                if not rows:
                    return "✅ 查詢成功但無數據返回"
                
                # 格式化輸出
                if isinstance(rows[0], dict):
                    headers = list(rows[0].keys())
                    result_lines = [
                        "✅ 查詢成功！",
                        "",
                        f"**SQL:** `{sql}`",
                        f"**結果:** {len(rows)} 行",
                        "",
                    ]
                    
                    # 構建表格
                    result_lines.append("| " + " | ".join(headers) + " |")
                    result_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                    
                    for row in rows:
                        result_lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
                    
                    return "\n".join(result_lines)
                else:
                    # tuple 格式
                    return f"✅ 查詢成功！\n\n**SQL:** `{sql}`\n\n**結果:** {len(rows)} 行\n\n" + "\n".join(
                        str(dict(row)) for row in rows
                    )
        
        except Exception as e:
            logger.error(f"❌ DirectSQL 執行失敗: {e}")
            return f"❌ SQL 執行錯誤: {str(e)}\n\nSQL: {sql}"


class GetTableInfoTool(Tool):
    """
    [Tool] 獲取特定表的詳細信息
    
    用於查看單個表的結構、索引、约束等
    """
    
    @property
    def name(self) -> str:
        return "get_table_info"
    
    @property
    def description(self) -> str:
        return (
            "Get detailed information about a specific table including columns, "
            "types, indexes, and constraints. Use this to understand table structure "
            "before writing SQL queries."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table to describe"
                }
            },
            "required": ["table_name"]
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(self, table_name: str, context: dict = None) -> str:
        """獲取表結構"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient.get_instance()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 獲取列信息
                columns = await conn.fetch("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = $1
                    ORDER BY ordinal_position
                """, table_name)
                
                if not columns:
                    return f"❌ 表 '{table_name}' 不存在或無列信息"
                
                result_lines = [
                    f"📋 表結構: **{table_name}**",
                    "",
                    "| Column | Type | Nullable | Default |",
                    "| --- | --- | --- | --- |"
                ]
                
                for col in columns:
                    result_lines.append(
                        f"| {col['column_name']} | {col['data_type']} | "
                        f"{'YES' if col['is_nullable'] == 'YES' else 'NO'} | {col['column_default'] or ''} |"
                    )
                
                return "\n".join(result_lines)
        
        except Exception as e:
            return f"❌ 獲取表結構失敗: {str(e)}"
