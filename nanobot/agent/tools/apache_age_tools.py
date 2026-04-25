"""
Apache AGE Graph Tools for Agent

Provides tools for inserting nodes and edges into Apache AGE graph database.
Enables the agent to build knowledge graphs from unstructured text.
"""
import json
from typing import Any, Optional
from loguru import logger

# Import Tool base class
try:
    from nanobot.agent.tools.base import Tool
except ImportError:
    # Fallback: define a minimal Tool base class
    class Tool:
        @property
        def name(self) -> str:
            raise NotImplementedError
        
        @property
        def description(self) -> str:
            raise NotImplementedError
        
        @property
        def parameters(self) -> dict:
            return {}
        
        @property
        def read_only(self) -> bool:
            return True
        
        async def execute(self, **kwargs) -> str:
            raise NotImplementedError


def _get_db_connection(context: dict = None):
    """Get database connection from context"""
    if context and context.get("db_client"):
        return context["db_client"]
    
    # Fallback: create new connection
    from nanobot.ingestion.repository.db_client import DBClient
    return DBClient.get_instance()


class InsertGraphNodeTool(Tool):
    """
    [Tool] Insert a node into Apache AGE graph
    
    Creates a node (Company, Person, or custom entity) in the financial_graph.
    """
    
    @property
    def name(self) -> str:
        return "insert_graph_node"
    
    @property
    def description(self) -> str:
        return (
            "Insert a node into Apache AGE knowledge graph. "
            "Use this to create Company, Person, or other entity nodes. "
            "Example: Create a company node with name and stock_code."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Node label/type (e.g., 'Company', 'Person', 'Organization')"
                },
                "properties": {
                    "type": "object",
                    "description": "Node properties as key-value pairs (e.g., name, stock_code, person_id)"
                }
            },
            "required": ["label", "properties"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        label: str,
        properties: dict,
        context: dict = None
    ) -> str:
        """Insert a node into Apache AGE graph"""
        
        if not properties.get("name"):
            return json.dumps({
                "success": False,
                "error": "Node must have a 'name' property"
            }, ensure_ascii=False)
        
        try:
            db = _get_db_connection(context)
            
            # Build property string for Cypher
            props_parts = []
            for k, v in properties.items():
                if isinstance(v, str):
                    # Escape single quotes
                    v_escaped = v.replace("'", "\\'")
                    props_parts.append(f"{k}: '{v_escaped}'")
                elif isinstance(v, (int, float)):
                    props_parts.append(f"{k}: {v}")
                elif v is None:
                    props_parts.append(f"{k}: null")
                else:
                    v_escaped = str(v).replace("'", "\\'")
                    props_parts.append(f"{k}: '{v_escaped}'")
            
            props_str = ", ".join(props_parts)
            
            # Execute Cypher query
            async with db.connection() as conn:
                await conn.execute("SET search_path = ag_catalog, '$user', public")
                
                result = await conn.fetch(f"""
                    SELECT * FROM cypher('financial_graph', $$
                        MERGE (n:{label} {{{props_str}}})
                        RETURN n.name
                    $$) as (name agtype)
                """)
            
            return json.dumps({
                "success": True,
                "message": f"Created/updated {label} node: {properties.get('name')}",
                "node_name": properties.get("name")
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Failed to insert graph node: {e}")
            return json.dumps({
                "success": False,
                "error": str(e)
            }, ensure_ascii=False)


class InsertGraphEdgeTool(Tool):
    """
    [Tool] Insert an edge (relationship) into Apache AGE graph
    
    Creates a relationship between two nodes in the financial_graph.
    """
    
    @property
    def name(self) -> str:
        return "insert_graph_edge"
    
    @property
    def description(self) -> str:
        return (
            "Insert an edge (relationship) between two nodes in Apache AGE graph. "
            "Use this to create relationships like SUBSIDIARY_OF, INVESTED_IN, PARTNERED_WITH. "
            "Both source and target nodes must exist (or will be auto-created)."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_label": {
                    "type": "string",
                    "description": "Source node label (e.g., 'Company', 'Person')"
                },
                "source_name": {
                    "type": "string",
                    "description": "Source node name (used to match the node)"
                },
                "target_label": {
                    "type": "string",
                    "description": "Target node label (e.g., 'Company', 'Person')"
                },
                "target_name": {
                    "type": "string",
                    "description": "Target node name (used to match the node)"
                },
                "relation_type": {
                    "type": "string",
                    "description": "Relationship type (e.g., 'SUBSIDIARY_OF', 'INVESTED_IN', 'PARTNERED_WITH', 'EXECUTIVE_OF')",
                    "enum": [
                        "SUBSIDIARY_OF",
                        "INVESTED_IN", 
                        "PARTNERED_WITH",
                        "COMPETITOR_OF",
                        "EXECUTIVE_OF",
                        "DIRECTOR_OF",
                        "SUPPLIER_OF",
                        "CUSTOMER_OF",
                        "ACQUIRED_BY",
                        "JOINT_VENTURE_WITH"
                    ]
                },
                "properties": {
                    "type": "object",
                    "description": "Optional edge properties (e.g., ownership_percentage, since_year)"
                }
            },
            "required": ["source_label", "source_name", "target_label", "target_name", "relation_type"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        source_label: str,
        source_name: str,
        target_label: str,
        target_name: str,
        relation_type: str,
        properties: dict = None,
        context: dict = None
    ) -> str:
        """Insert an edge into Apache AGE graph"""
        
        try:
            db = _get_db_connection(context)
            
            # Build optional edge properties
            edge_props_str = ""
            if properties:
                props_parts = []
                for k, v in properties.items():
                    if isinstance(v, str):
                        v_escaped = v.replace("'", "\\'")
                        props_parts.append(f"{k}: '{v_escaped}'")
                    elif isinstance(v, (int, float)):
                        props_parts.append(f"{k}: {v}")
                if props_parts:
                    edge_props_str = " {" + ", ".join(props_parts) + "}"
            
            # Escape names
            source_name_escaped = source_name.replace("'", "\\'")
            target_name_escaped = target_name.replace("'", "\\'")
            
            async with db.connection() as conn:
                await conn.execute("SET search_path = ag_catalog, '$user', public")
                
                # Use MERGE to create nodes if they don't exist, then create relationship
                result = await conn.fetch(f"""
                    SELECT * FROM cypher('financial_graph', $$
                        MERGE (a:{source_label} {{name: '{source_name_escaped}'}})
                        MERGE (b:{target_label} {{name: '{target_name_escaped}'}})
                        MERGE (a)-[r:{relation_type}{edge_props_str}]->(b)
                        RETURN a.name, type(r), b.name
                    $$) as (a_name agtype, r_type agtype, b_name agtype)
                """)
            
            return json.dumps({
                "success": True,
                "message": f"Created edge: {source_name} -[{relation_type}]-> {target_name}",
                "source": source_name,
                "relation": relation_type,
                "target": target_name
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Failed to insert graph edge: {e}")
            return json.dumps({
                "success": False,
                "error": str(e)
            }, ensure_ascii=False)


class QueryGraphTool(Tool):
    """
    [Tool] Query Apache AGE graph with Cypher
    
    Execute a Cypher query against the financial_graph.
    """
    
    @property
    def name(self) -> str:
        return "query_graph"
    
    @property
    def description(self) -> str:
        return (
            "Execute a Cypher query against the Apache AGE financial_graph. "
            "Use this to find relationships, company networks, or person connections. "
            "Example: Find all subsidiaries of a company, or find common directors between companies."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Cypher query to execute. "
                        "Examples:\n"
                        "- 'MATCH (a:Company)-[:SUBSIDIARY_OF]->(b:Company) RETURN a.name, b.name'\n"
                        "- 'MATCH (p:Person)-[:EXECUTIVE_OF]->(c:Company) RETURN p.name, c.name'\n"
                        "- 'MATCH path = shortestPath((a:Company {name: \"CK Hutchison\"})-[*]-(b:Company {name: \"Hutchison Telecom\"})) RETURN path'"
                    )
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
        context: dict = None
    ) -> str:
        """Execute a Cypher query"""
        
        try:
            db = _get_db_connection(context)
            
            async with db.connection() as conn:
                await conn.execute("SET search_path = ag_catalog, '$user', public")
                
                # Execute query - return as agtype
                result = await conn.fetch(f"""
                    SELECT * FROM cypher('financial_graph', $$
                        {query}
                    $$) as (result agtype)
                """)
            
            # Parse results
            results = []
            for row in result:
                results.append(str(row['result']))
            
            return json.dumps({
                "success": True,
                "count": len(results),
                "results": results[:20],  # Limit to 20 results
                "truncated": len(results) > 20
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Failed to query graph: {e}")
            return json.dumps({
                "success": False,
                "error": str(e)
            }, ensure_ascii=False)


class SyncToGraphTool(Tool):
    """
    [Tool] Sync entity_relations and key_personnel to Apache AGE graph
    
    One-shot tool to populate the graph from existing relational data.
    """
    
    @property
    def name(self) -> str:
        return "sync_to_graph"
    
    @property
    def description(self) -> str:
        return (
            "Sync all entity_relations and key_personnel to Apache AGE graph. "
            "This creates Company nodes, Person nodes, and their relationships. "
            "Use this after extracting data to populate the knowledge graph."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "integer",
                    "description": "Optional: Only sync relations for this document"
                },
                "sync_companies": {
                    "type": "boolean",
                    "default": True,
                    "description": "Sync company-to-company relations"
                },
                "sync_personnel": {
                    "type": "boolean", 
                    "default": True,
                    "description": "Sync person-to-company relations (directors, executives)"
                }
            },
            "required": []
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        document_id: int = None,
        sync_companies: bool = True,
        sync_personnel: bool = True,
        context: dict = None
    ) -> str:
        """Sync relational data to Apache AGE graph"""
        
        try:
            db = _get_db_connection(context)
            stats = {"companies_synced": 0, "personnel_synced": 0, "edges_created": 0}
            
            async with db.connection() as conn:
                await conn.execute("SET search_path = ag_catalog, '$user', public")
                
                # Ensure graph exists
                try:
                    await conn.execute("SELECT create_graph('financial_graph')")
                except:
                    pass  # Graph already exists
                
                if sync_companies:
                    # Sync entity_relations
                    query = """
                        SELECT er.source_company_id, er.target_company_id, 
                               er.relation_type, er.ownership_percentage,
                               c1.name_en as source_name, c2.name_en as target_name
                        FROM entity_relations er
                        JOIN companies c1 ON c1.id = er.source_company_id
                        JOIN companies c2 ON c2.id = er.target_company_id
                    """
                    if document_id:
                        query += f" WHERE er.document_id = {document_id}"
                    
                    relations = await conn.fetch(query)
                    
                    for r in relations:
                        rel_type = r['relation_type'].upper()
                        source_name = r['source_name'].replace("'", "\\'")
                        target_name = r['target_name'].replace("'", "\\'")
                        
                        await conn.execute(f"""
                            SELECT * FROM cypher('financial_graph', $$
                                MERGE (a:Company {{name: '{source_name}'}})
                                MERGE (b:Company {{name: '{target_name}'}})
                                MERGE (a)-[:{rel_type}]->(b)
                            $$) as (a agtype)
                        """)
                        stats["edges_created"] += 1
                    
                    stats["companies_synced"] = len(relations)
                
                if sync_personnel:
                    # Sync key_personnel
                    query = """
                        SELECT kp.name_en, kp.position_title_en, c.name_en as company_name
                        FROM key_personnel kp
                        JOIN companies c ON c.id = kp.company_id
                    """
                    if document_id:
                        query += f" WHERE kp.document_id = {document_id}"
                    
                    personnel = await conn.fetch(query)
                    
                    for p in personnel:
                        if not p['name_en']:
                            continue
                        
                        person_name = p['name_en'].replace("'", "\\'")
                        company_name = p['company_name'].replace("'", "\\'")
                        position = p['position_title_en'] or 'Executive'
                        
                        await conn.execute(f"""
                            SELECT * FROM cypher('financial_graph', $$
                                MERGE (p:Person {{name: '{person_name}'}})
                                MERGE (c:Company {{name: '{company_name}'}})
                                MERGE (p)-[:EXECUTIVE_OF {{position: '{position}'}}]->(c)
                            $$) as (a agtype)
                        """)
                        stats["personnel_synced"] += 1
            
            return json.dumps({
                "success": True,
                "message": "Sync completed",
                "stats": stats
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Failed to sync to graph: {e}")
            return json.dumps({
                "success": False,
                "error": str(e)
            }, ensure_ascii=False)


# Export tools
__all__ = [
    "InsertGraphNodeTool",
    "InsertGraphEdgeTool", 
    "QueryGraphTool",
    "SyncToGraphTool"
]
