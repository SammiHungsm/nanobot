"""
Stage Handlers for Document Pipeline (v3.2)

遵循 Orchestrator 模式，每个 Stage 只负责单一职责：
- Stage 0: 预处理与公司元数据提取（封面 Vision 提取）
- Stage 1: LlamaParse 基础解析
- Stage 2: 多模态富文本扩充（保存 Artifacts + Vision 分析）
- Stage 3: 关键字扫描与目标页面路由
- Stage 4: 深度结构化提取（LLM 提取）
- Stage 5: Agentic 写入与行业分配（规则 A/B）
- Stage 6: Vanna 训练与后续处理

pipeline.py 只负责流程编排（Orchestrator）
"""

from .stage0_preprocessor import Stage0Preprocessor
from .stage1_parser import Stage1Parser
from .stage2_enrichment import Stage2Enrichment
from .stage3_router import Stage3Router
from .stage4_extractor import Stage4Extractor
from .stage5_agentic_writer import Stage5AgenticWriter
from .stage6_vanna_training import Stage6VannaTraining

__all__ = [
    "Stage0Preprocessor",
    "Stage1Parser",
    "Stage2Enrichment",
    "Stage3Router",
    "Stage4Extractor",
    "Stage5AgenticWriter",
    "Stage6VannaTraining",
]