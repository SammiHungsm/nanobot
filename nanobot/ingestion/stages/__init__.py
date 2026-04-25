"""
Stage Handlers for Document Pipeline (v4.19 Simplified)

Actual Pipeline Stages:
- Stage 0: Preprocessor (Cover Vision + Doc Registration)
- Stage 1: Parser (LlamaParse - via self.parser)
- Stage 2: Enrichment + Vision + ImageTextLinker
- Stage 4: Agentic Extractor (Tool Calling - single extraction entry)
- Stage 5: Validate + Vector + Archive

Internal Stages (called within Stage 5):
- Stage 6: Validator (validation logic)
- Stage 7: Vector Indexer (embedding)
- Stage 8: Archiver (cleanup)
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