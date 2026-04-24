"""
Utils Module - 共用工具

🎯 v2.0: 使用统一的 llm_core 封装
- 所有 LLM/Vision 调用统一在 nanobot.core.llm_core
- 直接导出 llm_core，不再需要兼容函数

🎯 v4.0: 新增 pipeline_utils
- 从 pipeline.py 移出的辅助函数
- 文件 Hash、表格转换、关键词搜索

🎯 v4.9: 新增 json_utils
- LLM JSON 响应解析公共函数
- 消除重复的 _parse_json_response 代码

🎯 v4.10: 新增 rag_context 和 content_builder
- RAG-Anything 风格精准上下文提取
- 统一的内容拼接构建工具
"""

# 🌟 LLM 核心
from nanobot.core.llm_core import (
    llm_core,
    chat,
    vision,
    get_api_config,
    detect_provider
)

# 🌟 Pipeline 辅助工具
from .pipeline_utils import (
    compute_file_hash,
    find_keyword_pages,
    find_revenue_breakdown_pages,
    json_table_to_markdown,
    merge_page_artifacts,
    extract_year_from_filename
)

# 🌟 JSON 解析工具 (v4.9)
from .json_utils import (
    parse_llm_json_response,
    extract_json_from_response,
    build_json_response
)

# 🌟 RAG Context 工具 (v4.10)
from .rag_context import (
    extract_precise_context,
    extract_page_context,
    get_surrounding_texts,
    merge_context_with_prompt
)

# 🌟 Content Builder 工具 (v4.10)
from .content_builder import (
    build_page_content_text,
    build_content_by_pages,
    build_candidate_pages_content,
    build_tables_content,
    build_texts_content,
    build_content_for_agent,
    format_routing_hint,
    CONTENT_SEPARATOR,
    PAGE_SEPARATOR
)

__all__ = [
    # LLM Core
    "llm_core",
    "chat",
    "vision",
    "get_api_config",
    "detect_provider",
    # Pipeline Utils
    "compute_file_hash",
    "find_keyword_pages",
    "find_revenue_breakdown_pages",
    "json_table_to_markdown",
    "merge_page_artifacts",
    "extract_year_from_filename",
    # JSON Utils (v4.9)
    "parse_llm_json_response",
    "extract_json_from_response",
    "build_json_response",
    # RAG Context (v4.10)
    "extract_precise_context",
    "extract_page_context",
    "get_surrounding_texts",
    "merge_context_with_prompt",
    # Content Builder (v4.10)
    "build_page_content_text",
    "build_content_by_pages",
    "build_candidate_pages_content",
    "build_tables_content",
    "build_texts_content",
    "build_content_for_agent",
    "format_routing_hint",
    "CONTENT_SEPARATOR",
    "PAGE_SEPARATOR"
]