import asyncio
import asyncpg
import sys
import io

# Fix encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def check_all_tables():
    conn = await asyncpg.connect('postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports')
    
    tables = ['key_personnel', 'shareholding_structure', 'entity_relations']
    
    for table in tables:
        cols = await conn.fetch(f"""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = '{table}'
            ORDER BY ordinal_position
        """)
        print(f'\n=== {table} 表结构 ===')
        for c in cols:
            print(f'  {c["column_name"]}: {c["data_type"]} (nullable={c["is_nullable"]})')
        
        # Check data count
        count = await conn.fetchval(f'SELECT COUNT(*) FROM {table}')
        print(f'  数据量: {count} 条')
    
    await conn.close()

asyncio.run(check_all_tables())
