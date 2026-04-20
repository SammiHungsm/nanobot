import asyncio
import asyncpg
import sys
import io

# Fix encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def check_db():
    conn = await asyncpg.connect('postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports')
    
    # 1. 检查 documents 表
    docs = await conn.fetch('SELECT id, doc_id, filename, processing_status FROM documents ORDER BY created_at DESC LIMIT 5')
    print('=== Documents (最近5条) ===')
    for d in docs:
        print(f'  {d["id"]}: {d["doc_id"]} ({d["filename"]}) - {d["processing_status"]}')
    
    # 2. 检查各表数量
    tables = [
        'document_tables', 'entity_relations', 'financial_metrics', 
        'market_data', 'revenue_breakdown', 'key_personnel', 
        'shareholding_structure', 'document_pages', 'document_chunks'
    ]
    print('\n=== 各表数量统计 ===')
    for table in tables:
        try:
            count = await conn.fetchval(f'SELECT COUNT(*) FROM {table}')
            print(f'  {table}: {count} 条')
        except Exception as e:
            print(f'  {table}: 错误 - {e}')
    
    # 3. 检查 processing_history
    history = await conn.fetch('SELECT * FROM document_processing_history ORDER BY created_at DESC LIMIT 15')
    print(f'\n=== document_processing_history (最近15条) ===')
    for h in history:
        print(f'  doc_id={h["document_id"]}: {h["stage"]} - {h["status"]} @ {h["created_at"]}')
    
    # 4. 检查 revenue_breakdown 数据
    revenue = await conn.fetch('SELECT * FROM revenue_breakdown LIMIT 5')
    print(f'\n=== revenue_breakdown (前5条) ===')
    for r in revenue:
        print(f'  company_id={r["company_id"]}, year={r["year"]}, segment={r["segment_name"]}, amount={r.get("revenue_amount")}')
    
    # 5. 检查 dynamic_attributes
    docs_attr = await conn.fetch('SELECT id, doc_id, dynamic_attributes FROM documents ORDER BY created_at DESC LIMIT 3')
    print(f'\n=== documents.dynamic_attributes ===')
    for d in docs_attr:
        print(f'  {d["doc_id"]}: {str(d["dynamic_attributes"])[:200]}...')
    
    await conn.close()

asyncio.run(check_db())
