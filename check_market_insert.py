import re

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and print the current INSERT statement for market_data
# Look for the INSERT INTO market_data section
idx = content.find('INSERT INTO market_data')
if idx >= 0:
    # Print 30 lines around it
    lines = content[idx:idx+2000].split('\n')[:25]
    for i, line in enumerate(lines):
        print(f"{i}: {line}")
