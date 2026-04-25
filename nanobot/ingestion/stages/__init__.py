"""
Stage Handlers for Document Pipeline (v4.18 Simplified)

Active Stages:
- Stage 0: Preprocessor (Vision + Hash + DB Registration)
- Stage 1: Parser (LlamaParse - via self.parser)
- Stage 2: Enrichment (Save Artifacts + Vision Analysis)
- Stage 4: Agentic Extractor (Tool Calling - single extraction entry)
- Stage 5: Validate + Vector + Archive
- Stage 6: Entity Resolver (Image-Text Linking)
- Stage 7: Vector Indexer
- Stage 8: Archiver
"""

from .stage0_preprocessor import Stage0Preprocessor
from .stage2_enrichment import Stage2Enrichment
from .stage4_agentic_extractor import Stage4AgenticExtractor
from .stage5_validate_archive import Stage5ValidateArchive
from .stage6_validator import Stage6Validator
from .stage7_vector_indexer import Stage7VectorIndexer
from .stage8_archiver import Stage8Archiver

__all__ = [
    "Stage0Preprocessor",
    "Stage2Enrichment",
    "Stage4AgenticExtractor",
    "Stage5ValidateArchive",
    "Stage6Validator",
    "Stage7VectorIndexer",
    "Stage8Archiver",
]