"""
Nanobot Ingestion - 資料導入模組

模組：
- base_pipeline: Pipeline 基類（模板方法模式）
- agentic_pipeline: Agent Pipeline（繼承基類）
- batch_processor: 简化版批量处理器
- pipeline: 文档 Pipeline（主流程）
- repository: DB 客户端
- parsers: PDF Parser
- extractors: 数据提取器

使用方式：
    # 使用新的 AgenticPipeline
    from nanobot.ingestion.agentic_pipeline import AgenticPipeline
    
    pipeline = AgenticPipeline(db_url="postgresql://...")
    await pipeline.connect()
    result = await pipeline.run("report.pdf")
    await pipeline.close()
    
    # 使用批量处理器
    from nanobot.ingestion.batch_processor import process_directory
    
    stats = await process_directory("./pdfs", pipeline_type="agentic")
"""

from .base_pipeline import BaseIngestionPipeline, create_pipeline
from .agentic_pipeline import AgenticPipeline, create_agentic_pipeline
from .batch_processor import process_directory, process_file_list

__all__ = [
    # Base Pipeline
    "BaseIngestionPipeline",
    "create_pipeline",
    # Agentic Pipeline
    "AgenticPipeline",
    "create_agentic_pipeline",
    # Batch Processor
    "process_directory",
    "process_file_list"
]