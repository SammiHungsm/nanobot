"""
Nanobot Core - 核心模組 (v3.2)

提供統一的底層封裝，避免代碼重複。

模組：
- pdf_core: LlamaParse 統一封裝（支持 130+ 格式）
- llm_core: LLM/Vision 統一封裝

🌟 v3.2: 移除 OpenDataLoader，只使用 LlamaParse
"""

from .pdf_core import (
    PDFParser,
    PDFParseResult,
    parse_pdf,
    parse_pdf_async,
    parse_pdf_url,
    load_from_raw_output,
    get_llamaparse_api_key,
    get_llamaparse_tier,
    get_data_dir,
    get_raw_output_dir,
)

from .llm_core import (
    UnifiedLLMCore,
    llm_core,
    chat,
    vision,
    get_api_config,
    detect_provider
)

__all__ = [
    # PDF Core (LlamaParse only)
    "PDFParser",
    "PDFParseResult",
    "parse_pdf",
    "parse_pdf_async",
    "parse_pdf_url",
    "load_from_raw_output",
    "get_llamaparse_api_key",
    "get_llamaparse_tier",
    "get_data_dir",
    "get_raw_output_dir",
    # LLM Core
    "UnifiedLLMCore",
    "llm_core",
    "chat",
    "vision",
    "get_api_config",
    "detect_provider"
]