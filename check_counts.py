import psycopg2
conn = psycopg2.connect('postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports')
cur = conn.cursor()
tables = ['revenue_breakdown', 'shareholding_structure', 'market_data', 'financial_metrics', 'key_personnel', 'raw_artifacts', 'document_tables']
for t in tables:
    cur.execute('SELECT COUNT(*) FROM ' + t)
    cnt = cur.fetchone()[0]
    print('%s: %d' % (t, cnt))
conn.close()
