import asyncio
import asyncpg
import sys
import io

# Fix encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def clear_data():
    conn = await asyncpg.connect('postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports')
    
    # Clear tables
    tables = ['financial_metrics', 'market_data', 'revenue_breakdown', 'shareholding_structure', 
              'key_personnel', 'entity_relations']
    
    for table in tables:
        await conn.execute(f'TRUNCATE TABLE {table} CASCADE')
        print(f'✅ Cleared {table}')
    
    # Also clear documents
    await conn.execute('DELETE FROM documents')
    print('✅ Cleared documents')
    
    await conn.close()

asyncio.run(clear_data())
