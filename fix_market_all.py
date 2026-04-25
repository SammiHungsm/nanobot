import re

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Update parameters - replace old market_data params block
old_params = '''"fiscal_period": {"type": "string", "description": "Fiscal period (e.g., 'FY2023'). If provided, overrides data_date and is converted to year-end date."},
                "period_type": {"type": ["string", "null"], "description": "Period type (e.g., 'daily', 'yearly')"},
                "pe_ratio": {"type": ["number", "null"], "description": "Price-to-Earnings ratio"},
                "pb_ratio": {"type": ["number", "null"], "description": "Price-to-Book ratio"},
                "market_cap": {"type": ["number", "null"], "description": "Market capitalization"},
                "close_price": {"type": ["number", "null"], "description": "Closing stock price"},
                "open_price": {"type": ["number", "null"], "description": "Opening stock price"},
                "high_price": {"type": ["number", "null"], "description": "High stock price"},
                "low_price": {"type": ["number", "null"], "description": "Low stock price"},
                "volume": {"type": ["number", "null"], "description": "Trading volume"},
                "turnover": {"type": ["number", "null"], "description": "Trading turnover"},
                "dividend_yield": {"type": ["number", "null"], "description": "Dividend yield (%)"},
                "source": {"type": ["string", "null"], "description": "Data source"},'''

new_params = '''"fiscal_period": {"type": ["string", "null"], "description": "Fiscal period (e.g., 'FY2023' or '2023'). Used to derive year."},
                "stock_price": {"type": ["number", "null"], "description": "Stock price (HKD)"},
                "market_cap": {"type": ["number", "null"], "description": "Market capitalization (HKD)"},
                "pe_ratio": {"type": ["number", "null"], "description": "Price-to-Earnings ratio"},
                "dividend_yield": {"type": ["number", "null"], "description": "Dividend yield (%)"},
                "additional_data": {"type": ["object", "null"], "description": "Additional market data as JSON object"},'''

if old_params in content:
    content = content.replace(old_params, new_params, 1)
    print("Fix 1 applied: updated parameters schema")
else:
    print("Fix 1: old params pattern not found")
    # Check if the new pattern already exists
    if '"stock_price"' in content:
        print("  -> stock_price found, may already be fixed")

# Fix 2: Update description to remove data_date requirement
old_desc = '"Required: company_id OR company_name, data_date.'
new_desc = '"Required: company_id OR company_name, fiscal_period (e.g. FY2023).'
if old_desc in content:
    content = content.replace(old_desc, new_desc, 1)
    print("Fix 2 applied: updated description")
else:
    print("Fix 2: old description not found")

# Fix 3: Remove data_date from required array
old_required = '"required": ["data_date"],'
new_required = '"required": [],'
if old_required in content:
    content = content.replace(old_required, new_required, 1)
    print("Fix 3 applied: data_date no longer required")
else:
    print("Fix 3: old required not found")

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("All parameter fixes done!")
