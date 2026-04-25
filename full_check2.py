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

print('=== UNIQUE CONSTRAINTS ===')
cur.execute("""
    SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE contype = 'u'
""")
for r in cur.fetchall():
    print(f'  {r}')

print()
print('=== FINANCIAL_METRICS SAMPLE ===')
cur.execute('SELECT id, document_id, company_id, metric_name, year, value FROM financial_metrics ORDER BY id DESC LIMIT 5')
for r in cur.fetchall():
    print(f'  {r}')

print()
print('=== SHAREHOLDING_STRUCTURE SAMPLE ===')
cur.execute('SELECT id, document_id, company_id, shareholder_name, share_percentage FROM shareholding_structure ORDER BY id DESC LIMIT 5')
for r in cur.fetchall():
    print(f'  {r}')

print()
print('=== REVENUE_BREAKDOWN SAMPLE ===')
cur.execute('SELECT COUNT(*) FROM revenue_breakdown')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== MARKET_DATA SAMPLE ===')
cur.execute('SELECT COUNT(*) FROM market_data')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== ENTITY_RELATIONS SAMPLE ===')
cur.execute('SELECT COUNT(*) FROM entity_relations')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== ARTIFACT_RELATIONS SAMPLE ===')
cur.execute('SELECT COUNT(*) FROM artifact_relations')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== DOCUMENT_COMPANIES SAMPLE ===')
cur.execute('SELECT COUNT(*) FROM document_companies')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== CHECKING TABLE SCHEMAS FOR UNIQUE CONSTRAINTS NEEDED ===')
tables_to_check = ['revenue_breakdown', 'shareholding_structure', 'market_data']
for table in tables_to_check:
    print(f'\n{table}:')
    cur.execute(f"""
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = '{table}'::regclass
    """)
    constraints = cur.fetchall()
    for c in constraints:
        print(f'  {c}')

cur.close()
conn.close()
