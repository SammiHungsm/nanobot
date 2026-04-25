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

print('=== DOCUMENT_PROCESSING_HISTORY ===')
cur.execute('SELECT * FROM document_processing_history ORDER BY id DESC LIMIT 10')
for r in cur.fetchall():
    print(f'  {r}')

print()
print('=== DOCUMENTS TABLE ===')
cur.execute('SELECT id, doc_id, filename, processing_status, processing_error FROM documents ORDER BY id DESC')
for r in cur.fetchall():
    print(f'  id={r[0]}, doc_id={r[1]}, filename={r[2]}, status={r[3]}, error={r[4]}')

print()
print('=== FINANCIAL_METRICS DETAIL ===')
cur.execute('SELECT id, document_id, company_id, metric_name, year, value FROM financial_metrics ORDER BY id DESC LIMIT 10')
for r in cur.fetchall():
    print(f'  id={r[0]}, doc={r[1]}, company={r[2]}, metric={r[3]}, year={r[4]}, value={r[5]}')

cur.close()
conn.close()
