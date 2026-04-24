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

print("=== doc_id=12 最終狀態 ===\n")

# documents table
cur.execute("""
    SELECT id, doc_id, filename, owner_company_id, processing_status
    FROM documents
    WHERE id = 12
""")
row = cur.fetchone()
print(f"documents: id={row[0]}, doc_id={row[1]}, owner_company_id={row[3]}, status={row[4]}")

# document_companies
print("\ndocument_companies:")
cur.execute("""
    SELECT c.name_en, dc.relation_type
    FROM document_companies dc
    JOIN companies c ON dc.company_id = c.id
    WHERE dc.document_id = 12
    ORDER BY dc.relation_type
""")
for r in cur.fetchall():
    print(f"  {r[1]}: {r[0]}")

# artifact_relations
cur.execute("SELECT COUNT(*) FROM artifact_relations WHERE document_id = 12")
print(f"\nartifact_relations: {cur.fetchone()[0]} rows")

cur.close()
conn.close()
