"""
Document Pipeline - 主流程协调器 (v4.0 极简版 - Single Source of Truth)

🌟 纯粹的 Orchestrator：只负责流程编排，不包含任何业务逻辑

Pipeline 直线化：
- Stage 0: Preprocessor (封面 Vision 提取)
- Stage 0.5: Registrar (Hash + 注册文档 + 创建公司)
- Stage 1: Parser (LlamaParse 解析)
- Stage 2: Enrichment (保存 Artifacts + RAGAnything Vision)
- Stage 3: Router (关键字路由)
- Stage 4: Agentic Extractor (Tool Calling 提取) 🌟 唯一的提取入口
- Stage 5: Vanna Training (Text-to-SQL 训练)
- Stage 6: Validator (数据验证 + 单位换算)
- Stage 7: Vector Indexer (切块 + Embedding)
- Stage 8: Archiver (归档 + 清理 + 报告) 🆕

行数对比：
- v3.2 (臃肿版): 1647 行
- v4.0 (极简版): ~130 行 🎉
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from loguru import logger

from nanobot.ingestion.base_pipeline import BaseIngestionPipeline
from nanobot.ingestion.stages import (
    Stage0Preprocessor,
    Stage0_5_Registrar,
    Stage2Enrichment,
    Stage3Router,
    Stage4AgenticExtractor,
    Stage5VannaTraining,
    Stage6Validator,
    Stage7VectorIndexer,
    Stage8Archiver,
)


class DocumentPipeline(BaseIngestionPipeline):
    """
    Document Pipeline - 极简版协调器
    
    🌟 只负责调用 Stage handlers，不包含任何具体逻辑
    """
    
    def __init__(
        self,
        db_url: str = None,
        data_dir: str = None,
        tier: str = "agentic"
    ):
        super().__init__(db_url=db_url, data_dir=data_dir, tier=tier)
    
    async def connect(self):
        """连接数据库"""
        await super().connect()
    
    async def close(self):
        """关闭数据库连接"""
        if self.db:
            await self.db.close()
    
    # ===========================================
    # 🌟 实现抽象方法（委托给 Stage 4）
    # ===========================================
    
    async def extract_information(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        🎯 实现抽象方法：委托给 Stage4AgenticExtractor
        
        这是 v4.0 的核心：所有提取逻辑都在 Stage 4 中
        """
        logger.info("🎯 extract_information: 委托给 Stage4AgenticExtractor")
        
        company_id = kwargs.get("company_id")
        year = kwargs.get("year")
        document_id = kwargs.get("document_id")
        
        # 调用 Stage 4 Agentic Extractor
        result = await Stage4AgenticExtractor.run_agentic_write(
            artifacts=artifacts,
            company_id=company_id,
            year=year or 2025,
            doc_id=kwargs.get("doc_id"),
            document_id=document_id,
            db_client=self.db
        )
        
        return result
    
    # ===========================================
    # 🌟 核心流程：唯一的入口
    # ===========================================
    
    async def process_pdf_full(
        self,
        pdf_path: str,
        company_id: int = None,
        doc_id: str = None,
        original_filename: str = None,  # 🌟 v4.3: 新增参数 - 原始上传文件名
        progress_callback: Callable = None,
        replace: bool = False,
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None
    ) -> Dict[str, Any]:
        """
        🌟 完整 PDF 处理流程
        
        Pipeline 直线化（无 Toggle，无分支）：
        Stage 0 → Stage 0.5 → Stage 1 → Stage 2 → Stage 3 → Stage 4 → Stage 5 → Stage 6 → Stage 7
        
        🌟 v4.3: 新增 original_filename 参数，用于保存原始上传文件名
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        doc_id = doc_id or pdf_path.stem
        # 🌟 v4.3: 如果没有传入 original_filename，使用 pdf_path 的文件名
        original_filename = original_filename or pdf_path.name
        logger.info(f"🚀 process_pdf_full: {pdf_path} (original_filename={original_filename})")
        
        result = {"doc_id": doc_id, "status": "success", "stages": {}}
        
        try:
            # ===== Stage 0: Vision 提取封面 =====
            if progress_callback:
                progress_callback(5.0, "Stage 0: Vision 提取封面")
            
            stage0_result = await Stage0Preprocessor.extract_cover_metadata(
                pdf_path=str(pdf_path),
                doc_id=doc_id,
                is_index_report=is_index_report,
                confirmed_doc_industry=confirmed_doc_industry,
                parser=self.parser
            )
            
            if stage0_result is None:
                stage0_result = {"stock_code": None, "year": 2025}
            
            result["stages"]["stage0"] = stage0_result
            
            # ===== Stage 0.5: Registrar =====
            if progress_callback:
                progress_callback(10.0, "Stage 0.5: Registrar")
            
            registrar_result = await Stage0_5_Registrar.run(
                pdf_path=str(pdf_path),
                doc_id=doc_id,
                original_filename=original_filename,  # 🌟 v4.3: 传递原始文件名
                metadata=stage0_result,
                db_client=self.db,
                skip_duplicate=False
            )
            result["stages"]["stage0_5"] = registrar_result
            
            company_id = registrar_result.get("company_id")
            document_id = registrar_result.get("document_id")  # 🌟 获取 document_id
            
            # 🌟 v4.4: 记录 processing history (Stage 0 + Stage 0.5)
            if self.db and document_id:
                # Stage 0
                await self.db.insert_processing_history(  # 🌟 v4.5: 修正方法名
                    document_id=document_id,
                    stage="stage0",
                    status="success",
                    message="Vision 提取封面完成",
                    artifacts_count=1
                )
                # Stage 0.5
                await self.db.insert_processing_history(
                    document_id=document_id,
                    stage="stage0_5",
                    status="success",
                    message="文档和公司注册完成",
                    artifacts_count=2  # document + company
                )
            document_id = registrar_result.get("document_id")
            year = stage0_result.get("year") or 2025
            
            # ===== Stage 1: LlamaParse 解析 =====
            if progress_callback:
                progress_callback(15.0, "Stage 1: LlamaParse 解析")
            
            pdf_filename = pdf_path.name
            
            # 🌟 v4.1: 先尝试从 raw output 加载，失败才调用 API
            parse_result = None
            try:
                parse_result = self.parser.load_from_raw_output(pdf_filename)
                logger.info(f"   ✅ 从 raw output 加载成功（不扣费）")
            except FileNotFoundError:
                logger.info(f"   📂 Raw output 不存在，调用 LlamaParse API...")
                parse_result = await self.parser.parse_async(str(pdf_path))
                logger.info(f"   ✅ LlamaParse API 解析完成，job_id={parse_result.job_id}")
            
            if parse_result is None:
                raise ValueError("parse_result is None")
            
            artifacts = parse_result.artifacts or []
            
            result["stages"]["stage1"] = {
                "job_id": parse_result.job_id,
                "total_pages": parse_result.total_pages,
                "tables_count": len(parse_result.tables) if parse_result.tables else 0,
                "images_count": len(parse_result.images) if parse_result.images else 0
            }
            
            # ===== Stage 2: Enrichment =====
            if progress_callback:
                progress_callback(30.0, "Stage 2: Enrichment")
            
            # 🌟 v4.2: 修复图片传递 - parse_result.images 包含下载后的图片信息
            images_list = parse_result.images or []
            
            stage2_result = await Stage2Enrichment.save_all_artifacts(
                artifacts=artifacts,
                images=images_list,  # 🌟 新增：传递图片列表
                doc_id=doc_id,
                company_id=company_id,
                document_id=document_id,
                data_dir=Path(self.data_dir) if hasattr(self, 'data_dir') else Path("/app/data"),
                db_client=self.db,
                vision_limit=20
            )
            result["stages"]["stage2"] = stage2_result
            
            # 🌟 v4.4: 记录 processing history (Stage 1 + Stage 2)
            if self.db and document_id:
                # Stage 1
                await self.db.insert_processing_history(
                    document_id=document_id,
                    stage="stage1",
                    status="success",
                    message=f"LlamaParse 解析完成，job_id={parse_result.job_id}",
                    artifacts_count=len(artifacts)
                )
                # Stage 2
                await self.db.insert_processing_history(
                    document_id=document_id,
                    stage="stage2",
                    status="success",
                    message=f"页面和图片保存完成，pages={stage2_result.get('pages_saved', 0)}",
                    artifacts_count=stage2_result.get("pages_saved", 0) + stage2_result.get("images_saved", 0)
                )
            
            # ===== Stage 3: Router =====
            if progress_callback:
                progress_callback(50.0, "Stage 3: Router")
            
            stage3_result = await Stage3Router.find_target_pages(
                artifacts=artifacts,
                target_types=["revenue_breakdown"]
            )
            result["stages"]["stage3"] = stage3_result
            
            # ===== Stage 4: Agentic Extractor 🌟 唯一的入口 =====
            if progress_callback:
                progress_callback(60.0, "Stage 4: Agentic Extractor")
            
            stage4_result = await Stage4AgenticExtractor.run_agentic_write(
                artifacts=artifacts,
                company_id=company_id,
                year=year,
                doc_id=doc_id,
                document_id=document_id,
                is_index_report=is_index_report,
                index_theme=index_theme,
                confirmed_doc_industry=confirmed_doc_industry,
                db_client=self.db,
                extraction_types=["revenue_breakdown"]
            )
            result["stages"]["stage4"] = stage4_result
            
            # ===== Stage 5: Vanna Training =====
            if progress_callback:
                progress_callback(80.0, "Stage 5: Vanna Training")
            
            await Stage5VannaTraining.train_vanna(
                doc_id=doc_id,
                company_id=company_id,
                year=year,
                db_client=self.db
            )
            
            # ===== Stage 6: Validator =====
            if progress_callback:
                progress_callback(85.0, "Stage 6: Validator")
            
            extraction_result = result["stages"].get("stage4", {}).get("extracted_data", {})
            
            if extraction_result and document_id:
                stage6_result = await Stage6Validator(db_client=self.db).run(
                    extraction_result=extraction_result,
                    company_id=company_id,
                    year=year,
                    document_id=document_id
                )
                result["stages"]["stage6"] = stage6_result
            
            # ===== Stage 7: Vector Indexer =====
            if progress_callback:
                progress_callback(90.0, "Stage 7: Vector Indexer")
            
            if document_id:
                stage7_result = await Stage7VectorIndexer(db_client=self.db).run(
                    document_id=document_id,
                    stage2_result=stage2_result
                )
                result["stages"]["stage7"] = stage7_result
            
            # ===== Stage 8: Archiver =====
            if progress_callback:
                progress_callback(95.0, "Stage 8: Archiver (归档与清理)")
            
            stage8_result = await Stage8Archiver.run(
                artifacts=artifacts,
                doc_id=doc_id,
                document_id=document_id,
                stages_result=result["stages"],
                db_client=self.db,
                data_dir=str(self.data_dir) if hasattr(self, 'data_dir') else None
            )
            result["stages"]["stage8"] = stage8_result
            
            # 🌟 v4.4: 记录 processing history (Stage 4 + Stage 7 + Stage 8)
            if self.db and document_id:
                # Stage 4
                extracted_count = len(stage4_result.get("extracted_data", {}))
                await self.db.insert_processing_history(
                    document_id=document_id,
                    stage="stage4",
                    status="success",
                    message=f"Agentic 提取完成",
                    artifacts_count=extracted_count
                )
                # Stage 7
                if result["stages"].get("stage7"):
                    await self.db.insert_processing_history(
                        document_id=document_id,
                        stage="stage7",
                        status="success",
                        message=f"向量索引完成",
                        artifacts_count=result["stages"]["stage7"].get("total_vectors", 0)
                    )
                # Stage 8
                await self.db.insert_processing_history(
                    document_id=document_id,
                    stage="stage8",
                    status="success",
                    message="处理完成，已归档",
                    artifacts_count=0
                )
            
            if progress_callback:
                progress_callback(100.0, "处理完成")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ process_pdf_full 失败: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
            return result
    
    async def process_pdf(
        self,
        pdf_path: str,
        company_id: int = None,
        doc_id: str = None,
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """简化版入口"""
        return await self.process_pdf_full(
            pdf_path=pdf_path,
            company_id=company_id,
            doc_id=doc_id,
            progress_callback=progress_callback
        )
    
    async def process_pdf_url(
        self,
        url: str,
        doc_id: str = None,
        company_id: int = None,
        progress_callback: Callable = None,
        is_index_report: bool = False,
        confirmed_doc_industry: str = None
    ) -> Dict[str, Any]:
        """处理 URL PDF"""
        logger.info(f"🚀 process_pdf_url: {url}")
        
        if progress_callback:
            progress_callback(10.0, "Stage 1: URL PDF 解析")
        
        parse_result = await self.parser.parse_url_async(url)
        
        if not parse_result:
            return {"status": "failed", "error": "URL PDF 解析失败"}
        
        # 保存 raw output
        pdf_filename = url.split("/")[-1] or "url_pdf"
        self.parser.save_raw_output(parse_result, pdf_filename)
        
        return await self.process_pdf_full(
            pdf_path=pdf_filename,
            company_id=company_id,
            doc_id=doc_id,
            progress_callback=progress_callback,
            is_index_report=is_index_report,
            confirmed_doc_industry=confirmed_doc_industry
        )
    
    async def load_from_raw_output(
        self,
        pdf_filename: str,
        job_id: str = None
    ) -> Dict[str, Any]:
        """从已保存的 raw output 加载"""
        parse_result = self.parser.load_from_raw_output(pdf_filename, job_id)
        return {
            "status": "success",
            "job_id": parse_result.job_id,
            "total_pages": parse_result.total_pages,
            "artifacts": parse_result.artifacts
        }


# ===========================================
# 工厂函数
# ===========================================

def create_pipeline(db_url: str = None, data_dir: str = None) -> DocumentPipeline:
    """创建 DocumentPipeline 实例"""
    return DocumentPipeline(db_url=db_url, data_dir=data_dir)