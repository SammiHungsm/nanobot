"""
Ingestion Module - 數據攝取管道

企業級模組化架構：
- pipeline: 主流程協調器
- parsers: PDF 解析 (快速/Vision)
- extractors: LLM 數據提取
- validators: 數據驗證
- repository: 數據庫操作
"""

from .pipeline import DocumentPipeline, process_pdf_simple
from .parsers import VisionParser, FastParser
from .extractors import FinancialAgent, get_prompt
from .validators import validate_all, ValidationResult
from .repository import DBClient

__all__ = [
    "DocumentPipeline",
    "process_pdf_simple",
    "VisionParser",
    "FastParser",
    "FinancialAgent",
    "get_prompt",
    "validate_all",
    "ValidationResult",
    "DBClient"
]