"""
Financial Tools for Nanobot Agent

Provides database query, document search, and entity resolution tools
for the financial analysis skill.

Tools:
1. query_financial_database - SQL queries for exact numbers
2. search_documents - Text search for policies/commentary
3. resolve_entity - CN/EN company name resolution
4. parse_financial_pdf - PDF parsing with OpenDataLoader
5. 🎯 v2.0: upsert_metric - Taxonomy-driven metric insertion (EAV + JSONB)
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger
from pathlib import Path

# Import storage layer
from ..storage.financial_storage import (
    PostgresStorage, 
    MongoDocumentStore, 
    FinancialMetric,
    create_storage,
    create_document_store
)

# Import entity resolver
from .entity_resolver import resolve_company, search_companies, list_all_companies

# Import PDF parser
from .pdf_parser import OpenDataLoaderPDF, ParsedPDF

# Import prompts (v2.0)
from ..ingestion.extractors.prompts import get_metric_extraction_prompt


@dataclass
class ToolResult:
    """Standard tool result format"""
    success: bool
    data: Any
    message: str
    citations: Optional[List[Dict]] = None


class FinancialTools:
    """
    Financial analysis tools for Nanobot agent.
    
    Example:
        tools = FinancialTools()
        result = tools.query_database("SELECT * FROM companies LIMIT 5")
        print(result.data)
    """
    
    def __init__(self, 
                 pg_url: Optional[str] = None,
                 mongo_url: Optional[str] = None):
        """
        Initialize financial tools.
        
        Args:
            pg_url: PostgreSQL connection URL
            mongo_url: MongoDB connection URL
        """
        self.pg_url = pg_url or "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
        self.mongo_url = mongo_url or "mongodb://mongo:mongo_password_change_me@localhost:27018/annual_reports"
        
        self._pg_storage: Optional[PostgresStorage] = None
        self._mongo_store: Optional[MongoDocumentStore] = None
        self._pdf_parser: Optional[OpenDataLoaderPDF] = None
        
        logger.info("FinancialTools initialized")
    
    @property
    def pg_storage(self) -> PostgresStorage:
        """Lazy load PostgreSQL storage"""
        if not self._pg_storage:
            self._pg_storage = create_storage(self.pg_url)
        return self._pg_storage
    
    @property
    def mongo_store(self) -> MongoDocumentStore:
        """Lazy load MongoDB store"""
        if not self._mongo_store:
            self._mongo_store = create_document_store(self.mongo_url)
        return self._mongo_store
    
    @property
    def pdf_parser(self) -> OpenDataLoaderPDF:
        """Get PDF parser"""
        if not self._pdf_parser:
            self._pdf_parser = OpenDataLoaderPDF(hybrid_mode=False)
        return self._pdf_parser
    
    # ========================================================================
    # Tool 1: Query Financial Database
    # ========================================================================
    
    def query_database(self, sql: str) -> ToolResult:
        """
        Execute SQL query against financial database.
        
        Use for: Exact numbers, rankings, trends, math operations
        
        Args:
            sql: SQL query string
        
        Returns:
            ToolResult with query results
        """
        try:
            logger.info(f"Executing SQL: {sql[:200]}...")
            results = self.pg_storage.query(sql)
            
            return ToolResult(
                success=True,
                data=results,
                message=f"Query returned {len(results)} rows",
                citations=self._extract_citations(results)
            )
        except Exception as e:
            logger.error(f"SQL query failed: {e}")
            return ToolResult(
                success=False,
                data=None,
                message=f"Query failed: {str(e)}"
            )
    
    def get_company_metrics(self, company_name: str, 
                           metric_name: Optional[str] = None,
                           year: Optional[int] = None) -> ToolResult:
        """
        Get metrics for a specific company.
        
        Args:
            company_name: Company name (CN or EN)
            metric_name: Optional metric filter (e.g., "Revenue")
            year: Optional year filter
        
        Returns:
            ToolResult with metrics
        """
        # Resolve company name
        entity = resolve_company(company_name)
        if not entity:
            return ToolResult(
                success=False,
                data=None,
                message=f"Company not found: {company_name}"
            )
        
        # Build SQL
        sql = """
            SELECT c.name_en, c.name_zh, c.stock_code,
                   m.year, m.metric_name, m.value, m.unit,
                   m.source_file, m.source_page
            FROM metric_records m
            JOIN companies c ON m.company_id = c.id
            WHERE c.name_en = :company_name
        """
        params = {'company_name': entity.name_en}
        
        if metric_name:
            sql += " AND m.metric_name = :metric_name"
            params['metric_name'] = metric_name
        
        if year:
            sql += " AND m.year = :year"
            params['year'] = year
        
        sql += " ORDER BY m.year DESC"
        
        try:
            results = self.pg_storage.query(sql, params)
            return ToolResult(
                success=True,
                data=results,
                message=f"Found {len(results)} metrics for {entity.name_en}",
                citations=self._extract_citations(results)
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                message=f"Query failed: {str(e)}"
            )
    
    def get_top_companies(self, metric_name: str = "Revenue",
                         year: int = 2023, limit: int = 10) -> ToolResult:
        """
        Get top N companies by metric.
        
        Args:
            metric_name: Metric to rank by
            year: Year to filter
            limit: Number of results
        
        Returns:
            ToolResult with rankings
        """
        results = self.pg_storage.get_top_companies(metric_name, year, limit)
        
        return ToolResult(
            success=True,
            data=results,
            message=f"Top {limit} companies by {metric_name} ({year})",
            citations=self._extract_citations(results)
        )
    
    # ========================================================================
    # Tool 2: Search Documents
    # ========================================================================
    
    def search_documents(self, query: str,
                        company_name: Optional[str] = None,
                        year: Optional[int] = None,
                        limit: int = 10) -> ToolResult:
        """
        Search documents by text.
        
        Use for: Policies, strategies, commentary, explanations
        
        Args:
            query: Search query
            company_name: Optional company filter
            year: Optional year filter
            limit: Max results
        
        Returns:
            ToolResult with matching documents
        """
        try:
            results = self.mongo_store.search_text(query, company_name, year, limit)
            
            return ToolResult(
                success=True,
                data=results,
                message=f"Found {len(results)} documents",
                citations=[{'source': r.get('source_file'), 'page': r.get('source_page')} 
                          for r in results]
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                message=f"Search failed: {str(e)}"
            )
    
    # ========================================================================
    # Tool 3: Resolve Entity
    # ========================================================================
    
    def resolve_entity(self, name: str) -> ToolResult:
        """
        Resolve company name to standard entity.
        
        Args:
            name: Company name or alias
        
        Returns:
            ToolResult with entity info
        """
        entity = resolve_company(name)
        
        if entity:
            return ToolResult(
                success=True,
                data={
                    'name_en': entity.name_en,
                    'name_zh': entity.name_zh,
                    'stock_code': entity.stock_code,
                    'industry': entity.industry,
                    'aliases_en': entity.aliases_en,
                    'aliases_zh': entity.aliases_zh
                },
                message=f"Resolved '{name}' → {entity.name_en}"
            )
        else:
            return ToolResult(
                success=False,
                data=None,
                message=f"Company not found: {name}"
            )
    
    def list_companies(self) -> ToolResult:
        """List all known companies"""
        companies = list_all_companies()
        
        return ToolResult(
            success=True,
            data=[{
                'name_en': c.name_en,
                'name_zh': c.name_zh,
                'stock_code': c.stock_code,
                'industry': c.industry
            } for c in companies],
            message=f"Found {len(companies)} companies"
        )
    
    # ========================================================================
    # Tool 4: Parse PDF
    # ========================================================================
    
    def parse_financial_pdf(self, pdf_path: str,
                           save_raw: bool = True) -> ToolResult:
        """
        Parse financial PDF with OpenDataLoader.
        
        Args:
            pdf_path: Path to PDF file
            save_raw: Save raw output files
        
        Returns:
            ToolResult with parsed content
        """
        try:
            result = self.pdf_parser.parse(pdf_path, save_raw=save_raw)
            
            return ToolResult(
                success=True,
                data={
                    'markdown': result.markdown[:5000],  # Limit size
                    'total_pages': result.total_pages,
                    'tables_count': len(result.tables),
                    'images_count': len(result.images),
                    'markdown_length': len(result.markdown)
                },
                message=f"Parsed {result.total_pages} pages, {len(result.tables)} tables"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                message=f"PDF parsing failed: {str(e)}"
            )
    
    # ========================================================================
    # 🎯 v2.0: Tool 5 - Taxonomy-Driven Metric Upsert (EAV + JSONB)
    # ========================================================================
    
    async def upsert_metric(
        self,
        company_id: int,
        year: int,
        standard_name: str,
        original_name: str,
        value: Any,
        unit: str
    ) -> ToolResult:
        """
        🎯 v2.0: 將標準化後的財務或人員指標寫入資料庫
        
        核心邏輯：
        1. **年度指標** → 寫入 financial_metrics (EAV 模型)
           - 例如：Revenue, Net Income, R&D Expenses（隨年度變化）
        2. **靜態屬性** → 寫入 companies.extra_data (JSONB 模型)
           - 例如：CEO, Auditor, Principal Banker（不隨年度變化）
        
        Args:
            company_id: 公司 ID
            year: 年份（靜態屬性時可忽略）
            standard_name: 標準化名稱（必須來自 Taxonomy）
            original_name: 原始名稱（供溯源）
            value: 數值或字符串
            unit: 單位
        
        Returns:
            ToolResult: 成功或失敗訊息
        """
        try:
            # 智能路由：判斷是年度指標還是靜態屬性
            static_attributes = [
                "chief_executive", "auditor", 
                "ultimate_controlling_shareholder", 
                "principal_banker"
            ]
            
            if standard_name in static_attributes:
                # 🔹 靜態屬性 → JSONB
                from ..ingestion.repository.db_client import DBClient
                
                db = DBClient(self.pg_url)
                await db.connect()
                
                success = await db.update_company_extra_data(
                    company_id=company_id,
                    attribute_key=standard_name,
                    attribute_value={
                        "original_name": original_name,
                        "value": str(value)
                    }
                )
                
                await db.close()
                
                if success:
                    return ToolResult(
                        success=True,
                        data={"company_id": company_id, "attribute": standard_name},
                        message=f"✅ 成功更新公司屬性: {standard_name} (原名: {original_name})"
                    )
                else:
                    return ToolResult(
                        success=False,
                        data=None,
                        message=f"❌ JSONB 寫入失敗: {standard_name}"
                    )
            
            else:
                # 🔹 年度指標 → EAV
                from ..ingestion.repository.db_client import DBClient
                import re
                
                db = DBClient(self.pg_url)
                await db.connect()
                
                # 🎯 數值清洗：處理千分位、貨幣符號、括號負數
                numeric_value = self._clean_numeric_value(value)
                
                # 如果清洗失敗，視為非數值型 → 寫入 JSONB
                if numeric_value is None:
                    success = await db.update_company_extra_data(
                        company_id=company_id,
                        attribute_key=standard_name,
                        attribute_value={
                            "original_name": original_name,
                            "value": str(value)
                        }
                    )
                    await db.close()
                    
                    return ToolResult(
                        success=True,
                        data={"company_id": company_id, "attribute": standard_name},
                        message=f"✅ 非數值型屬性已寫入 JSONB: {standard_name}"
                    )
                
                # 寫入 EAV 表
                success = await db.insert_financial_metric(
                    company_id=company_id,
                    year=year,
                    metric_name_raw=standard_name,  # 直接使用標準名稱
                    value=numeric_value,
                    unit=unit
                )
                
                await db.close()
                
                if success:
                    return ToolResult(
                        success=True,
                        data={"company_id": company_id, "year": year, "metric": standard_name},
                        message=f"✅ 成功寫入年度指標: {standard_name} = {numeric_value} {unit} (原名: {original_name})"
                    )
                else:
                    return ToolResult(
                        success=False,
                        data=None,
                        message=f"❌ EAV 寫入失敗: {standard_name}"
                    )
                    
        except Exception as e:
            logger.error(f"❌ upsert_metric 失敗: {e}")
            return ToolResult(
                success=False,
                data=None,
                message=f"❌ 寫入失敗: {str(e)}"
            )
    
    async def upsert_metrics_batch(
        self,
        company_id: int,
        year: int,
        metrics: List[Dict[str, Any]]
    ) -> ToolResult:
        """
        🎯 v2.0: 批量寫入標準化指標
        
        Args:
            company_id: 公司 ID
            year: 年份
            metrics: 指標列表 [{"standard_name": "...", "original_name": "...", "value": ..., "unit": "..."}]
            
        Returns:
            ToolResult: 成功寫入的數量
        """
        success_count = 0
        failed_count = 0
        
        for metric in metrics:
            result = await self.upsert_metric(
                company_id=company_id,
                year=year,
                standard_name=metric.get("standard_name"),
                original_name=metric.get("original_name"),
                value=metric.get("value"),
                unit=metric.get("unit", "HKD")
            )
            
            if result.success:
                success_count += 1
            else:
                failed_count += 1
        
        return ToolResult(
            success=failed_count == 0,
            data={"success_count": success_count, "failed_count": failed_count},
            message=f"✅ 成功寫入 {success_count}/{len(metrics)} 個指標"
        )
    
    def _clean_numeric_value(self, value: Any) -> Optional[float]:
        """
        🎯 數值清洗：處理千分位、貨幣符號、括號負數
        
        支持格式：
        - "1,500,000" → 1500000.0
        - "HKD 1.5M" → 1500000.0
        - "(1,500,000)" → -1500000.0
        - "-$1,500" → -1500.0
        - "USD 1.5 billion" → 1500000000.0
        
        Args:
            value: 原始數值（可能是字串、整數、浮點數）
            
        Returns:
            Optional[float]: 清洗後的數值，如果無法轉換則返回 None
        """
        import re
        
        # 如果已經是數值型，直接返回
        if isinstance(value, (int, float)):
            return float(value)
        
        if not isinstance(value, str):
            return None
        
        # 去除前後空白
        value_str = value.strip()
        
        # 檢測是否為括號表示的負數（會計慣例）
        is_negative = False
        if value_str.startswith('(') and value_str.endswith(')'):
            is_negative = True
            value_str = value_str[1:-1]  # 移除括號
        
        # 移除貨幣符號和文字
        value_str = re.sub(r'[HKD|USD|CNY|RMB|€|£|¥]', '', value_str, flags=re.IGNORECASE)
        
        # 處理數量級縮寫 (M = Million, B = Billion, K = Thousand)
        multiplier = 1.0
        if 'M' in value_str.upper() or 'million' in value_str.lower():
            multiplier = 1_000_000.0
            value_str = re.sub(r'[Mm](illion)?', '', value_str)
        elif 'B' in value_str.upper() or 'billion' in value_str.lower():
            multiplier = 1_000_000_000.0
            value_str = re.sub(r'[Bb](illion)?', '', value_str)
        elif 'K' in value_str.upper() or 'thousand' in value_str.lower():
            multiplier = 1_000.0
            value_str = re.sub(r'[Kk](thousand)?', '', value_str)
        
        # 移除千分位逗號
        value_str = value_str.replace(',', '')
        
        # 移除所有非數字字符（保留小數點和負號）
        value_str = re.sub(r'[^\d\.\-]', '', value_str)
        
        # 如果結果為空，返回 None
        if not value_str or value_str == '.' or value_str == '-':
            return None
        
        # 轉換為浮點數
        try:
            result = float(value_str) * multiplier
            
            # 應用括號負數標記
            if is_negative:
                result = -result
            
            return result
        except ValueError:
            return None
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _extract_citations(self, results: List[Dict]) -> List[Dict]:
        """Extract citations from query results"""
        citations = []
        for row in results[:10]:  # Limit citations
            if 'source_file' in row or 'source_page' in row:
                citations.append({
                    'source': row.get('source_file'),
                    'page': row.get('source_page'),
                    'table': row.get('source_table_id')
                })
        return citations


# Global instance
_tools: Optional[FinancialTools] = None


def get_tools() -> FinancialTools:
    """Get global financial tools instance"""
    global _tools
    if not _tools:
        _tools = FinancialTools()
    return _tools


# Convenience functions for skill use
def query_db(sql: str) -> ToolResult:
    """Quick database query"""
    return get_tools().query_database(sql)


def search_docs(query: str) -> ToolResult:
    """Quick document search"""
    return get_tools().search_documents(query)


def resolve(name: str) -> ToolResult:
    """Quick entity resolution"""
    return get_tools().resolve_entity(name)


def parse_pdf(path: str) -> ToolResult:
    """Quick PDF parsing"""
    return get_tools().parse_financial_pdf(path)


async def upsert(company_id: int, year: int, standard_name: str, 
                 original_name: str, value: Any, unit: str) -> ToolResult:
    """Quick metric upsert (v2.0)"""
    tools = get_tools()
    return await tools.upsert_metric(company_id, year, standard_name, 
                                     original_name, value, unit)


if __name__ == "__main__":
    # Test tools
    print("Testing Financial Tools...\n")
    
    tools = FinancialTools()
    
    # Test 1: List companies
    print("1. List Companies:")
    result = tools.list_companies()
    print(f"   {result.message}")
    if result.data:
        for c in result.data[:3]:
            print(f"   - {c['name_en']} ({c['stock_code']})")
    
    # Test 2: Query database
    print("\n2. Query Database:")
    result = tools.query_database("SELECT COUNT(*) as count FROM companies")
    print(f"   Companies in DB: {result.data[0]['count']}")
    
    # Test 3: Entity resolution
    print("\n3. Entity Resolution:")
    for name in ["腾讯", "Alibaba", "恒生"]:
        result = tools.resolve_entity(name)
        if result.success:
            print(f"   ✓ {name:10} → {result.data['name_en']}")
    
    # Test 4: Search documents (empty DB)
    print("\n4. Search Documents:")
    result = tools.search_documents("strategy")
    print(f"   {result.message}")
    
    # Test 5: Upsert metric (v2.0)
    print("\n5. Upsert Metric (v2.0):")
    import asyncio
    result = asyncio.run(tools.upsert_metric(
        company_id=1,
        year=2023,
        standard_name="revenue",
        original_name="Total Revenue",
        value=1500000,
        unit="HKD"
    ))
    print(f"   {result.message}")
    
    print("\n✅ Financial Tools test complete!")
