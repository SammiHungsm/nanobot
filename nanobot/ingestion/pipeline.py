"""
Document Pipeline - 主流程協調器

這是整個 ingestion 系統的大腦，協調各個模組完成 PDF 處理流程。

Two-Stage LLM Pipeline:
1. Stage 1 (便宜 & 快速): PageClassifier (gpt-4o-mini) 語義分類
2. Stage 2 (昂貴 & 精準): Vision Parser + Financial Agent 只處理相關頁面

流程：
1. Parser: 解析 PDF → Markdown/文字
2. Classifier: LLM 智能路由 (找出目標頁面)
3. Agent: LLM 提取結構化數據
4. Validator: 數據驗證
5. Repository: 數據入庫

改進：
- 跨頁表格合併：自動檢測並合併跨頁表格
"""

import os
import json
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Callable
from datetime import datetime
from loguru import logger

# 導入各個模組
from .parsers.vision_parser import VisionParser, FastParser
from .extractors.financial_agent import FinancialAgent
from .extractors.page_classifier import PageClassifier


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
    
    Two-Stage LLM Pipeline:
    1. Stage 1 (便宜 & 快速): PageClassifier 語義分類
    2. Stage 2 (昂貴 & 精準): Vision Parser + Financial Agent 只處理相關頁面
    
    所有配置從 config.json 讀取，不硬編碼模型名稱或 API Key。
    """
    
    @staticmethod
    def _get_config_credentials() -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        從 nanobot config.json 讀取 API 憑證和模型
        
        API 憑證從 provider 讀取，模型從 agents.defaults 讀取。
        Vision 模型使用相同的 model（不單獨配置）。
        
        Returns:
            tuple: (api_key, api_base, model)
        """
        try:
            from nanobot.config.loader import load_config
            from pathlib import Path
            
            config_path = None
            nanobot_config_env = os.getenv("NANOBOT_CONFIG")
            if nanobot_config_env:
                config_path = Path(nanobot_config_env)
                if not config_path.exists():
                    config_path = None
            
            config = load_config(config_path)
            provider = config.get_provider()
            
            # 從 agents.defaults 讀取模型
            model = None
            try:
                model = config.agents.defaults.model
            except AttributeError:
                pass
            
            if provider:
                api_key = provider.api_key or None
                api_base = provider.api_base or None
                
                if api_key and api_key.startswith("sk-YOUR"):
                    api_key = None
                
                if api_key:
                    logger.debug(f"✅ DocumentPipeline 從 config 讀取: model={model}")
                    return api_key, api_base, model
        except Exception as e:
            logger.warning(f"⚠️ DocumentPipeline 無法從 config.json 載入配置: {e}")
        
        return None, None, None
    
    def __init__(
        self,
        db_url: str = None,
        data_dir: str = None,
        api_key: str = None,
        api_base: str = None,
        vision_model: str = None,
        llm_model: str = None
    ):
        """
        初始化
        
        Args:
            db_url: 數據庫連接字符串
            data_dir: 數據存儲目錄
            api_key: API Key (優先使用參數，其次從 config.json 讀取)
            api_base: API Base URL (優先使用參數，其次從 config.json 讀取)
            vision_model: Vision 模型名稱 (優先使用參數，其次使用默認值)
            llm_model: LLM 模型名稱 (優先使用參數，其次從 config.json 讀取)
        """
        # 🌟 從 config.json 讀取配置
        config_key, config_base, config_model = self._get_config_credentials()
        
        # 優先順序：參數 > config.json
        api_key = api_key or config_key
        api_base = api_base or config_base
        llm_model = llm_model or config_model
        vision_model = vision_model or llm_model  # 使用相同的 model
        
        # 驗證必要配置
        if not llm_model:
            raise ValueError("❌ LLM model 未配置！請在 config.json 的 agents.defaults.model 中設定")
        
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
        )
        self.data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data/raw"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化各個組件
        self.db = DBClient(self.db_url)
        self.vision_parser = VisionParser(api_key, api_base, vision_model)
        self.fast_parser = FastParser()
        self.agent = FinancialAgent(api_key, api_base, llm_model)
        
        # 🌟 LLM 智能頁面路由器 (使用相同的 LLM 模型)
        self.page_classifier = PageClassifier(api_key=api_key, api_base=api_base, model=llm_model)
        
        logger.info(f"📁 DocumentPipeline 初始化完成 (model={llm_model})")
    
    async def connect(self):
        """連接數據庫"""
        await self.db.connect()
    
    async def close(self):
        """關閉連接"""
        await self.db.close()
    
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
            if not company_id:
                if progress_callback:
                    progress_callback(20.0, "提取公司信息...")
                company_id = await self._extract_and_create_company(pdf_path, doc_id)
                # 更新 documents 表的 company_id 和 year
                if company_id:
                    year = self._infer_year(doc_id)
                    await self.db.update_document_company_id(doc_id, company_id, year)
            
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
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """
        智能結構化提取
        
        自動掃描 PDF，找出包含財務數據的頁面並提取。
        
        Args:
            pdf_path: PDF 路徑
            company_id: 公司 ID
            doc_id: 文檔 ID
            progress_callback: 進度回調
            
        Returns:
            Dict: 提取結果統計
        """
        logger.info(f"🧠 開始智能結構化提取...")
        
        result = {
            "revenue_breakdown": {"pages": [], "extracted": 0},
            "document_pages_saved": 0,  # 🌟 新增：記錄保存到兜底表的頁數
            "errors": []
        }
        
        try:
            # Step 1: 推斷年份
            year = self._infer_year(doc_id)
            logger.info(f"   推斷年份: {year}")
            
            # 🌟 Step 2: 保存所有頁面到兜底表 (Zone 2) - 確保數據不流失
            if progress_callback:
                progress_callback(35.0, "保存所有頁面到兜底表...")
            
            saved_pages = await self.save_all_pages_to_fallback_table(
                pdf_path, company_id, doc_id, year
            )
            result["document_pages_saved"] = saved_pages
            logger.info(f"   ✅ 已保存 {saved_pages} 個頁面到 document_pages 兜底表")
            
            # 🌟 Step 3: 使用 LLM 智能路由找出目標頁面 (取代傳統 keyword scanning)
            if progress_callback:
                progress_callback(37.0, "LLM 智能路由分析頁面...")
            
            # 提取所有頁面的文字（用於 LLM 分類）
            pages_text = await self._extract_all_pages_text(pdf_path)
            
            # 使用 PageClassifier 進行語義分類
            classification_result = await self.page_classifier.find_candidate_pages(
                pages_text,
                target_data_types=["revenue_breakdown", "key_personnel"]
            )
            
            revenue_pages = classification_result.get("revenue_breakdown", [])
            result["revenue_breakdown"]["pages"] = revenue_pages
            
            logger.info(f"   🎯 LLM 路由找到 {len(revenue_pages)} 個 Revenue Breakdown 候選頁面: {revenue_pages}")
            
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
        🛡️ 保存所有 PDF 頁面到兜底表 (Zone 2)
        
        這是「雙軌制」的關鍵步驟：確保所有原始內容都被保存，
        即使無法提取結構化數據，Vanna 仍然可以通過全文搜索找到答案。
        
        Args:
            pdf_path: PDF 路徑
            company_id: 公司 ID
            doc_id: 文檔 ID
            year: 年份
            
        Returns:
            int: 成功保存的頁面數
        """
        logger.info(f"   📄 正在保存所有頁面到兜底表...")
        
        total_pages = FastParser.get_page_count(pdf_path)
        if total_pages == 0:
            logger.warning("   ⚠️ 無法獲取 PDF 頁數")
            return 0
        
        saved_count = 0
        source_file = Path(pdf_path).name
        
        for page_num in range(1, total_pages + 1):
            try:
                # 使用 FastParser 快速提取文字
                text_content = FastParser.extract_text(pdf_path, page_num)
                
                if not text_content or len(text_content.strip()) < 10:
                    # 跳過空白或太短的頁面
                    continue
                
                # 檢測頁面類型（是否包含圖表）
                # 這裡用簡單的啟發式規則判斷
                has_charts = any(kw in text_content.lower() for kw in 
                    ['chart', 'figure', 'pie', 'bar', 'graph', '圖', '表'])
                
                # 保存到兜底表
                success = await self.db.insert_document_page(
                    company_id=company_id,
                    doc_id=doc_id,
                    year=year,
                    page_num=page_num,
                    markdown_content=text_content,
                    source_file=source_file,
                    content_type="text",
                    has_charts=has_charts
                )
                
                if success:
                    saved_count += 1
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Page {page_num} 保存失敗: {e}")
                continue
        
        logger.info(f"   ✅ 已保存 {saved_count}/{total_pages} 頁到 document_pages 表")
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
        """提取公司信息並創建公司記錄"""
        # 快速提取前幾頁文字
        text_content = ""
        for page_num in range(1, min(6, FastParser.get_page_count(pdf_path) + 1)):
            text = FastParser.extract_text(pdf_path, page_num)
            if text:
                text_content += text + "\n"
        
        if not text_content:
            return None
        
        # 提取公司信息
        company_info = await self.agent.extract_company_info(text_content[:5000])
        
        if not company_info:
            return None
        
        # 創建公司
        company_id = await self.db.get_or_create_company(
            stock_code=company_info.get("stock_code"),
            name_en=company_info.get("name_en"),
            name_zh=company_info.get("name_zh"),
            industry=company_info.get("industry"),
            sector=company_info.get("sector")
        )
        
        return company_id
    
    def _infer_year(self, doc_id: str) -> int:
        """從文檔 ID 推斷年份"""
        import re
        year_match = re.search(r'(\d{4})', doc_id)
        if year_match:
            year = int(year_match.group(1))
            if 2000 <= year <= 2030:
                return year
        return datetime.now().year


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