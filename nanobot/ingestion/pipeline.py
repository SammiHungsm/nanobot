"""
Document Pipeline - 主流程協調器

這是整個 ingestion 系統的大腦，協調各個模組完成 PDF 處理流程。

流程：
1. Parser: 解析 PDF → Markdown/文字
2. Agent: LLM 提取結構化數據
3. Validator: 數據驗證
4. Repository: 數據入庫
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
from .validators.math_rules import validate_all, ValidationResult
from .repository.db_client import DBClient


class DocumentPipeline:
    """
    Document Pipeline - 企業級文檔處理管道
    
    協調 Parser → Agent → Validator → Repository 完成完整的數據處理流程。
    """
    
    def __init__(
        self,
        db_url: str = None,
        data_dir: str = None,
        api_key: str = None,
        api_base: str = None,
        vision_model: str = "qwen-vl-max",
        llm_model: str = "qwen3.5-plus"
    ):
        """
        初始化
        
        Args:
            db_url: 數據庫連接字符串
            data_dir: 數據存儲目錄
            api_key: API Key
            api_base: API Base URL
            vision_model: Vision 模型名稱
            llm_model: LLM 模型名稱
        """
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
        
        logger.info("📁 DocumentPipeline 初始化完成")
    
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
            "errors": []
        }
        
        try:
            # Step 1: 推斷年份
            year = self._infer_year(doc_id)
            logger.info(f"   推斷年份: {year}")
            
            # Step 2: 找出 Revenue Breakdown 頁面
            revenue_keywords = [
                "revenue breakdown", "geographical breakdown",
                "revenue by region", "收入分佈", "地區收入"
            ]
            revenue_pages = FastParser.scan_for_keywords(pdf_path, revenue_keywords)
            result["revenue_breakdown"]["pages"] = revenue_pages
            
            logger.info(f"   找到 {len(revenue_pages)} 個 Revenue Breakdown 候選頁面: {revenue_pages}")
            
            # Step 3: 對每個頁面進行提取
            for i, page_num in enumerate(revenue_pages):
                if progress_callback:
                    progress = 30.0 + (i + 1) / len(revenue_pages) * 50.0
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
                
                # Step 2: Markdown → JSON
                extracted_data = await self.agent.extract_revenue_breakdown(markdown)
                
                if not extracted_data:
                    logger.warning(f"   ⚠️ JSON 提取失敗，重試...")
                    continue
                
                # Step 3: 驗證
                validation = validate_all(extracted_data, "revenue_breakdown")
                
                if not validation.is_valid:
                    logger.warning(f"   ⚠️ 驗證失敗: {validation.message}，重試...")
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