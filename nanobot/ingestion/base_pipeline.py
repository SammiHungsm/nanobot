"""
Base Ingestion Pipeline - 資料導入流水線基類 (v3.2)

🎯 使用模板方法模式 (Template Method Pattern)
- 共用的流程寫死在基類（parse、save）
- 提取邏輯交給子類實作（extract_information）

🌟 v3.2: 使用 LlamaParse (移除 OpenDataLoader)
"""

import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path
from loguru import logger

from nanobot.core.pdf_core import PDFParser, PDFParseResult


class BaseIngestionPipeline(ABC):
    """
    資料導入流水線基類
    
    🌟 v3.2: 使用 PDFParser (LlamaParse)
    
    模板方法模式：
    - run() 是骨架（不可修改）
    - extract_information() 是抽象方法（子類實作）
    """
    
    def __init__(self, db_url: str = None, data_dir: str = None, tier: str = "agentic"):
        """
        初始化
        
        Args:
            db_url: PostgreSQL 連接字符串
            data_dir: 數據存儲目錄
            tier: LlamaParse 解析层级
        """
        self.db_url = db_url
        self.data_dir = Path(data_dir) if data_dir else Path("data/raw")
        self.tier = tier
        
        # 🌟 v3.2: 使用 PDFParser (LlamaParse)
        self.parser = PDFParser(tier=tier)
        
        # DB Client（延遲初始化）
        self.db = None
        
        logger.info(f"✅ BaseIngestionPipeline 初始化完成 (tier={tier})")
    
    async def connect(self):
        """
        連接資料庫
        
        🌟 v4.16: 使用 Singleton 模式，整個 Pipeline 共享同一個 DBClient
        """
        if self.db_url:
            from nanobot.ingestion.repository.db_client import DBClient
            # 🌟 使用 Singleton（pool_size=20 適合高並發）
            self.db = DBClient.get_instance(db_url=self.db_url, pool_size=20)
            if not DBClient.is_initialized():
                await self.db.connect()
                logger.info("✅ DBClient singleton connected")
    
    async def close(self):
        """關閉連接"""
        if self.db:
            await self.db.close()
            logger.info("✅ 資料庫連接已關閉")
    
    async def run(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """
        🌟 主流程（模板方法）- 不可修改的骨架
        
        流程：
        1. 解析 PDF（統一）
        2. 提取資訊（子類實作）
        3. 儲存資料庫（統一）
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        logger.info(f"🚀 Pipeline 開始處理: {file_path.name}")
        
        try:
            # ===== Step 1: 統一解析 =====
            logger.info("📍 Step 1: 解析 PDF")
            parse_result: PDFParseResult = await self.parser.parse_async(str(file_path))
            
            artifacts = parse_result.artifacts
            logger.info(f"✅ 解析完成：{parse_result.total_pages} 頁, {len(artifacts)} 個 artifacts")
            
            # ===== Step 2: 提取邏輯（子類實作）=====
            logger.info("📍 Step 2: 提取結構化資訊")
            extracted_data = await self.extract_information(
                artifacts,
                metadata=parse_result.metadata,
                **kwargs
            )
            logger.info(f"✅ 提取完成：{len(extracted_data)} 個數據項")
            
            # ===== Step 3: 統一儲存 =====
            logger.info("📍 Step 3: 儲存資料庫")
            if self.db:
                saved_count = await self.save_to_db(extracted_data, str(file_path), parse_result)
                logger.info(f"✅ 儲存完成：{saved_count} 個記錄")
            else:
                logger.warning("⚠️ 未連接資料庫，跳過儲存")
                saved_count = 0
            
            return {
                "success": True,
                "file_path": str(file_path),
                "job_id": parse_result.job_id,
                "total_pages": parse_result.total_pages,
                "artifacts_count": len(artifacts),
                "extracted_count": len(extracted_data),
                "saved_count": saved_count,
                "raw_output_dir": parse_result.raw_output_dir,
                "metadata": parse_result.metadata
            }
            
        except Exception as e:
            logger.error(f"❌ Pipeline 失敗: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "file_path": str(file_path),
                "error": str(e)
            }
    
    async def save_to_db(self, data: Dict[str, Any], file_path: str, parse_result: PDFParseResult) -> int:
        """
        🌟 共用邏輯：寫入資料庫
        
        Args:
            data: 提取的數據
            file_path: 源文件路徑
            parse_result: PDF 解析結果
            
        Returns:
            int: 儲存的記錄數
        """
        saved_count = 0
        
        if not self.db:
            return 0
        
        try:
            doc_id = Path(file_path).stem
            
            # 儲存到 documents 表
            await self.db.create_document(
                doc_id=doc_id,
                filename=Path(file_path).name,
                file_path=file_path,
                file_size_bytes=Path(file_path).stat().st_size,
                status="completed"
            )
            saved_count += 1
            
            # 儲存页面内容
            for artifact in parse_result.artifacts:
                if artifact.get('type') == 'text':
                    await self.db.insert_document_page(
                        document_id=doc_id,
                        page_number=artifact.get('page', 0),
                        content=artifact.get('content', ''),
                        has_tables=False,
                        has_images=False
                    )
                    saved_count += 1
            
            # 儲存表格
            for table in parse_result.tables:
                await self.db.insert_raw_artifact(
                    document_id=doc_id,
                    artifact_type='table',
                    page_number=table.get('page', 0),
                    content_json=table.get('content', {}),
                    raw_text=str(table.get('content', {}))
                )
                saved_count += 1
            
            # 储存图片
            for img in parse_result.images:
                await self.db.insert_raw_artifact(
                    document_id=doc_id,
                    artifact_type='image',
                    page_number=img.get('page', 0),
                    content_json=img,
                    raw_text=img.get('filename', '')
                )
                saved_count += 1
            
        except Exception as e:
            logger.error(f"❌ 儲存失敗: {e}")
        
        return saved_count
    
    @abstractmethod
    async def extract_information(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        🎯 抽象方法：由子類決定怎麼提取
        
        子類實作範例：
        
        # AgenticPipeline（AI Agent）
        async def extract_information(self, artifacts, **kwargs):
            agent = FinancialAgent()
            analysis = await agent.analyze(artifacts)
            return analysis
        """
        raise NotImplementedError("必須由子類實作")


# ===========================================
# 工厂函数
# ===========================================

def create_pipeline(pipeline_type: str = "agentic", **kwargs) -> BaseIngestionPipeline:
    """
    创建 Pipeline 实例
    
    Args:
        pipeline_type: Pipeline 类型（"agentic", "document"）
        **kwargs: 其他参数
        
    Returns:
        BaseIngestionPipeline: Pipeline 实例
    """
    if pipeline_type == "agentic":
        from nanobot.ingestion.agentic_pipeline import AgenticPipeline
        return AgenticPipeline(**kwargs)
    elif pipeline_type == "document":
        from nanobot.ingestion.pipeline import DocumentPipeline
        return DocumentPipeline(**kwargs)
    else:
        raise ValueError(f"未知的 Pipeline 类型: {pipeline_type}")