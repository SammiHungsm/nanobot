import re

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the market_data parameters section
old_params = '''"data_date": {"type": "string", "description": "Data date (YYYY-MM-DD format, e.g., '2023-12-31')"},
                "fiscal_period": {"type": "string", "description": "Fiscal period (e.g., 'FY2023'). If provided, overrides data_date and is converted to year-end date."},
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
    print("Fix applied: updated market_data parameters schema")
else:
    print("Old params pattern not found - checking if already fixed...")
    # Try to find what's currently there
    idx = content.find('"fiscal_period"')
    if idx >= 0:
        end = content.find('"source"', idx)
        if end >= 0:
            print("Current section:")
            print(content[idx-50:end+50])

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
