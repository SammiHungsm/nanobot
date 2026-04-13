"""
Parsers Module - PDF 解析層

提供 OpenDataLoader 解析功能。

⚠️ VisionParser 和 FastParser 已废弃，使用 nanobot.core.pdf_core 替代
"""

from .opendataloader_parser import OpenDataLoaderParser

__all__ = ["OpenDataLoaderParser"]