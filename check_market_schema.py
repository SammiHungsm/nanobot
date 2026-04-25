import psycopg2
conn = psycopg2.connect('postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports')
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'market_data' ORDER BY ordinal_position")
for r in cur.fetchall():
    print('%s: %s' % (r[0], r[1]))
conn.close()
