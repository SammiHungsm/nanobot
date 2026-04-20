import asyncio
import asyncpg
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def check_all():
    conn = await asyncpg.connect('postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports')
    
    tables = [
        'documents',
        'financial_metrics', 
        'revenue_breakdown',
        'market_data',
        'shareholding_structure',
        'key_personnel',
        'entity_relations'
    ]
    
    for table_name in tables:
        try:
            count = await conn.fetchval(f'SELECT COUNT(*) FROM {table_name}')
            print(f'\n📊 {table_name}: {count} 條')
            if count > 0:
                rows = await conn.fetch(f'SELECT * FROM {table_name} LIMIT 3')
                for row in rows:
                    print(f'   {dict(row)}')
        except Exception as e:
            print(f'   ❌ Error: {e}')
    
    await conn.close()

asyncio.run(check_all())
