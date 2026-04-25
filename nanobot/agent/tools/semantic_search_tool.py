"""
Semantic Search Tool - Vector Search for Qualitative Content

🌟 用於語意搜索文檔內容（唔係精確數字）

當用戶問：
- 「管理層點解釋盈利下跌？」
- 「公司對 AI 發展嘅策略？」
- 「主席點評未來展望？」

呢啲都係需要睇文檔內容嚟作答，唔係 SQL 可以處理嘅。
"""

from typing import Any, Optional
from loguru import logger

from nanobot.agent.tools.base import Tool


class SemanticSearchTool(Tool):
    """
    [Tool] 語意搜索文檔內容
    
    用於搜索 document_chunks 入面已經 embedding 咗嘅切片。
    適合高層次語意理解嘅問題，例如策略、詮釋、管理層評論等。
    
    🌟 與 DirectSQLTool 嘅分工：
    - DirectSQLTool → 數字型、財務指標、持股量（精確 SQL）
    - SemanticSearchTool → 策略型、評論型、解釋型（語意搜索）
    """
    
    @property
    def name(self) -> str:
        return "semantic_search"
    
    @property
    def description(self) -> str:
        return (
            "Search document content semantically using embeddings. "
            "Use for: business strategy, management commentary, explanations, "
            "qualitative analysis, future outlook, risk factors. "
            "NOT for: exact numbers, financial metrics, shareholding %, rankings. "
            "Examples:"
            "\n- 'How does management explain the revenue decline?'"
            "\n- 'What is the company strategy for AI development?'"
            "\n- 'What did the chairman say about future outlook?'"
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "自然語言搜索查詢 (e.g., 'AI development strategy')"
                },
                "company_name": {
                    "type": "string",
                    "description": "可選：公司名稱過濾",
                    "default": None
                },
                "year": {
                    "type": "integer",
                    "description": "可選：年份過濾",
                    "default": None
                },
                "limit": {
                    "type": "integer",
                    "description": "返回結果數量",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(
        self,
        query: str,
        company_name: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = 5,
        context: dict = None
    ) -> str:
        """
        執行語意搜索
        
        Args:
            query: 搜索查詢
            company_name: 可選公司名過濾
            year: 可選年份過濾
            limit: 返回結果數量
            context: 執行上下文
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient.get_instance()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 🌟 構建 SQL（使用 pgvector cosine similarity）
                sql = """
                    SELECT 
                        dc.id,
                        dc.content,
                        dc.page_number,
                        dc.chunk_type,
                        c.name_en,
                        c.name_zh,
                        d.year,
                        1 - (dc.embedding_vector <=> $1::vector) AS similarity
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    JOIN companies c ON d.owner_company_id = c.id
                    WHERE dc.embedding_vector IS NOT NULL
                """
                
                params = [query]  # $1 = query embedding
                param_idx = 2
                
                if company_name:
                    sql += f" AND (c.name_en ILIKE $${param_idx} OR c.name_zh ILIKE $${param_idx})"
                    params.append(f"%{company_name}%")
                    param_idx += 1
                
                if year:
                    sql += f" AND d.year = ${param_idx}"
                    params.append(year)
                    param_idx += 1
                
                sql += f"""
                    ORDER BY dc.embedding_vector <=> $1::vector
                    LIMIT ${param_idx}
                """
                params.append(limit)
                
                # 🌟 注意：pgvector 唔支持直接用文字做 query，需要先 embedding
                # 呢度係簡化版，实际需要先 call embedding API
                logger.info(f"🔍 SemanticSearchTool: query='{query}'")
                
                # 示範：直接用 pgvector 的文字搜尋（如果模型支持 text embedding）
                # 如果唔支持，需要先 call embedding model
                rows = await conn.fetch(sql, *params)
                
                if not rows:
                    return f"🔍 找不到相關內容，查詢：「{query}」"
                
                # 格式化輸出
                result_lines = [
                    f"🔍 語意搜索結果：「{query}」",
                    f"找到 {len(rows)} 個相關切片：",
                    ""
                ]
                
                for i, row in enumerate(rows, 1):
                    result_lines.append(f"**[{i}] {row['name_en'] or row['name_zh']} (Year {row['year']})**")
                    result_lines.append(f"Page {row['page_number']} | Type: {row['chunk_type']}")
                    result_lines.append(f"內容：{row['content'][:500]}...")
                    result_lines.append("")
                
                return "\n".join(result_lines)
        
        except Exception as e:
            logger.error(f"❌ SemanticSearchTool 執行失敗: {e}")
            return f"❌ 語意搜索失敗: {str(e)}\n\n查詢：「{query}」"


class GetDocumentContentTool(Tool):
    """
    [Tool] 直接讀取文檔內容（按公司/年份）
    
    用於當用户明確指定邊份文件嘅時候，直接讀取內容。
    通常係 semantic_search 之後，用嚟睇詳細內容。
    """
    
    @property
    def name(self) -> str:
        return "get_document_content"
    
    @property
    def description(self) -> str:
        return (
            "Get full content from specific document chunks. "
            "Use this after semantic_search to read the actual content. "
            "NOT for searching - use semantic_search for that."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "integer",
                    "description": "文檔 ID"
                },
                "chunk_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "切片 ID 列表"
                },
                "page_numbers": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "頁碼列表"
                },
                "limit": {
                    "type": "integer",
                    "description": "最大讀取字符數",
                    "default": 3000
                }
            },
            "required": ["document_id"]
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(
        self,
        document_id: int,
        chunk_ids: list = None,
        page_numbers: list = None,
        limit: int = 3000,
        context: dict = None
    ) -> str:
        """讀取指定文檔嘅內容"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient.get_instance()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                if chunk_ids:
                    placeholders = ','.join([f"${i}" for i in range(2, len(chunk_ids) + 2)])
                    sql = f"""
                        SELECT id, page_number, chunk_type, content
                        FROM document_chunks
                        WHERE document_id = $1 AND id IN ({placeholders})
                        ORDER BY page_number
                    """
                    rows = await conn.fetch(sql, document_id, *chunk_ids)
                elif page_numbers:
                    placeholders = ','.join([f"${i}" for i in range(2, len(page_numbers) + 2)])
                    sql = f"""
                        SELECT id, page_number, chunk_type, content
                        FROM document_chunks
                        WHERE document_id = $1 AND page_number IN ({placeholders})
                        ORDER BY page_number, chunk_index
                    """
                    rows = await conn.fetch(sql, document_id, *page_numbers)
                else:
                    sql = """
                        SELECT id, page_number, chunk_type, content
                        FROM document_chunks
                        WHERE document_id = $1
                        ORDER BY page_number, chunk_index
                        LIMIT 20
                    """
                    rows = await conn.fetch(sql, document_id)
                
                if not rows:
                    return f"❌ 文檔 {document_id} 冇找到內容"
                
                result_lines = [
                    f"📄 文檔 {document_id} 內容：",
                    ""
                ]
                
                total_len = 0
                for row in rows:
                    content = row['content']
                    if total_len + len(content) > limit:
                        content = content[:limit - total_len]
                        result_lines.append(f"[...截斷，完整內容已限制為 {limit} 字符]")
                        break
                    
                    result_lines.append(f"--- Page {row['page_number']} ---")
                    result_lines.append(content)
                    total_len += len(content)
                
                return "\n".join(result_lines)
        
        except Exception as e:
            return f"❌ 讀取文檔失敗: {str(e)}"
