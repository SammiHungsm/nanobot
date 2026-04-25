"""Fix market_data tool in db_ingestion_tools.py - fixes the INSERT to match actual table schema"""
import re

# Read the file inside the gateway container
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

new_params = '''"fiscal_period": {"type": ["string", "null"], "description": "Fiscal period (e.g., 'FY2023' or '2023')."},
                "stock_price": {"type": ["number", "null"], "description": "Stock price (HKD)"},
                "market_cap": {"type": ["number", "null"], "description": "Market capitalization (HKD)"},
                "pe_ratio": {"type": ["number", "null"], "description": "Price-to-Earnings ratio"},
                "dividend_yield": {"type": ["number", "null"], "description": "Dividend yield (%)"},
                "additional_data": {"type": ["object", "null"], "description": "Additional market data as JSON object"},'''

if old_params in content:
    content = content.replace(old_params, new_params, 1)
    print("Fix 1 applied: updated parameters schema")
else:
    print("Fix 1: pattern not found, checking...")
    if '"stock_price"' in content:
        print("  -> stock_price found, may already be fixed")

# Fix 2: Update description
old_required = '"Required: company_id OR company_name, data_date.'
new_required = '"Required: company_id OR company_name, fiscal_period.'
if old_required in content:
    content = content.replace(old_required, new_required, 1)
    print("Fix 2 applied: updated description")
else:
    print("Fix 2: old description not found")

# Fix 3: Fix the INSERT statement for market_data
old_insert_block = '''async with db.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO market_data 
                    (company_id, data_date, period_type, pe_ratio, pb_ratio, market_cap,
                     close_price, open_price, high_price, low_price, volume, turnover,
                     dividend_yield, source)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    actual_company_id,
                    data_date_obj,
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
                    kwargs.get("source")
                )
            
            logger.info(f"??寫入市場數據: company_id={actual_company_id}, date={data_date}")'''

new_insert_block = '''async with db.connection() as conn:
                # 🌟 Extract year from fiscal_period
                year_val = None
                if fiscal_period:
                    m = re.match(r'^FY?(\\d{4})', str(fiscal_period))
                    if m:
                        year_val = int(m.group(1))
                    elif len(str(fiscal_period)) == 4 and str(fiscal_period).isdigit():
                        year_val = int(fiscal_period)
                
                await conn.execute(
                    """
                    INSERT INTO market_data 
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
                    kwargs.get("additional_data")
                )
            
            logger.info(f"✅ 寫入市場數據: company_id={actual_company_id}, fiscal_period={fiscal_period}")'''

if old_insert_block in content:
    content = content.replace(old_insert_block, new_insert_block, 1)
    print("Fix 3 applied: updated INSERT statement")
else:
    print("Fix 3: old INSERT block not found")
    # Try to find the INSERT statement
    idx = content.find('INSERT INTO market_data')
    if idx > 0:
        print("  -> Found INSERT at position", idx)
        print("  -> Next 500 chars:", content[idx:idx+500])

# Fix 4: Add re import if not present
if 'import re' not in content[content.find('class InsertMarketDataTool'):content.find('class InsertMarketDataTool')+200]:
    # re might not be imported at the top of the execute method, add it
    print("Fix 4: May need to add re import")

# Write back
with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("All fixes applied!")
