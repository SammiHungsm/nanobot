import re
import sys

# Read the file
with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Update the parameters dict to add fiscal_period after data_date
old_data_date_param = '''"data_date": {"type": "string", "description": "Data date (YYYY-MM-DD format, e.g., '2023-12-31')"},'''
new_data_date_param = '''"data_date": {"type": "string", "description": "Data date (YYYY-MM-DD format, e.g., '2023-12-31')"},
                "fiscal_period": {"type": "string", "description": "Fiscal period (e.g., 'FY2023'). If provided, overrides data_date and is converted to year-end date."},'''
if old_data_date_param in content:
    content = content.replace(old_data_date_param, new_data_date_param, 1)
    print("Fix 1 applied: added fiscal_period to schema")
else:
    print("Fix 1 already applied or pattern not found")

# Fix 2: Update execute signature to include fiscal_period
old_sig = "async def execute(self, data_date: str, company_id: int = None, company_name: str = None,"
new_sig = "async def execute(self, data_date: str = None, fiscal_period: str = None, company_id: int = None, company_name: str = None,"
if old_sig in content:
    content = content.replace(old_sig, new_sig, 1)
    print("Fix 2 applied: added fiscal_period to execute signature")
else:
    print("Fix 2 already applied or pattern not found")

# Fix 3: Update the date parsing section to handle fiscal_period
old_date_parsing = '''            # 🌟 將字串日期轉換為 date 物件
            if isinstance(data_date, str):
                data_date_obj = datetime.strptime(data_date, "%Y-%m-%d").date()
            elif isinstance(data_date, date_type):
                data_date_obj = data_date
            else:
                data_date_obj = date_type.today()  # Fallback'''

new_date_parsing = '''            # 🌟 將字串日期轉換為 date 物件
            # 🌟 支持 fiscal_period 格式 (e.g., "FY2023" → "2023-12-31")
            resolved_data_date = data_date
            if not resolved_data_date and fiscal_period:
                # Convert "FY2023" → "2023-12-31"
                m = re.match(r'^FY(\\d{4})$', str(fiscal_period).strip())
                if m:
                    resolved_data_date = f"{m.group(1)}-12-31"
            
            if isinstance(resolved_data_date, str):
                data_date_obj = datetime.strptime(resolved_data_date, "%Y-%m-%d").date()
            elif isinstance(resolved_data_date, date_type):
                data_date_obj = resolved_data_date
            else:
                data_date_obj = date_type.today()  # Fallback'''

if old_date_parsing in content:
    content = content.replace(old_date_parsing, new_date_parsing, 1)
    print("Fix 3 applied: added fiscal_period date parsing")
else:
    print("Fix 3 already applied or pattern not found")

# Fix 4: Update required from ["data_date"] to ["data_date"] (now optional with fallback)
# Actually keep data_date required but fiscal_period can override

# Write back
with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("All fixes applied!")
