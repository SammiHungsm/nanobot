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

# Check revenue_breakdown table constraints
print('=== revenue_breakdown constraints ===')
cur.execute("""
    SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE conrelid = 'revenue_breakdown'::regclass
""")
for r in cur.fetchall():
    print(f'  {r}')

print()
print('=== revenue_breakdown indexes ===')
cur.execute("""
    SELECT indexname, indexdef
    FROM pg_indexes
    WHERE tablename = 'revenue_breakdown'
""")
for r in cur.fetchall():
    print(f'  {r}')

print()
print('=== shareholding_structure constraints ===')
cur.execute("""
    SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE conrelid = 'shareholding_structure'::regclass
""")
for r in cur.fetchall():
    print(f'  {r}')

print()
print('=== market_data constraints ===')
cur.execute("""
    SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE conrelid = 'market_data'::regclass
""")
for r in cur.fetchall():
    print(f'  {r}')

print()
print('=== financial_metrics constraints ===')
cur.execute("""
    SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE conrelid = 'financial_metrics'::regclass
""")
for r in cur.fetchall():
    print(f'  {r}')

print()
print('=== key_personnel constraints ===')
cur.execute("""
    SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE conrelid = 'key_personnel'::regclass
""")
for r in cur.fetchall():
    print(f'  {r}')

cur.close()
conn.close()
