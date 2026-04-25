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

print('=== ALL TABLES AND RECORD COUNTS ===')
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema='public' 
    ORDER BY table_name
""")
tables = [t[0] for t in cur.fetchall()]

for t in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        count = cur.fetchone()[0]
        print(f'{t}: {count}')
    except Exception as e:
        print(f'{t}: ERROR - {e}')

print()
print('=== TABLES WITH DATA (> 0) ===')
for t in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        count = cur.fetchone()[0]
        if count > 0:
            print(f'✅ {t}: {count} records')
    except:
        pass

print()
print('=== TABLES WITH NO DATA (= 0) ===')
for t in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        count = cur.fetchone()[0]
        if count == 0:
            print(f'❌ {t}: 0 records')
    except:
        pass

print()
print('=== UNIQUE CONSTRAINTS (excluding primary keys) ===')
cur.execute("""
    SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE contype = 'u' AND conrelid::regclass NOT LIKE '%_pkey'
""")
for r in cur.fetchall():
    print(f'  {r}')

print()
print('=== CHECK CONSTRAINTS WITH ON CONFLICT ===')
# Find the insert statements that use ON CONFLICT
tables_to_check = ['revenue_breakdown', 'shareholding_structure', 'market_data', 'financial_metrics', 'key_personnel']
for table in tables_to_check:
    cur.execute(f"""
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = '{table}'::regclass AND contype = 'u'
    """)
    constraints = cur.fetchall()
    if constraints:
        print(f'{table}: UNIQUE constraints = {[c[0] for c in constraints]}')
    else:
        print(f'{table}: NO UNIQUE CONSTRAINTS (only primary key)')

cur.close()
conn.close()
