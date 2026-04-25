content = open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'r', encoding='utf-8').read()

old = '# 🌟 將字串日期轉換為 date 物件\n            if isinstance(data_date, str):\n                data_date_obj = datetime.strptime(data_date, "%Y-%m-%d").date()\n            elif isinstance(data_date, date_type):\n                data_date_obj = data_date\n            else:\n                data_date_obj = date_type.today()  # Fallback'

new = '# 🌟 Extract year from fiscal_period\n            year_val = None\n            if fiscal_period:\n                import re as _re\n                m = _re.match(r"^FY?(\d{4})", str(fiscal_period))\n                if m:\n                    year_val = int(m.group(1))\n                elif len(str(fiscal_period)) == 4 and str(fiscal_period).isdigit():\n                    year_val = int(fiscal_period)'

if old in content:
    content = content.replace(old, new, 1)
    print('Applied: year extraction fix')
else:
    print('Pattern not found - may already be fixed')
    idx = content.find('year_val')
    print('year_val appears at positions:', [pos for pos in range(len(content)) if content[pos:pos+8] == 'year_val'])

open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'w', encoding='utf-8').write(content)
print('Done')
