"""
Apache AGE Graph Query Tool for PostgreSQL
===========================================

Apache AGE allows running Cypher queries inside PostgreSQL.
This tool provides graph query capabilities without needing a separate graph database.

🌟 License Advantages:
- Apache AGE: Apache License 2.0 (commercial-friendly)
- PostgreSQL: PostgreSQL License (MIT-like)
- No GPL contamination risk, suitable for commercial products

Key Features:
- OpenCypher syntax (same syntax as Neo4j Cypher)
- Hybrid queries (SQL + Graph in one query)
- Single PostgreSQL connection pool
- No licensing fees
"""

import json
from typing import Any, Dict, List, Optional
from loguru import logger

from nanobot.agent.tools.base import Tool


class AgeGraphQueryTool(Tool):
    """
    Execute Cypher graph queries via Apache AGE in PostgreSQL.
    
    Usage:
        query: Cypher query string (MATCH, CREATE, RETURN, etc.)
        graph: Graph name (default: 'annual_report_graph')
        
    Example:
        tool.execute(
            query="MATCH (p:Person)-[:OWNS_SHARES]->(c:Company) RETURN p.name, c.name",
            graph="annual_report_graph"
        )
    """
    
    @property
    def name(self) -> str:
        return "age_graph_query"
    
    @property
    def description(self) -> str:
        return """Execute Cypher graph queries via Apache AGE in PostgreSQL.
        
        Use this tool to query entity relationships (person-company, company-subsidiary, shareholding network).
        Supports standard OpenCypher syntax (same as Neo4j).
        
        Common use cases:
        - Find all companies a person is connected to
        - Find shareholding chains (A owns B owns C)
        - Find subsidiaries of a company
        - Find directors of multiple companies
        
        Returns results as JSON array.
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Cypher query (e.g., MATCH (p:Person)-[:OWNS]->(c:Company) RETURN p.name, c.name)"
                },
                "graph": {
                    "type": "string",
                    "description": "Graph name (default: annual_report_graph)",
                    "default": "annual_report_graph"
                },
                "returns": {
                    "type": "string",
                    "description": "Column definitions for return values (e.g., 'name agtype, company agtype')"
                }
            },
            "required": ["query"]
        }
    
    async def execute(
        self,
        query: str,
        graph: str = "annual_report_graph",
        returns: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Execute Cypher query via Apache AGE."""
        
        if not context or "db_client" not in context:
            return json.dumps({"error": "Database client not available in context"})
        
        db_client = context["db_client"]
        
        # Build return columns definition
        if returns:
            return_columns = [col.strip() for col in returns.split(',')]
        else:
            return_columns = ['result agtype']
        
        try:
            # 🌟 使用新的 execute_age_query 方法
            results = await db_client.execute_age_query(
                cypher=query,
                graph_name=graph,
                return_columns=return_columns
            )
            
            # Parse AGE results (agtype format)
            parsed_results = []
            for row in results:
                if isinstance(row, dict):
                    # AGE returns agtype which is JSON-like
                    parsed_row = {}
                    for key, value in row.items():
                        if value and isinstance(value, str):
                            # Parse agtype string (e.g., '"value"' or '{"key": "value"}')
                            try:
                                if value.startswith('"') and value.endswith('"'):
                                    parsed_row[key] = value[1:-1]
                                elif value.startswith('{'):
                                    parsed_row[key] = json.loads(value)
                                else:
                                    parsed_row[key] = value
                            except:
                                parsed_row[key] = value
                        else:
                            parsed_row[key] = value
                    parsed_results.append(parsed_row)
                else:
                    parsed_results.append(row)
            
            logger.info(f"AGE query returned {len(parsed_results)} results")
            return json.dumps({
                "success": True,
                "count": len(parsed_results),
                "results": parsed_results,
                "query": query,
                "graph": graph
            }, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"AGE query failed: {e}")
            return json.dumps({
                "error": str(e),
                "query": query,
                "graph": graph
            })


class GetPersonNetworkTool(Tool):
    """
    Find all entities connected to a person through the graph.
    
    This is a convenience tool that wraps common Cypher patterns.
    """
    
    @property
    def name(self) -> str:
        return "get_person_network"
    
    @property
    def description(self) -> str:
        return """Find all companies, positions, and relationships for a person.
        
        Returns:
        - Companies they own shares in
        - Companies they manage
        - Board positions they hold
        - Connected persons (co-directors, family members)
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "person_name": {
                    "type": "string",
                    "description": "Person's name to search"
                }
            },
            "required": ["person_name"]
        }
    
    async def execute(
        self,
        person_name: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Find person's network."""
        
        cypher = f"""
        MATCH (p:Person {{name: '{person_name}'}})
        OPTIONAL MATCH (p)-[:OWNS_SHARES]->(c1:Company)
        OPTIONAL MATCH (p)-[:MANAGES]->(c2:Company)
        OPTIONAL MATCH (p)-[:DIRECTOR_OF]->(c3:Company)
        OPTIONAL MATCH (p)-[:FAMILY_OF]->(p2:Person)
        RETURN 
            p.name as person_name,
            collect(DISTINCT c1.name) as owns_shares_in,
            collect(DISTINCT c2.name) as manages,
            collect(DISTINCT c3.name) as director_of,
            collect(DISTINCT p2.name) as family_members
        """
        
        # Delegate to AgeGraphQueryTool
        age_tool = AgeGraphQueryTool()
        return await age_tool.execute(
            query=cypher,
            returns="person_name agtype, owns_shares_in agtype, manages agtype, director_of agtype, family_members agtype",
            context=context
        )


class GetCompanyControllersTool(Tool):
    """
    Find ultimate controllers of a company through shareholding chain.
    
    Traces ownership upwards to find ultimate beneficial owners.
    """
    
    @property
    def name(self) -> str:
        return "get_company_controllers"
    
    @property
    def description(self) -> str:
        return """Find the ultimate controllers/beneficial owners of a company.
        
        Traces the shareholding chain upwards to find:
        - Direct shareholders
        - Ultimate beneficial owners (persons)
        - Parent companies
        - Cross-shareholding patterns
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Company name to analyze"
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum depth to trace (default: 3)",
                    "default": 3
                }
            },
            "required": ["company_name"]
        }
    
    async def execute(
        self,
        company_name: str,
        depth: int = 3,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Find company controllers."""
        
        cypher = f"""
        MATCH path = (controller)-[:OWNS_SHARES*1..{depth}]->(c:Company {{name: '{company_name}'}})
        WHERE controller:Person OR controller:Company
        RETURN 
            controller.name as controller_name,
            labels(controller)[0] as controller_type,
            length(path) as depth,
            [rel in relationships(path) | rel.percentage] as ownership_chain
        ORDER BY depth
        """
        
        age_tool = AgeGraphQueryTool()
        return await age_tool.execute(
            query=cypher,
            returns="controller_name agtype, controller_type agtype, depth agtype, ownership_chain agtype",
            context=context
        )


class CreateGraphRelationTool(Tool):
    """
    Create a relationship (edge) between two entities in the graph.
    
    Used by Agent to store extracted relationships.
    """
    
    @property
    def name(self) -> str:
        return "create_graph_relation"
    
    @property
    def description(self) -> str:
        return """Create a relationship between two entities in the graph.
        
        Supported relationship types:
        - OWNS_SHARES (Person->Company, Company->Company)
        - MANAGES (Person->Company)
        - DIRECTOR_OF (Person->Company)
        - SUBSIDIARY_OF (Company->Company)
        - FAMILY_OF (Person->Person)
        
        Properties can include:
        - percentage: ownership percentage
        - position: job title
        - since: date relationship started
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "from_type": {
                    "type": "string",
                    "description": "Source entity type (Person, Company)",
                    "enum": ["Person", "Company"]
                },
                "from_name": {
                    "type": "string",
                    "description": "Source entity name"
                },
                "relation_type": {
                    "type": "string",
                    "description": "Relationship type",
                    "enum": ["OWNS_SHARES", "MANAGES", "DIRECTOR_OF", "SUBSIDIARY_OF", "FAMILY_OF"]
                },
                "to_type": {
                    "type": "string",
                    "description": "Target entity type (Person, Company)",
                    "enum": ["Person", "Company"]
                },
                "to_name": {
                    "type": "string",
                    "description": "Target entity name"
                },
                "properties": {
                    "type": "object",
                    "description": "Optional properties (percentage, position, since)"
                }
            },
            "required": ["from_type", "from_name", "relation_type", "to_type", "to_name"]
        }
    
    async def execute(
        self,
        from_type: str,
        from_name: str,
        relation_type: str,
        to_type: str,
        to_name: str,
        properties: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create graph relationship."""
        
        # Build properties string for Cypher
        props_str = ""
        if properties:
            props_list = []
            for key, value in properties.items():
                if isinstance(value, str):
                    props_list.append(f"{key}: '{value}'")
                elif isinstance(value, (int, float)):
                    props_list.append(f"{key}: {value}")
            if props_list:
                props_str = " {" + ", ".join(props_list) + "}"
        
        # MERGE creates if not exists
        cypher = f"""
        MERGE (from:{from_type} {{name: '{from_name}'}})
        MERGE (to:{to_type} {{name: '{to_name}'}})
        MERGE (from)-[r:{relation_type}{props_str}]->(to)
        RETURN from.name as from_name, type(r) as relation, to.name as to_name
        """
        
        age_tool = AgeGraphQueryTool()
        return await age_tool.execute(
            query=cypher,
            returns="from_name agtype, relation agtype, to_name agtype",
            context=context
        )


# Export tools
AGE_TOOLS = [
    AgeGraphQueryTool(),
    GetPersonNetworkTool(),
    GetCompanyControllersTool(),
    CreateGraphRelationTool()
]


def get_age_tools() -> List[Tool]:
    """Return all Apache AGE tools."""
    return AGE_TOOLS
