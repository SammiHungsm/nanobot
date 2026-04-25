import re

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the problematic block - the market_data INSERT area that got messed up
# We need to find and fix the section between "async with db.connection()" and the next INSERT

# First, let's find where the messed up section starts
pattern = r'(async with db\.connection\(\) as conn:\s+await conn\.execute\(\s+"""\s+# 🌟 Extract year)'
match = re.search(pattern, content)
if match:
    start = match.start()
    # Find the next occurrence of the logger.info after the INSERT
    # We want to replace everything from async with to the logger.info
    end_pattern = r'(logger\.info\(f"✅ 寫入市場數據)'
    end_match = re.search(end_pattern, content[start:])
    if end_match:
        end = start + end_match.start()
        # Get the block to replace
        old_block = content[start:end]
        print("Found messy block, length:", len(old_block))
        print("First 200 chars:", old_block[:200])
        
        # Create the correct replacement
        new_block = '''async with db.connection() as conn:
                # 🌟 Extract year from fiscal_period
                year_val = None
                fiscal_val = fiscal_period
                if fiscal_val:
                    m = re.match(r'^FY?(\\d{4})', str(fiscal_val))
                    if m:
                        year_val = int(m.group(1))
                    elif len(str(fiscal_val)) == 4 and str(fiscal_val).isdigit():
                        year_val = int(fiscal_val)
                
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
            
            logger.info(f"✅ 寫入市場數據: company_id={actual_company_id}, fiscal_period={fiscal_period}")
'''
        content = content[:start] + new_block + content[end:]
        print("Block replaced successfully!")
    else:
        print("Could not find end of block")
else:
    print("Could not find messy block")

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
