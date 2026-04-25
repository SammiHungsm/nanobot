import re

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The old INSERT block
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
                    kwargs.get("source")
                )'''

# The new INSERT block matching actual table schema
new_insert = '''# 🌟 Extract year from fiscal_period or data_date
            import re
            year_val = None
            fiscal_val = fiscal_period or str(data_date_obj.year) if data_date_obj else None
            if fiscal_val:
                m = re.match(r'^FY?(\\d{4})', str(fiscal_val))
                if m:
                    year_val = int(m.group(1))
                elif len(str(fiscal_val)) == 4 and str(fiscal_val).isdigit():
                    year_val = int(fiscal_val)
            
            async with db.connection() as conn:
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
                )'''

if old_insert in content:
    content = content.replace(old_insert, new_insert, 1)
    print("Fix applied: updated market_data INSERT to match schema")
else:
    print("Old INSERT pattern not found - may already be fixed or pattern changed")

with open('/app/nanobot/agent/tools/db_ingestion_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
