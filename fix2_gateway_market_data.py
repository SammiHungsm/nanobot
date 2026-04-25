"""Fix market_data tool - version 2"""
import re

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Replace the data_date + other params with fiscal_period + correct params
# The actual current schema has data_date, period_type, pb_ratio, close_price, etc.
old_block = '''"data_date": {"type": "string", "description": "Data date (YYYY-MM-DD format, e.g., '2023-12-31')"},
                "period_type": {"type": ["string", "null"], "description": "Period type (e.g., 'daily', 'yearly')"},
                "pe_ratio": {"type": ["number", "null"], "description": "Price-to-Earnings ratio"},
                "pb_ratio": {"type": ["number", "null"], "description": "Price-to-Book ratio"},
                "market_cap": {"type": ["number", "null"], "description": "Market capitalization"},
                "close_price": {"type": ["number", "null"], "description": "Closing stock price"},
                "open_price": {"type": ["number", "null"], "description": "Opening stock price"},
                "high_price": {"type": ["number", "null"], "description": "High stock price"},
                "low_price": {"type": ["number", "null"], "description": "Low stock price"},
                "volume": {"type": ["integer", "null"], "description": "Trading volume"},
                "turnover": {"type": ["number", "null"], "description": "Turnover"},
                "dividend_yield": {"type": ["number", "null"], "description": "Dividend yield (%)"},
                "source": {"type": ["string", "null"], "description": "Data source"}'''

new_block = '''"fiscal_period": {"type": ["string", "null"], "description": "Fiscal period (e.g., 'FY2023' or '2023')."},
                "stock_price": {"type": ["number", "null"], "description": "Stock price (HKD)"},
                "market_cap": {"type": ["number", "null"], "description": "Market capitalization (HKD)"},
                "pe_ratio": {"type": ["number", "null"], "description": "Price-to-Earnings ratio"},
                "dividend_yield": {"type": ["number", "null"], "description": "Dividend yield (%)"},
                "additional_data": {"type": ["object", "null"], "description": "Additional market data as JSON object"}'''

if old_block in content:
    content = content.replace(old_block, new_block, 1)
    print("Fix 1 applied: updated params schema")
else:
    print("Fix 1: pattern not found")
    # Debug: print what we have around data_date
    idx = content.find('"data_date"')
    if idx >= 0:
        print("  -> Found data_date at", idx)
        print("  -> Next 300 chars:", repr(content[idx:idx+300]))

# Fix 2: Update description
old_desc = '"Required: company_id OR company_name, data_date.'
new_desc = '"Required: company_id OR company_name, fiscal_period.'
if old_desc in content:
    content = content.replace(old_desc, new_desc, 1)
    print("Fix 2 applied: updated description")
else:
    print("Fix 2: not found")

# Fix 3: Fix the INSERT statement - use the actual pattern from the file
old_insert = '''INSERT INTO market_data 
                    (company_id, data_date, period_type, pe_ratio, pb_ratio, market_cap,
                     close_price, open_price, high_price, low_price, volume, turnover,
                     dividend_yield, source)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    actual_company_id,  # 🌟 使用转换后的 ID
                    data_date_obj,  # 🌟 使用 date 物件
                    kwargs.get("period_type"),
                    kwargs.get("pe_ratio"),
                    kwargs.get("pb_ratio"),
                    kwargs.get("market_cap"),
                    kwargs.get("close_price"),
                    kwargs.get("open_price"),
                    kwargs.get("high_price"),
                    kwargs.get("low_price"),
                    kwargs.get("volume"),
                    kwargs.get("turnover"),
                    kwargs.get("dividend_yield"),
                    kwargs.get("source")'''

new_insert = '''INSERT INTO market_data 
                    (company_id, document_id, year, fiscal_period, stock_price, market_cap,
                     pe_ratio, dividend_yield, additional_data)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    actual_company_id,
                    document_id,
                    year_val,
                    fiscal_period,
                    kwargs.get("stock_price"),
                    kwargs.get("market_cap"),
                    kwargs.get("pe_ratio"),
                    kwargs.get("dividend_yield"),
                    kwargs.get("additional_data")'''

if old_insert in content:
    content = content.replace(old_insert, new_insert, 1)
    print("Fix 3 applied: updated INSERT")
else:
    print("Fix 3: pattern not found")
    # Debug: show what we have
    idx = content.find('INSERT INTO market_data')
    if idx >= 0:
        print("  -> Found INSERT at", idx)
        print("  -> Next 400 chars:", repr(content[idx:idx+400]))

# Fix 4: Update the year extraction and logger.info
old_year_extract = '''            # 🌟 將字串日期轉換為 date 物件
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

new_year_extract = '''            # 🌟 Extract year from fiscal_period
            year_val = None
            if fiscal_period:
                m = re.match(r'^FY?(\\d{4})', str(fiscal_period))
                if m:
                    year_val = int(m.group(1))
                elif len(str(fiscal_period)) == 4 and str(fiscal_period).isdigit():
                    year_val = int(fiscal_period)'''

if old_year_extract in content:
    content = content.replace(old_year_extract, new_year_extract, 1)
    print("Fix 4 applied: updated year extraction")
else:
    print("Fix 4: not found")

# Fix 5: Fix the logger.info
old_logger = 'logger.info(f"??寫入市場數據: company_id={actual_company_id}, date={data_date}")'
new_logger = 'logger.info(f"✅ 寫入市場數據: company_id={actual_company_id}, fiscal_period={fiscal_period}")'
if old_logger in content:
    content = content.replace(old_logger, new_logger, 1)
    print("Fix 5 applied: updated logger")
else:
    print("Fix 5: not found")

# Fix 6: Fix the return dict
old_return_data = '"data_date": data_date,'
new_return_data = '"fiscal_period": fiscal_period,'
if old_return_data in content:
    content = content.replace(old_return_data, new_return_data, 1)
    print("Fix 6 applied: updated return data")
else:
    print("Fix 6: not found")

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("All done!")
