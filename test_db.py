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

print("=== financial_metrics 詳細分析 ===\n")

# Check which companies have financial_metrics
print("--- financial_metrics companies ---")
cur.execute("""
    SELECT company_id, COUNT(*) as cnt
    FROM financial_metrics
    GROUP BY company_id
    ORDER BY company_id
""")
for r in cur.fetchall():
    print(f"  company_id={r[0]}: {r[1]} rows")

# Check what metric_names are in financial_metrics for CK Hutchison
print("\n--- financial_metrics metric_names (company_id=1) ---")
cur.execute("""
    SELECT DISTINCT metric_name, year
    FROM financial_metrics
    WHERE company_id = 1
    ORDER BY metric_name, year
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# Compare: operational_metrics has these, financial_metrics doesn't?
print("\n--- financial_metrics vs operational_metrics metric_names ---")
cur.execute("""
    SELECT DISTINCT metric_name FROM financial_metrics
    UNION
    SELECT DISTINCT metric_type FROM operational_metrics
""")
all_metrics = [r[0] for r in cur.fetchall()]
print(f"All unique metrics: {all_metrics}")

# Check source_document_id for financial_metrics
print("\n--- financial_metrics source_document_id (company_id=1) ---")
cur.execute("""
    SELECT DISTINCT source_document_id, year, COUNT(*)
    FROM financial_metrics
    WHERE company_id = 1
    GROUP BY source_document_id, year
""")
for r in cur.fetchall():
    print(f"  doc_id={r[0]}, year={r[1]}, {r[2]} rows")

cur.close()
conn.close()
