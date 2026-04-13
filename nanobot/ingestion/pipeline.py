"""
Document Pipeline - 主流程協調器

這是整個 ingestion 系統的大腦，協調各個模組完成 PDF 虄理流程。

職責分離（Separation of Concerns）：
1. Parser 層 (OpenDataLoaderParser)：只負責「看」，輸出原始 Artifacts
2. Agent 層 (FinancialAgent, PageClassifier)：只負責「想」，輸出結構化 JSON
3. Pipeline 層 (DocumentPipeline)：唯一的大腦，負責資料庫和流程控制

🔧 重構後：不再使用 PyMuPDF 自己切 PDF，完全依賴 OpenDataLoader 解析結果

流程：
1. Parser: 解析 PDF → Markdown/文字/Artifacts (使用 OpenDataLoaderParser)
2. Classifier: LLM 智能路由 (找出目標頁面)
3. Agent: LLM 提取結構化數據
4. Validator: 數據驗證
5. Repository: 數據入庫

🌟 重構後統一入口：
- WebUI 直接使用 DocumentPipeline
- OpenDataLoaderProcessor 已廢棄
"""

import os
import json
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Callable
from datetime import datetime
from loguru import logger

# 導入 Parser 層
from .parsers.opendataloader_parser import OpenDataLoaderParser

# 導入各個模組（Agent 層）
from .extractors.financial_agent import FinancialAgent
from .extractors.page_classifier import PageClassifier

# 導入統一的 LLM 客戶端
# 🌟 使用统一的 llm_core
# 🌟 使用统一的 llm_core 和 pdf_core
from nanobot.core.llm_core import llm_core, detect_provider
from nanobot.core.pdf_core import OpenDataLoaderCore

# 🌟 继承 BaseIngestionPipeline
from nanobot.ingestion.base_pipeline import BaseIngestionPipeline

# 🌟 导入跨页表格合并器
from nanobot.ingestion.utils.table_merger import cross_page_merger, merge_cross_page_tables

# 導入 Keyword Manager（動態關鍵字管理）
from .utils.keyword_manager import KeywordManager


# ===========================================
# 跨頁表格合併工具
# ===========================================


# ===========================================
# 跨頁表格合併工具（已移到 utils/table_merger.py）
# ===========================================

# 🌟 使用全局跨頁表格合併器（已在顶部导入）
_cross_page_merger = cross_page_merger

from .repository.db_client import DBClient


class DocumentPipeline(BaseIngestionPipeline):
    """
    Document Pipeline - 企業級文檔處理管道
    
    🌟 新架構：Agentic Dynamic Ingestion
    Stage 0 (智能預處理): Agent 分析前 1-2 頁，提取實體信息
    Stage 1 (便宜 & 快速): PageClassifier 語義分類
    Stage 2 (昂貴 & 精準): Vision Parser + Financial Agent 只處理相關頁面
    
    所有配置從 config.json 讀取，不硬編碼模型名稱或 API Key。
    """
    
    def __init__(
        self,
        db_url: str = None,
        data_dir: str = None,
        use_opendataloader: bool = True,
        enable_agentic_ingestion: bool = True,
        agent_loop = None,
        enable_hybrid: bool = True  # 🌟 新增：启用 Hybrid AI 视觉模式（提取图片）
    ):
        """
        初始化
        
        🌟 继承 BaseIngestionPipeline，共用基类的初始化逻辑
        
        Args:
            db_url: 數據庫連接字符串
            data_dir: 數據存儲目錄
            use_opendataloader: 是否使用 OpenDataLoader 解析（默認 True）
            enable_agentic_ingestion: 是否啟用智能代理寫入（默認 True）
            agent_loop: AgentLoop 實例（可選，用於 Agentic Ingestion）
            enable_hybrid: 是否启用 Hybrid AI 视觉模式（默認 True，用于提取图片）
        """
        # 🌟 调用基类的构造函数
        super().__init__(db_url=db_url, data_dir=data_dir)
        
        # 🌟 DocumentPipeline 特有的配置
        self.enable_agentic_ingestion = enable_agentic_ingestion
        self.agent_loop = agent_loop
        self._agentic_pipeline = None
        self.use_opendataloader = use_opendataloader
        self.enable_hybrid = enable_hybrid  # 🌟 保存 hybrid 设置
        
        # 🌟 初始化数据库客户端（基类只设置了 db_url，这里需要实际初始化）
        from .repository.db_client import DBClient
        self.db = DBClient(self.db_url)
        
        # 🌟 使用統一的 LLM 客戶端（基类已有 pdf_core）
        self.llm_client = llm_core
        self.llm_model = llm_core.default_model
        self.vision_model = llm_core.vision_model
        
        # 🌟 初始化 Parser 層
        if use_opendataloader:
            from .parsers.opendataloader_parser import OpenDataLoaderParser
            # 🌟 传入 enable_hybrid 参数，启用 Hybrid AI 视觉模式
            self.opendataloader_parser = OpenDataLoaderParser(enable_hybrid=enable_hybrid)
            logger.info(f"   ✅ OpenDataLoaderParser 初始化完成 (hybrid={enable_hybrid})")
        else:
            self.opendataloader_parser = None
        
        # 🌟 初始化 Agent 层
        from .extractors.financial_agent import FinancialAgent
        from .extractors.page_classifier import PageClassifier
        self.agent = FinancialAgent()
        self.page_classifier = PageClassifier()
        
        logger.info(f"DocumentPipeline initialized (model={self.llm_model}, opendataloader={use_opendataloader}, hybrid={enable_hybrid}, agentic={enable_agentic_ingestion})")
    
    def _get_agentic_pipeline(self):
        """獲取或創建 AgenticPipeline 實例"""
        if self._agentic_pipeline is None and self.enable_agentic_ingestion:
            # 🌟 使用新的精簡版 AgenticPipeline
            from .agentic_pipeline import AgenticPipeline
            self._agentic_pipeline = AgenticPipeline(
                db_url=self.db_url,
                data_dir=str(self.data_dir)
            )
            logger.info("✅ AgenticPipeline 已初始化（新版精簡版）")
        return self._agentic_pipeline
    
    async def connect(self):
        """連接數據庫"""
        await self.db.connect()
    
    async def close(self):
        """關閉連接"""
        await self.db.close()
    
    # ===========================================
    # 🌟 Stage 0: Agentic Dynamic Ingestion
    # ===========================================
    
    async def run_agentic_ingestion(
        self,
        pdf_path: str,
        filename: str,
        task_id: str = None
    ) -> Dict[str, Any]:
        """
        🌟 Stage 0: 智能代理動態寫入
        
        在傳統 ETL 流程之前，使用 AI Agent 分析前 1-2 頁，
        提取實體信息（公司、行業、關係），並動態寫入數據庫。
        
        這個方法解決了：
        1. 處理「無母公司」報告（如恒指報告）
        2. 動態發現新屬性並存入 JSONB
        3. 建立複雜的一對多公司關係
        
        Args:
            pdf_path: PDF 文件路徑
            filename: 原始文件名
            task_id: 任務 ID (可選)
        
        Returns:
            Dict: {
                "success": bool,
                "document_id": str,
                "analysis": DocumentAnalysis,
                "needs_review": bool
            }
        """
        if not self.enable_agentic_ingestion:
            logger.info("⏭️ Agentic ingestion disabled, skipping Stage 0")
            return {"success": True, "skipped": True, "reason": "disabled"}
        
        pipeline = self._get_agentic_pipeline()
        if pipeline is None:
            logger.warning("⚠️ AgenticPipeline not available, skipping Stage 0")
            return {"success": True, "skipped": True, "reason": "no_pipeline"}
        
        logger.info(f"🤖 Stage 0: Running agentic ingestion for {filename}")
        
        try:
            result = await pipeline.ingest_with_agent(
                pdf_path=pdf_path,
                filename=filename,
                task_id=task_id
            )
            
            # 檢查是否需要人工覆核
            analysis = result.get("analysis", {})
            confidence_scores = analysis.get("confidence_scores", {})
            needs_review = any(score < 0.8 for score in confidence_scores.values()) if confidence_scores else False
            
            result["needs_review"] = needs_review
            
            if needs_review:
                logger.info(f"⚠️ Low confidence detected, creating review record")
            
            logger.info(f"✅ Stage 0 complete: document_id={result.get('document_id')}")
            
            return result
            
        except Exception as e:
            logger.exception(f"❌ Stage 0 failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ===========================================
    # 主流程
    # ===========================================
    
    async def process_pdf(
        self,
        pdf_path: str,
        company_id: int = None,
        doc_id: str = None,
        progress_callback: Callable = None,
        replace: bool = False
    ) -> Dict[str, Any]:
        """
        處理 PDF 文檔的主流程
        
        Args:
            pdf_path: PDF 檔案路徑
            company_id: 公司 ID (可選)
            doc_id: 文檔 ID
            progress_callback: 進度回調
            replace: 是否強制重新處理
            
        Returns:
            Dict: 處理結果
        """
        logger.info(f"🚀 開始處理 PDF: {pdf_path}")
        
        try:
            # Step 1: 計算 Hash
            if progress_callback:
                progress_callback(5.0, "計算 Hash...")
            file_hash = self._compute_file_hash(pdf_path)
            
            # Step 2: 檢查重複
            if progress_callback:
                progress_callback(10.0, "檢查重複...")
            
            if replace:
                await self.db.delete_document(doc_id)
            else:
                exists = await self.db.check_document_exists(doc_id, file_hash)
                if exists:
                    return {"status": "skipped", "reason": "duplicate"}
            
            # Step 3: 創建文檔記錄
            await self._create_document(pdf_path, company_id, doc_id, file_hash)
            
            # Step 4: 提取公司信息 (如果沒有 company_id)
            # 🎯 漸進式提取：只取前 2 頁，Upsert 公司信息
            if not company_id:
                if progress_callback:
                    progress_callback(20.0, "從封面提取公司元數據...")
                company_id = await self._extract_and_create_company(pdf_path, doc_id)
                # 注意：_extract_and_create_company 已內部處理 year 更新
            
            # Step 5: 智能結構化提取
            if company_id:
                if progress_callback:
                    progress_callback(30.0, "智能提取結構化數據...")
                
                extraction_result = await self.smart_extract(
                    pdf_path, company_id, doc_id, progress_callback
                )
            else:
                extraction_result = {"status": "skipped", "reason": "no company_id"}
            
            # Step 6: 更新狀態
            if progress_callback:
                progress_callback(90.0, "更新狀態...")
            
            await self.db.update_document_status(doc_id, "completed", extraction_result)
            
            if progress_callback:
                progress_callback(100.0, "✅ 處理完成")
            
            return {
                "status": "completed",
                "doc_id": doc_id,
                "company_id": company_id,
                **extraction_result
            }
            
        except Exception as e:
            logger.error(f"❌ 處理失敗: {e}")
            await self.db.update_document_status(doc_id, "failed", error=str(e))
            return {"status": "failed", "error": str(e)}
    
    async def extract_information(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        🎯 实现基类的抽象方法
        
        从 Artifacts 中提取结构化数据
        
        Args:
            artifacts: OpenDataLoader 解析出的 Artifacts
            metadata: PDF 元数据
            **kwargs: 其他参数
            
        Returns:
            Dict: 提取的结构化数据
            
        实现：
        - 调用 smart_extract() 进行智能提取
        - 返回标准化结果
        """
        # 🌟 直接调用 smart_extract 的逻辑
        logger.info("🎯 DocumentPipeline.extract_information 开始提取...")
        
        # 提取 PDF 路径和文档 ID（从 kwargs 或 metadata）
        pdf_path = kwargs.get("pdf_path")
        doc_id = kwargs.get("doc_id")
        
        if not pdf_path:
            logger.warning("⚠️ 没有 pdf_path，无法提取")
            return {"success": False, "error": "missing pdf_path"}
        
        # 🌟 使用 smart_extract 的核心逻辑
        try:
            # 调用 smart_extract（如果已实现）
            # 或者实现简化版的提取逻辑
            
            # 简化版：直接从 artifacts 提取关键信息
            extracted_data = {
                "success": True,
                "artifacts_count": len(artifacts),
                "tables": [],
                "images": [],
                "text_chunks": []
            }
            
            # 分类 Artifacts
            for artifact in artifacts:
                artifact_type = artifact.get("type", "unknown")
                
                if artifact_type == "table":
                    extracted_data["tables"].append(artifact)
                elif artifact_type == "image":
                    extracted_data["images"].append(artifact)
                elif artifact_type == "text_chunk":
                    extracted_data["text_chunks"].append(artifact)
            
            logger.info(f"✅ extract_information 完成: {len(extracted_data['tables'])} 个表格, {len(extracted_data['images'])} 张图片")
            
            return extracted_data
            
        except Exception as e:
            logger.error(f"❌ extract_information 失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def smart_extract(
        self,
        pdf_path: str,
        company_id: int,
        doc_id: str,
        progress_callback: Callable = None,
        year: int = None,
        artifacts: List[Dict[str, Any]] = None,
        # 🌟 新增 UI 参数（来自 WebUI）
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None
    ) -> Dict[str, Any]:
        """
        智能結構化提取
        
        🌟 核心改进：根据用户建议，实现真正的 Agentic 写入逻辑
        - UI 决定大方向 (is_index_report, index_theme, confirmed_doc_industry)
        - AI 处理细节落库 (查 Schema、写 SQL、塞 JSON)
        
        Args:
            pdf_path: PDF 路徑
            company_id: 公司 ID (指数报告时为 None)
            doc_id: 文檔 ID
            progress_callback: 進度回調
            year: 年份（由主流程传入）
            artifacts: OpenDataLoader 解析结果
            is_index_report: 是否為指數報告（来自 UI）
            index_theme: 指數主題 (如 "Hang Seng Biotech Index")
            confirmed_doc_industry: 報告定義的行業 (如 "Biotech")
            
        Returns:
            Dict: 提取結果統計
        """
        logger.info(f"🧠 開始智能結構化提取...")
        logger.info(f"   👉 UI 設定: 指數報告={is_index_report}, 行業={confirmed_doc_industry}")
        
        # 🌟 如果没有传入年份，使用当前年份作为 fallback
        if not year:
            year = datetime.now().year
            logger.warning(f"   ⚠️ 未傳入年份，使用當前年份: {year}")
        else:
            logger.info(f"   📅 文檔年份: {year}")
        
        result = {
            "revenue_breakdown": {"pages": [], "extracted": 0},
            "errors": []
        }
        
        # 🌟 Phase 3: 获取总页数（用于上下文感知）
        total_pages = 0
        if artifacts:
            total_pages = max(a.get("page_num", 1) for a in artifacts)
            logger.info(f"   📊 PDF 总页数: {total_pages}")
        
        # 🌟 如果没有 artifacts，跳过提取（不再自己切 PDF）
        if not artifacts:
            logger.warning("⚠️ 沒有 artifacts，跳過結構化提取（不再使用 PyMuPDF 自己切 PDF）")
            result["errors"].append("No artifacts available")
            return result
        
        try:
            # 🌟 Step 3: 在 artifacts 中搜索關鍵字（不再使用 PyMuPDF）
            if progress_callback:
                progress_callback(37.0, "在 artifacts 中搜索目標頁面...")
            
            revenue_pages = set()
            
            # 🌟 方法 A：在 artifacts 中搜索關鍵字（替代 FastParser.scan_for_keywords）
            # 🌟 改為從 JSON 讀取關鍵字（支持 Agent 動態學習）
            # 使用 raw 目录（Docker 容器可写）
            keyword_manager = KeywordManager("/app/data/raw/search_keywords.json")
            keywords = keyword_manager.get_all_keywords_flat("revenue_breakdown")
            
            # 如果 JSON 沒有關鍵字，使用基本 Cold-start 名單
            if not keywords:
                keywords = [
                    "revenue breakdown", "geographical", "geographic", 
                    "region", "segment", "business segment",
                    "收入分佈", "地區收入", "業務分佈"
                ]
                logger.warning("⚠️ Keyword JSON 空白，使用 Cold-start 名單")
            
            for artifact in artifacts:
                artifact_type = artifact.get("type")
                page_num = artifact.get("page_num")
                
                # 只在有文字或表格的區塊搜尋
                if artifact_type == "text_chunk":
                    content = str(artifact.get("content", "")).lower()
                    for keyword in keywords:
                        if keyword.lower() in content:
                            revenue_pages.add(page_num)
                            logger.debug(f"   Page {page_num}: text_chunk 命中 '{keyword}'")
                            break
                
                elif artifact_type == "table":
                    # 表格內容可能在 content_json 中
                    table_json = artifact.get("content_json", {})
                    content = json.dumps(table_json, ensure_ascii=False).lower()
                    for keyword in keywords:
                        if keyword.lower() in content:
                            revenue_pages.add(page_num)
                            logger.debug(f"   Page {page_num}: table 命中 '{keyword}'")
                            break
            
            logger.info(f"   📊 Artifacts 搜索找到 {len(revenue_pages)} 個候選頁面: {sorted(revenue_pages)}")
            
            # 🌟 Phase 3: 记录关键词使用（上下文感知）
            keyword_hits = {}  # 记录每个关键词命中的页面
            for keyword in keywords:
                keyword_hits[keyword] = []  # 初始化
            
            # 🌟 Phase 3: 重新扫描，记录每个关键词命中的页面（用于后续上下文记录）
            for artifact in artifacts:
                artifact_type = artifact.get("type")
                page_num = artifact.get("page_num")
                
                if artifact_type == "text_chunk":
                    content = str(artifact.get("content", "")).lower()
                    for keyword in keywords:
                        if keyword.lower() in content and page_num not in keyword_hits[keyword]:
                            keyword_hits[keyword].append(page_num)
                            break
                
                elif artifact_type == "table":
                    table_json = artifact.get("content_json", {})
                    content = json.dumps(table_json, ensure_ascii=False).lower()
                    for keyword in keywords:
                        if keyword.lower() in content and page_num not in keyword_hits[keyword]:
                            keyword_hits[keyword].append(page_num)
                            break
            
            # 🌟 记录关键词使用（usage_count）
            for keyword, hit_pages in keyword_hits.items():
                if hit_pages:
                    logger.debug(f"   📝 Keyword '{keyword}' used in pages: {hit_pages}")
            
            # 🌟 移除方法 B (LLM 語義分類)：用户明确不想用 PyMuPDF 自己切 PDF
            # 🌟 完全依赖 Artifacts 搜索结果，不再调用 _extract_all_pages_text
            
            revenue_pages = sorted(list(revenue_pages))
            result["revenue_breakdown"]["pages"] = revenue_pages
            
            if not revenue_pages:
                logger.warning("⚠️ 混合路由找不到任何候選頁面，放棄結構化提取（但兜底資料已保存）")
                return result
            
            logger.info(f"   🎯 總共找到 {len(revenue_pages)} 個 Revenue Breakdown 候選頁面: {sorted(revenue_pages)}")
            
            if not revenue_pages:
                logger.warning("⚠️ 找不到任何候選頁面，放棄結構化提取")
                return result
            
            # 🌟 Step 4: 從 artifacts 中提取候選頁面內容，調用 LLM 提取結構化數據
            for i, page_num in enumerate(sorted(revenue_pages)):
                if progress_callback:
                    progress = 40.0 + (i + 1) / max(len(revenue_pages), 1) * 40.0
                    progress_callback(progress, f"提取 Page {page_num}...")
                
                # 🌟 從 artifacts 中提取該頁面的所有內容
                page_artifacts = [a for a in artifacts if a.get("page_num") == page_num]
                
                if not page_artifacts:
                    logger.warning(f"   ⚠️ Page {page_num} 在 artifacts 中找不到，跳過")
                    continue
                
                # 合併該頁面的所有文本和表格
                page_content = self._merge_page_artifacts(page_artifacts)
                
                if not page_content or len(page_content.strip()) < 50:
                    logger.warning(f"   ⚠️ Page {page_num} 內容過短，跳過")
                    continue
                
                logger.info(f"   📊 提取 Page {page_num} ({len(page_content)} chars)...")
                
                # 🌟 核心改进：根据用户建议，实现 Agentic 写入逻辑
                # UI 决定大方向，AI 处理细节落库
                
                try:
                    # 🌟 真正的 Agentic 写入逻辑（Stage 5 专属 Prompt）
                    # 🌟 修正：直接调用 _get_agentic_pipeline()，而不是检查 self.agent_loop
                    
                    # 1. 构建专属于 Stage 5 的 Prompt
                    if is_index_report:
                        report_context = f"""
这是一份【指数/行业报告】(主题: {index_theme or 'Unknown'}, 行业: {confirmed_doc_industry or 'Unknown'})。
里面包含多间公司的数据，请不要预设单一母公司。
行业分配规则：规则 A - 所有成分股都应指派行业 '{confirmed_doc_industry or 'Unknown'}'"""
                    else:
                        report_context = f"""
这是一份【单一公司年报】，母公司 ID 为 {company_id or '待提取'}。
行业分配规则：规则 B - 使用 AI 提取各公司的行业"""
                    
                    # 2. 🌟 改进版：智能多表写入 Prompt（不再只关注 revenue_breakdown）
                    stage5_prompt = f"""
你是一个高级 PostgreSQL 数据库写入 Agent。
任务目标：分析 PDF 第 {page_num} 页的内容类型，智能提取并写入对应的数据表。

【背景资讯】
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
                    
                    # 3. 🎯 直接获取 Agentic Pipeline（不依赖 agent_loop）
                    pipeline = self._get_agentic_pipeline()
                    
                    if pipeline:
                        # 🌟 构建 user_hints，标记这是 Stage 5
                        user_hints = {
                            "stage": "structured_extraction",  # 🌟 标记这是 Stage 5（不是 Stage 0）
                            "doc_type": "index_report" if is_index_report else "annual_report",
                            "index_theme": index_theme,
                            "confirmed_doc_industry": confirmed_doc_industry,
                            "page_num": page_num,
                            "year": year,
                            "company_id": company_id,
                            "page_content": page_content[:6000]  # 传入页面内容
                        }
                        
                        logger.info(f"   🤖 将 Page {page_num} 交给 AgenticIngestionOrchestrator 处理...")
                        
                        # 🌟 调用 process_document 并传入 Stage 5 Prompt
                        result_agentic = await pipeline.process_document(
                            document_content=stage5_prompt,  # 🌟 传入 Stage 5 Prompt（不叠加 Stage 0 的 System Prompt）
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
                                        company_id, year, extracted_data, 
                                        Path(pdf_path).name, page_num
                                    )
                                    result["revenue_breakdown"]["extracted"] += inserted
                                    logger.info(f"   ✅ Page {page_num} 提取成功: {inserted} 瀦記錄")
                                    
                                    # 🌟 Phase 3: 记录关键词命中（带上下文）
                                    km = KeywordManager()
                                    for keyword, hit_pages in keyword_hits.items():
                                        if page_num in hit_pages:
                                            km.record_hit_with_context(
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
                                logger.warning(f"   ⚠️ Page {page_num} 百分比總和 {total_pct}% 不為 100%，跳過")
                        else:
                            logger.warning(f"   ⚠️ Page {page_num} LLM 提取失敗")
                            logger.warning(f"   ⚠️ Page {page_num} LLM 提取失敗")
                            
                except Exception as e:
                    logger.error(f"   ❌ Page {page_num} 提取失敗: {e}")
                    result["errors"].append(f"Page {page_num}: {str(e)}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 智能提取失敗: {e}")
            result["errors"].append(str(e))
            return result
    
    def _merge_page_artifacts(self, page_artifacts: List[Dict[str, Any]]) -> str:
        """
        合併一個頁面的所有 artifacts 為文本
        
        Args:
            page_artifacts: 該頁面的所有 artifacts
            
        Returns:
            str: 合併後的文本內容
        """
        text_parts = []
        
        for artifact in page_artifacts:
            artifact_type = artifact.get("type")
            
            if artifact_type == "text_chunk":
                content = artifact.get("content", "")
                if content:
                    text_parts.append(content)
            
            elif artifact_type == "table":
                table_json = artifact.get("content_json", {})
                table_md = self._json_table_to_markdown(table_json)
                if table_md:
                    text_parts.append(table_md)
        
        return "\n\n".join(text_parts)
    
    async def _insert_revenue_breakdown(
        self,
        company_id: int,
        year: int,
        extracted_data: Dict[str, Any],
        source_file: str,
        source_page: int,
        source_document_id: int = None  # 🌟 Schema v2.3: 需要 document_id (Integer)
    ) -> int:
        """
        将 Revenue Breakdown 数据写入数据库（Schema v2.3）
        
        Args:
            company_id: 公司 ID
            year: 年份
            extracted_data: 提取的数据
            source_file: 源文件名（向后兼容）
            source_page: 源页码（向后兼容）
            source_document_id: documents 表的 Integer ID
            
        Returns:
            int: 插入的记录数
        """
        try:
            inserted_count = 0
            
            for category, data in extracted_data.items():
                percentage = data.get("percentage")
                amount = data.get("amount")
                
                # 🌟 Schema v2.3: 使用新的参数名
                await self.db.insert_revenue_breakdown(
                    company_id=company_id,
                    year=year,
                    extracted_data={category: data},  # 传递单条数据
                    source_file=source_file,
                    source_page=source_page,
                    segment_type="business",  # 🌟 新参数
                    currency="HKD",
                    source_document_id=source_document_id  # 🌟 新参数
                )
                inserted_count += 1
            
            logger.debug(f"   💾 已寫入 {inserted_count} 瀦 Revenue Breakdown 記錄")
            return inserted_count
            
        except Exception as e:
            logger.error(f"   ❌ Revenue Breakdown 入庫失敗: {e}")
            return 0
    
    async def save_all_pages_to_fallback_table(
        self,
        pdf_path: str,
        company_id: int,
        doc_id: str,
        year: int,
        artifacts: List[Dict[str, Any]] = None  # 🌟 新增：OpenDataLoader 解析结果
    ) -> int:
        """
        Save all PDF pages to document_pages table (Zone 2 fallback).
        
        🔧 重构：不再使用 PyMuPDF 自己切 PDF，完全依赖 OpenDataLoader artifacts
        
        Args:
            pdf_path: PDF file path
            company_id: Company ID
            doc_id: Document ID
            year: Document year
            artifacts: OpenDataLoader 解析结果
            
        Returns:
            int: Number of pages saved
        """
        logger.info(f"   Saving pages to fallback table from artifacts...")
        
        if not artifacts:
            logger.warning("   ⚠️ 没有 artifacts，跳过保存")
            return 0
        
        # 🌟 N+1 效能優化：在迴圈外先查出 document_id（一次查詢，重複使用）
        document_id = await self.db.get_document_internal_id(doc_id)
        if not document_id:
            logger.error(f"❌ 找不到文檔 ID={doc_id} 的內部 ID，無法保存 pages")
            return 0
        
        source_file = Path(pdf_path).name
        saved_count = 0
        
        # 🌟 从 artifacts 中按页面分组
        pages_content: Dict[int, Dict[str, Any]] = {}
        
        for artifact in artifacts:
            page_num = artifact.get("page_num", 1)
            artifact_type = artifact.get("type")
            
            if page_num not in pages_content:
                pages_content[page_num] = {
                    "text_chunks": [],
                    "tables": [],
                    "images": [],
                    "has_charts": False
                }
            
            if artifact_type == "text_chunk":
                content = artifact.get("content", "")
                if content:
                    pages_content[page_num]["text_chunks"].append(content)
            
            elif artifact_type == "table":
                table_json = artifact.get("content_json", {})
                pages_content[page_num]["tables"].append(table_json)
                pages_content[page_num]["has_charts"] = True
            
            elif artifact_type == "image":
                pages_content[page_num]["images"].append(artifact)
                pages_content[page_num]["has_charts"] = True
        
        # 🌟 将每页内容合并为 markdown 格式
        for page_num, page_data in pages_content.items():
            try:
                # 合并所有文本块
                text_content = "\n\n".join(page_data["text_chunks"])
                
                # 如果有表格，将表格 JSON 转为 markdown 表格
                for table_json in page_data["tables"]:
                    table_md = self._json_table_to_markdown(table_json)
                    if table_md:
                        text_content += "\n\n" + table_md
                
                if not text_content or len(text_content.strip()) < 10:
                    continue
                
                content_type = "opendataloader_text"
                if page_data["tables"] or page_data["images"]:
                    content_type = "opendataloader_hybrid"
                
                success = await self.db.insert_document_page(
                    company_id=company_id,
                    document_id=document_id,  # 🌟 N+1 效能優化：傳入整數 ID
                    year=year,
                    page_num=page_num,
                    markdown_content=text_content,
                    source_file=source_file,
                    content_type=content_type,
                    has_charts=page_data["has_charts"]
                )
                
                if success:
                    saved_count += 1
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Page {page_num} 保存失敗: {e}")
                continue
        
        logger.info(f"   ✅ Saved {saved_count}/{len(pages_content)} pages from artifacts")
        return saved_count
    
    def _json_table_to_markdown(self, table_json: Dict[str, Any]) -> Optional[str]:
        """
        将 OpenDataLoader 表格 JSON 转换为 Markdown 表格
        
        Args:
            table_json: OpenDataLoader 表格数据
            
        Returns:
            str: Markdown 表格字符串
        """
        try:
            # OpenDataLoader 表格结构可能在不同的字段中
            content = table_json.get("content", "")
            if isinstance(content, str) and content.strip():
                return content
            
            # 尝试从其他字段提取
            rows = table_json.get("rows", table_json.get("data", []))
            if not rows or not isinstance(rows, list):
                return None
            
            # 构建简单的 markdown 表格
            md_lines = []
            for i, row in enumerate(rows[:20]):  # 限制行数
                if isinstance(row, list):
                    cells = [str(cell) if cell else "" for cell in row]
                    md_lines.append("| " + " | ".join(cells) + " |")
                    if i == 0:
                        # 添加表头分隔线
                        md_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
            
            return "\n".join(md_lines) if md_lines else None
            
        except Exception as e:
            logger.debug(f"   ⚠️ 表格转换失败: {e}")
            return None
    
    # ===========================================
    # 輔助方法
    # ===========================================
    
    def _compute_file_hash(self, file_path: str) -> str:
        """計算文件 Hash"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    # 🔧 已移除 _extract_all_pages_text - 不再使用 PyMuPDF 自己切 PDF
    
    async def _create_document(
        self,
        pdf_path: str,
        company_id: Optional[int],
        doc_id: str,
        file_hash: str
    ):
        """創建文檔記錄"""
        pdf_path_obj = Path(pdf_path)
        await self.db.create_document(
            doc_id=doc_id,
            company_id=company_id,
            filename=pdf_path_obj.name,     # 👈 確保這行存在！
            title=pdf_path_obj.stem,
            file_path=str(pdf_path_obj.absolute()),
            file_hash=file_hash,
            file_size=pdf_path_obj.stat().st_size
        )
    
    async def _extract_and_create_company(
        self,
        pdf_path: str,
        doc_id: str,
        artifacts: List[Dict[str, Any]] = None  # 🌟 新增：OpenDataLoader 解析结果
    ) -> Optional[int]:
        """
        🎯 從封面提取公司信息
        
        🔧 重構：不再使用 PyMuPDF 自己切 PDF，完全依賴 OpenDataLoader artifacts
        
        Args:
            pdf_path: PDF 路徑
            doc_id: 文檔 ID
            artifacts: OpenDataLoader 解析结果
            
        Returns:
            int: 公司 ID
        """
        logger.info(f"🎯 正在從封面提取公司元數據...")
        
        stock_code = None
        year = None
        name_en = None
        name_zh = None
        
        # ==========================================
        # 🌟 方案 A: 從 artifacts 提取（逐页尝试）
        # ==========================================
        
        if artifacts:
            # 🌟 逻辑改进：先尝试 Page 1，失败才尝试 Page 2
            for page_num in [1, 2]:
                if stock_code:  # 已提取成功，跳过后续页面
                    break
                
                page_artifacts = [a for a in artifacts if a.get("page_num") == page_num]
                
                if not page_artifacts:
                    logger.info(f"   ⚠️ Page {page_num} 在 artifacts 中找不到")
                    continue
                
                page_text = self._merge_page_artifacts(page_artifacts)
                
                if not page_text or len(page_text.strip()) < 50:
                    logger.info(f"   ⚠️ Page {page_num} 内容过短，跳过")
                    continue
                
                logger.info(f"   📄 从 Page {page_num} 提取公司信息...")
                
                # 調用 LLM 提取公司信息
                metadata = await self.agent.extract_company_metadata_from_cover(page_text)
                
                if metadata:
                    stock_code_raw = metadata.get("stock_code")
                    year_raw = metadata.get("year")
                    name_en_raw = metadata.get("name_en")
                    name_zh_raw = metadata.get("name_zh")
                    
                    # 只有 stock_code 有效才算成功
                    if stock_code_raw:
                        stock_code = stock_code_raw
                        
                        # 🌟 强制转换 year 为 int
                        try:
                            year = int(year_raw) if year_raw else None
                        except ValueError:
                            logger.warning(f"   ⚠️ Artifacts 提取嘅 year ({year_raw}) 無法轉為整數")
                            year = None
                        
                        name_en = name_en_raw
                        name_zh = name_zh_raw
                        
                        logger.info(f"   ✅ Artifacts Page {page_num} 提取成功: Stock={stock_code}, Year={year}")
                        break  # 成功，不再尝试其他页面
                    else:
                        logger.info(f"   ⚠️ Page {page_num} 未找到 stock_code，继续尝试...")
        
        # ==========================================
        # 🌟 方案 A2: Vision LLM 提取封面（逐页尝试）
        # ==========================================
        
        if not stock_code:
            logger.info("   🎨 Artifacts 未提取到公司信息，启动 Vision API...")
            
            try:
                # 🌟 使用 llm_core.vision() 替代 VisionAPIClient
                import fitz  # PyMuPDF
                import base64
                
                # 打开 PDF
                doc = fitz.open(pdf_path)
                
                # 🌟 逻辑改进：先尝试 Page 1，失败才尝试 Page 2
                for page_num in [1, 2]:
                    if stock_code:  # 已提取成功，跳过后续页面
                        break
                    
                    if page_num > len(doc):
                        logger.info(f"   ⚠️ PDF 只有 {len(doc)} 页，跳过 Page {page_num}")
                        continue
                    
                    logger.info(f"   🎨 使用 Vision API 分析 Page {page_num}...")
                    
                    # 将页面转换为图片
                    page = doc.load_page(page_num - 1)  # PyMuPDF 是 0-indexed
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
                    img_bytes = pix.tobytes("png")
                    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                    
                    # 调用 llm_core.vision() 提取封面信息
                    from nanobot.core.llm_core import llm_core
                    
                    prompt = """
提取封面中的公司信息，返回 JSON 格式：
{
    "stock_code": "股票代码（如 02359）",
    "year": "年份（如 2023）",
    "name_en": "英文公司名称",
    "name_zh": "中文公司名称"
}

只返回 JSON，不要其他解释。
"""
                    
                    vision_response = await llm_core.vision(
                        img_base64,
                        prompt,
                        model="qwen3.5-plus"  # 使用云端 API
                    )
                    
                    # 解析 JSON 响应
                    import json as json_module
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', vision_response)
                    if json_match:
                        vision_result = json_module.loads(json_match.group(0))
                        
                        vision_stock = vision_result.get("stock_code")
                        vision_year = vision_result.get("year")
                        vision_name_en = vision_result.get("name_en")
                        vision_name_zh = vision_result.get("name_zh")
                        
                        # 只有 stock_code 有效才算成功
                        if vision_stock:
                            stock_code = vision_stock
                            logger.info(f"   ✅ Vision Page {page_num} 提取 stock_code: {stock_code}")
                            
                            if vision_year:
                                try:
                                    year = int(vision_year)
                                    logger.info(f"   ✅ Vision Page {page_num} 提取 year: {year}")
                                except ValueError:
                                    logger.warning(f"   ⚠️ Vision 提取嘅 year ({vision_year}) 無法轉為整數")
                            
                            if vision_name_en or vision_name_zh:
                                name_en = vision_name_en or name_en
                                name_zh = vision_name_zh or name_zh
                                logger.info(f"   ✅ Vision Page {page_num} 提取 name: {name_en or name_zh}")
                            
                            break  # 成功，不再尝试其他页面
                        else:
                            logger.info(f"   ⚠️ Vision Page {page_num} 未找到 stock_code，继续尝试...")
                    else:
                        logger.info(f"   ⚠️ Vision Page {page_num} 无法解析 JSON，继续尝试...")
                
                doc.close()
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Vision 提取异常: {e}，继续 Fallback...")
        
        # ==========================================
        # 🌟 方案 B: Fallback - 從文件名提取
        # ==========================================
        
        if not stock_code or not year:
            import re
            filename = Path(pdf_path).stem
            logger.info(f"   📄 提取失敗，嘗試從文件名提取: {filename}")
            
            # 提取 stock_code (格式: stock_XXXXX)
            stock_match = re.search(r'stock_(\d{4,5})', filename)
            if stock_match:
                stock_code = stock_match.group(1).zfill(5)
                logger.info(f"   ✅ 從文件名提取 stock_code: {stock_code}")
            
            # 提取 year (格式: _YYYY 或 _YYYY_)
            year_matches = re.findall(r'_(\d{4})(?:_|$)', filename)
            for y in year_matches:
                y_int = int(y)
                if 2000 <= y_int <= 2030:
                    year = y_int
                    logger.info(f"   ✅ 從文件名提取 year: {year}")
                    break
        
        # ==========================================
        # 验证必要字段
        # ==========================================
        
        if not stock_code:
            logger.error(f"❌ 封面解析失敗：找不到 Stock Code！PDF: {pdf_path}")
            return None
        
        logger.info(f"✅ 元數據提取成功: Stock={stock_code}, Year={year}, Name={name_en or name_zh or 'N/A'}")
        
        # Upsert 公司信息
        company_id = await self.db.upsert_company(
            stock_code=stock_code,
            name_en=name_en,
            name_zh=name_zh,
            name_source="extracted",  # 來自 PDF 提取（Vision 方法）
            sector="BioTech"
        )
        
        # 更新文檔的 year
        if year and company_id:
            try:
                year = int(year)  # 🌟 確保一定係 int
                await self.db.update_document_company_id(doc_id, company_id, year)
                logger.info(f"✅ 文檔 {doc_id} 已關聯公司 ID={company_id}, Year={year}")
            except ValueError:
                logger.error(f"❌ 嘗試更新 year 失敗，無效的整數: {year}")
        
        return company_id
    
    async def _get_document_year(self, doc_id: str) -> Optional[int]:
        """
        從數據庫獲取文檔的年份
        
        🎯 取代爛正則表達式：年份現在由 LLM 從封面精準提取
        
        Args:
            doc_id: 文檔 ID
            
        Returns:
            int: 年份，如果未找到則返回 None
        """
        try:
            row = await self.db.conn.fetchrow(
                "SELECT year FROM documents WHERE doc_id = $1",
                doc_id
            )
            if row and row['year']:
                return row['year']
        except Exception as e:
            logger.warning(f"⚠️ 無法從數據庫獲取年份: {e}")
        
        return None
    
    # ===========================================
    # 🌟 OpenDataLoader 整合方法 (替代 OpenDataLoaderProcessor)
    # ===========================================
    
    async def process_pdf_full(
        self,
        pdf_path: str,
        company_id: int = None,
        doc_id: str = None,
        progress_callback: Callable = None,
        replace: bool = False,
        # 🌟 新增指數報告參數（接收 WebUI 傳過來的設定）
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None
    ) -> Dict[str, Any]:
        """
        🌟 完整 PDF 處理流程（整合 OpenDataLoaderParser）
        
        此方法取代舊的 OpenDataLoaderProcessor，使用清晰的分層架構：
        1. OpenDataLoaderParser - 解析 PDF → Artifacts
        2. FinancialAgent - 結構化提取（從 Artifacts 中提取）
        3. DBClient - 數據入庫
        
        🔧 不再使用 PyMuPDF 自己切 PDF，完全依賴 OpenDataLoader 解析結果
        
        Args:
            pdf_path: PDF 檔案路徑
            company_id: 公司 ID (可選，將從封面自動提取)
            doc_id: 文檔 ID
            progress_callback: 進度回調
            replace: 是否強制重新處理
            is_index_report: 是否為指數報告（恆指生技指數等）
            index_theme: 指數主題 (如 "Hang Seng Biotech Index")
            confirmed_doc_industry: 報告定義的行業 (如 "Biotech")
                - 規則 A: 所有成分股都會被強制指派此行業
            
        Returns:
            Dict: 處理結果（兼容 OpenDataLoaderProcessor 返回格式）
        """
        logger.info(f"🚀 DocumentPipeline.process_pdf_full: {pdf_path}")
        
        # 🌟 根據文件類型決定處理方式
        if is_index_report:
            logger.info(f"📊 路線 A: 指數報告處理 (行業: {confirmed_doc_industry})")
        else:
            logger.info(f"📄 路線 B: 一般年報處理 (AI 提取行業)")
        
        try:
            # Step 1: 計算 Hash & 檢查重複
            if progress_callback:
                progress_callback(5.0, "計算 Hash 與檢查重複...")
            file_hash = self._compute_file_hash(pdf_path)
            
            if replace:
                logger.info(f"🔄 Replace mode: 清理舊數據...")
                await self.db.delete_document(doc_id)
            else:
                exists = await self.db.check_document_exists(doc_id, file_hash)
                if exists:
                    logger.warning(f"⚠️ 文檔已存在，跳過: {doc_id}")
                    return {"status": "skipped", "reason": "duplicate"}
            
            # Step 2: 創建文檔記錄
            await self._create_document(pdf_path, company_id, doc_id, file_hash)
            
            # Step 3: 🌟 快速解析 Page 1-2（用于公司提取）
            if progress_callback:
                progress_callback(10.0, "快速解析封面...")
            
            cover_artifacts = []
            if self.opendataloader_parser:
                # 🌟 只解析 Page 1-2（快速模式，不启用 Hybrid）
                cover_artifacts = self.opendataloader_parser.parse_pages(pdf_path, pages=[1, 2], doc_id=doc_id)
                logger.info(f"   ✅ 封面解析完成: {len(cover_artifacts)} 個 artifacts")
            
            # Step 4: 提取公司信息（如果沒有 company_id，且不是指數報告）
            if progress_callback:
                progress_callback(20.0, "🧠 提取公司信息...")
            
            # 🌟 修正：如果是指數報告，絕對不能提取母公司！
            if not company_id and not is_index_report:
                # 🌟 使用封面 artifacts 提取公司信息（更快）
                company_id = await self._extract_and_create_company(pdf_path, doc_id, artifacts=cover_artifacts)
                if company_id:
                    logger.info(f"✅ 已關聯公司: ID={company_id}")
                else:
                    logger.warning("⚠️ 無法提取公司信息")
            elif is_index_report:
                logger.info("ℹ️ 指數報告無需提取母公司，跳過提取")
                company_id = None
            
            # Step 5: 🌟 完整解析 PDF（用于数据提取）
            if progress_callback:
                progress_callback(30.0, "完整解析 PDF...")
            
            if self.opendataloader_parser:
                artifacts = await self.opendataloader_parser.parse_async(pdf_path, doc_id)
                logger.info(f"   ✅ OpenDataLoader 完整解析: {len(artifacts)} 個 artifacts")
                
                # 合併封面 artifacts（如果完整解析沒有 Page 1-2）
                if cover_artifacts and not any(a.get("page_num") in [1, 2] for a in artifacts):
                    artifacts.extend(cover_artifacts)
                    logger.info(f"   📄 已合併封面 artifacts")
                
                # 保存 Artifacts
                await self._save_opendataloader_artifacts(artifacts, doc_id, company_id, pdf_path)
                
                # 保存 output.json
                output_json_path = self.data_dir / doc_id / "output.json"
                output_json_path.parent.mkdir(parents=True, exist_ok=True)
                import json as json_module
                with open(output_json_path, "w", encoding="utf-8") as f:
                    json_module.dump(artifacts, f, ensure_ascii=False, indent=2)
                logger.info(f"   💾 已保存 output.json: {output_json_path}")
            else:
                logger.warning("⚠️ OpenDataLoaderParser 未啟用")
                artifacts = cover_artifacts
            
            # Step 6: 保存所有頁面到兜底表 (Zone 2)
            if progress_callback:
                progress_callback(60.0, "保存所有頁面到兜底表...")
            
            doc_year = await self._get_document_year(doc_id) or datetime.now().year
            
            stats = {
                "total_chunks": len([a for a in artifacts if a.get("type") == "text_chunk"]),
                "total_tables": len([a for a in artifacts if a.get("type") == "table"]),
                "total_images": len([a for a in artifacts if a.get("type") == "image"]),
                "total_artifacts": len(artifacts)
            }
            
            saved_pages = await self.save_all_pages_to_fallback_table(
                pdf_path, company_id, doc_id, doc_year,
                artifacts=artifacts
            )
            stats["document_pages_saved"] = saved_pages
            
            # Step 7: 智能結構化提取
            if progress_callback:
                progress_callback(70.0, "智能提取結構化數據...")
            
            extraction_result = await self.smart_extract(
                pdf_path, company_id, doc_id, 
                lambda p, m: progress_callback(70 + p * 0.2, m) if progress_callback else None,
                year=doc_year,
                artifacts=artifacts,
                # 🌟 传递 UI 参数，让 Agent 知道报告类型
                is_index_report=is_index_report,
                index_theme=index_theme,
                confirmed_doc_industry=confirmed_doc_industry
            )
            stats["structured_extraction"] = extraction_result
            
            if is_index_report:
                logger.info("ℹ️ 指數報告處理完成（多公司數據已由 Agent 提取）")
            elif not company_id:
                logger.warning("⚠️ 一般年報但無 company_id，結構化提取可能不完整")
            else:
                logger.info("✅ 一般年報結構化提取完成")
            
            # Step 5.5: 🎯 圖文關聯映射 (跨模態 Magic)
            if progress_callback:
                progress_callback(92.0, "建立圖文關聯...")
            
            try:
                # 初始化 EntityResolver（帶 DBClient）
                from .extractors.entity_resolver import EntityResolver
                
                resolver = EntityResolver(db_client=self.db)
                
                # 🌟 使用 document_id（整數）而非 doc_id（字串）
                document_internal_id = await self.db.get_document_internal_id(doc_id)
                
                if document_internal_id:
                    links_count = await resolver.link_image_and_text_context(document_internal_id)
                    stats["cross_modal_links"] = links_count
                    logger.info(f"✅ Stage 5.5 完成：建立了 {links_count} 條跨頁圖文關聯")
                else:
                    logger.warning(f"⚠️ Stage 5.5 跳過：無法獲取 document_id")
                    stats["cross_modal_links"] = 0
                    
            except Exception as e:
                logger.warning(f"⚠️ Stage 5.5 失敗（可忽略）: {e}")
                stats["cross_modal_links"] = 0
            
            # Step 6: 觸發 Vanna 訓練
            if progress_callback:
                progress_callback(95.0, "觸發 Vanna 訓練...")
            await self._trigger_vanna_training(doc_id)
            
            # Step 7: 更新文檔狀態
            await self.db.update_document_status(doc_id, "completed", stats)
            
            if progress_callback:
                progress_callback(100.0, "✅ 處理完成")
            
            return {
                "status": "completed",
                "doc_id": doc_id,
                "company_id": company_id,
                **stats
            }
            
        except Exception as e:
            logger.error(f"❌ process_pdf_full 失敗: {e}")
            import traceback
            traceback.print_exc()
            await self.db.update_document_status(doc_id, "failed", error=str(e))
            return {"status": "failed", "error": str(e)}
    
    async def _save_opendataloader_artifacts(
        self,
        artifacts: List[Dict[str, Any]],
        doc_id: str,
        company_id: Optional[int],
        pdf_path: str = None  # 🔧 新增：PDF 路徑參數
    ):
        """
        保存 OpenDataLoader Artifacts 到數據庫
        
        🌟 N+1 效能優化：在迴圈外先查出 document_id，避免每次寫入都執行 SELECT
        
        Args:
            artifacts: Artifacts 列表
            doc_id: 文檔 ID
            company_id: 公司 ID
        """
        import json as json_module
        
        doc_dir = self.data_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        
        # 🌟 N+1 效能優化：在迴圈外先查出 document_id（一次查詢，重複使用）
        document_id = await self.db.get_document_internal_id(doc_id)
        if not document_id:
            logger.error(f"❌ 找不到文檔 ID={doc_id} 的內部 ID，無法保存 Artifacts")
            return
        
        for idx, artifact in enumerate(artifacts):
            artifact_type = artifact.get("type")
            page_num = artifact.get("page_num")
            metadata = artifact.get("metadata", {})
            
            try:
                if artifact_type == "table":
                    # 保存表格 JSON
                    table_json_path = doc_dir / f"table_{idx:04d}.json"
                    with open(table_json_path, 'w', encoding='utf-8') as f:
                        json_module.dump(artifact.get("content_json", {}), f, ensure_ascii=False, indent=2)
                    
                    # 記錄到 raw_artifacts
                    # 🌟 N+1 效能優化：傳入整數 ID
                    await self.db.insert_raw_artifact(
                        artifact_id=f"{doc_id}_table_{idx:04d}",
                        document_id=document_id,  # 🌟 傳入整數 ID
                        company_id=company_id,
                        file_type="table_json",
                        file_path=str(table_json_path.relative_to(self.data_dir)),
                        page_num=page_num,
                        metadata=json_module.dumps(metadata)
                    )
                
                elif artifact_type == "image":
                    # 🔧 修復：實際保存圖片文件（支持 base64 和外部文件）
                    image_dir = doc_dir / "images"
                    image_dir.mkdir(parents=True, exist_ok=True)
                    
                    image_filename = f"image_{idx:04d}.png"
                    image_path = image_dir / image_filename
                    image_saved = False
                    
                    # 🌟 优先检查外部图片文件路径（image_path）
                    image_path_source = artifact.get("image_path")
                    if image_path_source and Path(image_path_source).exists():
                        try:
                            # 直接复制外部图片文件
                            import shutil
                            shutil.copy2(image_path_source, str(image_path))
                            image_saved = True
                            logger.debug(f"✅ 已复制外部图片: {image_path_source} → {image_path}")
                        except Exception as e:
                            logger.warning(f"⚠️ 图片复制失败: {e}")
                    
                    # 🌟 如果没有外部文件，尝试从 base64 数据保存
                    if not image_saved:
                        image_data = artifact.get("image_data")
                        
                        if image_data:
                            try:
                                if isinstance(image_data, str) and image_data.startswith("data:image"):
                                    base64_data = image_data.split(",", 1)[1] if "," in image_data else image_data
                                    import base64
                                    image_bytes = base64.b64decode(base64_data)
                                    
                                    with open(image_path, 'wb') as f:
                                        f.write(image_bytes)
                                    image_saved = True
                                    logger.debug(f"✅ 已保存圖片 (base64 data URI): {image_path}")
                                
                                elif isinstance(image_data, str) and len(image_data) > 100:
                                    import base64
                                    try:
                                        image_bytes = base64.b64decode(image_data)
                                        with open(image_path, 'wb') as f:
                                            f.write(image_bytes)
                                        image_saved = True
                                        logger.debug(f"✅ 已保存圖片 (base64): {image_path}")
                                    except Exception:
                                        pass
                                
                            except Exception as e:
                                logger.warning(f"⚠️ 圖片保存失敗：{e}")
                    
                    # 🔧 移除 PDF fallback - 不再自己切 PDF
                    if not image_saved:
                        logger.warning(f"⚠️ OpenDataLoader 未提供圖片數據，跳過保存: {image_filename}")
                    
                    # 記錄到 raw_artifacts
                    # 🌟 N+1 效能優化：傳入整數 ID
                    await self.db.insert_raw_artifact(
                        artifact_id=f"{doc_id}_image_{idx:04d}",
                        document_id=document_id,  # 🌟 傳入整數 ID
                        company_id=company_id,
                        file_type="image",
                        file_path=str(image_path.relative_to(self.data_dir)) if image_saved else f"{doc_id}/images/{image_filename}",
                        page_num=page_num,
                        metadata=json_module.dumps({
                            **metadata,
                            "image_saved": image_saved,
                            "image_path_source": image_path_source
                        })
                    )
                    
                    if image_saved:
                        logger.debug(f"🖼️ 圖片已保存：{image_path}")
                    else:
                        logger.warning(f"⚠️ 圖片無法保存，僅記錄 metadata: {image_filename}")
                
                # text_chunk 已保存在 output.json 中，無需單獨入庫
                
            except Exception as e:
                logger.warning(f"⚠️ Artifact {idx} 保存失敗: {e}")
                continue
    
    async def _trigger_vanna_training(self, doc_id: str, max_retries: int = 3):
        """
        觸發 Vanna 訓練 (具備重試機制)
        
        Args:
            doc_id: 文檔 ID
            max_retries: 最大重試次數
        """
        import httpx
        import asyncio
        
        vanna_url = os.getenv("VANNA_SERVICE_URL", "http://vanna-service:8000")  # 🌟 修正端口为 8000
        
        for attempt in range(1, max_retries + 1):
            try:
                # 增加 Timeout 時間到 60 秒，並使用 async client
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{vanna_url}/api/train",
                        json={"train_type": "sql", "doc_id": doc_id}
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"✅ Vanna 訓練已觸發: {doc_id} (Attempt {attempt})")
                        return  # 成功就提早結束
                    else:
                        logger.warning(f"⚠️ Vanna 訓練失敗 (HTTP {response.status_code}) - Attempt {attempt}")
                        
            except Exception as e:
                logger.warning(f"⚠️ Vanna 連線失敗 ({e}) - Attempt {attempt}")
            
            # 如果不是最後一次嘗試，就等待後重試 (遞增延遲：2s, 4s, 8s...)
            if attempt < max_retries:
                wait_time = 2 ** attempt
                logger.info(f"⏳ 等待 {wait_time} 秒後重試觸發 Vanna...")
                await asyncio.sleep(wait_time)
                
        logger.error(f"❌ Vanna 訓練觸發徹底失敗，已達最大重試次數: {doc_id}")
    
    # ===========================================
# 便捷函數
# ===========================================

async def process_pdf_simple(
    pdf_path: str,
    doc_id: str,
    company_id: int = None,
    db_url: str = None
) -> Dict[str, Any]:
    """
    簡單的 PDF 處理入口
    
    Args:
        pdf_path: PDF 路徑
        doc_id: 文檔 ID
        company_id: 公司 ID (可選)
        db_url: 數據庫 URL
        
    Returns:
        Dict: 處理結果
    """
    pipeline = DocumentPipeline(db_url=db_url, enable_hybrid=True)  # 🌟 启用 Hybrid 模式
    
    try:
        await pipeline.connect()
        result = await pipeline.process_pdf(
            pdf_path=pdf_path,
            doc_id=doc_id,
            company_id=company_id
        )
        return result
    finally:
        await pipeline.close()