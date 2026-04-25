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

# Get all tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema='public' 
    ORDER BY table_name
""")
tables = [t[0] for t in cur.fetchall()]

print('=== ALL TABLES AND RECORD COUNTS ===')
for t in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        count = cur.fetchone()[0]
        print(f'{t}: {count}')
    except Exception as e:
        print(f'{t}: ERROR - {e}')

print()
print('=== DOCUMENTS TABLE (latest 5) ===')
cur.execute('SELECT id, doc_id, filename, owner_company_id, processing_status FROM documents ORDER BY id DESC LIMIT 5')
for r in cur.fetchall():
    print(f'  id={r[0]}, doc_id={r[1]}, filename={r[2]}, owner={r[3]}, status={r[4]}')

cur.close()
conn.close()
