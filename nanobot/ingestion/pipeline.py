"""
Document Pipeline - 主流程协调器 (v3.3 简化版)

🌟 v3.3: 拆分大方法到 Stage handlers，遵循单一职责原则

pipeline.py 只负责协调（Orchestrator），不再包含具体业务逻辑：
- 调用 Stage handlers 处理各个阶段
- 管理进度回调
- 处理异常

具体逻辑已移到：
- Stage0Preprocessor: 封面提取、公司创建
- Stage3Router: 关键字搜索、页面路由
- Stage4Extractor: 结构化提取、Revenue 提取
- Stage5AgenticWriter: Agentic 写入

行数对比：
- v3.2 (完整版): 1647 行
- v3.3 (简化版): ~300 行
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from loguru import logger

# 🌟 继承 BaseIngestionPipeline
from nanobot.ingestion.base_pipeline import BaseIngestionPipeline

# 🌟 导入 Stage Handlers
from .stages import (
    Stage0Preprocessor,
    Stage1Parser,
    Stage2Enrichment,
    Stage3Router,
    Stage4Extractor,
    Stage5AgenticWriter,
    Stage6VannaTraining,
)

# 🌟 导入 Agent 层
from .extractors.financial_agent import FinancialAgent
from .extractors.page_classifier import PageClassifier

# 🌟 导入 Repository
from .repository.db_client import DBClient


class DocumentPipeline(BaseIngestionPipeline):
    """
    Document Pipeline - 企业级文档处理管道（简化版 v3.3）
    
    🌟 只负责协调（Orchestrator），具体逻辑由 Stage handlers 处理
    
    核心方法：
    - smart_extract(): 调用 Stage3 + Stage4
    - process_pdf_full(): 调用 Stage0-6
    - process_pdf(): 简化版入口
    """
    
    def __init__(
        self,
        db_url: str = None,
        data_dir: str = None,
        tier: str = "agentic"
    ):
        """
        初始化
        
        Args:
            db_url: 数据库连接字符串
            data_dir: 数据存储目录
            tier: LlamaParse 解析层级
        """
        super().__init__(db_url=db_url, data_dir=data_dir, tier=tier)
        
        self.agent = FinancialAgent()
        self.page_classifier = PageClassifier()
        
        logger.info(f"✅ DocumentPipeline 初始化完成 (tier={tier})")
    
    # ===========================================
    # 🌟 协调者方法（调用 Stage handlers）
    # ===========================================
    
    async def smart_extract(
        self,
        pdf_path: str,
        company_id: int = None,
        doc_id: str = None,
        progress_callback: Callable = None,
        year: int = None,
        artifacts: List[Dict[str, Any]] = None,
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None,
        keywords: List[str] = None,
        extraction_types: List[str] = None,
        use_llm: bool = True,
        use_agentic: bool = True
    ) -> Dict[str, Any]:
        """
        🌟 智能提取入口（协调者）
        
        调用 Stage handlers 完成：
        - Stage 1: PDF 解析（如果没有 artifacts）
        - Stage 3: 关键字搜索 + 页面路由
        - Stage 4: 结构化提取
        - Stage 5: Agentic 写入（可选）
        
        Args:
            pdf_path: PDF 路径
            company_id: 公司 ID
            doc_id: 文档 ID
            progress_callback: 进度回调
            year: 年份
            artifacts: LlamaParse 解析结果（可选）
            is_index_report: 是否为指数报告
            index_theme: 指数主题
            confirmed_doc_industry: 确认的行业
            keywords: 关键词列表
            extraction_types: 提取类型
            use_llm: 是否使用 LLM 分类
            use_agentic: 是否使用 Agentic 写入
            
        Returns:
            Dict: 提取结果
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        doc_id = doc_id or pdf_path.stem
        keywords = keywords or ["revenue", "segment", "geography"]
        extraction_types = extraction_types or ["revenue_breakdown"]
        
        logger.info(f"🧠 smart_extract: {pdf_path}")
        
        # 🌟 Step 1: 如果没有 artifacts，先解析
        if not artifacts:
            if progress_callback:
                progress_callback(10.0, "Stage 1: PDF 解析")
            
            try:
                parse_result = self.parser.load_from_raw_output(pdf_path.name)
                logger.info(f"   ✅ 从 raw output 加载（不扣费）")
            except FileNotFoundError:
                parse_result = await self.parser.parse_async(str(pdf_path))
                logger.info(f"   ✅ LlamaParse 解析完成")
            
            artifacts = parse_result.artifacts
        
        if progress_callback:
            progress_callback(30.0, f"解析完成: {len(artifacts)} artifacts")
        
        # 🌟 Step 2: Stage 3 - 关键字搜索 + 页面路由
        if progress_callback:
            progress_callback(40.0, "Stage 3: 页面路由")
        
        router_result = await Stage3Router.find_target_pages(
            artifacts=artifacts,
            target_types=extraction_types,
            keywords=keywords
        )
        
        target_pages = router_result.get("revenue_breakdown", [])
        logger.info(f"   📊 找到目标页面: {target_pages}")
        
        if not target_pages:
            logger.warning("⚠️ 未找到目标页面")
            return {"status": "no_target_pages", "artifacts_count": len(artifacts)}
        
        # 🌟 Step 3: Stage 4 - 结构化提取
        if progress_callback:
            progress_callback(60.0, "Stage 4: 结构化提取")
        
        # 获取年份
        if not year:
            from datetime import datetime
            year = datetime.now().year
        
        # 🌟 如果启用 Agentic，直接调用 Stage 5
        if use_agentic:
            if progress_callback:
                progress_callback(70.0, "Stage 5: Agentic 写入")
            
            # 获取 AgenticPipeline
            agentic_pipeline = self._get_agentic_pipeline()
            
            if agentic_pipeline:
                # 构建 stage5_prompt
                for page_num in target_pages:
                    # 🌟 v3.5: 跳过 None 元素
                    page_artifacts = [a for a in artifacts if a is not None and a.get("page") == page_num]
                    page_content = self._merge_page_artifacts(page_artifacts)
                    
                    stage5_prompt = self._build_stage5_prompt(
                        page_content=page_content,
                        page_num=page_num,
                        doc_id=doc_id,
                        year=year,
                        company_id=company_id,
                        is_index_report=is_index_report,
                        index_theme=index_theme,
                        confirmed_doc_industry=confirmed_doc_industry
                    )
                    
                    result_agentic = await agentic_pipeline.process_document(
                        document_content=stage5_prompt,
                        filename=pdf_path.name,
                        user_hints={
                            "stage": "structured_extraction",
                            "page_num": page_num
                        }
                    )
                    
                    logger.info(f"   ✅ Page {page_num} Agentic 写入完成")
            else:
                # 🌟 Fallback: 使用 Stage4Extractor
                extraction_result = await Stage4Extractor.extract_structured_data(
                    artifacts=artifacts,
                    target_pages=target_pages,
                    company_id=company_id,
                    year=year,
                    doc_id=doc_id,
                    extraction_types=extraction_types,
                    db_client=self.db
                )
        
        if progress_callback:
            progress_callback(100.0, "提取完成")
        
        return {
            "status": "success",
            "doc_id": doc_id,
            "target_pages": target_pages,
            "artifacts_count": len(artifacts)
        }
    
    async def process_pdf_full(
        self,
        pdf_path: str,
        company_id: int = None,
        doc_id: str = None,
        progress_callback: Callable = None,
        replace: bool = False,
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None
    ) -> Dict[str, Any]:
        """
        🌟 完整 PDF 处理流程（协调者）
        
        调用 Stage handlers 完成：
        - Stage 0: Vision 封面提取
        - Stage 1: LlamaParse 解析
        - Stage 2: 保存 Artifacts
        - Stage 3: 关键字路由
        - Stage 4: 结构化提取
        - Stage 5: Agentic 写入
        - Stage 6: Vanna 训练
        
        Args:
            pdf_path: PDF 文件路径
            company_id: 公司 ID
            doc_id: 文档 ID
            progress_callback: 进度回调
            replace: 是否强制重新处理
            is_index_report: 是否为指数报告
            index_theme: 指数主题
            confirmed_doc_industry: 确认的行业
            
        Returns:
            Dict: 处理结果
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        doc_id = doc_id or pdf_path.stem
        
        logger.info(f"🚀 process_pdf_full: {pdf_path}")
        
        result = {
            "doc_id": doc_id,
            "status": "success",
            "stages": {}
        }
        
        try:
            # ===== Stage 0: Vision 提取封面 =====
            if progress_callback:
                progress_callback(5.0, "Stage 0: Vision 提取封面")
            
            stage0_result = await Stage0Preprocessor.extract_cover_metadata(
                pdf_path=str(pdf_path),
                doc_id=doc_id,
                is_index_report=is_index_report,
                confirmed_doc_industry=confirmed_doc_industry,
                parser=self.parser  # 🌟 v3.4: 传入已有的 parser，避免重复创建
            )
            
            # 🌟 v3.5: 安全检查 Stage 0 返回值
            if stage0_result is None:
                logger.warning("⚠️ Stage 0 返回 None，使用默认值")
                stage0_result = {"stock_code": None, "year": 2025}
            
            result["stages"]["stage0"] = stage0_result
            
            # 提取公司信息
            if not company_id and stage0_result.get("stock_code"):
                # 🌟 v3.6: 直接使用已有的 stage0_result，不重复调用 Stage 0
                company_id = await self._create_company_from_metadata(stage0_result)
            
            year = stage0_result.get("year") or 2025
            
            # ===== Stage 1: LlamaParse 解析 =====
            if progress_callback:
                progress_callback(15.0, "Stage 1: LlamaParse 解析")
            
            # 🌟 v3.10: Stage 0 已经解析完成，Stage 1 应该直接使用 raw output
            # 不再调用 parse_async()，避免重复上传和解析
            
            pdf_filename = pdf_path.name
            raw_output_dir = None
            
            # 🌟 尝试从 raw output 加载
            parse_result = None
            try:
                parse_result = self.parser.load_from_raw_output(pdf_filename)
                logger.info(f"   ✅ 从 raw output 加载成功: job_id={parse_result.job_id}, {parse_result.total_pages} 页")
            except FileNotFoundError as e:
                # 🌟 v3.10: 如果 raw output 不存在，说明 Stage 0 没有成功保存
                # 这不应该发生！记录错误并跳过后续 Stage
                logger.error(f"   ❌ Raw output 不存在，无法继续: {e}")
                logger.error(f"   ⚠️ Stage 0 应该已经解析并保存了 raw output，但没有找到")
                raise ValueError(f"Stage 0 raw output not found: {e}")
            except Exception as e:
                logger.error(f"   ❌ 加载 raw output 失败: {e}")
                raise
            
            # 🌟 v3.10: 安全检查 parse_result
            if parse_result is None:
                raise ValueError("parse_result is None after Stage 1")
            
            artifacts = parse_result.artifacts
            if artifacts is None:
                logger.warning("   ⚠️ artifacts is None, using empty list")
                artifacts = []
            
            result["stages"]["stage1"] = {
                "job_id": parse_result.job_id,
                "total_pages": parse_result.total_pages,
                "tables_count": len(parse_result.tables) if parse_result.tables else 0,
                "images_count": len(parse_result.images) if parse_result.images else 0,
                "loaded_from": "raw_output"
            }
            
            # ===== Stage 2: 保存 Artifacts =====
            if progress_callback:
                progress_callback(30.0, "Stage 2: 储存与分析图片 (PyMuPDF + RAGAnything 上下文)")
            
            # 创建文档记录
            file_hash = self._compute_file_hash(str(pdf_path))
            await self._create_document(doc_id, str(pdf_path), company_id, file_hash)
            
            # 🌟 新增：呼叫 Stage 2 处理所有 Artifacts（包含 RAGAnything 上下文 Vision 分析）
            stage2_result = await Stage2Enrichment.save_all_artifacts(
                artifacts=artifacts,
                doc_id=doc_id,
                company_id=company_id,
                document_id=doc_id,
                data_dir=Path(self.data_dir) if hasattr(self, 'data_dir') else Path("/app/data"),
                db_client=self.db,
                vision_limit=20
            )
            result["stages"]["stage2"] = stage2_result
            
            # ===== Stage 3: 关键字路由 =====
            if progress_callback:
                progress_callback(50.0, "Stage 3: 关键字路由")
            
            stage3_result = await Stage3Router.find_target_pages(
                artifacts=artifacts,
                target_types=["revenue_breakdown"]
            )
            result["stages"]["stage3"] = stage3_result
            
            # ===== Stage 4: Agent 提取 =====
            if progress_callback:
                progress_callback(60.0, "Stage 4: Agent 提取")
            
            revenue_pages = stage3_result.get("revenue_breakdown", [])
            
            if revenue_pages and company_id:
                extraction_result = await Stage4Extractor.extract_structured_data(
                    artifacts=artifacts,
                    target_pages=revenue_pages,
                    company_id=company_id,
                    year=year,
                    doc_id=doc_id,
                    extraction_types=["revenue_breakdown"],
                    db_client=self.db
                )
                result["stages"]["stage4"] = extraction_result
            
            # ===== Stage 5: Agentic 写入 =====
            if progress_callback:
                progress_callback(80.0, "Stage 5: Agentic 写入")
            
            # 🌟 v3.11: 使用正确的参数签名
            stage5_result = await Stage5AgenticWriter.run_agentic_write(
                artifacts=artifacts,
                company_id=company_id,
                year=year,
                doc_id=doc_id,
                document_id=None,  # 后续补充
                is_index_report=is_index_report,
                index_theme=index_theme,
                confirmed_doc_industry=confirmed_doc_industry,
                db_client=self.db,
                extraction_types=["revenue_breakdown"]
            )
            result["stages"]["stage5"] = stage5_result
            
            # ===== Stage 6: Vanna 训练 =====
            if progress_callback:
                progress_callback(90.0, "Stage 6: Vanna 训练")
            
            # 🌟 v3.18: 传递 company_id 和 year 参数
            await self._trigger_vanna_training(
                doc_id=doc_id,
                company_id=company_id,
                year=year
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
        progress_callback: Callable = None,
        replace: bool = False
    ) -> Dict[str, Any]:
        """简化版 PDF 处理流程"""
        return await self.process_pdf_full(
            pdf_path=pdf_path,
            company_id=company_id,
            doc_id=doc_id,
            progress_callback=progress_callback,
            replace=replace
        )
    
    async def process_pdf_url(
        self,
        url: str,
        doc_id: str = None,
        company_id: int = None,
        progress_callback: Callable = None,
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None
    ) -> Dict[str, Any]:
        """
        🌟 处理 URL PDF（完整流程）
        
        Args:
            url: PDF URL
            doc_id: 文档 ID
            company_id: 公司 ID
            progress_callback: 进度回调
            is_index_report: 是否为指数报告
            index_theme: 指数主题
            confirmed_doc_industry: 确认的行业
            
        Returns:
            Dict: 处理结果
        """
        logger.info(f"🚀 process_pdf_url: {url}")
        
        # 🌟 Step 1: 使用 PDFParser 解析 URL
        if progress_callback:
            progress_callback(10.0, "Stage 1: URL PDF 解析")
        
        parse_result = await self.parser.parse_url_async(url)
        
        if not parse_result:
            return {"status": "failed", "error": "URL PDF 解析失败"}
        
        artifacts = parse_result.artifacts
        
        if progress_callback:
            progress_callback(30.0, f"解析完成: {parse_result.total_pages} 页")
        
        # 🌟 Step 2: 调用完整流程
        return await self.process_pdf_full_with_artifacts(
            artifacts=artifacts,
            company_id=company_id,
            doc_id=doc_id,
            progress_callback=progress_callback,
            is_index_report=is_index_report,
            index_theme=index_theme,
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
    # 🌟 公共方法（保留）
    # ===========================================
    
    def _compute_file_hash(self, file_path: str) -> str:
        """计算文件 Hash"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]
    
    def _merge_page_artifacts(self, page_artifacts: List[Dict]) -> str:
        """合并页面 artifacts"""
        from nanobot.ingestion.utils.llm_mixin import LLMMixin
        return LLMMixin.merge_page_artifacts(page_artifacts)
    
    async def _create_document(
        self,
        doc_id: str,
        pdf_path: str,
        company_id: int,
        file_hash: str
    ) -> int:
        """创建文档记录"""
        # 🌟 v3.9: 使用正确的 db_client 方法
        await self.db.create_document(
            doc_id=doc_id,
            company_id=company_id,
            filename=Path(pdf_path).name,
            file_path=pdf_path,
            file_hash=file_hash
        )
        # 🌟 v3.9: 不需要调用 get_document_id，create_document 已经创建了记录
        return doc_id  # 返回 doc_id 而不是数字 ID
    
    async def _create_company_from_metadata(self, metadata: Dict[str, Any]) -> int:
        """从已有 metadata 创建或获取公司记录（不重复调用 Stage 0）"""
        if metadata.get("stock_code"):
            # 🌟 v3.8: 先检查公司是否存在，不存在则创建
            existing_company = await self.db.get_company_by_stock_code(metadata["stock_code"])
            if existing_company:
                logger.info(f"   ✅ 公司已存在: stock_code={metadata['stock_code']}, company_id={existing_company['id']}")
                return existing_company['id']
            
            # 🌟 v3.7: 只传入 companies 表有的列
            company_data = {
                "stock_code": metadata["stock_code"],
                "name_en": metadata.get("name_en"),
                "name_zh": metadata.get("name_zh")
            }
            company_id = await self.db.insert_company(company_data)
            logger.info(f"   ✅ 公司创建成功: stock_code={metadata['stock_code']}, company_id={company_id}")
            return company_id
        
        return None
    
    async def _extract_and_create_company(
        self,
        pdf_path: str,
        doc_id: str
    ) -> int:
        """从封面提取公司信息并创建公司记录（⚠️ 已废弃，使用 _create_company_from_metadata）"""
        # 使用 Stage0 提取
        metadata = await Stage0Preprocessor.extract_cover_metadata(
            pdf_path=pdf_path,
            doc_id=doc_id
        )
        
        if metadata.get("stock_code"):
            company_id = await self.db.insert_company(
                stock_code=metadata["stock_code"],
                name_en=metadata.get("name_en"),
                year=metadata.get("year")
            )
            return company_id
        
        return None
    
    async def _trigger_vanna_training(self, doc_id: str, company_id: int = None, year: int = None):
        """
        触发 Vanna 训练
        
        🌟 v3.18: 使用正确的 Stage6VannaTraining.run_complete_stage 方法
        """
        await Stage6VannaTraining.run_complete_stage(
            doc_id=doc_id,
            company_id=company_id,
            year=year,
            db_client=self.db,
            data_dir=str(self.data_dir) if hasattr(self, 'data_dir') else None
        )
    
    def _build_stage5_prompt(
        self,
        page_content: str,
        page_num: int,
        doc_id: str,
        year: int,
        company_id: int,
        is_index_report: bool,
        index_theme: str,
        confirmed_doc_industry: str
    ) -> str:
        """构建 Stage 5 Prompt"""
        report_type = "指数报告" if is_index_report else "年报"
        
        return f"""
你是专业的 PostgreSQL 数据库写入 Agent。
从第 {page_num} 页提取结构化数据并写入数据库。

【基本信息】
- 文档 ID: {doc_id}
- 年份: {year}
- 公司 ID: {company_id}
- 报告类型: {report_type}
- 指数主题: {index_theme or '无'}
- 确认行业: {confirmed_doc_industry or '无'}

【页面内容】
{page_content[:3000]}

请：
1. 调用 get_db_schema 查看数据库结构
2. 判断页面类型（Revenue Breakdown / Key Personnel）
3. 提取数据并调用 smart_insert_document 写入
4. 如果发现新关键词，调用 register_new_keyword
"""
    
    def _get_agentic_pipeline(self):
        """获取 AgenticPipeline"""
        if self._agentic_pipeline is None and self.enable_agentic_ingestion:
            from .agentic_pipeline import AgenticPipeline
            self._agentic_pipeline = AgenticPipeline(
                db_url=self.db_url,
                data_dir=str(self.data_dir)
            )
        return self._agentic_pipeline
    
    async def connect(self):
        """连接数据库"""
        await super().connect()  # 调用 BaseIngestionPipeline.connect() 初始化 self.db
    
    async def close(self):
        """关闭数据库连接"""
        await self.db.close()
    
    # ===========================================
    # 🌟 补回的重要方法（从备份恢复）
    # ===========================================
    
    async def process_pdf_full_with_artifacts(
        self,
        artifacts: List[Dict[str, Any]],
        company_id: int = None,
        doc_id: str = None,
        year: int = None,
        extraction_types: List[str] = None,
        is_index_report: bool = False,
        confirmed_doc_industry: str = None,
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """
        🌟 从已有的 artifacts 继续处理（跳过解析步骤）
        
        适用场景：
        - 已有 LlamaParse raw output，不想重新解析
        - 需要重新提取结构化数据
        
        Args:
            artifacts: Artifacts 列表（来自 LlamaParse）
            company_id: 公司 ID
            doc_id: 文档 ID
            year: 年份
            extraction_types: 提取类型
            is_index_report: 是否为指数报告
            confirmed_doc_industry: 确认的行业
            progress_callback: 进度回调
            
        Returns:
            Dict: 处理结果
        """
        if not doc_id:
            doc_id = "unknown_doc"
        
        extraction_types = extraction_types or ["revenue_breakdown", "key_personnel"]
        
        logger.info(f"🚀 从 artifacts 继续处理: {doc_id}")
        
        result = {
            "doc_id": doc_id,
            "company_id": company_id,
            "status": "success",
            "stages": {}
        }
        
        try:
            # ===== Stage 3: 关键字路由 =====
            if progress_callback:
                progress_callback(20.0, "Stage 3: 关键字路由")
            
            stage3_result = await Stage3Router.find_target_pages(
                artifacts=artifacts,
                target_types=extraction_types
            )
            result["stages"]["stage3"] = stage3_result
            
            # ===== Stage 4: Agent 提取 =====
            if progress_callback:
                progress_callback(40.0, "Stage 4: Agent 提取")
            
            all_target_pages = set()
            for target_type in extraction_types:
                pages = stage3_result.get(target_type, [])
                all_target_pages.update(pages)
            
            if all_target_pages:
                target_artifacts = [
                    a for a in artifacts 
                    if a is not None and a.get("page") in all_target_pages
                ]
                
                # 提取 Revenue
                if "revenue_breakdown" in extraction_types:
                    revenue_pages = stage3_result.get("revenue_breakdown", [])
                    revenue_artifacts = [
                        a for a in artifacts 
                        if a is not None and a.get("page") in revenue_pages
                    ]
                    
                    revenue_result = await self._extract_revenue_from_page(
                        page_artifacts=revenue_artifacts,
                        company_id=company_id,
                        year=year,
                        doc_id=doc_id,
                        page_num=min(revenue_pages) if revenue_pages else 0
                    )
                    result["stages"]["revenue_extraction"] = revenue_result
            
            if progress_callback:
                progress_callback(100.0, "处理完成")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 处理失败: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
            return result
    
    async def run_agentic_ingestion(
        self,
        pdf_path: str,
        filename: str,
        task_id: str = None
    ) -> Dict[str, Any]:
        """
        🌟 Stage 5: Agentic 智能写入
        
        使用 AI Agent 分析前 1-2 页，提取实体信息并动态写入数据库
        
        Args:
            pdf_path: PDF 文件路径
            filename: 原始文件名
            task_id: 任务 ID (可选)
            
        Returns:
            Dict: {"success": bool, "document_id": str, "needs_review": bool}
        """
        if not self.enable_agentic_ingestion:
            logger.info("⏭️ Agentic ingestion disabled, skipping Stage 5")
            return {"success": True, "skipped": True, "reason": "disabled"}
        
        pipeline = self._get_agentic_pipeline()
        if pipeline is None:
            logger.warning("⚠️ AgenticPipeline not available, skipping Stage 5")
            return {"success": True, "skipped": True, "reason": "no_pipeline"}
        
        logger.info(f"🤖 Stage 5: Running agentic ingestion for {filename}")
        
        try:
            result = await pipeline.ingest_with_agent(
                pdf_path=pdf_path,
                filename=filename,
                task_id=task_id
            )
            
            analysis = result.get("analysis", {})
            confidence_scores = analysis.get("confidence_scores", {})
            needs_review = any(score < 0.8 for score in confidence_scores.values()) if confidence_scores else False
            
            result["needs_review"] = needs_review
            
            logger.info(f"✅ Stage 5 complete: document_id={result.get('document_id')}")
            
            return result
            
        except Exception as e:
            logger.exception(f"❌ Stage 5 failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _extract_revenue_from_page(
        self,
        page_artifacts: List[Dict[str, Any]],
        company_id: int,
        year: int,
        doc_id: str,
        page_num: int
    ) -> Dict[str, Any]:
        """
        🌟 从特定页面的 artifacts 提取 Revenue Breakdown
        
        Args:
            page_artifacts: 页面级别的 artifacts
            company_id: 公司 ID
            year: 年份
            doc_id: 文档 ID
            page_num: 页码
            
        Returns:
            Dict: 提取结果
        """
        logger.info(f"   🔍 从页面 {page_num} 提取 Revenue...")
        
        merged_text = self._merge_page_artifacts(page_artifacts)
        
        agent = FinancialAgent()
        
        extraction_prompt = f"""
从以下内容中提取 Revenue Breakdown 数据：

{merged_text[:3000]}

返回 JSON 格式：
```json
{
  "items": [
    {"segment_name": "Europe", "segment_type": "geography", "revenue_percentage": 25.0}
  ]
}
```

只返回 JSON。
"""
        
        llm_response = await llm_core.chat(
            prompt=extraction_prompt,
            require_json=True
        )
        
        extracted_data = {}
        if isinstance(llm_response, dict):
            extracted_data = llm_response
        elif isinstance(llm_response, str):
            import re
            json_match = re.search(r'\{[\s\S]*\}', llm_response)
            if json_match:
                extracted_data = json.loads(json_match.group())
        
        items = extracted_data.get("items", [])
        inserted_count = 0
        
        for item in items:
            try:
                await self.db.insert_revenue_breakdown(
                    company_id=company_id,
                    year=year,
                    segment_name=item.get("segment_name"),
                    segment_type=item.get("segment_type", "geography"),
                    revenue_percentage=item.get("revenue_percentage"),
                    revenue_amount=item.get("revenue_amount"),
                    currency=item.get("currency", "HKD")
                )
                inserted_count += 1
            except Exception as e:
                logger.warning(f"      ⚠️ Revenue 插入失败: {e}")
        
        logger.info(f"   ✅ 页面 {page_num} 提取完成: {inserted_count} 条")
        
        return {
            "page_num": page_num,
            "items_count": len(items),
            "inserted_count": inserted_count,
            "extracted_data": extracted_data
        }
    
    async def _insert_revenue_breakdown(
        self,
        extracted_data: Dict[str, Any],
        company_id: int,
        year: int,
        doc_id: str,
        source_document_id: int = None
    ) -> int:
        """
        🌟 插入 Revenue Breakdown 数据到数据库
        
        Args:
            extracted_data: 提取的数据
            company_id: 公司 ID
            year: 年份
            doc_id: 文档 ID
            source_document_id: 源文档 ID
            
        Returns:
            int: 插入的记录数
        """
        inserted_count = 0
        
        revenue_items = extracted_data.get("revenue_breakdown", [])
        
        if not revenue_items:
            logger.warning("   ⚠️ 没有 revenue_breakdown 数据")
            return 0
        
        for item in revenue_items:
            segment_name = item.get("segment_name") or item.get("category")
            segment_type = item.get("segment_type") or "geography"
            percentage = item.get("revenue_percentage") or item.get("percentage")
            amount = item.get("revenue_amount") or item.get("amount")
            currency = item.get("currency", "HKD")
            
            if not segment_name:
                continue
            
            try:
                await self.db.insert_revenue_breakdown(
                    company_id=company_id,
                    year=year,
                    segment_name=segment_name,
                    segment_type=segment_type,
                    revenue_percentage=percentage,
                    revenue_amount=amount,
                    currency=currency,
                    source_document_id=source_document_id
                )
                inserted_count += 1
                logger.debug(f"   ✅ 插入: {segment_name} ({percentage}%)")
                
            except Exception as e:
                logger.warning(f"   ⚠️ 插入失败: {segment_name} - {e}")
        
        logger.info(f"✅ Revenue Breakdown 插入完成: {inserted_count} 条")
        
        return inserted_count
    
    def _find_keyword_pages(self, artifacts: List[Dict], keywords: List[str]) -> List[int]:
        """
        在 artifacts 中搜索关键词
        
        Args:
            artifacts: Artifacts 列表
            keywords: 关键词列表
            
        Returns:
            List[int]: 找到的页面列表
        """
        candidate_pages = set()
        
        for artifact in artifacts:
            content = artifact.get("content", "") or ""
            content_lower = content.lower()
            
            for keyword in keywords:
                if keyword.lower() in content_lower:
                    candidate_pages.add(artifact.get("page", 0))
                    break
        
        return sorted(list(candidate_pages))
    
    def _find_revenue_breakdown_pages(
        self,
        artifacts: List[Dict[str, Any]],
        keywords: List[str] = None
    ) -> List[int]:
        """
        🌟 在 artifacts 中搜索关键词，找到 Revenue Breakdown 页面
        
        Args:
            artifacts: Artifacts 列表
            keywords: 关键词列表
            
        Returns:
            List[int]: 找到的页面列表
        """
        keywords = keywords or [
            "revenue breakdown", "revenue by", "geographical", 
            "segment", "business segment", "product mix",
            "region", "市場分部", "收入分部", "地區"
        ]
        
        candidate_pages = set()
        
        for artifact in artifacts:
            content = artifact.get("content", "") or artifact.get("markdown", "") or ""
            content_clean = content.lower().replace("\n", " ").replace(" ", "")
            
            for keyword in keywords:
                keyword_clean = keyword.lower().replace(" ", "")
                if keyword_clean in content_clean:
                    candidate_pages.add(artifact.get("page", 0))
                    break
        
        for artifact in artifacts:
            if artifact.get("type") == "table":
                table_content = artifact.get("content", {})
                if isinstance(table_content, dict):
                    table_str = str(table_content).lower()
                    if "%" in table_str or "percentage" in table_str:
                        candidate_pages.add(artifact.get("page", 0))
        
        return sorted(list(candidate_pages))
    
    def _json_table_to_markdown(self, table_json: Dict[str, Any]) -> Optional[str]:
        """
        🌟 将 JSON 表格转换为 Markdown
        
        Args:
            table_json: 表格 JSON
            
        Returns:
            str: Markdown 表格
        """
        if not table_json:
            return None
        
        rows = table_json.get("rows", []) or table_json.get("data", [])
        headers = table_json.get("headers", [])
        
        if not rows:
            return None
        
        if headers:
            header_line = "| " + " | ".join(headers) + " |"
            separator = "| " + " | ".join(["---"] * len(headers)) + " |"
        else:
            first_row = rows[0] if rows else []
            if isinstance(first_row, dict):
                headers = list(first_row.keys())
            elif isinstance(first_row, list):
                headers = [f"Col{i+1}" for i in range(len(first_row))]
            else:
                return None
            
            header_line = "| " + " | ".join(headers) + " |"
            separator = "| " + " | ".join(["---"] * len(headers)) + " |"
        
        body_lines = []
        for row in rows:
            if isinstance(row, dict):
                cells = [str(row.get(h, "")) for h in headers]
            elif isinstance(row, list):
                cells = [str(cell) for cell in row]
            else:
                continue
            
            body_lines.append("| " + " | ".join(cells) + " |")
        
        return header_line + "\n" + separator + "\n" + "\n".join(body_lines)
    
    async def _get_document_year(self, doc_id: str) -> Optional[int]:
        """从数据库获取文档年份"""
        try:
            doc = await self.db.get_document(doc_id)
            if doc:
                filename = doc.get("filename", "")
                import re
                year_match = re.search(r'(20[0-9]{2})', filename)
                if year_match:
                    return int(year_match.group(1))
        except Exception:
            pass
        
        from datetime import datetime
        return datetime.now().year
    
    async def parse_with_smart_routing(
        self,
        pdf_path: str,
        output_dir: str = None,
        use_cuda: bool = None,
        save_raw: bool = True
    ) -> Dict[str, Any]:
        """
        🌟 智能路由解析
        
        Args:
            pdf_path: PDF 路径
            output_dir: 输出目录
            use_cuda: 是否使用 CUDA
            save_raw: 是否保存 raw output
            
        Returns:
            Dict: 解析结果
        """
        logger.info(f"🚀 智能路由解析: {pdf_path}")
        
        if use_cuda is None:
            use_cuda = os.environ.get("USE_CUDA", "false").lower() == "true"
        
        result = await self.parser.parse_async(pdf_path)
        
        return {
            "status": "success",
            "job_id": result.job_id,
            "total_pages": result.total_pages,
            "tables_count": len(result.tables),
            "images_count": len(result.images),
            "raw_output_dir": result.raw_output_dir,
            "routing": "llamaparse_cloud",
            "use_cuda": use_cuda
        }
    
    async def save_all_pages_to_fallback_table(
        self,
        artifacts: List[Dict[str, Any]],
        doc_id: str,
        company_id: int = None,
        year: int = None
    ) -> int:
        """
        🌟 保存所有页面到 document_pages 表
        
        Args:
            artifacts: Artifacts 列表
            doc_id: 文档 ID
            company_id: 公司 ID
            year: 年份
            
        Returns:
            int: 保存的页面数
        """
        saved_count = 0
        
        for artifact in artifacts:
            if artifact.get("type") != "text":
                continue
            
            page_num = artifact.get("page", 0)
            content = artifact.get("content", "")
            
            if not content:
                continue
            
            try:
                await self.db.insert_document_page(
                    document_id=doc_id,
                    page_number=page_num,
                    content=content,
                    has_tables=False,
                    has_images=False
                )
                saved_count += 1
            except Exception as e:
                logger.warning(f"   ⚠️ 页面 {page_num} 保存失败: {e}")
        
        logger.info(f"✅ 保存页面完成: {saved_count} 页")
        return saved_count
    
    async def extract_information(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Agent 提取逻辑（实现 BaseIngestionPipeline 抽象方法）"""
        return await self.smart_extract(
            pdf_path=kwargs.get("pdf_path"),
            company_id=kwargs.get("company_id"),
            extraction_types=["revenue_breakdown", "key_personnel"],
            use_llm=True
        )


# ===========================================
# 工厂函数
# ===========================================

def create_pipeline(db_url: str = None, data_dir: str = None) -> DocumentPipeline:
    """创建 DocumentPipeline 实例"""
    return DocumentPipeline(db_url=db_url, data_dir=data_dir)