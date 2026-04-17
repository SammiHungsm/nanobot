"""
Utils Module - 共用工具

🎯 v2.0: 使用统一的 llm_core 封装
- 所有 LLM/Vision 调用统一在 nanobot.core.llm_core
- 直接导出 llm_core，不再需要兼容函数

🎯 v4.0: 新增 pipeline_utils
- 从 pipeline.py 移出的辅助函数
- 文件 Hash、表格转换、关键词搜索
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

__all__ = [
    "llm_core",
    "chat",
    "vision",
    "get_api_config",
    "detect_provider",
    "compute_file_hash",
    "find_keyword_pages",
    "find_revenue_breakdown_pages",
    "json_table_to_markdown",
    "merge_page_artifacts",
    "extract_year_from_filename"
]