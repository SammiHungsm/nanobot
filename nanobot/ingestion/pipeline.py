"""
Document Pipeline - 主流程協調器

這是整個 ingestion 系統的大腦，協調各個模組完成 PDF 處理流程。

職責分離（Separation of Concerns）：
1. Parser 層 (VisionParser, FastParser, OpenDataLoaderParser)：只負責「看」，輸出原始資料
2. Agent 層 (FinancialAgent, PageClassifier)：只負責「想」，輸出結構化 JSON
3. Pipeline 層 (DocumentPipeline)：唯一的大腦，負責資料庫和流程控制

Two-Stage LLM Pipeline:
1. Stage 1 (便宜 & 快速): PageClassifier 語義分類
2. Stage 2 (昂貴 & 精準): Vision Parser + Financial Agent 只處理相關頁面

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

# 導入各個模組（Parser 層）
from .parsers.vision_parser import VisionParser, FastParser
from .parsers.opendataloader_parser import OpenDataLoaderParser

# 導入各個模組（Agent 層）
from .extractors.financial_agent import FinancialAgent
from .extractors.page_classifier import PageClassifier

# 導入統一的 LLM 客戶端
from .utils.llm_client import get_llm_client, get_llm_model, get_vision_model


# ===========================================
# 跨頁表格合併工具
# ===========================================

class CrossPageTableMerger:
    """
    跨頁表格合併器
    
    檢測並合併跨頁表格：
    - 判斷表格是否延續到下一頁
    - 合併表格內容
    - 組合後再交給 LLM 提取
    """
    
    def __init__(self):
        self.previous_table: Optional[Dict[str, Any]] = None
        self.previous_page: Optional[int] = None
    
    def reset(self):
        """重置狀態"""
        self.previous_table = None
        self.previous_page = None
    
    def is_table_continuation(
        self,
        current_page: int,
        table_data: Dict[str, Any],
        table_position: str = "top"
    ) -> bool:
        """
        判斷當前表格是否是上一頁表格的延續
        
        啟發式規則：
        1. 當前頁碼 = 上一頁碼 + 1
        2. 當前表格在頁面頂部
        3. 當前表格缺乏標準表頭
        4. 上一頁表格沒有 "Total" 或 "總計" 行
        """
        if not self.previous_table or not self.previous_page:
            return False
        
        # 規則 1: 頁碼連續
        if current_page != self.previous_page + 1:
            return False
        
        # 規則 2: 當前表格在頁面頂部
        if table_position != "top":
            return False
        
        markdown = table_data.get("markdown_content", "")
        
        # 規則 3: 缺乏標準表頭
        header_indicators = ["2024", "2023", "2022", "HK$", "RMB", "人民幣", "千元", "million"]
        has_header = any(indicator in markdown for indicator in header_indicators)
        if has_header:
            return False
        
        # 規則 4: 上一頁表格沒有 Total
        prev_markdown = self.previous_table.get("markdown_content", "")
        total_indicators = ["Total", "total", "總計", "合計", "總額", "TOTAL"]
        has_total = any(indicator in prev_markdown for indicator in total_indicators)
        if has_total:
            return False
        
        logger.info(f"   🔗 檢測到跨頁表格: Page {self.previous_page} → Page {current_page}")
        return True
    
    def merge_tables(self, current_table: Dict[str, Any]) -> Dict[str, Any]:
        """合併當前表格與上一頁表格"""
        if not self.previous_table:
            return current_table
        
        prev_markdown = self.previous_table.get("markdown_content", "")
        curr_markdown = current_table.get("markdown_content", "")
        
        merged_markdown = self._merge_markdown(prev_markdown, curr_markdown)
        
        merged_table = {
            "markdown_content": merged_markdown,
            "source_pages": [
                self.previous_table.get("source_page", self.previous_page),
                current_table.get("source_page", self.previous_page + 1)
            ],
            "is_merged": True
        }
        
        logger.info(f"   ✅ 跨頁表格已合併 ({len(prev_markdown)} + {len(curr_markdown)} chars)")
        return merged_table
    
    def _merge_markdown(self, prev_md: str, curr_md: str) -> str:
        """智能合併兩個 Markdown 表格"""
        prev_lines = prev_md.strip().split("\n")
        curr_lines = curr_md.strip().split("\n")
        
        # 找數據開始位置
        prev_data_start = 0
        for i, line in enumerate(prev_lines):
            if line.strip().startswith("|") and "---" in line:
                prev_data_start = i + 1
                break
        
        curr_data_start = 0
        for i, line in enumerate(curr_lines):
            if line.strip().startswith("|") and "---" in line:
                curr_data_start = i + 1
                break
        
        header_lines = prev_lines[:prev_data_start]
        prev_data = prev_lines[prev_data_start:]
        curr_data = curr_lines[curr_data_start:]
        
        merged = header_lines + prev_data + curr_data
        return "\n".join(merged)
    
    def update_state(self, page: int, table_data: Dict[str, Any], position: str = "bottom"):
        """更新狀態"""
        self.previous_table = {**table_data, "source_page": page, "position": position}
        self.previous_page = page


# 全局跨頁表格合併器
_cross_page_merger = CrossPageTableMerger()
from .validators.math_rules import validate_all, ValidationResult
from .repository.db_client import DBClient


class DocumentPipeline:
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
        agent_loop = None
    ):
        """
        初始化
        
        Args:
            db_url: 數據庫連接字符串
            data_dir: 數據存儲目錄
            use_opendataloader: 是否使用 OpenDataLoader 解析（默認 True）
            enable_agentic_ingestion: 是否啟用智能代理寫入（默認 True）
            agent_loop: AgentLoop 實例（可選，用於 Agentic Ingestion）
        """
        # Fix: 使用環境變數，端口改為 5432
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres_password_change_me@localhost:5432/annual_reports"
        )
        self.data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data/raw"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 🌟 Agentic Ingestion 設置
        self.enable_agentic_ingestion = enable_agentic_ingestion
        self.agent_loop = agent_loop
        self._agentic_pipeline = None
        
        # 🌟 使用統一的 LLM 客戶端
        self.llm_client = get_llm_client()
        self.llm_model = get_llm_model()
        self.vision_model = get_vision_model()
        
        # 初始化 Parser 層
        self.db = DBClient(self.db_url)
        self.vision_parser = VisionParser()
        self.fast_parser = FastParser()
        self.opendataloader_parser = OpenDataLoaderParser() if use_opendataloader else None
        
        # 初始化 Agent 層
        self.agent = FinancialAgent()
        self.page_classifier = PageClassifier()
        
        self.use_opendataloader = use_opendataloader
        
        logger.info(f"📁 DocumentPipeline 初始化完成 (model={self.llm_model}, opendataloader={use_opendataloader}, agentic={enable_agentic_ingestion})")
    
    def _get_agentic_pipeline(self):
        """獲取或創建 AgenticPipeline 實例"""
        if self._agentic_pipeline is None and self.enable_agentic_ingestion:
            from .agentic_ingestion import AgenticIngestionPipeline
            self._agentic_pipeline = AgenticIngestionPipeline(agent_loop=self.agent_loop)
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
    
    async def smart_extract(
        self,
        pdf_path: str,
        company_id: int,
        doc_id: str,
        progress_callback: Callable = None,
        year: int = None  # 🌟 新增：年份参数（由主流程传入）
    ) -> Dict[str, Any]:
        """
        智能結構化提取
        
        🌟 重要變更：
        - save_all_pages_to_fallback_table 已抽離到 process_pdf_full Step 4.5
        - 確保所有文檔（包括指數報告）都會保存兜底數據
        - 此函數只負責結構化提取
        
        Args:
            pdf_path: PDF 路徑
            company_id: 公司 ID
            doc_id: 文檔 ID
            progress_callback: 進度回調
            year: 年份（由主流程传入）
            
        Returns:
            Dict: 提取結果統計
        """
        logger.info(f"🧠 開始智能結構化提取...")
        
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
        
        try:
            # 🌟 Step 1 已移除：年份由主流程傳入 (process_pdf_full Step 4.5)
            # 不再從資料庫查詢年份
            
            # 🌟 Step 2 已移除：保存兜底表已抽離到 process_pdf_full Step 4.5
            # 確保指數報告也能保存全文檢索數據
            
            # 🌟 Step 3: 混合路由 (Hybrid Routing) - 結合特徵掃描與 LLM 分類
            # 注意：進度回調調整為從 37% 開始（原來 Step 1/2 佔用的進度已移除） (Hybrid Routing) - 結合特徵掃描與 LLM 分類
            if progress_callback:
                progress_callback(37.0, "混合路由掃描目標頁面...")
            
            revenue_pages = set()
            
            # 方法 A：企業級多維度特徵掃描 (抓出圖表、表格與關鍵字)
            # 使用 FastParser.scan_for_keywords 的三重策略：
            # - 正規化模糊搜尋 (Normalized Text Search)
            # - 視覺特徵偵測 (Visual Feature Detection - 針對圖表)
            # - 表格特徵偵測 (Table Feature Detection)
            keyword_pages = FastParser.scan_for_keywords(
                pdf_path,
                keywords=[
                    "revenue breakdown", "geographical", "geographic", 
                    "region", "segment", "business segment",
                    "收入分佈", "地區收入", "業務分佈", "地理分佈",
                    "歐洲", "美洲", "中國", "亞洲", "香港",
                    "turnover", "sales by", "income by"
                ]
            )
            revenue_pages.update(keyword_pages)
            logger.info(f"   📊 特徵掃描找到 {len(keyword_pages)} 個候選頁面: {keyword_pages}")
            
            # 方法 B：LLM 語義分類 (作為輔助補強，不當作唯一依賴)
            # 注意：LLM 分類可能因為 FastParser 抓出空白文字而失敗
            try:
                pages_text = await self._extract_all_pages_text(pdf_path)
                if pages_text:
                    classification_result = await self.page_classifier.find_candidate_pages(
                        pages_text,
                        target_data_types=["revenue_breakdown", "key_personnel"]
                    )
                    llm_pages = classification_result.get("revenue_breakdown", [])
                    revenue_pages.update(llm_pages)
                    logger.info(f"   🧠 LLM 分類找到 {len(llm_pages)} 個額外候選頁面: {llm_pages}")
            except Exception as e:
                logger.warning(f"   ⚠️ LLM 分類失敗（跳過，不影響特徵掃描結果）: {e}")
            
            revenue_pages = sorted(list(revenue_pages))
            result["revenue_breakdown"]["pages"] = revenue_pages
            
            if not revenue_pages:
                logger.warning("⚠️ 混合路由找不到任何候選頁面，放棄結構化提取（但兜底資料已保存）")
                return result
            
            logger.info(f"   🎯 混合路由總共找到 {len(revenue_pages)} 個 Revenue Breakdown 候選頁面: {revenue_pages}")
            
            # Step 4: 對每個頁面進行結構化提取 (Zone 1)
            for i, page_num in enumerate(revenue_pages):
                if progress_callback:
                    progress = 40.0 + (i + 1) / max(len(revenue_pages), 1) * 40.0
                    progress_callback(progress, f"提取 Page {page_num}...")
                
                extracted = await self.extract_revenue_from_page(
                    pdf_path, page_num, company_id, year, doc_id
                )
                
                if extracted:
                    result["revenue_breakdown"]["extracted"] += extracted
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 智能提取失敗: {e}")
            result["errors"].append(str(e))
            return result
    
    async def extract_revenue_from_page(
        self,
        pdf_path: str,
        page_num: int,
        company_id: int,
        year: int,
        doc_id: str,
        max_retries: int = 2
    ) -> int:
        """
        從特定頁面提取 Revenue Breakdown
        
        Args:
            pdf_path: PDF 路徑
            page_num: 頁碼
            company_id: 公司 ID
            year: 年份
            doc_id: 文檔 ID
            max_retries: 最大重試次數
            
        Returns:
            int: 插入的記錄數
        """
        logger.info(f"   📊 提取 Page {page_num}...")
        
        for attempt in range(max_retries):
            try:
                # Step 1: Vision → Markdown
                md_save_path = self.data_dir / "debug" / f"page_{page_num}_markdown.txt"
                markdown = await self.vision_parser.to_markdown(
                    pdf_path, page_num, str(md_save_path)
                )
                
                if not markdown:
                    logger.warning(f"   ⚠️ Markdown 轉換失敗，重試...")
                    continue
                
                # 🌟 Step 1.5: 雙重寫入 (Dual-Write) - 保存原始 Markdown 到兜底表
                # 這是 Zone 2，確保所有數據都不會流失
                await self.db.insert_document_page(
                    company_id=company_id,
                    doc_id=doc_id,
                    year=year,
                    page_num=page_num,
                    markdown_content=markdown,
                    source_file=Path(pdf_path).name,
                    content_type="markdown",
                    has_images=True,  # 使用了 Vision 解析，通常有圖表
                    has_charts=True
                )
                logger.info(f"   💾 Page {page_num} 已寫入 document_pages 兜底表 (Zone 2)")
                
                # Step 2: Markdown → JSON (Zone 1 結構化提取)
                extracted_data = await self.agent.extract_revenue_breakdown(markdown)
                
                if not extracted_data:
                    logger.warning(f"   ⚠️ JSON 提取失敗，但原始 Markdown 已保存，可通過全文搜索查詢")
                    continue
                
                # Step 3: 驗證
                validation = validate_all(extracted_data, "revenue_breakdown")
                
                if not validation.is_valid:
                    logger.warning(f"   ⚠️ 驗證失敗: {validation.message}，但原始 Markdown 已保存")
                    continue
                
                # Step 4: 入庫
                inserted = await self.db.insert_revenue_breakdown(
                    company_id=company_id,
                    year=year,
                    extracted_data=extracted_data,
                    source_file=Path(pdf_path).name,
                    source_page=page_num
                )
                
                logger.info(f"   ✅ Page {page_num} 提取成功: {inserted} 條記錄")
                return inserted
                
            except Exception as e:
                logger.error(f"   ❌ 提取失敗 (attempt {attempt + 1}): {e}")
                continue
        
        return 0
    
    async def save_all_pages_to_fallback_table(
        self,
        pdf_path: str,
        company_id: int,
        doc_id: str,
        year: int
    ) -> int:
        """
        Save all PDF pages to document_pages table (Zone 2 fallback).
        
        Uses hybrid parsing:
        - Complex pages (charts/images) → VisionParser
        - Simple pages → FastParser
        
        Args:
            pdf_path: PDF file path
            company_id: Company ID
            doc_id: Document ID
            year: Document year
            
        Returns:
            int: Number of pages saved
        """
        logger.info(f"   Saving all pages to fallback table (hybrid parsing mode)...")
        
        total_pages = FastParser.get_page_count(pdf_path)
        if total_pages == 0:
            logger.warning("   Unable to get PDF page count")
            return 0
        
        saved_count = 0
        vision_count = 0
        source_file = Path(pdf_path).name
        
        for page_num in range(1, total_pages + 1):
            try:
                import fitz
                doc = fitz.open(pdf_path)
                page = doc.load_page(page_num - 1)
                
                is_complex = VisionParser.is_complex_page(page)
                
                if is_complex:
                    markdown_content = await self.vision_parser.to_markdown(
                        pdf_path, page_num, 
                        save_debug_path=None
                    )
                    
                    if markdown_content and len(markdown_content.strip()) > 10:
                        content_type = "vision_markdown"
                        vision_count += 1
                    else:
                        markdown_content = FastParser.extract_text(pdf_path, page_num)
                        content_type = "text"
                    
                    doc.close()
                    
                else:
                    markdown_content = FastParser.extract_text(pdf_path, page_num)
                    content_type = "text"
                    doc.close()
                
                if not markdown_content or len(markdown_content.strip()) < 10:
                    continue
                
                has_charts = is_complex or any(kw in markdown_content.lower() for kw in 
                    ['chart', 'figure', 'pie', 'bar', 'graph', '圖', '表'])
                
                success = await self.db.insert_document_page(
                    company_id=company_id,
                    doc_id=doc_id,
                    year=year,
                    page_num=page_num,
                    markdown_content=markdown_content,
                    source_file=source_file,
                    content_type=content_type,
                    has_charts=has_charts
                )
                
                if success:
                    saved_count += 1
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Page {page_num} 保存失敗: {e}")
                continue
        
        logger.info(f"   Saved {saved_count}/{total_pages} pages (Vision: {vision_count})")
        return saved_count
    
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
    
    async def _extract_all_pages_text(
        self,
        pdf_path: str,
        preview_chars: int = 400
    ) -> Dict[int, str]:
        """
        提取 PDF 所有頁面的文字 (用於 LLM 分類)
        
        Args:
            pdf_path: PDF 路徑
            preview_chars: 每頁提取的字符數 (用於節省 Token)
            
        Returns:
            Dict[int, str]: {page_num: "頁面文字..."}
        """
        pages_text = {}
        
        try:
            total_pages = FastParser.get_page_count(pdf_path)
            logger.info(f"   📄 提取 {total_pages} 頁文字用於 LLM 分類...")
            
            for page_num in range(1, total_pages + 1):
                text = FastParser.extract_text(pdf_path, page_num)
                if text and len(text.strip()) > 10:
                    # 取頁面開頭部分 (通常包含標題和關鍵內容)
                    pages_text[page_num] = text[:preview_chars]
            
            logger.info(f"   ✅ 已提取 {len(pages_text)} 頁文字")
            
        except Exception as e:
            logger.error(f"   ❌ 提取頁面文字失敗: {e}")
        
        return pages_text
    
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
        doc_id: str
    ) -> Optional[int]:
        """
        🎯 Vision 提取公司信息（替代 FastParser）
        
        核心改進：
        1. 將 PDF 封面（第 1 頁）轉成高解析度圖片
        2. 使用 Vision LLM 同時執行 OCR + 語義提取
        3. 解決港股年報封面文字被向量化或嵌入圖片的問題
        
        Returns:
            int: 公司 ID
        """
        logger.info(f"🎯 正在透過 Vision 從封面提取公司元數據...")
        
        stock_code = None
        year = None
        name_en = None
        name_zh = None
        
        # ==========================================
        # 🌟 方案 A: Vision 提取（優先，解決 OCR 層問題）
        # ==========================================
        
        # Step 1: 將封面（第 1 頁）轉成高解析度圖片
        cover_image_base64 = self.vision_parser.convert_page_to_image_base64(
            pdf_path, 
            page_num=1, 
            zoom=2.0  # 高解析度
        )
        
        if cover_image_base64:
            # Step 2: 使用 Vision Agent 提取
            metadata = await self.agent.extract_company_metadata_with_vision(cover_image_base64)
            
            if metadata:
                stock_code = metadata.get("stock_code")
                year = metadata.get("year")
                name_en = metadata.get("name_en")
                name_zh = metadata.get("name_zh")
                logger.info(f"✅ Vision 提取成功: Stock={stock_code}, Year={year}")
            else:
                logger.warning("⚠️ Vision 提取失敗，嘗試 Fallback...")
        else:
            logger.warning("⚠️ 無法獲取封面圖片，嘗試 Fallback...")
        
        # ==========================================
        # 🌟 方案 B: Fallback - 從文件名提取
        # ==========================================
        
        if not stock_code or not year:
            import re
            filename = Path(pdf_path).stem
            logger.info(f"   📄 Vision 提取失敗，嘗試從文件名提取: {filename}")
            
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
        # 🌟 方案 C: 嘗試 FastParser（最後手段）
        # ==========================================
        
        if not stock_code:
            logger.info("   📄 Vision 和文件名都失敗，嘗試 FastParser...")
            front_pages_text = ""
            total_pages = FastParser.get_page_count(pdf_path)
            
            for page_num in range(1, min(3, total_pages + 1)):
                text = FastParser.extract_text(pdf_path, page_num)
                if text:
                    front_pages_text += text + "\n"
            
            if front_pages_text:
                metadata = await self.agent.extract_company_metadata_from_cover(front_pages_text)
                if metadata:
                    stock_code = metadata.get("stock_code") or stock_code
                    year = metadata.get("year") or year
                    name_en = metadata.get("name_en") or name_en
                    name_zh = metadata.get("name_zh") or name_zh
        
        # ==========================================
        # 驗證必要欄位
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
            await self.db.update_document_company_id(doc_id, company_id, year)
            logger.info(f"✅ 文檔 {doc_id} 已關聯公司 ID={company_id}, Year={year}")
        
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
        2. VisionParser + FinancialAgent - 結構化提取
        3. DBClient - 數據入庫
        
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
            
            # Step 3: 🌟 使用 OpenDataLoaderParser 解析 PDF
            if progress_callback:
                progress_callback(15.0, "OpenDataLoader 解析 PDF...")
            
            if self.opendataloader_parser:
                artifacts = await self.opendataloader_parser.parse_async(pdf_path, doc_id)
                logger.info(f"   ✅ OpenDataLoader 解析完成: {len(artifacts)} 個 artifacts")
                
                # Step 3.1: 保存 Artifacts 到文件和數據庫
                await self._save_opendataloader_artifacts(artifacts, doc_id, company_id, pdf_path)
                
                # Step 3.2: 保存 output.json 供 WebUI 預覽
                output_json_path = self.data_dir / doc_id / "output.json"
                output_json_path.parent.mkdir(parents=True, exist_ok=True)
                import json as json_module
                with open(output_json_path, "w", encoding="utf-8") as f:
                    json_module.dump(artifacts, f, ensure_ascii=False, indent=2)
                logger.info(f"   💾 已保存 output.json: {output_json_path}")
            else:
                logger.warning("⚠️ OpenDataLoaderParser 未啟用")
                artifacts = []
            
            # Step 4: 提取公司信息（如果沒有 company_id，且不是指數報告）
            if progress_callback:
                progress_callback(55.0, "🧠 Vision 提取公司信息...")
            
            # 🌟 修正：如果是指數報告，絕對不能提取母公司！
            # 指數報告涵蓋多間公司，不應該有單一母公司 (company_id)
            # 提取母公司會導致 AI 將「恒生指數公司」等發行商當成財報公司，污染數據庫
            if not company_id and not is_index_report:
                company_id = await self._extract_and_create_company(pdf_path, doc_id)
                if company_id:
                    logger.info(f"✅ 已關聯公司: ID={company_id}")
                else:
                    logger.warning("⚠️ 無法提取公司信息")
            elif is_index_report:
                logger.info("ℹ️ 指數報告無需提取母公司，跳過 Vision 提取 (報告涵蓋多間成分股公司)")
                company_id = None  # 確保 company_id 保持 None
            
            # 🌟 Step 4.5: 保存所有頁面到兜底表 (Zone 2) - 所有文檔都必須執行！
            # 這是 Vanna 全文檢索的關鍵數據源，無論是年報還是指數報告都需要
            if progress_callback:
                progress_callback(60.0, "保存所有頁面到兜底表(全文檢索用)...")
            
            # 獲取年份，若無則用當前年份
            doc_year = await self._get_document_year(doc_id) or datetime.now().year
            
            # 🔧 修復：提前初始化 stats，避免 UnboundLocalError
            stats = {
                "total_chunks": len([a for a in artifacts if a.get("type") == "text_chunk"]),
                "total_tables": len([a for a in artifacts if a.get("type") == "table"]),
                "total_images": len([a for a in artifacts if a.get("type") == "image"]),
                "total_artifacts": len(artifacts)
            }
            
            saved_pages = await self.save_all_pages_to_fallback_table(
                pdf_path, company_id, doc_id, doc_year  # company_id 可以是 None，DB 已支援
            )
            stats["document_pages_saved"] = saved_pages
            
            # Step 5: 智能結構化提取
            
            if company_id:
                if progress_callback:
                    progress_callback(70.0, "智能提取結構化數據...")
                
                # 🌟 传入年份参数（已由 Step 4.5 获取）
                extraction_result = await self.smart_extract(
                    pdf_path, company_id, doc_id, 
                    lambda p, m: progress_callback(70 + p * 0.2, m) if progress_callback else None,
                    year=doc_year  # 🌟 传入年份
                )
                stats["structured_extraction"] = extraction_result
            elif is_index_report:
                # 🌟 指數報告雖無 company_id，但兜底數據已在 Step 4.5 保存
                stats["structured_extraction"] = {"status": "skipped", "reason": "index_report_no_single_company"}
                logger.info("ℹ️ 指數報告跳過結構化提取（無單一母公司）")
            else:
                stats["structured_extraction"] = {"status": "skipped", "reason": "no company_id"}
            
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
        
        Args:
            artifacts: Artifacts 列表
            doc_id: 文檔 ID
            company_id: 公司 ID
        """
        import json as json_module
        
        doc_dir = self.data_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        
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
                    await self.db.insert_raw_artifact(
                        artifact_id=f"{doc_id}_table_{idx:04d}",
                        doc_id=doc_id,
                        company_id=company_id,
                        file_type="table_json",
                        file_path=str(table_json_path.relative_to(self.data_dir)),
                        page_num=page_num,
                        metadata=json_module.dumps(metadata)
                    )
                
                elif artifact_type == "image":
                    # 🔧 修復：實際保存圖片文件
                    image_dir = doc_dir / "images"
                    image_dir.mkdir(parents=True, exist_ok=True)
                    
                    image_filename = f"image_{idx:04d}.png"
                    image_path = image_dir / image_filename
                    image_saved = False
                    
                    # 嘗試從 artifact 中提取圖片數據
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
                                logger.debug(f"✅ 已保存圖片 (base64): {image_path}")
                            
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
                    
                    # 🔧 如果 OpenDataLoader 沒有提供圖片數據，從 PDF 提取
                    if not image_saved and pdf_path and os.path.exists(pdf_path):
                        try:
                            import fitz
                            doc = fitz.open(pdf_path)
                            page_num = artifact.get("page_num", 1)
                            
                            if 1 <= page_num <= len(doc):
                                page = doc.load_page(page_num - 1)
                                bounding_box = metadata.get("bounding_box")
                                
                                if bounding_box and len(bounding_box) == 4:
                                    # 使用 bounding box 裁切圖片
                                    x0, y0, x1, y1 = bounding_box
                                    rect = fitz.Rect(x0, y0, x1, y1)
                                    mat = fitz.Matrix(2.0, 2.0)
                                    pix = page.get_pixmap(matrix=mat, clip=rect)
                                    
                                    with open(image_path, 'wb') as f:
                                        f.write(pix.tobytes("png"))
                                    image_saved = True
                                    logger.info(f"🖼️ 圖片已從 PDF 提取 (bbox): {image_path}")
                                else:
                                    # 沒有 bounding box，保存整個頁面
                                    mat = fitz.Matrix(2.0, 2.0)
                                    pix = page.get_pixmap(matrix=mat)
                                    
                                    with open(image_path, 'wb') as f:
                                        f.write(pix.tobytes("png"))
                                    image_saved = True
                                    logger.info(f"🖼️ 圖片已從 PDF 提取 (full page): {image_path}")
                            
                            doc.close()
                            
                        except Exception as e:
                            logger.warning(f"⚠️ 從 PDF 提取圖片失敗：{e}")
                    
                    # 記錄到 raw_artifacts
                    await self.db.insert_raw_artifact(
                        artifact_id=f"{doc_id}_image_{idx:04d}",
                        doc_id=doc_id,
                        company_id=company_id,
                        file_type="image",
                        file_path=str(image_path.relative_to(self.data_dir)) if image_saved else f"{doc_id}/images/{image_filename}",
                        page_num=page_num,
                        metadata=json_module.dumps({
                            **metadata,
                            "image_saved": image_saved
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
        
        vanna_url = os.getenv("VANNA_SERVICE_URL", "http://vanna-service:8082")
        
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
    pipeline = DocumentPipeline(db_url=db_url)
    
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