"""
Stage Handlers for Document Pipeline (v4.18 Simplified)

🌟 简化后的 Pipeline（6 Stages）：
- Stage 0: Preprocessor + Registrar (Vision + Hash + DB Registration) 🌟 合併
- Stage 1: Parser (LlamaParse 基础解析)
- Stage 2: Enrichment (保存 Artifacts + Vision 分析)
- Stage 3: REMOVED (Agent 自己規劃)
- Stage 4: Agentic Extractor (Tool Calling 提取与动态写入) 🌟 唯一的提取入口
- Stage 5: Validate + Vector + Archive (合并原 Stage 6/7/8)
- Stage 6: Entity Resolver (圖文關聯)
"""

from .stage0_preprocessor import Stage0Preprocessor
from .stage1_parser import Stage1Parser
from .stage2_enrichment import Stage2Enrichment
from .stage3_router import Stage3Router
from .stage4_agentic_extractor import Stage4AgenticExtractor
from .stage4_5_kg_extractor import Stage4_5_KGExtractor
from .stage4_6_trend_extractor import Stage4_6_TrendExtractor
from .stage5_validate_archive import Stage5ValidateArchive
from .stage6_validator import Stage6Validator
from .stage7_vector_indexer import Stage7VectorIndexer
from .stage8_archiver import Stage8Archiver

__all__ = [
    "Stage0Preprocessor",
    "Stage1Parser",
    "Stage2Enrichment",
    "Stage3Router",
    "Stage4AgenticExtractor",
    "Stage4_5_KGExtractor",
    "Stage4_6_TrendExtractor",
    "Stage5ValidateArchive",
    "Stage6Validator",
    "Stage7VectorIndexer",
    "Stage8Archiver",
]