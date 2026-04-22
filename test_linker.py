import asyncio
from nanobot.ingestion.extractors.image_text_linker import ImageTextLinker
from nanobot.ingestion.repository.db_client import DBClient

async def test_linker():
    db = DBClient()
    await db.connect()
    
    async with db.connection() as conn:
        doc_id = await conn.fetchval("SELECT id FROM documents LIMIT 1")
        print(f"Document ID: {doc_id}")
    
    linker = ImageTextLinker(db)
    count = await linker.link_image_and_text_context(document_id=doc_id)
    print(f"Links created: {count}")
    
    # Check artifact_relations
    async with db.connection() as conn:
        result = await conn.fetch("SELECT source_artifact_id, target_artifact_id, relation_type FROM artifact_relations")
        print(f"Artifact Relations: {len(result)} rows")
        for row in result:
            print(f"  {row['source_artifact_id']} -> {row['target_artifact_id']} ({row['relation_type']})")
    
    await db.close()

asyncio.run(test_linker())
