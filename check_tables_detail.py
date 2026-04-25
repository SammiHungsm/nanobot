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
print('=== RAW_ARTIFACTS - SAMPLE (type breakdown) ===')
cur.execute("""
    SELECT artifact_type, COUNT(*) 
    FROM raw_artifacts 
    GROUP BY artifact_type
""")
for r in cur.fetchall():
    print(f'  type={r[0]}, count={r[1]}')

print()
print('=== DOCUMENT_TABLES - SAMPLE ===')
cur.execute('SELECT id, document_id, table_type, section_title, page_num FROM document_tables ORDER BY id DESC LIMIT 5')
for r in cur.fetchall():
    print(f'  id={r[0]}, doc={r[1]}, type={r[2]}, section={r[3]}, page={r[4]}')

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

cur.close()
conn.close()
