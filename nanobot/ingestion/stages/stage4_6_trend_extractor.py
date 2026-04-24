"""
Stage 4.6: Multi-Year Trend Extractor
自動提取多年趨勢數據（2019-2023, 2014-2023 等）

功能：
1. 掃描 raw_artifacts 中包含多年數據的表格
2. 使用 LLM 識別並提取趨勢數據
3. 寫入 operational_metrics 表

觸發條件：
- 表格包含 3+ 個年份列（如 2019, 2020, 2021, 2022, 2023）
- 表格內容為數值型數據（營收、利潤、EPS 等）
"""

import re
import json
from typing import Dict, Any, List, Optional
from loguru import logger
from pathlib import Path

from nanobot.core.llm_core import get_llm_client, get_llm_model


class Stage4_6_TrendExtractor:
    """多年趨勢數據自動提取器"""
    
    # 年份模式：匹配 2010-2030
    YEAR_PATTERN = re.compile(r'\b(20[1-2][0-9])\b')
    
    # 最少年份數量（少於此數量不視為趨勢表）
    MIN_YEARS = 3
    
    # 數值指標關鍵詞
    METRIC_KEYWORDS = [
        'revenue', 'profit', 'ebitda', 'eps', 'dividend', 'dps',
        'assets', 'equity', 'debt', 'stores', 'stores', 'income',
        '營收', '利潤', '盈利', '股息', '資產', '負債', '門店'
    ]
    
    @classmethod
    async def extract_trends(
        cls,
        document_id: int,
        company_id: int,
        db_client,
        doc_id: str = None
    ) -> Dict[str, Any]:
        """
        主入口：提取多年趨勢數據
        
        Args:
            document_id: 文檔 ID
            company_id: 公司 ID
            db_client: 數據庫客戶端
            doc_id: 文檔標識符（可選）
        
        Returns:
            {
                "status": "success",
                "tables_processed": int,
                "metrics_extracted": int,
                "details": [...]
            }
        """
        logger.info(f"📊 Stage 4.6: 開始提取多年趨勢數據 (doc_id={doc_id})")
        
        # 1. 查詢所有表格 artifacts
        tables = await cls._fetch_trend_tables(db_client, document_id)
        
        if not tables:
            logger.info("   ⚠️ 未發現多年趨勢表格")
            return {
                "status": "success",
                "tables_processed": 0,
                "metrics_extracted": 0,
                "details": []
            }
        
        logger.info(f"   📋 發現 {len(tables)} 個潛在趨勢表格")
        
        # 2. 確保 operational_metrics 表存在
        await cls._ensure_table_exists(db_client)
        
        # 3. 提取每個表格的趨勢數據（限制前 5 個表格用於測試）
        total_extracted = 0
        extraction_details = []
        
        # 🌟 限制只處理前 5 個表格
        tables_to_process = tables[:5]
        
        for table in tables_to_process:
            try:
                result = await cls._extract_single_table(
                    table=table,
                    company_id=company_id,
                    document_id=document_id,
                    db_client=db_client
                )
                
                if result["extracted"] > 0:
                    total_extracted += result["extracted"]
                    extraction_details.append(result)
                    
            except Exception as e:
                logger.error(f"   ❌ 提取失敗 (page={table['page_num']}): {e}")
        
        logger.info(f"   ✅ Stage 4.6 完成: {total_extracted} 條趨勢數據")
        
        return {
            "status": "success",
            "tables_processed": len(tables),
            "metrics_extracted": total_extracted,
            "details": extraction_details
        }
    
    @classmethod
    async def _fetch_trend_tables(cls, db_client, document_id: int) -> List[Dict]:
        """查詢包含多年數據的表格"""
        
        # 查詢所有表格
        query = """
            SELECT artifact_id, page_num, parsed_data
            FROM raw_artifacts
            WHERE artifact_type = 'table'
            ORDER BY page_num
        """
        
        async with db_client.connection() as conn:
            rows = await conn.fetch(query)
        
        trend_tables = []
        
        for row in rows:
            parsed_data = row.get("parsed_data", {})
            if isinstance(parsed_data, str):
                try:
                    parsed_data = json.loads(parsed_data)
                except:
                    continue
            
            # 提取表格文本
            table_text = parsed_data.get("fixed", "") or parsed_data.get("original", "")
            
            if not table_text:
                continue
            
            # 檢測年份
            years = set(cls.YEAR_PATTERN.findall(table_text))
            years = [int(y) for y in years if 2010 <= int(y) <= 2030]
            years = sorted(years)
            
            # 檢測數值指標關鍵詞
            has_metric = any(kw.lower() in table_text.lower() for kw in cls.METRIC_KEYWORDS)
            
            # 判斷是否為趨勢表
            if len(years) >= cls.MIN_YEARS and has_metric:
                trend_tables.append({
                    "artifact_id": row["artifact_id"],
                    "page_num": row["page_num"],
                    "table_text": table_text,
                    "years": years
                })
        
        return trend_tables
    
    @classmethod
    async def _ensure_table_exists(cls, db_client):
        """確保 operational_metrics 表存在"""
        
        create_sql = """
            CREATE TABLE IF NOT EXISTS operational_metrics (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                document_id INTEGER REFERENCES documents(id),
                metric_type VARCHAR(100) NOT NULL,
                metric_name VARCHAR(255) NOT NULL,
                segment VARCHAR(255),
                year INTEGER NOT NULL,
                value NUMERIC(20, 2),
                unit VARCHAR(50),
                source_page INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_operational_metrics_company_year 
            ON operational_metrics(company_id, year);
            
            CREATE INDEX IF NOT EXISTS idx_operational_metrics_type 
            ON operational_metrics(metric_type);
        """
        
        async with db_client.connection() as conn:
            await conn.execute(create_sql)
    
    @classmethod
    async def _extract_single_table(
        cls,
        table: Dict,
        company_id: int,
        document_id: int,
        db_client
    ) -> Dict:
        """使用 LLM 提取單個表格的趨勢數據"""
        
        table_text = table["table_text"]
        years = table["years"]
        page_num = table["page_num"]
        
        # 構建 LLM prompt
        prompt = f"""Extract multi-year trend data from this financial/operational table.

**Table Content:**
```
{table_text[:4000]}
```

**Years Found:** {years}

**Instructions:**
1. Identify each metric/row in the table
2. Extract values for each year
3. Return JSON array with this format:

```json
[
  {{
    "metric_type": "group_revenue",  // Use snake_case: group_revenue, eps, dps, roe, net_debt, ports_revenue, retail_stores, etc.
    "metric_name": "Revenue",  // Original name from table
    "segment": "Total",  // Or segment name if applicable (e.g., "Europe", "H&B China")
    "year": 2023,
    "value": 275575,  // Numeric value only
    "unit": "HK$ million"  // Unit: HK$ million, HK$, %, stores, etc.
  }}
]
```

**Important:**
- Extract ALL years present in the table
- Use consistent metric_type naming (snake_case)
- If table has segments (regions, divisions), include segment name
- Skip headers, totals, and non-numeric rows
- Return ONLY the JSON array, no explanation

Extract now:"""

        # 調用 LLM
        try:
            from nanobot.core.llm_core import chat
            
            response = await chat(
                prompt=prompt,
                temperature=0.1,
                max_tokens=4000
            )
            
            content = response.strip() if isinstance(response, str) else str(response)
            
            logger.debug(f"   🤖 LLM response: {content[:200]}...")
            
            # 解析 JSON
            # 處理可能的 markdown 代碼塊
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            metrics = json.loads(content)
            
            if not isinstance(metrics, list):
                metrics = [metrics]
            
            # 插入數據庫
            inserted = 0
            for m in metrics:
                try:
                    await cls._insert_metric(
                        db_client=db_client,
                        company_id=company_id,
                        document_id=document_id,
                        metric=m,
                        source_page=page_num
                    )
                    inserted += 1
                except Exception as e:
                    logger.warning(f"      ⚠️ 插入失敗: {e}")
            
            logger.info(f"   📊 Page {page_num}: 提取 {inserted} 條 (years={years})")
            
            return {
                "page_num": page_num,
                "years": years,
                "extracted": inserted,
                "metrics": [m.get("metric_type") for m in metrics[:5]]  # 只顯示前 5 個
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"   ❌ JSON 解析失敗 (page={page_num}): {e}")
            return {"page_num": page_num, "years": years, "extracted": 0, "error": str(e)}
        
        except Exception as e:
            logger.error(f"   ❌ LLM 調用失敗 (page={page_num}): {e}")
            return {"page_num": page_num, "years": years, "extracted": 0, "error": str(e)}
    
    @classmethod
    async def _insert_metric(
        cls,
        db_client,
        company_id: int,
        document_id: int,
        metric: Dict,
        source_page: int
    ):
        """插入單條指標數據"""
        
        # 轉換 value 為數值
        value = metric.get("value")
        if isinstance(value, str):
            # 移除逗號和其他非數字字符（保留小數點和負號）
            value = value.replace(",", "").replace("%", "").strip()
            try:
                value = float(value)
            except:
                return
        
        if value is None:
            return
        
        insert_sql = """
            INSERT INTO operational_metrics 
            (company_id, document_id, metric_type, metric_name, segment, year, value, unit, source_page)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        
        async with db_client.connection() as conn:
            await conn.execute(
                insert_sql,
                company_id,
                document_id,
                metric.get("metric_type", "unknown"),
                metric.get("metric_name", ""),
                metric.get("segment"),
                metric.get("year"),
                value,
                metric.get("unit"),
                source_page
            )
