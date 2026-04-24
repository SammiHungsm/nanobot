import sys
import asyncio
sys.path.insert(0, r"C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot")

import asyncio
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports')

async def run_stage9():
    from nanobot.ingestion.extractors.image_text_linker import ImageTextLinker
    from nanobot.ingestion.repository.db_client import DBClient
    
    print("=== Stage 9: ImageTextLinker ===\n")
    
    # Create DB client
    db = DBClient()
    await db.connect()
    
    # Run ImageTextLinker
    linker = ImageTextLinker(db_client=db)
    
    doc_id = 12
    print(f"Running for document_id={doc_id}...")
    
    try:
        links_count = await linker.link_image_and_text_context(document_id=doc_id)
        print(f"\n✅ artifact_relations created: {links_count} rows")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.close()

asyncio.run(run_stage9())
