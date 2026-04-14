"""
Stage Handlers for Document Pipeline

遵循 Orchestrator 模式，每个 Stage 只负责单一职责：
- Stage 0: 预处理与公司元数据提取
- Stage 1: OpenDataLoader 基础解析
- Stage 2: RAGAnything 多模态富文本扩充
- Stage 3: 关键字扫描与目标页面路由
- Stage 4: Agentic 深度结构化提取

pipeline.py 只负责流程编排（Orchestrator）
"""

from .stage0_preprocessor import Stage0Preprocessor
from .stage1_parser import Stage1Parser
from .stage2_enrichment import Stage2Enrichment
from .stage3_router import Stage3Router
from .stage4_extractor import Stage4Extractor

__all__ = [
    "Stage0Preprocessor",
    "Stage1Parser",
    "Stage2Enrichment",
    "Stage3Router",
    "Stage4Extractor",
]