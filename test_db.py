import psycopg2
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(
    host="localhost",
    port=5433,
    database="annual_reports",
    user="postgres",
    password="postgres_password_change_me"
)
conn.autocommit = True
cur = conn.cursor()

print("=== documents table ===")
cur.execute("""
    SELECT id, doc_id, filename, owner_company_id, processing_status
    FROM documents
    ORDER BY id DESC
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"  id={r[0]}, doc_id={r[1]}, filename={r[2]}, owner={r[3]}, status={r[4]}")

cur.close()
conn.close()
