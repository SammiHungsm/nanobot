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

print('=== DOCUMENTS TABLE (all) ===')
cur.execute('SELECT id, doc_id, filename, owner_company_id, processing_status FROM documents ORDER BY id DESC')
for r in cur.fetchall():
    print(f'  id={r[0]}, doc_id={r[1]}, filename={r[2]}, owner={r[3]}, status={r[4]}')

print()
print('=== RAW_ARTIFACTS - type breakdown ===')
cur.execute("""
    SELECT artifact_type, COUNT(*) 
    FROM raw_artifacts 
    GROUP BY artifact_type
""")
for r in cur.fetchall():
    print(f'  type={r[0]}, count={r[1]}')

print()
print('=== DOCUMENT_TABLES - columns ===')
cur.execute("""
    SELECT column_name FROM information_schema.columns 
    WHERE table_name = 'document_tables'
""")
cols = [c[0] for c in cur.fetchall()]
print(f'  Columns: {cols}')

print()
cur.execute('SELECT * FROM document_tables ORDER BY id DESC LIMIT 3')
rows = cur.fetchall()
for r in rows:
    print(f'  {r}')

print()
print('=== FINANCIAL_METRICS ===')
cur.execute('SELECT id, company_id, metric_type, year, value FROM financial_metrics ORDER BY id DESC LIMIT 5')
for r in cur.fetchall():
    print(f'  id={r[0]}, company={r[1]}, type={r[2]}, year={r[3]}, value={r[4]}')

print()
print('=== COMPANIES ===')
cur.execute('SELECT id, stock_code, name_en, name_tc FROM companies ORDER BY id DESC')
for r in cur.fetchall():
    print(f'  id={r[0]}, stock_code={r[1]}, name_en={r[2]}, name_tc={r[3]}')

print()
print('=== KEY_PERSONNEL ===')
cur.execute('SELECT COUNT(*) FROM key_personnel')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== SHAREHOLDING_STRUCTURE ===')
cur.execute('SELECT COUNT(*) FROM shareholding_structure')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== REVENUE_BREAKDOWN ===')
cur.execute('SELECT COUNT(*) FROM revenue_breakdown')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== MARKET_DATA ===')
cur.execute('SELECT COUNT(*) FROM market_data')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== DOCUMENT_PAGES ===')
cur.execute('SELECT COUNT(*) FROM document_pages')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== ENTITY_RELATIONS ===')
cur.execute('SELECT COUNT(*) FROM entity_relations')
print(f'  count={cur.fetchone()[0]}')

print()
print('=== ARTIFACT_RELATIONS ===')
cur.execute('SELECT COUNT(*) FROM artifact_relations')
print(f'  count={cur.fetchone()[0]}')

cur.close()
conn.close()
