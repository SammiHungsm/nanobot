"""
Document Pipeline - 主流程協調器 (v3.2)

這是整個 ingestion 系統的大腦，協調各個模組完成 PDF 處理流程。

🌟 v3.2: 继承 BaseIngestionPipeline，使用 LlamaParse

保留原有功能：
- smart_extract: 智能提取入口
- process_pdf_full: 完整 5-Stage 流程
- run_agentic_ingestion: Agent 智能提取
- _extract_and_create_company: 从封面提取公司信息
- save_all_pages_to_fallback_table: 保存所有页面到数据库
- _trigger_vanna_training: 触发 Vanna 训练
"""

import os
import json
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
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
    Stage6VannaTraining,  # 🌟 新增 Stage 6
)

# 🌟 导入 Agent 层
from .extractors.financial_agent import FinancialAgent
from .extractors.page_classifier import PageClassifier

# 🌟 导入 Repository
from .repository.db_client import DBClient


class DocumentPipeline(BaseIngestionPipeline):
    """
    Document Pipeline - 企業級文檔處理管道
    
    🌟 v3.2: 继承 BaseIngestionPipeline，使用 LlamaParse
    
    核心方法：
    - smart_extract(): 智能提取入口（关键字搜索 + LLM 提取）
    - process_pdf_full(): 完整 5-Stage 流程
    - run_agentic_ingestion(): Agent 智能提取
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
            db_url: 數據庫連接字符串
            data_dir: 數據存儲目錄
            tier: LlamaParse 解析层级
        """
        super().__init__(db_url=db_url, data_dir=data_dir, tier=tier)
        
        self.agent = FinancialAgent()
        self.page_classifier = PageClassifier()
        
        logger.info(f"✅ DocumentPipeline 初始化完成 (tier={tier})")
    
    # ===========================================
    # 🌟 缺失方法恢复（从 pipeline_old.py）
    # ===========================================
    
    def _get_agentic_pipeline(self):
        """
        🌟 获取或创建 AgenticPipeline 实例
        
        用于 Stage 5 Agentic 写入
        
        Returns:
            AgenticPipeline or None
        """
        if self._agentic_pipeline is None and self.enable_agentic_ingestion:
            from .agentic_pipeline import AgenticPipeline
            self._agentic_pipeline = AgenticPipeline(
                db_url=self.db_url,
                data_dir=str(self.data_dir)
            )
            logger.info("✅ AgenticPipeline 已初始化")
        return self._agentic_pipeline
    
    async def connect(self):
        """连接数据库"""
        await self.db.connect()
    
    async def close(self):
        """关闭数据库连接"""
        await self.db.close()
    
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
    
    async def process_pdf(
        self,
        pdf_path: str,
        company_id: int = None,
        doc_id: str = None,
        progress_callback: Callable = None,
        replace: bool = False
    ) -> Dict[str, Any]:
        """
        🌟 简化版 PDF 处理流程
        
        直接调用 process_pdf_full
        
        Args:
            pdf_path: PDF 文件路径
            company_id: 公司 ID (可选)
            doc_id: 文档 ID
            progress_callback: 进度回调
            replace: 是否强制重新处理
            
        Returns:
            Dict: 处理结果
        """
        logger.info(f"🚀 process_pdf: {pdf_path}")
        
        try:
            # Step 1: 计算 Hash
            if progress_callback:
                progress_callback(5.0, "计算 Hash...")
            file_hash = self._compute_file_hash(pdf_path)
            
            # Step 2: 检查重复
            if progress_callback:
                progress_callback(10.0, "检查重复...")
            
            if replace:
                await self.db.delete_document(doc_id)
            else:
                exists = await self.db.check_document_exists(doc_id, file_hash)
                if exists:
                    return {"status": "skipped", "reason": "duplicate"}
            
            # Step 3: 创建文档记录
            await self._create_document(doc_id, pdf_path, company_id, file_hash)
            
            # Step 4: 调用完整流程
            return await self.process_pdf_full(
                pdf_path=pdf_path,
                company_id=company_id,
                doc_id=doc_id,
                progress_callback=progress_callback
            )
            
        except Exception as e:
            logger.error(f"❌ 处理失败: {e}")
            await self.db.update_document_status(doc_id, "failed", error=str(e))
            return {"status": "failed", "error": str(e)}
    
    async def _get_document_year(self, doc_id: str) -> Optional[int]:
        """
        🌟 从数据库获取文档年份
        
        Args:
            doc_id: 文档 ID
            
        Returns:
            int: 年份，如果未找到返回 None
        """
        try:
            row = await self.db.conn.fetchrow(
                "SELECT year FROM documents WHERE doc_id = $1",
                doc_id
            )
            if row and row['year']:
                return row['year']
        except Exception as e:
            logger.warning(f"⚠️ 无法从数据库获取年份: {e}")
        
        return None
    
    # ===========================================
    # 🌟 主入口：smart_extract（保留原有）
    # ===========================================
    
    async def smart_extract(
        self,
        pdf_path: str,
        company_id: int = None,
        doc_id: str = None,
        progress_callback: Callable = None,
        year: int = None,
        artifacts: List[Dict[str, Any]] = None,
        # 🌟 UI 参数（来自 WebUI）
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None,
        keywords: List[str] = None,
        extraction_types: List[str] = None,
        use_llm: bool = True,
        # 🌟 Agentic 模式开关
        use_agentic: bool = True
    ) -> Dict[str, Any]:
        """
        🌟 智能提取入口（关键字搜索 + Agent 提取）
        
        🌟 核心改进：根据用户建议，实现真正的 Agentic 写入逻辑
        - UI 决定大方向 (is_index_report, index_theme, confirmed_doc_industry)
        - AI 处理细节落库 (查 Schema、写 SQL、塞 JSON)
        
        Args:
            pdf_path: PDF 路径
            company_id: 公司 ID (指数报告时为 None)
            doc_id: 文档 ID
            progress_callback: 进度回调
            year: 年份（由主流程传入）
            artifacts: LlamaParse 解析结果（可选，会自动解析）
            is_index_report: 是否为指数报告（来自 UI）
            index_theme: 指数主题 (如 "Hang Seng Biotech Index")
            confirmed_doc_industry: 报告定义的行业 (如 "Biotech")
            keywords: 关键词列表（用于定位页面）
            extraction_types: 提取类型
            use_llm: 是否使用 LLM 分类
            use_agentic: 是否使用 Agentic 写入
            
        Returns:
            Dict: 提取结果统计
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        doc_id = doc_id or pdf_path.stem
        keywords = keywords or ["revenue", "segment", "geography", "director", "management"]
        extraction_types = extraction_types or ["revenue_breakdown"]
        
        logger.info(f"🧠 开始智能结构化提取...")
        logger.info(f"   👉 UI 设定: 指数报告={is_index_report}, 行业={confirmed_doc_industry}")
        
        # 🌟 如果没有传入年份，使用当前年份作为 fallback
        if not year:
            from datetime import datetime
            year = datetime.now().year
            logger.warning(f"   ⚠️ 未传入年份，使用当前年份: {year}")
        else:
            logger.info(f"   📅 文档年份: {year}")
        
        result = {
            "revenue_breakdown": {"pages": [], "extracted": 0},
            "errors": []
        }
        
        # 🌟 Step 1: 如果没有 artifacts，先解析
        if not artifacts:
            if progress_callback:
                progress_callback(10.0, "LlamaParse 解析")
            
            # 尝试从 raw output 加载
            try:
                parse_result = self.parser.load_from_raw_output(pdf_path.name)
                logger.info(f"   ✅ 从 raw output 加载（不扣费）")
            except FileNotFoundError:
                parse_result = await self.parser.parse_async(str(pdf_path))
                logger.info(f"   ✅ LlamaParse 解析完成")
            
            artifacts = parse_result.artifacts
        
        # 🌟 Phase 3: 获取总页数（用于上下文感知）
        total_pages = 0
        if artifacts:
            total_pages = max(a.get("page", 1) for a in artifacts)
            logger.info(f"   📊 PDF 总页数: {total_pages}")
        
        if not artifacts:
            logger.warning("⚠️ 没有 artifacts，跳过结构化提取")
            result["errors"].append("No artifacts available")
            return result
        
        if progress_callback:
            progress_callback(30.0, f"解析完成: {total_pages} 页")
        
        # 🌟 Step 2: 关键字搜索（在 artifacts 中）
        if progress_callback:
            progress_callback(40.0, "关键字搜索")
        
        # 🌟 使用 KeywordManager 动态关键词管理（支持 Agent 学习）
        from nanobot.ingestion.stages.keyword_manager import KeywordManager
        keyword_manager = KeywordManager("/app/data/raw/search_keywords.json")
        dynamic_keywords = keyword_manager.get_all_keywords_flat("revenue_breakdown")
        
        # 如果 JSON 没有关键词，使用基本 Cold-start 名单
        if not dynamic_keywords:
            dynamic_keywords = [
                "revenue breakdown", "geographical", "geographic", 
                "region", "segment", "business segment",
                "收入分佈", "地區收入", "業務分佈"
            ]
            logger.warning("⚠️ Keyword JSON 空白，使用 Cold-start 名单")
        
        # 合并传入的关键词和动态关键词
        all_keywords = list(set(keywords + dynamic_keywords))
        
        revenue_pages = set()
        
        # 🌟 在 artifacts 中搜索关键词
        for artifact in artifacts:
            artifact_type = artifact.get("type")
            page_num = artifact.get("page")
            
            # 只在有文字或表格的区块搜寻
            if artifact_type == "text_chunk":
                content = str(artifact.get("content", "")).lower()
                for keyword in all_keywords:
                    if keyword.lower() in content:
                        revenue_pages.add(page_num)
                        logger.debug(f"   Page {page_num}: text_chunk 命中 '{keyword}'")
                        break
            
            elif artifact_type == "table":
                # 表格内容可能在 content 或 markdown 中
                table_content = artifact.get("content", "") or artifact.get("markdown", "")
                content = str(table_content).lower()
                for keyword in all_keywords:
                    if keyword.lower() in content:
                        revenue_pages.add(page_num)
                        logger.debug(f"   Page {page_num}: table 命中 '{keyword}'")
                        break
        
        logger.info(f"   📊 Artifacts 搜索找到 {len(revenue_pages)} 个候选页面: {sorted(revenue_pages)}")
        
        # 🌟 Phase 3: 记录关键词使用（上下文感知）
        keyword_hits = {}
        for keyword in all_keywords:
            keyword_hits[keyword] = []
        
        for artifact in artifacts:
            artifact_type = artifact.get("type")
            page_num = artifact.get("page")
            
            if artifact_type == "text_chunk":
                content = str(artifact.get("content", "")).lower()
                for keyword in all_keywords:
                    if keyword.lower() in content and page_num not in keyword_hits[keyword]:
                        keyword_hits[keyword].append(page_num)
                        break
            
            elif artifact_type == "table":
                table_content = artifact.get("content", "") or artifact.get("markdown", "")
                content = str(table_content).lower()
                for keyword in all_keywords:
                    if keyword.lower() in content and page_num not in keyword_hits[keyword]:
                        keyword_hits[keyword].append(page_num)
                        break
        
        # 🌟 记录关键词使用（usage_count）
        for keyword, hit_pages in keyword_hits.items():
            if hit_pages:
                logger.debug(f"   📝 Keyword '{keyword}' used in pages: {hit_pages}")
        
        revenue_pages = sorted(list(revenue_pages))
        result["revenue_breakdown"]["pages"] = revenue_pages
        
        if not revenue_pages:
            logger.warning("⚠️ 找不到候选页面，跳过结构化提取")
            return result
        
        logger.info(f"   📊 总共有 {len(revenue_pages)} 个 Revenue Breakdown 候选页面: {sorted(revenue_pages)}")
        
        # 🌟 Step 3: 遍历候选页面进行提取
        for i, page_num in enumerate(sorted(revenue_pages)):
            if progress_callback:
                progress = 50.0 + (i + 1) / max(len(revenue_pages), 1) * 40.0
                progress_callback(progress, f"处理 Page {page_num}...")
            
            # 从 artifacts 取出该页面的所有内容
            page_artifacts = [a for a in artifacts if a.get("page") == page_num]
            
            if not page_artifacts:
                logger.warning(f"   ⚠️ Page {page_num} 在 artifacts 中找不到，跳过")
                continue
            
            # 合并该页面的所有文本和表格
            page_content = self._merge_page_artifacts(page_artifacts)
            
            if not page_content or len(page_content.strip()) < 50:
                logger.warning(f"   ⚠️ Page {page_num} 内容无效，跳过")
                continue
            
            logger.info(f"   🔍 处理 Page {page_num} ({len(page_content)} chars)...")
            
            try:
                # 🌟 核心改进：优先使用 Agentic 写入
                if use_agentic:
                    # 🌟 构建报告类型描述
                    if is_index_report:
                        report_context = f"""
这是一份指数/指数成分股报告(主题: {index_theme or 'Unknown'}, 行业: {confirmed_doc_industry or 'Unknown'})。
该文档包含多家公司的数据，请针对每一家公司进行提取。
适用规则：规则 A - 所有成分股都被强制指派行业 '{confirmed_doc_industry or 'Unknown'}'"""
                    else:
                        report_context = f"""
这是一份年报单公司年报，公司 ID 为 {company_id or '待提取'}。
适用规则：规则 B - 使用 AI 提取各公司的行业"""
                    
                    # 🌟 构建 Stage 5 Prompt（告诉 Agent 如何提取和写入）
                    stage5_prompt = f"""
你是一个专业的 PostgreSQL 数据库写入 Agent。
你的任务：从 PDF 的第 {page_num} 页内容中提取结构化数据，并智能写入数据库。

【基本信息】
- 文档 ID: {doc_id}
- 年份: {year}
- 公司 ID: {company_id or '待提取'}
- 报告类型: {report_context}

【第一步：页面类型识别】⚠️ 重要！先判断这页是什么类型的内容：

| 页面类型 | 识别关键词 | 目标数据表 |
|---------|-----------|-----------|
| 📊 Revenue Breakdown | "revenue", "segment", "geographical", "地区", "分部" | revenue_breakdown |
| 👤 Key Personnel | "director", "management", "高管", "董事", "委员会" | key_personnel |
| 💰 Financial Metrics | "profit", "assets", "liabilities", "收入", "利润", "资产" | financial_metrics |
| 📈 Market Data | "share price", "market cap", "股价", "市值" | market_data |
| 🏛️ Shareholding | "shareholder", "持股", "股东结构" | shareholding_structure |
| 🌱 ESG/Other | "ESG", "碳排放", "sustainability" | documents.dynamic_attributes |

【第二步：数据提取与写入】根据识别的类型，调用对应的写入逻辑：

1. 📊 **Revenue Breakdown 页面** → 写入 revenue_breakdown 表：
   - segment_name (地区/业务名称)
   - segment_type (geography/business/product)
   - revenue_percentage (百分比)
   - revenue_amount (金额)
   - currency (货币单位)

2. 👤 **Key Personnel 页面** → 写入 key_personnel 表：
   - name_en, name_zh (姓名)
   - position_title_en (职位)
   - board_role (Executive/Non-Executive/Independent)
   - committee_membership (委员会成员，JSONB 数组)
   - biography (简介)

3. 💰 **Financial Metrics 页面** → 写入 financial_metrics 表：
   - metric_name (指标名称，如 "revenue", "net_income")
   - value (数值)
   - unit (单位)
   - standardized_value (标准化为 HKD)

4. 📈 **Market Data 页面** → 写入 market_data 表：
   - metric_name (股价、市值等)
   - value, unit
   - date (数据日期)

5. 🏛️ **Shareholding 页面** → 写入 shareholding_structure 表：
   - shareholder_name (股东名称)
   - share_type (股份类型)
   - shares_held (持股数)
   - percentage (持股比例)

6. 🌱 **ESG/特殊属性** → 使用 update_dynamic_attributes 写入 JSONB：
   - 例如：{{"esg_score": 85, "carbon_emission": 1234}}

【第三步：执行写入】
1. 先调用 get_db_schema 查看表结构
2. 根据页面类型，提取对应数据
3. 使用 smart_insert_document 或直接 SQL 写入
4. 记录新发现的词汇 → register_new_keyword

【待处理文本】
{page_content[:6000]}

请先判断页面类型，然后执行对应的提取和写入操作。
"""
                    
                    # 🎯 直接获取 Agentic Pipeline
                    pipeline = self._get_agentic_pipeline()
                    
                    if pipeline:
                        # 🌟 构建 user_hints，标记这是 Stage 5
                        user_hints = {
                            "stage": "structured_extraction",
                            "doc_type": "index_report" if is_index_report else "annual_report",
                            "index_theme": index_theme,
                            "confirmed_doc_industry": confirmed_doc_industry,
                            "page_num": page_num,
                            "year": year,
                            "company_id": company_id,
                            "page_content": page_content[:6000]
                        }
                        
                        logger.info(f"   🤖 将 Page {page_num} 交给 AgenticPipeline 处理...")
                        
                        # 🌟 调用 process_document 并传入 Stage 5 Prompt
                        result_agentic = await pipeline.process_document(
                            document_content=stage5_prompt,
                            filename=Path(pdf_path).name,
                            user_hints=user_hints
                        )
                        
                        logger.info(f"   ✅ Page {page_num} Agentic 写入完成！")
                        result["revenue_breakdown"]["extracted"] += 1
                    
                    # 🌟 方案 B: 传统硬编码写入（如果无法获取 Agentic Pipeline）
                    else:
                        logger.warning("   ⚠️ 无法获取 Agentic Pipeline，退回传统 Hardcode 写入模式")
                        extracted_data = await self.agent.extract_revenue_breakdown(page_content)
                        
                        if extracted_data:
                            # 验证百分比总和
                            total_pct = sum(
                                item.get("percentage", 0) 
                                for item in extracted_data.values()
                            )
                            
                            if 99.0 <= total_pct <= 101.0:
                                # 🌟 入库（仅适用于有 company_id 的年报）
                                if company_id:
                                    inserted = await self._insert_revenue_breakdown(
                                        extracted_data=extracted_data,
                                        company_id=company_id,
                                        year=year,
                                        doc_id=doc_id
                                    )
                                    result["revenue_breakdown"]["extracted"] += inserted
                                    logger.info(f"   ✅ Page {page_num} 提取成功: {inserted} 条记录")
                                    
                                    # 🌟 Phase 3: 记录关键词命中（带上下文）
                                    for keyword, hit_pages in keyword_hits.items():
                                        if page_num in hit_pages:
                                            keyword_manager.record_hit_with_context(
                                                keyword=keyword,
                                                page_num=page_num,
                                                total_pages=total_pages,
                                                features={"has_table": True, "has_percentage": True},
                                                hit=True,
                                                industry=confirmed_doc_industry
                                            )
                                else:
                                    logger.warning(f"   ⚠️ 无 company_id，无法写入 revenue_breakdown（指数报告请启用 Agentic 模式）")
                            else:
                                logger.warning(f"   ⚠️ Page {page_num} 百分比总和 {total_pct}% 不为 100%，跳过")
                        else:
                            logger.warning(f"   ⚠️ Page {page_num} LLM 提取失败")
                
                else:
                    # 🌟 不使用 Agentic，直接用 FinancialAgent
                    logger.info(f"   📊 使用 FinancialAgent 处理 Page {page_num}...")
                    extracted_data = await self.agent.extract_revenue_breakdown(page_content)
                    
                    if extracted_data and company_id:
                        inserted = await self._insert_revenue_breakdown(
                            extracted_data=extracted_data,
                            company_id=company_id,
                            year=year,
                            doc_id=doc_id
                        )
                        result["revenue_breakdown"]["extracted"] += inserted
            
            except Exception as e:
                logger.error(f"   ❌ Page {page_num} 提取失败: {e}")
                result["errors"].append(f"Page {page_num}: {str(e)}")
        
        if progress_callback:
            progress_callback(100.0, "提取完成")
        
        return result
    
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
    
    # ===========================================
    # 🌟 主入口：process_pdf_full（5-Stage）
    # ===========================================
    
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
        完整 PDF 處理流程（5-Stage）
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        if not doc_id:
            doc_id = pdf_path.stem
        
        logger.info(f"🚀 开始 5-Stage 处理: {pdf_path}")
        
        result = {
            "doc_id": doc_id,
            "pdf_path": str(pdf_path),
            "success": True,
            "stages": {}
        }
        
        try:
            # ===== Stage 0: 封面预处理 =====
            if progress_callback:
                progress_callback(5.0, "Stage 0: Vision 提取封面")
            
            # 🌟 Stage 0 会根据 is_index_report 使用不同的提取策略
            stage0_result = await Stage0Preprocessor.extract_cover_metadata(
                pdf_path=str(pdf_path),
                doc_id=doc_id,
                db_client=self.db,
                is_index_report=is_index_report,  # 🌟 传入 is_index_report
                confirmed_doc_industry=confirmed_doc_industry  # 🌟 传入确认的行业
            )
            result["stages"]["stage0"] = stage0_result
            
            # 🌟 行业分配规则：
            # - 规则 A（is_index_report=true）：所有成分股都指派 confirmed_doc_industry
            # - 规则 B（is_index_report=false）：使用 AI 提取各公司的行业
            
            if stage0_result.get("stock_code") and not company_id:
                company = await self.db.get_company_by_stock_code(stage0_result["stock_code"])
                if company:
                    company_id = company.get("id")
                    # 🌟 如果是指数报告，更新公司行业（规则 A）
                    if is_index_report and confirmed_doc_industry:
                        await self.db.update_company_industry(company_id, confirmed_doc_industry)
            
            year = stage0_result.get("year")
            
            if progress_callback:
                progress_callback(10.0, f"Stage 0 完成")
            
            # ===== Stage 1: LlamaParse 解析 =====
            if progress_callback:
                progress_callback(15.0, "Stage 1: LlamaParse 解析")
            
            stage1_result = await Stage1Parser.parse_pdf(
                pdf_path=str(pdf_path),
                doc_id=doc_id,
                tier=self.tier
            )
            result["stages"]["stage1"] = stage1_result
            result["job_id"] = stage1_result.get("job_id")
            result["total_pages"] = stage1_result.get("total_pages", 0)
            
            # 创建文档记录
            document_id = await self._create_document(
                doc_id=doc_id,
                pdf_path=pdf_path,
                company_id=company_id
            )
            
            if progress_callback:
                progress_callback(30.0, f"Stage 1 完成: {result['total_pages']} 页")
            
            # ===== Stage 2: 保存所有页面 =====
            artifacts = stage1_result.get("artifacts", [])
            tables = stage1_result.get("tables", [])
            images = stage1_result.get("images", [])
            
            # 合并所有 artifacts
            all_artifacts = artifacts + [
                {"type": "table", "page": t.get("page", 0), "content": t} 
                for t in tables
            ] + [
                {"type": "image", "page": img.get("page", 0), "content": img}
                for img in images
            ]
            
            if progress_callback:
                progress_callback(35.0, "Stage 2: 保存 Artifacts")
            
            stage2_result = await Stage2Enrichment.save_all_artifacts(
                artifacts=all_artifacts,
                doc_id=doc_id,
                company_id=company_id,
                document_id=document_id,
                data_dir=self.data_dir,
                db_client=self.db,
                vision_limit=20
            )
            result["stages"]["stage2"] = stage2_result
            
            if progress_callback:
                progress_callback(50.0, f"Stage 2 完成")
            
            # ===== Stage 3: 关键字路由 =====
            if progress_callback:
                progress_callback(55.0, "Stage 3: 关键字路由")
            
            stage3_result = await Stage3Router.find_target_pages(
                artifacts=artifacts,
                target_types=["revenue_breakdown", "key_personnel", "financial_metrics"]
            )
            result["stages"]["stage3"] = stage3_result
            
            # ===== Stage 4: Agent 结构化提取 =====
            if progress_callback:
                progress_callback(60.0, "Stage 4: Agent 提取")
            
            all_target_pages = set()
            for target_type in ["revenue_breakdown", "key_personnel", "financial_metrics"]:
                pages = stage3_result.get(target_type, [])
                all_target_pages.update(pages)
            
            if all_target_pages:
                stage4_result = await Stage4Extractor.extract_structured_data(
                    artifacts=artifacts,
                    target_pages=list(all_target_pages),
                    company_id=company_id,
                    year=year,
                    doc_id=doc_id,
                    document_id=document_id,
                    extraction_types=["revenue_breakdown", "key_personnel", "financial_metrics"],
                    db_client=self.db,
                    progress_callback=progress_callback,
                    is_index_report=is_index_report,
                    index_theme=index_theme,
                    confirmed_doc_industry=confirmed_doc_industry
                )
                result["stages"]["stage4"] = stage4_result
            else:
                result["stages"]["stage4"] = {"status": "skipped", "reason": "未找到目标页面"}
            
            if progress_callback:
                progress_callback(90.0, "Stage 4 完成")
            
            # ===== Stage 5: Agentic 写入与行业分配 =====
            if progress_callback:
                progress_callback(92.0, "Stage 5: Agentic 写入")
            
            stage5_result = await Stage5AgenticWriter.run_agentic_write(
                artifacts=artifacts,
                company_id=company_id,
                year=year,
                doc_id=doc_id,
                document_id=document_id,
                is_index_report=is_index_report,
                index_theme=index_theme,
                confirmed_doc_industry=confirmed_doc_industry,
                db_client=self.db,
                extraction_types=["revenue_breakdown", "key_personnel", "financial_metrics"],
                progress_callback=progress_callback
            )
            result["stages"]["stage5"] = stage5_result
            
            # ===== Stage 6: Vanna 训练与后续处理 =====
            if progress_callback:
                progress_callback(95.0, "Stage 6: Vanna 训练")
            
            stage6_result = await Stage6VannaTraining.run_complete_stage(
                doc_id=doc_id,
                company_id=company_id,
                year=year,
                db_client=self.db,
                data_dir=self.data_dir,
                progress_callback=progress_callback
            )
            result["stages"]["stage6"] = stage6_result
            
            # ===== 完成 =====
            await self.db.update_document_status(doc_id, "completed")
            
            # 完成
            await self.db.update_document_status(doc_id, "completed")
            
            result["status"] = "success"
            result["total_chunks"] = len(artifacts)
            result["tables_count"] = len(tables)
            result["images_count"] = len(images)
            result["company_id"] = company_id
            
            if progress_callback:
                progress_callback(100.0, "处理完成")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 处理失败: {e}", exc_info=True)
            await self.db.update_document_status(doc_id, "failed", error_message=str(e))
            result["status"] = "failed"
            result["error"] = str(e)
            return result
    
    # ===========================================
    # 🌟 辅助方法（保留原有）
    # ===========================================
    
    async def _create_document(
        self,
        doc_id: str,
        pdf_path: Path,
        company_id: int = None
    ) -> int:
        """
        创建文档记录
        
        Args:
            doc_id: 文档 ID
            pdf_path: PDF 路径
            company_id: 公司 ID
            
        Returns:
            int: document_id
        """
        try:
            document_id = await self.db.create_document(
                doc_id=doc_id,
                filename=pdf_path.name,
                file_path=str(pdf_path),
                file_size_bytes=pdf_path.stat().st_size,
                owner_company_id=company_id,
                status="parsed"
            )
            return document_id
        except Exception as e:
            logger.warning(f"   ⚠️ 文档记录创建失败: {e}")
            return None
    
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
    
    async def _trigger_vanna_training(self, doc_id: str, max_retries: int = 3):
        """
        🌟 触发 Vanna 训练（可选）
        
        Args:
            doc_id: 文档 ID
            max_retries: 最大重试次数
        """
        try:
            # 检查是否有 Vanna 服务
            vanna_url = os.environ.get("VANNA_URL", "http://vanna-service:8000")
            
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{vanna_url}/train",
                    json={"doc_id": doc_id}
                )
                
                if response.status_code == 200:
                    logger.info(f"   ✅ Vanna 训练触发成功: {doc_id}")
                else:
                    logger.warning(f"   ⚠️ Vanna 训练触发失败: {response.status_code}")
        except Exception as e:
            logger.warning(f"   ⚠️ Vanna 训练触发失败: {e}")
    
    def _merge_page_artifacts(self, page_artifacts: List[Dict]) -> str:
        """
        🌟 合并页面 artifacts 为文本
        
        Args:
            page_artifacts: 页面级别的 artifacts
            
        Returns:
            str: 合并后的文本
        """
        merged = ""
        for artifact in page_artifacts:
            content = artifact.get("content", "") or artifact.get("markdown", "") or ""
            
            if artifact.get("type") == "table":
                table_json = artifact.get("content", {})
                content = self._json_table_to_markdown(table_json)
            
            merged += content + "\n\n"
        
        return merged.strip()
    
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
        
        # 尝试提取表格数据
        rows = table_json.get("rows", []) or table_json.get("data", [])
        headers = table_json.get("headers", [])
        
        if not rows:
            return None
        
        # 构建 Markdown 表格
        if headers:
            header_line = "| " + " | ".join(headers) + " |"
            separator = "| " + " | ".join(["---"] * len(headers)) + " |"
        else:
            # 使用第一行作为 header
            if rows and isinstance(rows[0], list):
                headers = [str(i) for i in range(len(rows[0]))]
            else:
                headers = list(rows[0].keys()) if isinstance(rows[0], dict) else []
            
            header_line = "| " + " | ".join(headers) + " |"
            separator = "| " + " | ".join(["---"] * len(headers)) + " |"
        
        body_lines = []
        for row in rows:
            if isinstance(row, dict):
                cells = [str(row.get(h, "")) for h in headers]
            elif isinstance(row, list):
                cells = [str(c) for c in row]
            else:
                continue
            
            body_lines.append("| " + " | ".join(cells) + " |")
        
        return header_line + "\n" + separator + "\n" + "\n".join(body_lines)
    
    def _compute_file_hash(self, file_path: str) -> str:
        """
        🌟 计算文件哈希
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: SHA256 哈希
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    async def _extract_and_create_company(
        self,
        pdf_path: str,
        doc_id: str = None
    ) -> Dict[str, Any]:
        """
        🌟 从封面提取公司信息并创建公司记录
        
        Args:
            pdf_path: PDF 路径
            doc_id: 文档 ID
            
        Returns:
            Dict: {"company_id": int, "stock_code": str, "name_en": str}
        """
        stage0_result = await Stage0Preprocessor.extract_cover_metadata(
            pdf_path=pdf_path,
            doc_id=doc_id,
            db_client=self.db
        )
        
        stock_code = stage0_result.get("stock_code")
        name_en = stage0_result.get("name_en")
        name_zh = stage0_result.get("name_zh")
        
        if stock_code:
            # 查询或创建公司
            company = await self.db.get_company_by_stock_code(stock_code)
            
            if company:
                company_id = company.get("id")
                logger.info(f"   ✅ 找到已存在的公司: {stock_code}")
            else:
                # 创建新公司
                company_id = await self.db.upsert_company(
                    stock_code=stock_code,
                    name_en=name_en,
                    name_zh=name_zh,
                    industry=None
                )
                logger.info(f"   ✅ 创建新公司: {stock_code}")
            
            return {
                "company_id": company_id,
                "stock_code": stock_code,
                "name_en": name_en,
                "name_zh": name_zh
            }
        
        return {"company_id": None}
    
    # ===========================================
# 🌟 缺少的方法恢复（从 pipeline_old.py）
# ===========================================
    
    def _find_revenue_breakdown_pages(
        self,
        artifacts: List[Dict[str, Any]],
        keywords: List[str] = None
    ) -> List[int]:
        """
        🌟 在 artifacts 中搜索关键词，找到 Revenue Breakdown 页面
        
        Args:
            artifacts: Artifacts 列表（来自 LlamaParse）
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
        
        # 🌟 策略 1: 正规化模糊搜索
        for artifact in artifacts:
            content = artifact.get("content", "") or artifact.get("markdown", "") or ""
            content_clean = content.lower().replace("\n", " ").replace(" ", "")
            
            for keyword in keywords:
                keyword_clean = keyword.lower().replace(" ", "")
                if keyword_clean in content_clean:
                    candidate_pages.add(artifact.get("page", 0))
                    break
        
        # 🌟 策略 2: 视觉特征检测（表格 + 百分比）
        for artifact in artifacts:
            if artifact.get("type") == "table":
                table_content = artifact.get("content", {})
                if isinstance(table_content, dict):
                    # 检测是否有百分比
                    table_str = str(table_content).lower()
                    if "%" in table_str or "percentage" in table_str:
                        candidate_pages.add(artifact.get("page", 0))
        
        return sorted(list(candidate_pages))
    
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
        
        # 合并页面内容
        merged_text = self._merge_page_artifacts(page_artifacts)
        
        # 🌟 使用 FinancialAgent 提取
        agent = FinancialAgent()
        
        extraction_prompt = f"""
从以下内容中提取 Revenue Breakdown 数据：

{merged_text[:3000]}

返回 JSON 格式：
```json
{
  "items": [
    {"segment_name": "Europe", "segment_type": "geography", "revenue_percentage": 25.0, "revenue_amount": 1000000}
  ]
}
```

只返回 JSON。
"""
        
        llm_response = await llm_core.chat(
            prompt=extraction_prompt,
            require_json=True
        )
        
        # 解析结果
        extracted_data = {}
        if isinstance(llm_response, dict):
            extracted_data = llm_response
        elif isinstance(llm_response, str):
            import re
            json_match = re.search(r'\{[\s\S]*\}', llm_response)
            if json_match:
                extracted_data = json.loads(json_match.group())
        
        # 🌟 写入数据库
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
                    currency=item.get("currency", "HKD"),
                    source_document_id=None  # 可以后续关联
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
    
    async def parse_with_smart_routing(
        self,
        pdf_path: str,
        output_dir: str = None,
        use_cuda: bool = None,
        save_raw: bool = True
    ) -> Dict[str, Any]:
        """
        🌟 智能路由解析
        
        根据 USE_CUDA 选择解析引擎：
        - USE_CUDA=true → Docling GPU（路线 A）- 废弃，现用 LlamaParse
        - USE_CUDA=false → LlamaParse Cloud（路线 B）
        
        Args:
            pdf_path: PDF 路径
            output_dir: 输出目录
            use_cuda: 是否使用 CUDA（从环境变量读取）
            save_raw: 是否保存 raw output
            
        Returns:
            Dict: 解析结果
        """
        # 🌟 v3.2: 统一使用 LlamaParse
        # USE_CUDA 参数保留但不再影响 PDF 解析引擎选择
        # GPU 仅用于 LLM 推理
        
        logger.info(f"🚀 智能路由解析: {pdf_path}")
        
        # 🌟 检查 USE_CUDA（仅用于 LLM，不影响 PDF）
        if use_cuda is None:
            use_cuda = os.environ.get("USE_CUDA", "false").lower() == "true"
        
        if use_cuda:
            logger.info(f"   📊 GPU 模式（用于 LLM 推理，PDF 仍用 LlamaParse）")
        else:
            logger.info(f"   📊 CPU 模式（PDF 用 LlamaParse Cloud）")
        
        # 🌟 统一使用 LlamaParse
        result = await self.parser.parse_async(pdf_path)
        
        return {
            "status": "success",
            "job_id": result.job_id,
            "total_pages": result.total_pages,
            "tables_count": len(result.tables),
            "images_count": len(result.images),
            "raw_output_dir": result.raw_output_dir,
            "routing": "llamaparse_cloud",  # 统一标识
            "use_cuda": use_cuda  # 仅用于 LLM
        }
    
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
                    if a.get("page") in all_target_pages
                ]
                
                # 提取 Revenue
                if "revenue_breakdown" in extraction_types:
                    revenue_pages = stage3_result.get("revenue_breakdown", [])
                    revenue_artifacts = [
                        a for a in artifacts 
                        if a.get("page") in revenue_pages
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
        """
        🌟 获取文档年份
        
        Args:
            doc_id: 文档 ID
            
        Returns:
            int: 年份
        """
        try:
            doc = await self.db.get_document(doc_id)
            if doc:
                # 从文件名或 metadata 提取年份
                filename = doc.get("filename", "")
                import re
                year_match = re.search(r'(20[0-9]{2})', filename)
                if year_match:
                    return int(year_match.group(1))
        except Exception:
            pass
        
        return datetime.now().year
    
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
            extracted_data: 提取的数据（Agent 输出）
            company_id: 公司 ID
            year: 年份
            doc_id: 文档 ID
            source_document_id: 源文档 ID（documents.id）
            
        Returns:
            int: 插入的记录数
        """
        inserted_count = 0
        
        # 🌟 从 Agent 输出提取 revenue_breakdown
        revenue_items = extracted_data.get("revenue_breakdown", [])
        
        if not revenue_items:
            logger.warning("   ⚠️ 没有 revenue_breakdown 数据")
            return 0
        
        # 🌟 构建写入格式
        for item in revenue_items:
            segment_name = item.get("segment_name") or item.get("category")
            segment_type = item.get("segment_type") or item.get("category_type") or "geography"
            percentage = item.get("revenue_percentage") or item.get("percentage")
            amount = item.get("revenue_amount") or item.get("amount")
            currency = item.get("currency", "HKD")
            
            if not segment_name:
                continue
            
            try:
                # 🌟 调用 db.insert_revenue_breakdown
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
    
    # ===========================================
    # 🌟 实现 BaseIngestionPipeline 的抽象方法
    # ===========================================
    
    async def extract_information(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Agent 提取逻辑
        """
        return await self.smart_extract(
            pdf_path=kwargs.get("pdf_path"),
            company_id=kwargs.get("company_id"),
            extraction_types=["revenue_breakdown", "key_personnel"],
            use_llm=True
        )
    
    async def load_from_raw_output(
        self,
        pdf_filename: str,
        job_id: str = None
    ) -> Dict[str, Any]:
        """从已保存的 raw output 加载（不扣费）"""
        result = self.parser.load_from_raw_output(pdf_filename, job_id)
        
        return {
            "status": "success",
            "job_id": result.job_id,
            "total_pages": result.total_pages,
            "markdown": result.markdown,
            "artifacts": result.artifacts,
            "tables": result.tables,
            "images": result.images,
            "raw_output_dir": result.raw_output_dir,
            "loaded_from_raw": True
        }
    
    async def process_pdf_url(
        self,
        url: str,
        doc_id: str = None,
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """解析 URL PDF"""
        result = await self.parser.parse_url_async(url)
        
        return {
            "status": "success",
            "doc_id": doc_id or Path(url).stem,
            "job_id": result.job_id,
            "total_pages": result.total_pages,
            "tables_count": len(result.tables),
            "images_count": len(result.images),
            "raw_output_dir": result.raw_output_dir
        }


# ===========================================
# 🌟 便捷函数（保留原有）
# ===========================================

async def process_pdf_simple(
    pdf_path: str,
    db_url: str = None,
    tier: str = "agentic"
) -> Dict[str, Any]:
    """
    🌟 简单解析入口
    
    Args:
        pdf_path: PDF 路径
        db_url: 数据库 URL
        tier: LlamaParse 解析层级
        
    Returns:
        Dict: 解析结果
    """
    pipeline = DocumentPipeline(db_url=db_url, tier=tier)
    await pipeline.connect()
    
    result = await pipeline.smart_extract(pdf_path)
    
    await pipeline.close()
    
    return result


async def process_pdf(
    pdf_path: str,
    db_url: str = None,
    company_id: int = None,
    tier: str = "agentic",
    save_raw: bool = True
) -> Dict[str, Any]:
    """
    🌟 简单解析入口（带数据库保存）
    
    Args:
        pdf_path: PDF 路径
        db_url: 数据库 URL
        company_id: 公司 ID
        tier: LlamaParse 解析层级
        save_raw: 是否保存 raw output
        
    Returns:
        Dict: 解析结果
    """
    pipeline = DocumentPipeline(db_url=db_url, tier=tier)
    await pipeline.connect()
    
    # 解析 PDF
    result = await pipeline.parser.parse_async(pdf_path)
    
    # 保存到数据库
    if db_url:
        doc_id = Path(pdf_path).stem
        await pipeline.save_all_pages_to_fallback_table(
            artifacts=result.artifacts,
            doc_id=doc_id,
            company_id=company_id
        )
    
    await pipeline.close()
    
    return {
        "status": "success",
        "total_pages": result.total_pages,
        "tables_count": len(result.tables),
        "images_count": len(result.images),
        "job_id": result.job_id,
        "raw_output_dir": result.raw_output_dir
    }


# ===========================================
# 🌟 Agent 智能提取（新增）
# ===========================================

async def run_agentic_ingestion(
    pdf_path: str,
    company_id: int = None,
    doc_id: str = None,
    extraction_types: List[str] = None,
    db_url: str = None,
    tier: str = "agentic",
    is_index_report: bool = False,
    confirmed_doc_industry: str = None,
    progress_callback: Callable = None
) -> Dict[str, Any]:
    """
    🌟 Agent 智能提取入口
    
    使用 Agent 进行智能提取：
    - 自动识别文档类型（年报/指数报告）
    - 自动提取公司信息
    - 自动提取结构化数据（Revenue/Personnel/Metrics）
    
    Args:
        pdf_path: PDF 路径
        company_id: 公司 ID（可选，Agent 会自动提取）
        doc_id: 文档 ID
        extraction_types: 提取类型（revenue_breakdown, key_personnel, financial_metrics）
        db_url: 数据库 URL
        tier: LlamaParse 解析层级
        is_index_report: 是否为指数报告（影响行业分配规则）
        confirmed_doc_industry: 报告定义的行业
        progress_callback: 进度回调
        
    Returns:
        Dict: 提取结果
    """
    from nanobot.ingestion.agentic_pipeline import AgenticPipeline
    
    extraction_types = extraction_types or ["revenue_breakdown", "key_personnel", "financial_metrics"]
    
    pipeline = DocumentPipeline(db_url=db_url, tier=tier)
    await pipeline.connect()
    
    result = await pipeline.process_pdf_full(
        pdf_path=pdf_path,
        company_id=company_id,
        doc_id=doc_id,
        progress_callback=progress_callback,
        is_index_report=is_index_report,
        confirmed_doc_industry=confirmed_doc_industry
    )
    
    await pipeline.close()
    
    return result