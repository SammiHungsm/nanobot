"""
Content Builder - 统一的内容拼接构建工具

提供统一的内容拼接接口，支持：
- 按页码构建内容文本
- 按数据类型分组构建
- 表格和文本的混合拼接
- 截断和长度控制

使用方式：
```python
from nanobot.ingestion.utils.content_builder import (
    build_page_content_text,
    build_content_by_pages,
    build_tables_content,
    CONTENT_SEPARATOR
)

# 从指定页面构建内容
content = build_page_content_text(artifacts, page_nums=[1, 2, 3])

# 构建用户消息（带路由提示）
user_message = build_content_for_agent(
    artifacts,
    candidate_pages=candidate_pages,
    routing_hint="revenue_breakdown: 第 5, 10 页"
)
```
"""

from typing import Dict, List, Any, Optional, Callable
from loguru import logger


# 默认的分隔符
CONTENT_SEPARATOR = "\n\n"
PAGE_SEPARATOR = "\n\n=== Page {page} ===\n\n"
TABLE_PREFIX = "**Table @ Page {page}**\n\n"
IMAGE_PREFIX = "**Image @ Page {page}**\n\n"
TEXT_PREFIX = "**Text @ Page {page}**\n\n"


def build_page_content_text(
    artifacts: List[Dict[str, Any]],
    page_nums: List[int],
    prefix: str = PAGE_SEPARATOR,
    max_chars_per_page: int = 10000,
    content_getter: Optional[Callable[[Dict], str]] = None
) -> str:
    """
    从指定页面构建内容文本
    
    Args:
        artifacts: 所有 artifact 列表
        page_nums: 要包含的页面编号列表（从 1 开始）
        prefix: 每个页面的前缀格式，默认 "=== Page X ==="
        max_chars_per_page: 每页最大字符数
        content_getter: 可选的自定义内容提取函数
        
    Returns:
        str: 拼接后的内容文本
        
    Example:
        >>> artifacts = [{"page": 1, "type": "text", "content": "Hello"}, ...]
        >>> build_page_content_text(artifacts, [1, 2])
        '=== Page 1 ===\\n\\nHello\\n\\n=== Page 2 ===\\n\\nWorld'
    """
    content_parts = []
    
    for page_num in sorted(page_nums):
        if page_num <= 0 or page_num > len(artifacts):
            continue
            
        artifact = artifacts[page_num - 1]  # 页码从 1 开始，索引从 0 开始
        if artifact is None:
            continue
            
        # 获取内容
        if content_getter:
            content = content_getter(artifact)
        else:
            content = _get_artifact_content(artifact)
        
        if content:
            page_prefix = prefix.format(page=page_num)
            truncated_content = content[:max_chars_per_page]
            content_parts.append(f"{page_prefix}{truncated_content}")
    
    return CONTENT_SEPARATOR.join(content_parts)


def _get_artifact_content(artifact: Dict[str, Any]) -> str:
    """
    从 artifact 中提取文本内容
    
    支持的字段优先级：
    1. content
    2. markdown
    3. text
    """
    if artifact is None:
        return ""
    
    content = (
        artifact.get("content", "") or 
        artifact.get("markdown", "") or 
        artifact.get("text", "") or
        ""
    )
    
    # 如果是表格，尝试序列化为字符串
    if artifact.get("type") == "table":
        table_content = artifact.get("content_json", {}) or artifact.get("content", {})
        if isinstance(table_content, dict):
            import json
            try:
                content = json.dumps(table_content, ensure_ascii=False, default=str)
            except Exception:
                content = str(table_content)
    
    return str(content)


def build_content_by_pages(
    artifacts: List[Dict[str, Any]],
    start_page: int = 1,
    end_page: Optional[int] = None,
    max_chars: int = 50000,
    prefix: str = PAGE_SEPARATOR
) -> str:
    """
    构建指定页面范围的内容文本
    
    Args:
        artifacts: 所有 artifact 列表
        start_page: 起始页码（从 1 开始）
        end_page: 结束页码（如果为 None，则到最后一页）
        max_chars: 最大总字符数
        prefix: 页面前缀
        
    Returns:
        str: 拼接后的内容文本
    """
    if end_page is None:
        end_page = len(artifacts)
    
    page_nums = list(range(start_page, end_page + 1))
    content = build_page_content_text(artifacts, page_nums, prefix)
    
    # 截断
    if len(content) > max_chars:
        content = content[:max_chars] + f"\n\n... (内容已截断，原始长度 {len(content)} 字符)"
    
    return content


def build_candidate_pages_content(
    artifacts: List[Dict[str, Any]],
    candidate_pages: Dict[str, List[int]],
    max_pages: int = 50,
    max_chars_per_page: int = 5000
) -> tuple[str, str]:
    """
    从候选页面构建内容（用于 Agent）
    
    Args:
        artifacts: 所有 artifact 列表
        candidate_pages: {data_type: [page_nums]} 格式的候选页面
        max_pages: 最大页面数
        max_chars_per_page: 每页最大字符数
        
    Returns:
        tuple: (content_text, routing_hint)
        - content_text: 构建的内容文本
        - routing_hint: 路由提示字符串
    """
    # 合并所有候选页面
    all_candidate_page_nums = set()
    for pages in candidate_pages.values():
        all_candidate_page_nums.update(pages)
    
    sorted_pages = sorted(all_candidate_page_nums)[:max_pages]
    
    # 构建路由提示
    routing_parts = []
    for data_type, pages in candidate_pages.items():
        if pages:
            pages_str = ", ".join(map(str, sorted(pages)[:10]))
            if len(pages) > 10:
                pages_str += "..."
            routing_parts.append(f"- {data_type}: 第 {pages_str}")
    
    routing_hint = "\n".join(routing_parts)
    
    # 构建内容
    content_text = build_page_content_text(
        artifacts, 
        sorted_pages, 
        max_chars_per_page=max_chars_per_page
    )
    
    return content_text, routing_hint


def build_tables_content(
    tables: List[Dict[str, Any]],
    max_tables: int = 8,
    max_chars_per_table: int = 3000,
    include_section: bool = True
) -> str:
    """
    构建表格内容文本
    
    Args:
        tables: 表格列表，每个表格包含 page_num, md, section_title 等
        max_tables: 最大表格数
        max_chars_per_table: 每个表格最大字符数
        include_section: 是否包含 section_title
        
    Returns:
        str: 格式化的表格内容
    """
    if not tables:
        return ""
    
    content_parts = []
    
    for i, tbl in enumerate(tables[:max_tables]):
        page_num = tbl.get("page_num", tbl.get("page", "N/A"))
        md = tbl.get("md", tbl.get("markdown", ""))
        
        # 截断
        truncated_md = md[:max_chars_per_table] if md else ""
        
        if include_section:
            section_title = tbl.get("section_title", "N/A")
            part = f"**Table {i+1} @ Page {page_num} - Section: {section_title}**\n\n{truncated_md}"
        else:
            part = f"**Table {i+1} @ Page {page_num}**\n\n{truncated_md}"
        
        content_parts.append(part)
    
    return "\n\n".join(content_parts)


def build_texts_content(
    texts: List[Dict[str, Any]],
    max_texts: int = 5,
    max_chars_per_text: int = 2000,
    include_page: bool = True,
    label: str = "Text"
) -> str:
    """
    构建文本段落内容
    
    Args:
        texts: 文本段落列表，每个包含 page_num, content
        max_texts: 最大文本数
        max_chars_per_text: 每个文本最大字符数
        include_page: 是否包含页码
        label: 标签（如 "Text", "Paragraph"）
        
    Returns:
        str: 格式化的文本内容
    """
    if not texts:
        return ""
    
    content_parts = []
    
    for i, txt in enumerate(texts[:max_texts]):
        page_num = txt.get("page_num", txt.get("page", "N/A"))
        content = txt.get("content", "")
        
        # 截断
        truncated_content = content[:max_chars_per_text] if content else ""
        
        if include_page:
            part = f"**{label} {i+1} @ Page {page_num}**\n{truncated_content}"
        else:
            part = f"**{label} {i+1}**\n{truncated_content}"
        
        content_parts.append(part)
    
    return "\n\n".join(content_parts)


def build_content_for_agent(
    artifacts: List[Dict[str, Any]],
    candidate_pages: Optional[Dict[str, List[int]]] = None,
    context_result: Optional[Dict[str, Any]] = None,
    max_pages: int = 50,
    max_chars: int = 50000
) -> str:
    """
    为 Agent 构建完整的内容文本
    
    支持两种模式：
    1. 有 candidate_pages 时：使用路由结果构建
    2. 有 context_result 时：使用结构化上下文构建
    
    Args:
        artifacts: 所有 artifact 列表
        candidate_pages: Stage 3 路由结果
        context_result: Stage 3.5 结构化上下文
        max_pages: 最大页面数
        max_chars: 最大总字符数
        
    Returns:
        str: 构建的内容文本
    """
    content_parts = []
    
    if context_result:
        # 模式 1: 使用结构化上下文
        from nanobot.ingestion.stages.stage3_5_context_builder import Stage3_5_ContextBuilder
        
        # 格式化上下文
        context_text = Stage3_5_ContextBuilder.format_context_for_llm(context_result)
        content_parts.append(context_text)
        
        # 添加按类型分组的内容
        content_by_type = context_result.get("content_by_type", {})
        
        for data_type, type_data in content_by_type.items():
            tables = type_data.get("tables", [])
            texts = type_data.get("texts", [])
            
            if tables:
                content_parts.append(f"\n### {data_type.upper()} 表格\n")
                content_parts.append(build_tables_content(tables))
            
            # 针对 key_personnel 和 shareholding 强制注入文字段落
            if data_type in ["key_personnel", "shareholding"] and texts:
                content_parts.append(f"\n### {data_type.upper()} 相關文字段落\n")
                content_parts.append(build_texts_content(texts))
    
    elif candidate_pages:
        # 模式 2: 使用候选页面
        content_text, routing_hint = build_candidate_pages_content(
            artifacts, 
            candidate_pages,
            max_pages=max_pages
        )
        
        # 添加路由提示
        if routing_hint:
            content_parts.append(f"📌 Stage 3 路由提示（重点页面）：\n{routing_hint}\n")
        
        content_parts.append("\n📄 PDF 内容（候选页面）：\n")
        content_parts.append(content_text)
    
    else:
        # Fallback: 使用前 20 页
        content_parts.append(build_content_by_pages(
            artifacts,
            start_page=1,
            end_page=20,
            max_chars=max_chars
        ))
    
    result = "".join(content_parts)
    
    # 最终截断
    if len(result) > max_chars:
        result = result[:max_chars] + f"\n\n... (内容已截断)"
    
    return result


def format_routing_hint(candidate_pages: Dict[str, List[int]], max_pages_per_type: int = 10) -> str:
    """
    格式化路由提示字符串
    
    Args:
        candidate_pages: {data_type: [page_nums]}
        max_pages_per_type: 每个类型最多显示的页数
        
    Returns:
        str: 格式化的路由提示
    """
    if not candidate_pages:
        return "（没有路由提示，请自行分析）"
    
    parts = []
    for data_type, pages in sorted(candidate_pages.items()):
        if pages:
            sorted_pages = sorted(pages)[:max_pages_per_type]
            pages_str = ", ".join(map(str, sorted_pages))
            if len(pages) > max_pages_per_type:
                pages_str += "..."
            parts.append(f"- {data_type}: 第 {pages_str}")
    
    return "\n".join(parts) if parts else "（没有路由提示）"
