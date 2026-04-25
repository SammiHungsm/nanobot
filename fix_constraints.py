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

constraints = [
    ("revenue_breakdown", "revenue_breakdown_company_year_segment_unique", 
     "(company_id, year, segment_name, segment_type)"),
    ("shareholding_structure", "shareholding_structure_unique", 
     "(company_id, year, shareholder_name)"),
    ("market_data", "market_data_unique", 
     "(company_id, year, fiscal_period)"),
    ("entity_relations", "entity_relations_unique", 
     "(source_company_id, target_company_id, relation_type)"),
    ("artifact_relations", "artifact_relations_unique", 
     "(source_artifact_id, target_artifact_id, relation_type)"),
]

for table, constraint_name, unique_cols in constraints:
    sql = f"""
    ALTER TABLE {table}
    ADD CONSTRAINT {constraint_name} UNIQUE {unique_cols};
    """
    try:
        cur.execute(sql)
        print(f"[OK] {table}: added {constraint_name}")
    except Exception as e:
        err = str(e)
        if "already exists" in err.lower() or "duplicate" in err.lower():
            print(f"[SKIP] {table}: constraint already exists")
        else:
            print(f"[ERROR] {table}: {e}")

cur.close()
conn.close()
print("\nDone!")
