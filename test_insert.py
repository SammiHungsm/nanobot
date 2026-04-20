import asyncio
import asyncpg
import sys
import io

# Fix encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def test_insert():
    conn = await asyncpg.connect('postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports')
    
    try:
        # Test insert without metric_id
        result = await conn.execute(
            """
            INSERT INTO financial_metrics 
            (company_id, year, metric_name, value, unit, standardized_value, source_page)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            1,  # company_id
            2023,  # year
            "test_revenue",  # metric_name
            100000,  # value
            "HKD million",  # unit
            100000,  # standardized_value
            7  # source_page
        )
        print(f'✅ Insert successful: {result}')
        
        # Check the inserted row
        row = await conn.fetchrow('SELECT * FROM financial_metrics WHERE metric_name = $1', 'test_revenue')
        print(f'Inserted row: {dict(row)}')
        
        # Clean up
        await conn.execute('DELETE FROM financial_metrics WHERE metric_name = $1', 'test_revenue')
        print('✅ Cleaned up test row')
        
    except Exception as e:
        print(f'❌ Error: {e}')
    
    await conn.close()

asyncio.run(test_insert())
