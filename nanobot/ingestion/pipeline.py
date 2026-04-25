"""
Document Pipeline - Main Workflow Coordinator (v4.18)

🌟 Pure Orchestrator: Only handles workflow orchestration, no business logic

Pipeline Flow (v4.18 - 簡化版):
- Stage 0: Preprocessor + Registrar (Cover Vision + Doc Registration)
- Stage 1: Parser (LlamaParse)
- Stage 2: Enrichment (Save Artifacts + Vision Analysis)
- Stage 3: REMOVED (Agent 自己規劃 - Path A + B)
- Stage 4: Agentic Extractor 🌟 Single extraction entry point
- Stage 5: Validate + Vector Index + Archive

🌟 True Agentic Loop (v4.17):
- Phase 1: Planning → Agent 自己創建任務清單
- Phase 2: Execute → Tool Calling Loop
- Phase 3: Mid-Verification (60%)
- Phase 4: Final-Verification

Architecture: Minimalist orchestrator pattern
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
    Stage4AgenticExtractor,  # 🌟 True Agentic Loop - 包含 KG + Trends Tools
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
        """
        关闭数据库连接
        
        🌟 v4.16: 使用 Singleton close_instance() 确保连接池被正确关闭
        """
        from nanobot.ingestion.repository.db_client import DBClient
        DBClient.close_instance()
        self.db = None
    
    # ===========================================
    # 🌟 辅助方法
    # ===========================================
    
    async def _record_stage(
        self,
        document_id: int,
        stage: str,
        message: str,
        artifacts_count: int = 0,
        status: str = "success"
    ):
        """
        🌟 记录 Stage 执行历史（v4.10）
        
        统一 insert_processing_history 调用，减少重复代码。
        
        Args:
            document_id: 文档 ID
            stage: Stage 名称（如 "stage0", "stage1"）
            message: 状态消息
            artifacts_count: artifacts 数量
            status: 状态（success/failed）
        """
        if self.db and document_id:
            try:
                await self.db.insert_processing_history(
                    document_id=document_id,
                    stage=stage,
                    status=status,
                    message=message,
                    artifacts_count=artifacts_count
                )
            except Exception as e:
                logger.warning(f"   ⚠️ 记录 Stage {stage} 历史失败: {e}")
    
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
            # 🌟 v4.6 重構: Stage 1 先行，Vision 分析 Page 1 (而不是封面)
            # 原因: LlamaParse 解析後有 Page 1 Markdown + 所有圖片，Vision 提取更準確
            
            # ===== Stage 1: LlamaParse 解析 =====
            if progress_callback:
                progress_callback(5.0, "Stage 1: LlamaParse 解析")
            
            pdf_filename = pdf_path.name
            
            # 🌟 v4.0: 先尝试从 raw output 加载（使用 doc_id），失败才调用 API
            parse_result = None
            try:
                parse_result = self.parser.load_from_raw_output(pdf_filename, doc_id=doc_id)
                logger.info(f"   ✅ 从 raw output 加载成功（不扣费）: {doc_id}")
            except FileNotFoundError:
                logger.info(f"   📂 Raw output 不存在，调用 LlamaParse API...")
                # 🌟 v4.0: 传入 doc_id，统一文件夹命名
                parse_result = await self.parser.parse_async(str(pdf_path), doc_id=doc_id)
                logger.info(f"   ✅ LlamaParse API 解析完成，job_id={parse_result.job_id}")
            
            if parse_result is None:
                raise ValueError("parse_result is None")
            
            artifacts = parse_result.artifacts or []
            
            # 🌟 v4.4: 合併所有 artifacts (text + tables + images) 以確保 artifact_relations 可以建立
            tables_list = parse_result.tables or []
            images_list_for_merge = parse_result.images or []
            all_artifacts = artifacts + tables_list + images_list_for_merge
            logger.info(f"   📦 Artifacts 合併: text={len(artifacts)}, tables={len(tables_list)}, images={len(images_list_for_merge)}, total={len(all_artifacts)}")
            
            result["stages"]["stage1"] = {
                "job_id": parse_result.job_id,
                "total_pages": parse_result.total_pages,
                "tables_count": len(parse_result.tables) if parse_result.tables else 0,
                "images_count": len(parse_result.images) if parse_result.images else 0
            }
            
            # ===== Stage 0: Vision + Registrar (Combined) =====
            if progress_callback:
                progress_callback(15.0, "Stage 0: Vision + Registrar")
            
            # 🌟 v4.6: 使用合并后的 Stage 0 run() 方法
            stage0_result = await Stage0Preprocessor.run(
                artifacts=all_artifacts,
                pdf_path=str(pdf_path),
                doc_id=doc_id,
                original_filename=original_filename,
                db_client=self.db,
                skip_duplicate=False,
                is_index_report=is_index_report,
                confirmed_doc_industry=confirmed_doc_industry,
                images=parse_result.images,
                raw_output_dir=parse_result.raw_output_dir,
                pdf_filename=pdf_filename
            )
            
            if stage0_result is None:
                stage0_result = {"stage0_vision": {"stock_code": None, "year": 2025}, "file_hash": None}
            
            result["stages"]["stage0"] = stage0_result
            
            company_id = stage0_result.get("company_id")
            document_id = stage0_result.get("document_id")
            year = stage0_result.get("stage0_vision", {}).get("year") or 2025
            
            # 如果是重复文件，直接返回（Pipeline 结束）
            if stage0_result.get("is_duplicate"):
                logger.info(f"   ⚠️ 重复文件，跳过后续处理")
                result["status"] = "duplicate"
                return result
            
            # 🌟 v4.5: 记录 processing history (Stage 0)
            if self.db and document_id:
                await self.db.insert_processing_history(
                    document_id=document_id,
                    stage="stage0",
                    status="success",
                    message="Vision + Registrar 完成",
                    artifacts_count=2  # document + company
                )
            
            # ===== Stage 2: Enrichment =====
            if progress_callback:
                progress_callback(30.0, "Stage 2: Enrichment")
            
            # 🌟 v4.2: 修复图片传递 - parse_result.images 包含下载后的图片信息
            images_list = parse_result.images or []
            
            # 🌟 v4.1: 传入 raw_output_dir，Stage 2 直接使用 Stage 1 创建的文件夹
            raw_output_dir = parse_result.raw_output_dir
            
            stage2_result = await Stage2Enrichment.save_all_artifacts(
                artifacts=all_artifacts,  # 🌟 v4.4: 使用合併後的 artifacts
                images=images_list,  # 🌟 新增：传递图片列表
                doc_id=doc_id,
                company_id=company_id,
                document_id=document_id,
                data_dir=Path(self.data_dir) if getattr(self, 'data_dir', None) else Path("/app/data"),
                raw_output_dir=raw_output_dir,  # 🌟 v4.1: 传入 Stage 1 创建的文件夹路径
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
            
            # ===== Stage 4: Agentic Extractor 🌟 唯一的入口 =====
            # 🌟 v4.18: 移除 Stage 3 Router，Agent 自己規劃（Path A + B）
            if progress_callback:
                progress_callback(60.0, "Stage 4: Agentic Extractor")
            
            stage4_result = await Stage4AgenticExtractor.run_agentic_write(
                artifacts=all_artifacts,  # 直接接收 Stage 2 artifacts
                company_id=company_id,
                year=year,
                doc_id=doc_id,
                document_id=document_id,
                is_index_report=is_index_report,
                index_theme=index_theme,
                confirmed_doc_industry=confirmed_doc_industry,
                db_client=self.db,
                extraction_types=[
                    "revenue_breakdown",
                    "financial_metrics",
                    "key_personnel",
                    "shareholding",
                    "market_data"
                ],
                stage3_result=None,  # 🌟 v4.18: 已移除
                context_result=None   # 🌟 v4.18: 已移除
            )
            result["stages"]["stage4"] = stage4_result
            
            # ===== Stage 5: Validate + Vector Index + Archive =====
            if progress_callback:
                progress_callback(80.0, "Stage 5: Validate + Vector Index + Archive")
            
            stage5_result = await Stage5ValidateArchive(db_client=self.db).run(
                extraction_result=stage4_result.get("extracted_data", {}),
                company_id=company_id,
                year=year,
                document_id=document_id,
                doc_id=doc_id,
                stage2_result=stage2_result,
                stages_result=result["stages"],
                data_dir=str(self.data_dir) if getattr(self, 'data_dir', None) else "/app/data"
            )
            result["stages"]["stage5"] = stage5_result
            
            # ===== Stage 6: Entity Resolver (圖文關聯) =====
            if progress_callback:
                progress_callback(95.0, "Stage 6: Image Text Linker")
            
            if self.db and document_id:
                try:
                    from nanobot.ingestion.extractors.image_text_linker import ImageTextLinker
                    linker = ImageTextLinker(db_client=self.db)
                    links_count = await linker.link_image_and_text_context(document_id=document_id)
                    logger.info(f"   ✅ 圖文關聯完成: 成功寫入 {links_count} 條關聯到 artifact_relations")
                    result["stages"]["stage6"] = {"links_count": links_count}
                except Exception as e:
                    logger.warning(f"   ⚠️ 圖文關聯失敗: {e}")
            
            # 🌟 v4.5: 记录 processing history (Stage 4 + Stage 5 + Stage 6)
            if self.db and document_id:
                # Stage 4
                extracted_count = len(stage4_result.get("extracted_data", {}))
                await self.db.insert_processing_history(
                    document_id=document_id,
                    stage="stage4",
                    status="success",
                    message="Agentic 提取完成",
                    artifacts_count=extracted_count
                )
                # Stage 5
                if result["stages"].get("stage5"):
                    await self.db.insert_processing_history(
                        document_id=document_id,
                        stage="stage5",
                        status="success",
                        message="Validate + Vector + Archive 完成",
                        artifacts_count=result["stages"]["stage5"].get("vector_index", {}).get("total_vectors", 0)
                    )
                # Stage 6
                if result["stages"].get("stage6"):
                    await self.db.insert_processing_history(
                        document_id=document_id,
                        stage="stage6",
                        status="success",
                        message="圖文關聯完成",
                        artifacts_count=result["stages"]["stage6"].get("links_count", 0)
                    )
            
            if progress_callback:
                progress_callback(100.0, "处理完成")
            
            return result
            
        except Exception as e:
            import traceback
            logger.error(f"❌ process_pdf_full 失败: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
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
    
    async def process_pdf_resume(
        self,
        document_id: int,
        pdf_path: str = None,
        progress_callback: Callable = None,
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None
    ) -> Dict[str, Any]:
        """
        🌟 v4.13: 從 Checkpoint 恢復 PDF 處理
        
        檢查 DB 中該 document_id 的處理歷史，從最後成功的 stage 繼續。
        
        Args:
            document_id: 文檔 ID（必須已存在於 DB）
            pdf_path: PDF 路徑（如果 Stage 1 需要重新執行）
            progress_callback: 進度回調
            
        Returns:
            Dict: 處理結果
        """
        logger.info(f"🔄 process_pdf_resume: document_id={document_id}")
        
        if not self.db:
            raise ValueError("DB client required for resume")
        
        # 🌟 Step 1: 獲取處理歷史
        history = await self.db.get_processing_history(document_id)
        last_stage = await self.db.get_last_successful_stage(document_id)
        
        if not last_stage:
            logger.warning("   ⚠️ 沒有找到成功的 stage，無法恢復")
            return {"status": "error", "message": "No successful stage found"}
        
        logger.info(f"   ✅ 最後成功 stage: {last_stage}")
        
        # 🌟 Step 2: 獲取文檔信息
        doc_info = await self.db.get_document_by_id(document_id)
        if not doc_info:
            raise ValueError(f"Document {document_id} not found")
        
        company_id = doc_info.get("company_id")
        doc_id = doc_info.get("doc_id")
        year = doc_info.get("year") or 2025
        
        # 🌟 Step 3: 根據 last_stage 決定從哪裡繼續
        # Stage 順序: stage0, stage0_5, stage1, stage2, stage4, stage5, stage6, stage7
        stage_order = ["stage0", "stage0_5", "stage1", "stage2", "stage4", "stage5", "stage6", "stage7"]
        
        try:
            last_idx = stage_order.index(last_stage)
            resume_from = stage_order[last_idx + 1] if last_idx + 1 < len(stage_order) else None
        except ValueError:
            resume_from = "stage0"
        
        if not resume_from:
            logger.info("   ✅ 所有 stages 已完成")
            return {"status": "success", "message": "All stages completed", "document_id": document_id}
        
        logger.info(f"   🔄 從 {resume_from} 繼續...")
        
        # 🌟 Step 4: 根據 resume_from 執行後續 stages
        # 🌟 v4.18: 移除 stage3，簡化為只支援 stage4, stage5, stage6, stage7
        
        if resume_from in ["stage4", "stage5", "stage6", "stage7"]:
            # 這些 stages 可以直接從 DB 讀取 artifacts
            result = {"doc_id": doc_id, "document_id": document_id, "company_id": company_id, "status": "resumed", "stages": {}}
            
            if resume_from == "stage4":
                # Stage 4: Agentic Extractor
                if progress_callback:
                    progress_callback(60.0, "Stage 4: Agentic Extractor (Resumed)")
                
                from nanobot.ingestion.stages.stage4_agentic_extractor import Stage4AgenticExtractor
                stage4_result = await Stage4AgenticExtractor.run_agentic_write(
                    artifacts=None,  # 從 DB 讀取
                    company_id=company_id,
                    year=year,
                    doc_id=doc_id,
                    document_id=document_id,
                    db_client=self.db,
                    use_db_artifacts=True  # 🌟 從 DB 讀取
                )
                result["stages"]["stage4"] = stage4_result
                
                await self.db.insert_processing_history(
                    document_id=document_id,
                    stage="stage4",
                    status="success",
                    message="Agentic Extractor 完成 (Resumed)"
                )
            
            # Stage 5, 6, 7 類似...
            
            logger.info(f"✅ Resume 完成: {result}")
            return result
        
        else:
            logger.warning(f"   ⚠️ 不支援從 {resume_from} 恢復，請重新執行完整 pipeline")
            return {"status": "error", "message": f"Resume from {resume_from} not supported"}
    
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