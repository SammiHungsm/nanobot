"""
Neo4j Graph Query Tool - Knowledge Graph Queries

🌟 用於查詢知識圖譜中的關係數據

當用戶問：
- 「李嘉誠喺邊幾間公司有股份？」
- 「呢個人控制邊啲公司？」
- 「邊個係呢間公司嘅最終控制人？」
- 「A公司同B公司有咩關係？」

呢啲都係關係型查詢，適合用 Cypher 查询 Neo4j。
"""

from typing import Any, Optional
from loguru import logger
import os

from nanobot.agent.tools.base import Tool


class Neo4jGraphQueryTool(Tool):
    """
    [Tool] 查詢 Neo4j 知識圖譜
    
    用於查詢人物、公司、持股關係等結構化關係。
    
    🌟 與 DirectSQLTool 嘅分工：
    - DirectSQLTool → 數字型、財務指標（PostgreSQL）
    - Neo4jGraphQueryTool → 關係型持股、公司關聯（Neo4j）
    """
    
    @property
    def name(self) -> str:
        return "graph_query"
    
    @property
    def description(self) -> str:
        return (
            "Query the knowledge graph for relationships between people and companies. "
            "Use for: shareholding analysis, control relationships, board appointments, "
            "company networks, cross-company relationships. "
            "NOT for: exact financial numbers (use direct_sql instead). "
            "Examples:"
            "\n- 'Who does Li Ka-Shing have shares in?'"
            "\n- 'Find all companies controlled by this person'"
            "\n- 'Show the relationship network of Tencent'"
            "\n- 'Who are the ultimate beneficial owners of this company?'"
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Cypher query or natural language description"
                },
                "person_name": {
                    "type": "string",
                    "description": "可選：指定人物名稱查詢",
                    "default": None
                },
                "company_name": {
                    "type": "string",
                    "description": "可選：指定公司名稱查詢",
                    "default": None
                },
                "depth": {
                    "type": "integer",
                    "description": "關係查詢深度（1-3）",
                    "default": 1
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
        person_name: Optional[str] = None,
        company_name: Optional[str] = None,
        depth: int = 1,
        context: dict = None
    ) -> str:
        """
        執行 Neo4j 圖譜查詢
        
        Args:
            query: Cypher 查詢或自然語言描述
            person_name: 可選人物名稱
            company_name: 可選公司名稱
            depth: 關係深度
            context: 執行上下文
        """
        from neo4j import AsyncGraphDatabase
        
        # 獲取 Neo4j 連接配置
        neo4j_host = os.getenv("NEO4J_HOST", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
        neo4j_uri = f"bolt://{neo4j_host}:7687"
        
        logger.info(f"🔍 Neo4j GraphQuery: {query[:100]}...")
        
        try:
            async with AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", neo4j_password)) as driver:
                async with driver.session() as session:
                    # 根據輸入構建 Cypher
                    cypher = self._build_cypher(query, person_name, company_name, depth)
                    
                    if cypher:
                        result = await session.run(cypher)
                        records = await result.data()
                        
                        if not records:
                            return f"🔍 找不到關係數據，查詢：「{query}」"
                        
                        return self._format_results(records, query)
                    else:
                        # 自然語言查詢 → 嘗試通用模式
                        return await self._natural_language_query(session, query, person_name, company_name, depth)
        
        except Exception as e:
            logger.error(f"❌ Neo4j GraphQuery 失敗: {e}")
            return f"❌ 圖譜查詢失敗: {str(e)}\n\n查詢：「{query}」"
    
    def _build_cypher(
        self,
        query: str,
        person_name: Optional[str],
        company_name: Optional[str],
        depth: int
    ) -> Optional[str]:
        """根據輸入構建 Cypher 查詢"""
        
        # 持股查詢
        if any(kw in query.lower() for kw in ["share", "持股", "股份", "hold"]):
            if person_name:
                return f"""
                    MATCH (p:Person {{name: $name}})-[r:HOLDS_SHARE]->(c:Company)
                    RETURN p.name as person, r.percentage as percentage, c.name as company
                    ORDER BY r.percentage DESC
                """
            elif company_name:
                return f"""
                    MATCH (p:Person)-[r:HOLDS_SHARE]->(c:Company {{name: $name}})
                    RETURN p.name as person, r.percentage as percentage, c.name as company
                    ORDER BY r.percentage DESC
                """
        
        # 控制關係查詢
        if any(kw in query.lower() for kw in ["control", "控制", "最終控制"]):
            if person_name:
                return f"""
                    MATCH (p:Person {{name: $name}})-[r:CONTROLS*1..{depth}]->(c:Company)
                    RETURN p.name as person, c.name as company, r as path
                """
            elif company_name:
                return f"""
                    MATCH (p:Person)-[r:CONTROLS*1..{depth}]->(c:Company {{name: $name}})
                    RETURN p.name as person, c.name as company
                """
        
        # 任命查詢
        if any(kw in query.lower() for kw in ["appoint", "任命", "董事", "board", "director"]):
            if company_name:
                return f"""
                    MATCH (p:Person)-[r:APPOINTED_AS]->(c:Company {{name: $name}})
                    RETURN p.name as person, r.role as role, c.name as company
                """
        
        # 關係網絡查詢
        if any(kw in query.lower() for kw in ["network", "關係", "relationship", "connected"]):
            if person_name:
                return f"""
                    MATCH (p:Person {{name: $name}})-[r]-(other)
                    RETURN type(r) as relationship, other.name as connected_to
                """
            elif company_name:
                return f"""
                    MATCH (c:Company {{name: $name}})-[r]-(other)
                    RETURN type(r) as relationship, other.name as connected_to
                """
        
        return None
    
    async def _natural_language_query(
        self,
        session,
        query: str,
        person_name: Optional[str],
        company_name: Optional[str],
        depth: int
    ) -> str:
        """處理自然語言查詢（通用模式）"""
        
        if person_name:
            cypher = f"""
                MATCH (p:Person {{name: $name}})-[r]-(other)
                RETURN p.name as person, type(r) as relationship, 
                       other.name as connected_to, labels(other) as type
                LIMIT 20
            """
            result = await session.run(cypher, name=person_name)
        elif company_name:
            cypher = f"""
                MATCH (c:Company {{name: $name}})-[r]-(other)
                RETURN c.name as company, type(r) as relationship,
                       other.name as connected_to, labels(other) as type
                LIMIT 20
            """
            result = await session.run(cypher, name=company_name)
        else:
            return "❌ 請提供 person_name 或 company_name"
        
        records = await result.data()
        
        if not records:
            return f"🔍 找不到關係數據"
        
        return self._format_results(records, query)
    
    def _format_results(self, records: list, query: str) -> str:
        """格式化輸出"""
        result_lines = [
            f"🔗 圖譜查詢結果",
            f"查詢：「{query}」",
            f"找到 {len(records)} 筆記錄：",
            ""
        ]
        
        for i, record in enumerate(records, 1):
            if "person" in record and "company" in record:
                result_lines.append(
                    f"{i}. **{record['person']}** → **{record['company']}**"
                )
                if "percentage" in record:
                    result_lines.append(f"   持股：{record['percentage']}%")
                if "role" in record:
                    result_lines.append(f"   職位：{record['role']}")
            elif "relationship" in record:
                result_lines.append(
                    f"{i}. {record.get('person') or record.get('company', '?')} "
                    f"-[{record['relationship']}]-> "
                    f"{record['connected_to']}"
                )
        
        return "\n".join(result_lines)


class GetPersonHoldingsTool(Tool):
    """
    [Tool] 查詢某人身家（持股明細）
    
    專門用於查詢「李嘉誠有幾多間公司嘅股份？」
    """
    
    @property
    def name(self) -> str:
        return "get_person_holdings"
    
    @property
    def description(self) -> str:
        return (
            "Get all company holdings for a specific person. "
            "Use when asking 'Who does X have shares in?' or 'Show all holdings of person X'. "
            "This returns percentage ownership and company details."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "person_name": {
                    "type": "string",
                    "description": "人名（可輸入中文或英文）"
                }
            },
            "required": ["person_name"]
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(self, person_name: str, context: dict = None) -> str:
        """查詢某人所有持股"""
        from neo4j import AsyncGraphDatabase
        
        neo4j_host = os.getenv("NEO4J_HOST", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
        neo4j_uri = f"bolt://{neo4j_host}:7687"
        
        try:
            async with AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", neo4j_password)) as driver:
                async with driver.session() as session:
                    cypher = """
                        MATCH (p:Person)-[r:HOLDS_SHARE]->(c:Company)
                        WHERE p.name CONTAINS $name OR p.name_zh CONTAINS $name
                        RETURN p.name as person, c.name as company, 
                               c.stock_code as stock_code,
                               r.percentage as percentage,
                               r.shares as shares
                        ORDER BY r.percentage DESC
                    """
                    result = await session.run(cypher, name=person_name)
                    records = await result.data()
                    
                    if not records:
                        return f"❌ 找不到「{person_name}」嘅持股記錄"
                    
                    total_lines = [
                        f"💰 {person_name} 持股明細：",
                        f"共 {len(records)} 間公司：",
                        ""
                    ]
                    
                    total_percentage = 0
                    for i, row in enumerate(records, 1):
                        company = row['company']
                        stock = row.get('stock_code', 'N/A')
                        pct = row.get('percentage', 0)
                        total_percentage += pct if pct else 0
                        
                        total_lines.append(
                            f"{i}. {company} ({stock})"
                        )
                        if pct:
                            total_lines.append(f"   持股：{pct}%")
                    
                    if total_percentage:
                        total_lines.append(f"\n📊 合計持股：{total_percentage:.2f}%")
                    
                    return "\n".join(total_lines)
        
        except Exception as e:
            return f"❌ 持股查詢失敗: {str(e)}"


class GetCompanyControllersTool(Tool):
    """
    [Tool] 查詢公司最終控制人
    
    專門用於查詢「邊個係X公司嘅最終控制人？」
    """
    
    @property
    def name(self) -> str:
        return "get_company_controllers"
    
    @property
    def description(self) -> str:
        return (
            "Find the ultimate beneficial owners or controllers of a company. "
            "Use when asking 'Who controls company X?' or 'Who are the ultimate owners?'. "
            "This traces the control chain to the final beneficial owners."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "公司名稱"
                }
            },
            "required": ["company_name"]
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(self, company_name: str, context: dict = None) -> str:
        """查詢公司控制人"""
        from neo4j import AsyncGraphDatabase
        
        neo4j_host = os.getenv("NEO4J_HOST", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
        neo4j_uri = f"bolt://{neo4j_host}:7687"
        
        try:
            async with AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", neo4j_password)) as driver:
                async with driver.session() as session:
                    # 查找直接持股人
                    cypher = """
                        MATCH (p:Person)-[r:HOLDS_SHARE]->(c:Company)
                        WHERE c.name CONTAINS $name OR c.name_zh CONTAINS $name
                        AND r.percentage >= 5
                        RETURN p.name as person, r.percentage as percentage,
                               c.name as company, 'direct' as type
                        ORDER BY r.percentage DESC
                        LIMIT 20
                    """
                    result = await session.run(cypher, name=company_name)
                    records = await result.data()
                    
                    if not records:
                        return f"❌ 找不到「{company_name}」嘅控制權數據"
                    
                    result_lines = [
                        f"🏛️ {company_name} 主要股東/控制人：",
                        f"共 {len(records)} 個直接或主要持股人：",
                        ""
                    ]
                    
                    for i, row in enumerate(records, 1):
                        pct = row.get('percentage', 0)
                        result_lines.append(
                            f"{i}. **{row['person']}** — 持股 {pct}%"
                        )
                    
                    return "\n".join(result_lines)
        
        except Exception as e:
            return f"❌ 控制人查詢失敗: {str(e)}"
