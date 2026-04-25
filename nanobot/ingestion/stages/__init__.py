"""
Stage Handlers for Document Pipeline (v4.20 Simplified)

Actual Pipeline Stages:
- Stage 0: Preprocessor (Cover Vision + Doc Registration)
- Stage 1: Parser (LlamaParse - via self.parser)
- Stage 2: Enrichment + Vision + ImageTextLinker
- Stage 4: Agentic Extractor (Tool Calling - single extraction entry)
- Stage 5: Validate + Vector Index + Archive

Internal Helpers (used by Stage 5):
- Stage 7: VectorIndexer (embedding, called lazily by Stage5)
"""

from .stage0_preprocessor import Stage0Preprocessor
from .stage2_enrichment import Stage2Enrichment
from .stage4_agentic_extractor import Stage4AgenticExtractor
from .stage5_validate_archive import Stage5ValidateArchive

__all__ = [
    "Stage0Preprocessor",
    "Stage2Enrichment",
    "Stage4AgenticExtractor",
    "Stage5ValidateArchive",
]
