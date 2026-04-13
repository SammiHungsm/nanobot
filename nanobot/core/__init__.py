"""
Nanobot Core - 核心模組

提供統一的底層封裝，避免代碼重複。

模組：
- pdf_core: OpenDataLoader 統一封裝（解決 API 參數、Docker 網絡、JSON Schema 問題）
- llm_core: LLM/Vision 統一封裝（解決 Provider 路由、API Key 配置問題）
"""

from .pdf_core import (
    OpenDataLoaderCore,
    PDFParseResult,
    get_hybrid_url,
    get_cuda_enabled,
    create_pdf_core,
    parse_pdf,
    parse_pdf_async
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
    # PDF Core
    "OpenDataLoaderCore",
    "PDFParseResult",
    "get_hybrid_url",
    "get_cuda_enabled",
    "create_pdf_core",
    "parse_pdf",
    "parse_pdf_async",
    # LLM Core
    "UnifiedLLMCore",
    "llm_core",
    "chat",
    "vision",
    "get_api_config",
    "detect_provider"
]