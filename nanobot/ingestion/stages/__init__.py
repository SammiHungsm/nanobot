"""
Stage Handlers for Document Pipeline (v4.0 Enterprise-grade - 极简版)

遵循 Single Source of Truth 原则，每个 Stage 只负责单一职责：

🌟 简化后的 Pipeline（只有一条主线）：
- Stage 0: Preprocessor (封面 Vision 提取)
- Stage 0.5: Registrar (文件注册、Hash 重复检查、公司创建)
- Stage 1: Parser (LlamaParse 基础解析)
- Stage 2: Enrichment (保存 Artifacts + RAGAnything Vision 分析)
- Stage 3: Router (关键字扫描与目标页面路由)
- Stage 4: Agentic Extractor (Tool Calling 提取与动态写入) 🌟 唯一的提取入口
- Stage 4.5: KG Extractor (知识图谱实体关系抽取) 🆕
- Stage 5: Vanna Training (Text-to-SQL 训练)
- Stage 6: Validator (数据验证、单位换算、实体对齐)
- Stage 7: Vector Indexer (文本切块、Embedding、向量入库)
- Stage 8: Archiver (页面保存、清理、报告) 🆕

不再有 Toggle，不再有重复逻辑。
"""

from .stage0_preprocessor import Stage0Preprocessor
from .stage0_5_registrar import Stage0_5_Registrar
from .stage1_parser import Stage1Parser
from .stage2_enrichment import Stage2Enrichment
from .stage3_router import Stage3Router
from .stage4_agentic_extractor import Stage4AgenticExtractor
from .stage4_5_kg_extractor import Stage4_5_KGExtractor  # 🌟 KG 實體關係抽取
from .stage4_6_trend_extractor import Stage4_6_TrendExtractor  # 🆕 多年趨勢數據提取
from .stage6_validator import Stage6Validator
from .stage7_vector_indexer import Stage7VectorIndexer
from .stage8_archiver import Stage8Archiver

__all__ = [
    "Stage0Preprocessor",
    "Stage0_5_Registrar",
    "Stage1Parser",
    "Stage2Enrichment",
    "Stage3Router",
    "Stage4AgenticExtractor",
    "Stage4_5_KGExtractor",  # 🌟 KG 實體關係抽取
    "Stage4_6_TrendExtractor",  # 🆕 多年趨勢數據提取
    "Stage6Validator",
    "Stage7VectorIndexer",
    "Stage8Archiver",
]