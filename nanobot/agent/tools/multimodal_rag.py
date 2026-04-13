"""
Multimodal RAG Tools for Nanobot Agent

🎯 解決「圖表在第 5 頁，解釋在第 50 頁」的跨頁斷裂問題

核心功能：
1. get_chart_context - Runtime SQL JOIN，輸入圖片 ID，秒速獲取跨頁解釋文字
2. assemble_multimodal_prompt - 將圖片 + 跨頁文字組裝成完整 Prompt

技術架構：
- Step 1: Agent 識別用戶問題涉及圖表（例如：「圖 3 點解跌？」）
- Step 2: Agent 調用 get_chart_context(image_artifact_id) 工具
- Step 3: PostgreSQL 瞬間行 JOIN，0.01 秒將第 50 頁嗰段字嘔出來
- Step 4: Agent 攞住張圖 + 第 50 頁段字，完美解答

使用示例：
    from nanobot.agent.tools.multimodal_rag import get_chart_context, assemble_multimodal_prompt
    
    # Runtime Retrieval
    context = await get_chart_context("chart_page5_figure3", db_client)
    
    # 組裝 Prompt
    prompt = assemble_multimodal_prompt(
        image_description="Figure 3: Revenue trend chart showing decline from 2022 to 2023",
        context_text=context,
        user_question="為什麼圖 3 的營收會下跌？"
    )
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from loguru import logger
import asyncpg
import os


@dataclass
class ChartContextResult:
    """圖表關聯文字結果"""
    chart_artifact_id: str
    chart_page_num: int
    chart_content: Optional[str]  # 圖表的 Markdown 描述（如有）
    explanation_texts: List[Dict[str, Any]]  # 關聯的解釋文字列表
    assembled_prompt: str  # 組裝好的 Prompt


async def get_chart_context(
    image_artifact_id: str,
    db_url: str = None
) -> str:
    """
    🎯 [Step 3: SQL JOIN (Runtime Retrieval)]
    
    Agent 呼叫此工具，輸入圖片 ID，秒速獲取跨頁解釋文字
    
    核心邏輯：
    1. 從 artifact_relations 表查找圖表的關聯文字
    2. 使用 SQL JOIN 瞬間檢索（< 0.01 秒）
    3. 將所有相關文字合併為一個完整上下文
    
    Args:
        image_artifact_id: 圖表的 Artifact ID（例如："chart_page5_figure3")
        db_url: PostgreSQL 連接 URL
        
    Returns:
        str: 合併後的跨頁解釋文字，或提示訊息（如果找不到）
        
    Example:
        # 用戶問：「圖 3 點解跌？」
        context = await get_chart_context("chart_page5_figure3", db_url)
        
        # 返回：
        # "如圖 3 所示，本公司營收於 2023 年下跌 15%，
        #  主要原因為亞洲市場需求減弱及競爭加劇..."
    """
    if db_url is None:
        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
        )
    
    try:
        # 🚀 SQL JOIN - 瞬間檢索跨頁關聯
        conn = await asyncpg.connect(db_url)
        
        query = """
        SELECT 
            ra_target.content,
            ra_target.page_num,
            ar.confidence_score,
            ar.extraction_method
        FROM raw_artifacts ra_target
        JOIN artifact_relations ar ON ra_target.artifact_id = ar.target_artifact_id
        WHERE ar.source_artifact_id = $1
          AND ar.relation_type = 'explained_by'
        ORDER BY ar.confidence_score DESC, ra_target.page_num
        """
        
        rows = await conn.fetch(query, image_artifact_id)
        await conn.close()
        
        if not rows:
            return "資料庫中沒有找到與這張圖片相關的文字解釋。請嘗試使用其他工具（如全文搜索）查找相關內容。"
        
        # 將所有相關的跨頁文字合併
        context_parts = []
        for row in rows:
            page_num = row['page_num']
            content = row['content']
            confidence = row['confidence_score']
            extraction_method = row['extraction_method']
            
            context_parts.append(
                f"[第 {page_num} 頁] (置信度: {confidence:.2f}, 方法: {extraction_method})\n{content}"
            )
        
        full_context = "\n\n---\n\n".join(context_parts)
        
        logger.info(
            f"✅ 成功檢索 {len(rows)} 段跨頁解釋文字 "
            f"(來自第 {', '.join([str(r['page_num']) for r in rows])} 頁)"
        )
        
        return full_context
        
    except Exception as e:
        logger.error(f"❌ 檢索圖表關聯文字失敗: {e}")
        return f"檢索失敗: {str(e)}"


async def get_chart_context_with_db_client(
    image_artifact_id: str,
    db_client
) -> str:
    """
    🎯 使用 DBClient 版本（避免重新建立連接）
    
    Args:
        image_artifact_id: 圖表的 Artifact ID
        db_client: DBClient 實例
        
    Returns:
        str: 合併後的跨頁解釋文字
    """
    try:
        relations = await db_client.get_artifact_relations(
            image_artifact_id,
            direction="outgoing"
        )
        
        if not relations:
            return "資料庫中沒有找到與這張圖片相關的文字解釋。"
        
        context_parts = []
        for rel in relations:
            page_num = rel.get('page_num', '未知')
            content = rel.get('content', '')
            confidence = rel.get('confidence_score', 0.0)
            
            context_parts.append(f"[第 {page_num} 頁]\n{content}")
        
        full_context = "\n\n---\n\n".join(context_parts)
        
        logger.info(f"✅ 成功檢索 {len(relations)} 段跨頁解釋文字")
        return full_context
        
    except Exception as e:
        logger.error(f"❌ 檢索圖表關聯文字失敗: {e}")
        return f"檢索失敗: {str(e)}"


def assemble_multimodal_prompt(
    image_description: str,
    context_text: str,
    user_question: str,
    include_page_numbers: bool = True
) -> str:
    """
    🎯 [Step 4: 組裝 Prompt 畀 AI]
    
    將圖片描述 + 跨頁文字 + 用戶問題組裝成完整 Prompt
    
    Args:
        image_description: 圖表的描述（來自 Vision LLM 或人工標注）
        context_text: 跨頁解釋文字（來自 get_chart_context）
        user_question: 用戶的問題
        include_page_numbers: 是否包含頁碼提示
        
    Returns:
        str: 組裝好的完整 Prompt
        
    Example:
        prompt = assemble_multimodal_prompt(
            image_description="Figure 3: Revenue trend chart showing decline",
            context_text="如圖 3 所示，本公司營收於 2023 年下跌...",
            user_question="為什麼營收會下跌？"
        )
        
        # 返回：
        # [系統已為你檢索出與此圖片高度相關的文件背景文字]：
        # [第 50 頁] 如圖 3 所示，本公司營收於 2023 年下跌...
        # 
        # [圖表描述]：
        # Figure 3: Revenue trend chart showing decline
        # 
        # [用戶問題]：
        # 什麼營收會下跌？
        # 
        # [請結合上述資訊，準確回答用戶問題]
    """
    prompt_parts = [
        "[系統已為你檢索出與此圖片高度相關的文件背景文字，可能來自文件其他頁數]：",
        "",
        context_text,
        "",
        "---",
        "",
        "[圖表描述]：",
        image_description,
        "",
        "---",
        "",
        "[用戶問題]：",
        user_question,
        "",
        "[請結合圖表描述、上述背景文字，準確回答用戶的問題。]",
        "",
        "回答建議：",
        "1. 先引用圖表中的具體數據（如營收下跌百分比）",
        "2. 再引用背景文字中的解釋（如市場需求減弱）",
        "3. 如果背景文字不足以解釋，請明確指出並嘗試補充分析",
        "",
        "注意：避免幻覺，所有數據和解釋必須來自提供的資訊。"
    ]
    
    assembled_prompt = "\n".join(prompt_parts)
    
    logger.debug(f"📝 已組裝多模態 Prompt (長度: {len(assembled_prompt)} 字符)")
    return assembled_prompt


async def find_chart_by_figure_number(
    document_id: int,
    figure_number: str,
    db_url: str = None
) -> Optional[str]:
    """
    🎯 根據圖表編號（如 "3", "5A"）查找對應的 Artifact ID
    
    用於 Agent 解析用戶問題時，將 "圖 3" 轉換為具體的 artifact_id
    
    Args:
        document_id: 文檔 ID
        figure_number: 圖表編號（例如："3", "5A", "12B"）
        db_url: PostgreSQL 連接 URL
        
    Returns:
        str: Artifact ID，或 None（如果找不到）
        
    Example:
        # 用戶問：「圖 3 的營收點解跌？」
        # Agent 先調用此工具查找 "圖 3" 的 artifact_id
        artifact_id = await find_chart_by_figure_number(123, "3")
        
        # 然後調用 get_chart_context(artifact_id)
        context = await get_chart_context(artifact_id)
    """
    if db_url is None:
        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
        )
    
    try:
        conn = await asyncpg.connect(db_url)
        
        # 🚀 在 metadata 中查找包含 figure_number 的圖表
        query = """
        SELECT artifact_id
        FROM raw_artifacts
        WHERE document_id = $1
          AND artifact_type IN ('chart', 'image', 'table')
          AND (
            metadata->>'figure_number' = $2
            OR metadata->>'title' ILIKE '%' || $2 || '%'
            OR metadata->>'caption' ILIKE '%' || $2 || '%'
            OR content ILIKE '%Figure ' || $2 || '%'
            OR content ILIKE '%圖 ' || $2 || '%'
            OR content ILIKE '%Table ' || $2 || '%'
            OR content ILIKE '%表 ' || $2 || '%'
          )
        LIMIT 1
        """
        
        artifact_id = await conn.fetchval(query, document_id, figure_number)
        await conn.close()
        
        if artifact_id:
            logger.info(f"✅ 找到圖表 Figure {figure_number}: {artifact_id}")
            return artifact_id
        else:
            logger.warning(f"⚠️ 圖表 Figure {figure_number} 不存在於 Document {document_id}")
            return None
            
    except Exception as e:
        logger.error(f"❌ 查找圖表失敗: {e}")
        return None


class MultimodalRAGTools:
    """
    🎯 多模態 RAG 工具集
    
    提供完整的多模態檢索和組裝工具
    
    Example:
        tools = MultimodalRAGTools(db_url="postgresql://...")
        
        # 1. 查找圖表
        artifact_id = await tools.find_chart(123, "3")
        
        # 2. 檢索關聯文字
        context = await tools.get_context(artifact_id)
        
        # 3. 組裝 Prompt
        prompt = tools.assemble_prompt(
            image_desc="Figure 3: Revenue decline",
            context=context,
            question="為什麼營收下跌？"
        )
    """
    
    def __init__(self, db_url: str = None, db_client=None):
        """
        初始化
        
        Args:
            db_url: PostgreSQL 連接 URL（如果使用獨立連接）
            db_client: DBClient 實例（如果已有連接池）
        """
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
        )
        self.db_client = db_client
        
        logger.info("MultimodalRAGTools initialized")
    
    async def find_chart(self, document_id: int, figure_number: str) -> Optional[str]:
        """查找圖表 Artifact ID"""
        return await find_chart_by_figure_number(document_id, figure_number, self.db_url)
    
    async def get_context(self, artifact_id: str) -> str:
        """檢索圖表關聯文字"""
        if self.db_client:
            return await get_chart_context_with_db_client(artifact_id, self.db_client)
        else:
            return await get_chart_context(artifact_id, self.db_url)
    
    def assemble_prompt(self, image_desc: str, context: str, question: str) -> str:
        """組裝多模態 Prompt"""
        return assemble_multimodal_prompt(image_desc, context, question)


# ===========================================
# Agent Tool Registration Functions
# ===========================================

def get_multimodal_rag_tools_description() -> str:
    """
    返回工具描述（用於 Agent Skill 注册）
    
    Example:
        from nanobot.agent.tools.multimodal_rag import get_multimodal_rag_tools_description
        
        # 在 SKILL.md 中使用
        print(get_multimodal_rag_tools_description())
    """
    return """
## Multimodal RAG Tools

解決「圖表在第 5 頁，解釋在第 50 頁」的跨頁斷裂問題。

### Tools

1. **get_chart_context(image_artifact_id)** - Runtime SQL JOIN
   - 輸入：圖表的 Artifact ID
   - 輸出：跨頁解釋文字（合併多段）
   - 用於：用戶問「圖 3 點解跌？」時，檢索第 50 頁的解釋文字

2. **find_chart_by_figure_number(document_id, figure_number)** - 圖表查找
   - 輸入：文檔 ID + 圖表編號（如 "3"）
   - 輸出：對應的 Artifact ID
   - 用於：將用戶口中的「圖 3」轉換為具體 ID

3. **assemble_multimodal_prompt(image_desc, context, question)** - Prompt 組裝
   - 輸入：圖表描述 + 跨頁文字 + 用戶問題
   - 輸出：完整的多模態 Prompt
   - 用於：提供給 LLM 的完整上下文

### Workflow Example

用戶問：「圖 3 的營收為什麼下跌？」

Agent 思考流程：
1. 解析問題 → 識別 "圖 3"
2. 調用 find_chart_by_figure_number(123, "3") → 得到 "chart_page5_figure3"
3. 調用 get_chart_context("chart_page5_figure3") → 得到第 50 頁的解釋文字
4. 调用 assemble_multimodal_prompt(...) → 组装完整 Prompt
5. 发送给 LLM → 得到准确回答（无幻觉）

### 技術原理

- **入庫時 (Ingestion)**: EntityResolver.link_image_and_text_context() 使用 Regex 自动建立关联
- **Runtime 時**: artifact_relations 表提供 SQL JOIN 快速检索 (< 0.01秒)
"""


# ===========================================
# Test Functions
# ===========================================

if __name__ == "__main__":
    import asyncio
    
    print("Testing Multimodal RAG Tools...\n")
    
    # Test 1: Prompt Assembly
    print("1. Test Prompt Assembly:")
    prompt = assemble_multimodal_prompt(
        image_description="Figure 3: Revenue trend chart showing 15% decline from 2022 to 2023",
        context_text="[第 50 頁] 如圖 3 所示，本公司營收於 2023 年下跌 15%，主要原因為亞洲市場需求減弱。",
        user_question="為什麼營收會下跌？"
    )
    print(prompt[:500] + "...")
    
    # Test 2: Get Chart Context (需要 DB)
    print("\n2. Test Get Chart Context (requires database):")
    async def test_get_context():
        context = await get_chart_context("test_artifact_id")
        print(f"   Result: {context[:100]}...")
    
    asyncio.run(test_get_context())
    
    # Test 3: Find Chart (需要 DB)
    print("\n3. Test Find Chart (requires database):")
    async def test_find_chart():
        artifact_id = await find_chart_by_figure_number(1, "3")
        print(f"   Found: {artifact_id}")
    
    asyncio.run(test_find_chart())
    
    print("\n✅ Multimodal RAG Tools test complete!")