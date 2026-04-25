import psycopg2
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(
    host='localhost',
    port=5433,
    database='annual_reports',
    user='postgres',
    password='postgres_password_change_me'
)
conn.autocommit = True
cur = conn.cursor()

tables_to_check = [
    'financial_metrics', 'key_personnel', 'shareholding_structure',
    'revenue_breakdown', 'market_data', 'document_pages',
    'entity_relations', 'artifact_relations', 'document_companies'
]

for table in tables_to_check:
    print(f'=== {table} columns ===')
    cur.execute(f"""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = '{table}'
        ORDER BY ordinal_position
    """)
    cols = [c[0] for c in cur.fetchall()]
    print(f'  {cols}')
    
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    count = cur.fetchone()[0]
    print(f'  count={count}')
    
    if count > 0:
        cur.execute(f'SELECT * FROM {table} LIMIT 1')
        row = cur.fetchone()
        print(f'  sample: {row}')
    print()

cur.close()
conn.close()
