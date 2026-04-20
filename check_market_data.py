import asyncio
import asyncpg
import sys
import io

# Fix encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def check_market_data():
    conn = await asyncpg.connect('postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports')
    
    # 1. Check table structure
    cols = await conn.fetch("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'market_data'
        ORDER BY ordinal_position
    """)
    print('=== market_data 表结构 ===')
    for c in cols:
        print(f'  {c["column_name"]}: {c["data_type"]} (nullable={c["is_nullable"]})')
    
    # 2. Check data
    rows = await conn.fetch('SELECT * FROM market_data LIMIT 10')
    print(f'\n=== market_data 数据 (共 {len(rows)} 条) ===')
    for r in rows:
        print(f'  {dict(r)}')
    
    # 3. Check constraints
    constraints = await conn.fetch("""
        SELECT conname, pg_get_constraintdef(oid) 
        FROM pg_constraint 
        WHERE conrelid = 'market_data'::regclass
    """)
    print(f'\n=== market_data 约束 ===')
    for c in constraints:
        print(f'  {c["conname"]}: {c["pg_get_constraintdef"]}')
    
    await conn.close()

asyncio.run(check_market_data())
