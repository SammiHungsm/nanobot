"""
Neo4j Schema Migration Script

在 PostgreSQL 的 entity_relations 表有數據之後，
運行此腳本將數據同步到 Neo4j。

Usage:
    python -m nanobot.graph.migration --source postgresql --target neo4j
    python -m nanobot.graph.migration --init-schema  # 初始化 Neo4j schema
"""

import asyncio
import os
import argparse
from typing import Optional

from loguru import logger
from neo4j import AsyncGraphDatabase


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# PostgreSQL connection would be imported from db_client
# from nanobot.ingestion.repository.db_client import DBClient


async def init_schema(driver):
    """
    初始化 Neo4j Schema
    
    創建必要的約束條件和索引，提升查詢效能。
    """
    constraints = [
        # Person 約束
        "CREATE CONSTRAINT person_name IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
        "CREATE CONSTRAINT person_name_zh IF NOT EXISTS FOR (p:Person) REQUIRE p.name_zh IS UNIQUE",
        
        # Company 約束
        "CREATE CONSTRAINT company_name IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE",
        "CREATE CONSTRAINT company_stock_code IF NOT EXISTS FOR (c:Company) REQUIRE c.stock_code IS UNIQUE",
        
        # Trust 約束
        "CREATE CONSTRAINT trust_name IF NOT EXISTS FOR (t:Trust) REQUIRE t.name IS UNIQUE",
    ]
    
    indexes = [
        # Person 索引
        "CREATE INDEX person_type IF NOT EXISTS FOR (p:Person) ON (p.person_type)",
        
        # Company 索引
        "CREATE INDEX company_sector IF NOT EXISTS FOR (c:Company) ON (c.sector)",
        
        # 關係索引
        "CREATE INDEX HOLDS_SHARE_percentage IF NOT EXISTS FOR ()-[r:HOLDS_SHARE]-() ON (r.percentage)",
        "CREATE INDEX CONTROLS_depth IF NOT EXISTS FOR ()-[r:CONTROLS]-() ON (r.depth)",
    ]
    
    async with driver.session() as session:
        # 創建約束
        for constraint in constraints:
            try:
                await session.run(constraint)
                logger.info(f"✅ Constraint: {constraint[:60]}...")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.debug(f"⏭️  Constraint already exists")
                else:
                    logger.warning(f"⚠️ Constraint failed: {e}")
        
        # 創建索引
        for index in indexes:
            try:
                await session.run(index)
                logger.info(f"✅ Index: {index[:60]}...")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.debug(f"⏭️  Index already exists")
                else:
                    logger.warning(f"⚠️ Index failed: {e}")


async def create_relationships(driver):
    """
    從 PostgreSQL 讀取 entity_relations 並寫入 Neo4j
    """
    from nanobot.ingestion.repository.db_client import DBClient
    
    db = DBClient.get_instance()
    await db.connect()
    
    async with db.connection() as conn:
        # 讀取所有 entity_relations
        relations = await conn.fetch("""
            SELECT 
                er.id,
                er.source_entity_type,
                er.source_entity_name,
                er.target_entity_type,
                er.target_entity_name,
                er.relation_type,
                er.relation_strength,
                er.event_year,
                d.doc_id
            FROM entity_relations er
            JOIN documents d ON er.document_id = d.id
        """)
    
    logger.info(f"📦 找到 {len(relations)} 條關係記錄")
    
    async with driver.session() as session:
        for rel in relations:
            try:
                await _create_neo4j_relationship(session, rel)
            except Exception as e:
                logger.warning(f"⚠️ Failed to create relationship: {e}")
    
    logger.info("✅ 關係數據已同步到 Neo4j")


async def _create_neo4j_relationship(session, rel):
    """創建單個 Neo4j 關係"""
    
    source_type = rel['source_entity_type']
    source_name = rel['source_entity_name']
    target_type = rel['target_entity_type']
    target_name = rel['target_entity_name']
    rel_type = rel['relation_type']
    
    # 映射關係類型到 Cypher 關係類型
    relation_mapping = {
        'appointed': 'APPOINTED_AS',
        'resigned': 'RESIGNED_FROM',
        'holds_share': 'HOLDS_SHARE',
        'controls': 'CONTROLS',
        'subsidiary_of': 'SUBSIDIARY_OF',
        'competitor': 'COMPETES_WITH',
        'partner': 'PARTNERS_WITH',
    }
    
    cypher_rel_type = relation_mapping.get(rel_type, 'RELATED_TO')
    
    # 創建源節點
    source_label = _map_entity_type(source_type)
    if source_label:
        await session.run(f"""
            MERGE (s:{source_label} {{name: $source_name}})
        """, source_name=source_name)
    
    # 創建目標節點
    target_label = _map_entity_type(target_type)
    if target_label:
        await session.run(f"""
            MERGE (t:{target_label} {{name: $target_name}})
        """, target_name=target_name)
    
    # 創建關係
    if source_label and target_label:
        props = {
            'relation_type': rel_type,
            'strength': rel.get('relation_strength', 1.0),
            'year': rel.get('event_year'),
            'doc_id': rel.get('doc_id'),
        }
        
        cypher = f"""
            MATCH (s:{source_label} {{name: $source_name}})
            MATCH (t:{target_label} {{name: $target_name}})
            MERGE (s)-[r:{cypher_rel_type}]->(t)
            SET r += $props
        """
        await session.run(cypher, source_name=source_name, target_name=target_name, props=props)


def _map_entity_type(entity_type: str) -> Optional[str]:
    """映射實體類型到 Neo4j Label"""
    mapping = {
        'person': 'Person',
        'company': 'Company',
        'trust': 'Trust',
        'location': 'Location',
        'event': 'Event',
    }
    return mapping.get(entity_type.lower())


async def sync_shareholding(driver):
    """
    將 PostgreSQL shareholding_structure 表同步到 Neo4j
    """
    from nanobot.ingestion.repository.db_client import DBClient
    
    db = DBClient.get_instance()
    await db.connect()
    
    async with db.connection() as conn:
        # 讀取 shareholding_structure
        holdings = await conn.fetch("""
            SELECT 
                ss.shareholder_name,
                ss.shareholder_type,
                ss.percentage,
                ss.shares_held,
                ss.is_controlling,
                ss.is_institutional,
                c.name_en as company_name,
                c.stock_code
            FROM shareholding_structure ss
            JOIN companies c ON ss.company_id = c.id
        """)
    
    logger.info(f"📦 找到 {len(holdings)} 條持股記錄")
    
    async with driver.session() as session:
        for holding in holdings:
            try:
                await _create_shareholding_relationship(session, holding)
            except Exception as e:
                logger.warning(f"⚠️ Failed to create shareholding: {e}")
    
    logger.info("✅ 持股數據已同步到 Neo4j")


async def _create_shareholding_relationship(session, holding):
    """創建持股關係"""
    
    person_name = holding['shareholder_name']
    company_name = holding['company_name']
    percentage = holding.get('percentage')
    is_institutional = holding.get('is_institutional', False)
    
    # 自動創建 Person 和 Company 節點
    person_label = 'Person'
    if is_institutional:
        person_label = 'InstitutionalInvestor'
    
    await session.run(f"""
        MERGE (p:{person_label} {{name: $person_name}})
    """, person_name=person_name)
    
    await session.run("""
        MERGE (c:Company {name: $company_name})
    """, company_name=company_name)
    
    # 創建持股關係
    await session.run("""
        MATCH (p:Person {name: $person_name})
        MATCH (c:Company {name: $company_name})
        MERGE (p)-[r:HOLDS_SHARE]->(c)
        SET r.percentage = $percentage,
            r.shares = $shares,
            r.is_controlling = $is_controlling
    """, 
        person_name=person_name,
        company_name=company_name,
        percentage=percentage,
        shares=holding.get('shares_held'),
        is_controlling=holding.get('is_controlling', False)
    )


async def main():
    parser = argparse.ArgumentParser(description="Neo4j Schema Migration")
    parser.add_argument("--init-schema", action="store_true", help="Initialize Neo4j schema")
    parser.add_argument("--sync-relations", action="store_true", help="Sync entity_relations from PostgreSQL")
    parser.add_argument("--sync-shareholding", action="store_true", help="Sync shareholding from PostgreSQL")
    parser.add_argument("--all", action="store_true", help="Run all migrations")
    
    args = parser.parse_args()
    
    async with AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        if args.init_schema or args.all:
            logger.info("🚀 Initializing Neo4j schema...")
            await init_schema(driver)
        
        if args.sync_relations or args.all:
            logger.info("🚀 Syncing entity_relations...")
            await create_relationships(driver)
        
        if args.sync_shareholding or args.all:
            logger.info("🚀 Syncing shareholding...")
            await sync_shareholding(driver)
        
        if not any([args.init_schema, args.sync_relations, args.sync_shareholding, args.all]):
            parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
