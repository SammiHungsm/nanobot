"""
Batch PDF Processor

功能：
1. 監控目錄中的新 PDF 文件
2. 批量調用 DocumentPipeline 處理
3. 支持並行處理和進度追蹤
4. 失敗重試機制
"""

import os
import asyncio
import aiofiles
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from loguru import logger
import sys

# 🌟 使用新的模組化 DocumentPipeline
from nanobot.ingestion.pipeline import DocumentPipeline


class BatchPDFProcessor:
    """
    批量 PDF 處理器
    
    支持：
    - 監控目錄自動處理
    - 批量導入現有 PDF
    - 失敗重試
    - 進度報告
    """
    
    def __init__(self, db_url: str, data_dir: str, input_dir: str):
        """
        初始化
        
        Args:
            db_url: PostgreSQL 連接字符串
            data_dir: Docker Volume 路徑 (保存 Raw Data)
            input_dir: PDF 輸入目錄 (監控目錄)
        """
        self.db_url = db_url
        self.data_dir = data_dir
        self.input_dir = Path(input_dir)
        self.processor: Optional[DocumentPipeline] = None
        
        # 配置
        self.max_concurrent = int(os.getenv("MAX_CONCURRENT_TASKS", "5"))
        self.batch_size = int(os.getenv("BATCH_SIZE", "10"))
        
        logger.info(f"📁 Input Directory: {self.input_dir}")
        logger.info(f"💾 Data Directory: {self.data_dir}")
    
    async def initialize(self):
        """初始化處理器"""
        self.processor = DocumentPipeline(db_url=self.db_url, data_dir=self.data_dir)
        await self.processor.connect()
    
    async def close(self):
        """關閉連接"""
        if self.processor:
            await self.processor.close()
    
    async def process_all(self) -> dict:
        """
        處理輸入目錄中的所有 PDF
        
        Returns:
            處理統計
        """
        logger.info("🔍 掃描 PDF 文件...")
        
        # 找到所有 PDF 文件
        pdf_files = list(self.input_dir.glob("*.pdf"))
        
        if not pdf_files:
            logger.warning("⚠️ 未找到 PDF 文件")
            return {"total": 0, "processed": 0, "failed": 0, "skipped": 0}
        
        logger.info(f"📊 找到 {len(pdf_files)} 個 PDF 文件")
        
        # 分批處理
        stats = {
            "total": len(pdf_files),
            "processed": 0,
            "failed": 0,
            "skipped": 0
        }
        
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def process_with_semaphore(pdf_path: Path) -> dict:
            async with semaphore:
                return await self._process_single(pdf_path)
        
        # 創建任務
        tasks = [process_with_semaphore(pdf) for pdf in pdf_files]
        
        # 執行並收集結果
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 統計結果
        for result in results:
            if isinstance(result, Exception):
                stats["failed"] += 1
                logger.error(f"❌ 處理失敗：{result}")
            elif result.get("status") == "completed":
                stats["processed"] += 1
            elif result.get("status") == "skipped":
                stats["skipped"] += 1
            else:
                stats["failed"] += 1
        
        return stats
    
    async def _process_single(self, pdf_path: Path) -> dict:
        """
        處理單一 PDF
        
        Args:
            pdf_path: PDF 文件路徑
            
        Returns:
            處理結果
        """
        logger.info(f"📄 處理：{pdf_path.name}")
        
        try:
            # 生成 Doc ID (使用文件名 + Hash)
            import hashlib
            file_hash = hashlib.md5(str(pdf_path).encode()).hexdigest()[:8]
            doc_id = f"{pdf_path.stem}_{file_hash}"
            
            # 默認 Company ID (TODO: 從文件名解析或使用配置文件)
            company_id = 1  # 默認第一個公司
            
            # 處理
            result = await self.processor.process_pdf(
                pdf_path=str(pdf_path),
                company_id=company_id,
                doc_id=doc_id
            )
            
            if result.get("status") == "completed":
                logger.success(f"✅ 完成：{pdf_path.name}")
            elif result.get("status") == "skipped":
                logger.warning(f"⏭️ 跳過：{pdf_path.name}")
            else:
                logger.error(f"❌ 失敗：{pdf_path.name} - {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 異常：{pdf_path.name} - {e}")
            import traceback
            traceback.print_exc()
            return {"status": "failed", "error": str(e)}
    
    async def watch_directory(self, interval: int = 60):
        """
        監控目錄 (Watch Mode)
        
        Args:
            interval: 檢查間隔 (秒)
        """
        logger.info(f"👁️ 開始監控目錄 (間隔：{interval}秒)")
        
        processed_files = set()
        
        while True:
            try:
                # 掃描新文件
                pdf_files = set(self.input_dir.glob("*.pdf"))
                new_files = pdf_files - processed_files
                
                if new_files:
                    logger.info(f"🆕 發現 {len(new_files)} 個新文件")
                    
                    # 處理新文件
                    for pdf_path in new_files:
                        result = await self._process_single(pdf_path)
                        
                        if result.get("status") == "completed":
                            processed_files.add(pdf_path)
                
                # 等待
                await asyncio.sleep(interval)
                
            except KeyboardInterrupt:
                logger.info("⛔ 停止監控")
                break
            except Exception as e:
                logger.error(f"❌ 監控錯誤：{e}")
                await asyncio.sleep(interval)


async def main():
    """主函數"""
    from dotenv import load_dotenv
    load_dotenv()
    
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
    )
    data_dir = os.getenv("DATA_DIR", "./data/raw")
    input_dir = os.getenv("PDF_INPUT_DIR", "./data/pdfs")
    
    processor = BatchPDFProcessor(db_url, data_dir, input_dir)
    
    try:
        await processor.initialize()
        
        # 檢查命令行參數
        if len(sys.argv) > 1 and sys.argv[1] == "--watch":
            # Watch mode
            await processor.watch_directory(interval=60)
        else:
            # Batch mode
            logger.info("="*60)
            logger.info("🚀 開始批量處理 PDF")
            logger.info("="*60)
            
            stats = await processor.process_all()
            
            logger.info("="*60)
            logger.info("📊 處理完成")
            logger.info(f"   總數：{stats['total']}")
            logger.info(f"   成功：{stats['processed']}")
            logger.info(f"   失敗：{stats['failed']}")
            logger.info(f"   跳過：{stats['skipped']}")
            logger.info("="*60)
    
    finally:
        await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
