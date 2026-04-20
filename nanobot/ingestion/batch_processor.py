"""
Batch PDF Processor - 批量 PDF 处理器

🎯 简化版本（使用 BaseIngestionPipeline）

瘦身效果：
- 原本的 batch_processor.py 有 ~250 行
- 现在只需 ~120 行
- 只是一个简单的 for 循环 + 并发控制

Usage:
    # 批量处理目录
    python -m nanobot.ingestion.batch_processor --input-dir ./pdfs --pipeline-type agentic
"""

import asyncio
import argparse
from pathlib import Path
from typing import List, Dict
from loguru import logger

from nanobot.ingestion.base_pipeline import create_pipeline


async def process_directory(
    dir_path: str,
    pipeline_type: str = "agentic",
    db_url: str = None,
    data_dir: str = None,
    max_concurrent: int = 5
) -> Dict[str, int]:
    """
    🎯 批量处理目录中的 PDF
    
    Args:
        dir_path: PDF 文件目录
        pipeline_type: Pipeline 类型（"agentic", "document"）
        db_url: PostgreSQL 连接字符串
        data_dir: 数据存储目录
        max_concurrent: 最大并发数
        
    Returns:
        Dict: 处理统计
        {
            "total": int,
            "success": int,
            "failed": int
        }
    """
    input_dir = Path(dir_path)
    
    if not input_dir.exists():
        logger.error(f"目录不存在: {input_dir}")
        return {"total": 0, "success": 0, "failed": 0}
    
    # 扫描 PDF 文件
    pdf_files = list(input_dir.glob("*.pdf"))
    
    if not pdf_files:
        logger.warning(f"目录中没有 PDF 文件: {input_dir}")
        return {"total": 0, "success": 0, "failed": 0}
    
    logger.info(f"找到 {len(pdf_files)} 个 PDF 文件")
    
    # 创建 Pipeline 实例
    pipeline = create_pipeline(pipeline_type, db_url=db_url, data_dir=data_dir)
    await pipeline.connect()
    
    # 并发处理（使用 asyncio.Semaphore）
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_one(pdf_file: Path) -> bool:
        async with semaphore:
            try:
                result = await pipeline.run(str(pdf_file))
                return result.get("success", False)
            except Exception as e:
                logger.error(f"处理失败 {pdf_file.name}: {e}")
                return False
    
    # 并发执行
    tasks = [process_one(pdf) for pdf in pdf_files]
    results = await asyncio.gather(*tasks)
    
    # 统计结果
    success_count = sum(1 for r in results if r)
    failed_count = len(results) - success_count
    
    await pipeline.close()
    
    logger.info(f"批量处理完成：{success_count} 成功, {failed_count} 失败")
    
    return {
        "total": len(pdf_files),
        "success": success_count,
        "failed": failed_count
    }


async def process_file_list(
    file_paths: List[str],
    pipeline_type: str = "agentic",
    db_url: str = None,
    data_dir: str = None,
    max_concurrent: int = 5
) -> Dict[str, int]:
    """
    🎯 批量处理文件列表
    
    Args:
        file_paths: PDF 文件路径列表
        pipeline_type: Pipeline 类型
        db_url: PostgreSQL 连接字符串
        data_dir: 数据存储目录
        max_concurrent: 最大并发数
        
    Returns:
        Dict: 处理统计
    """
    logger.info(f"处理 {len(file_paths)} 个文件")
    
    # 创建 Pipeline
    pipeline = create_pipeline(pipeline_type, db_url=db_url, data_dir=data_dir)
    await pipeline.connect()
    
    # 并发处理
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_one(file_path: str) -> bool:
        async with semaphore:
            try:
                result = await pipeline.run(file_path)
                return result.get("success", False)
            except Exception as e:
                logger.error(f"处理失败 {file_path}: {e}")
                return False
    
    tasks = [process_one(fp) for fp in file_paths]
    results = await asyncio.gather(*tasks)
    
    await pipeline.close()
    
    success_count = sum(1 for r in results if r)
    failed_count = len(results) - success_count
    
    return {
        "total": len(file_paths),
        "success": success_count,
        "failed": failed_count
    }


# ===========================================
# CLI 入口
# ===========================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量处理 PDF")
    parser.add_argument("--input-dir", required=True, help="PDF 输入目录")
    parser.add_argument("--pipeline-type", default="agentic", choices=["agentic", "document"])
    parser.add_argument("--db-url", default=None, help="PostgreSQL 连接字符串")
    parser.add_argument("--data-dir", default="data/raw", help="数据存储目录")
    parser.add_argument("--max-concurrent", type=int, default=5, help="最大并发数")
    
    args = parser.parse_args()
    
    # 运行
    stats = asyncio.run(process_directory(
        dir_path=args.input_dir,
        pipeline_type=args.pipeline_type,
        db_url=args.db_url,
        data_dir=args.data_dir,
        max_concurrent=args.max_concurrent
    ))
    
    print(f"\n处理完成：")
    print(f"  总文件数：{stats['total']}")
    print(f"  成功：{stats['success']}")
    print(f"  失败：{stats['failed']}")