"""
OpenDataLoader Integration Module

⚠️ ⚠️ ⚠️ DEPRECATED - 此文件已廢棄 ⚠️ ⚠️ ⚠️

此模組已被 DocumentPipeline 取代，請使用：
    from nanobot.ingestion.pipeline import DocumentPipeline
    
    pipeline = DocumentPipeline(db_url, data_dir)
    await pipeline.connect()
    result = await pipeline.process_pdf_full(pdf_path, doc_id=doc_id)
    await pipeline.close()

廢棄原因：
1. 職責混雜：Parser + Agent + Repository 全包在一個類
2. 難以維護：代碼過長 (800+ 行)
3. 測試困難：無法單獨測試各個模組

新架構（DocumentPipeline）：
- Parser 層 (OpenDataLoaderParser)：只負責解析 PDF
- Agent 層 (FinancialAgent)：只負責 LLM 提取
- Repository 層 (DBClient)：只負責數據庫操作
- Pipeline 層 (DocumentPipeline)：協調各層

此文件將在下一版本中完全刪除。

功能（舊版）：
1. 解析 Annual Report PDF
2. 提取所有 Raw Data (文字、表格、圖片)
3. 保存檔案到 Docker Volume
4. 將路徑和元數據寫入 PostgreSQL
5. 使用 LLM 自動識別公司並提取關鍵信息
"""

# 🚨 Runtime Deprecation Warning
import warnings
warnings.warn(
    "OpenDataLoaderProcessor is DEPRECATED. "
    "Use DocumentPipeline instead: from nanobot.ingestion.pipeline import DocumentPipeline",
    DeprecationWarning,
    stacklevel=2
)

import os
import json
import hashlib
import asyncio
import re
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from loguru import logger
import asyncpg
import httpx
from decimal import Decimal, ROUND_HALF_UP

# Vision 解析所需
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("⚠️ PyMuPDF 未安裝，Vision 解析功能將不可用")

# OpenAI SDK (可用於連接 DashScope 或其他兼容 API)
try:
    from openai import AsyncOpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    logger.warning("⚠️ OpenAI SDK 未安裝，LLM Vision 功能將不可用")


class OpenDataLoaderProcessor:
    """
    OpenDataLoader 處理器
    
    ⚠️ DEPRECATED - 請使用 DocumentPipeline
    
    此類已被廢棄，將在下一版本中刪除。
    請改用：nanobot.ingestion.pipeline.DocumentPipeline
    
    負責：
    - 解析 PDF 文檔
    - 提取結構化和非結構化數據
    - 保存 Raw Artifacts
    - 更新 PostgreSQL 數據庫
    """
    
    def __init__(self, db_url: str, data_dir: str):
        """
        初始化
        
        Args:
            db_url: PostgreSQL 連接字符串
            data_dir: Docker Volume 路徑 (保存 Raw Data)
        """
        self.db_url = db_url
        self.data_dir = Path(data_dir)
        self.db_conn: Optional[asyncpg.Connection] = None
        
        # 確保數據目錄存在
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 OpenDataLoader 數據目錄：{self.data_dir}")
    
    async def connect(self):
        """連接數據庫"""
        self.db_conn = await asyncpg.connect(self.db_url)
        logger.info("✅ 數據庫連接成功")
    
    async def close(self):
        """關閉連接"""
        if self.db_conn:
            await self.db_conn.close()
            logger.info("📴 數據庫連接已關閉")
    
    async def process_pdf(self, pdf_path: str, company_id: Optional[int] = None, doc_id: str = None, progress_callback=None, replace: bool = False) -> Dict[str, Any]:
        """
        處理單一 PDF 文檔
        
        Args:
            pdf_path: PDF 檔案路徑
            company_id: 公司 ID (可選，如未提供將從文檔中自動提取)
            doc_id: 文檔唯一標識
            progress_callback: 進度回調函數 (percent: float, message: str)
            replace: 是否強制重新處理 (跳過去重檢查，刪除舊數據)
            
        Returns:
            處理結果統計
        """
        logger.info(f"🚀 開始處理 PDF: {pdf_path}")
        logger.info(f"   Company ID: {company_id or '待提取'}, Doc ID: {doc_id}, Replace: {replace}")
        
        try:
            # 1. 計算文件 Hash (用於去重)
            if progress_callback:
                progress_callback(5.0, "計算 Hash 與檢查重複...")
            file_hash = self._compute_file_hash(pdf_path)
            logger.info(f"   📝 File Hash: {file_hash[:16]}...")
            
            # 2. 檢查是否已處理 (如果 replace=True，則跳過檢查並清理舊數據)
            if replace:
                logger.info(f"🔄 Replace mode: 清理舊數據並重新處理...")
                await self._delete_existing_document(doc_id)
            else:
                exists = await self._check_document_exists(doc_id, file_hash)
                if exists:
                    logger.warning(f"⚠️ 文檔已存在，跳過處理: {doc_id}")
                    return {"status": "skipped", "reason": "duplicate"}
            
            # 3. 創建文檔記錄 (company_id 可為 NULL)
            await self._create_document_record(pdf_path, company_id, doc_id, file_hash)
            logger.info("✅ 文檔記錄已創建")
            
            # 4. 使用 OpenDataLoader 解析 PDF (這是最花時間的一步)
            if progress_callback:
                progress_callback(10.0, "OpenDataLoader 解析 PDF 中...")
            artifacts = await self._parse_with_opendataloader(pdf_path, doc_id, progress_callback)
            logger.info(f"📊 解析完成：{len(artifacts)} 個 artifacts")
            
            # 🚀 把解析出來的 Raw Data (artifacts) 存成 output.json 給 WebUI 讀取
            doc_dir = self.data_dir / doc_id
            doc_dir.mkdir(parents=True, exist_ok=True)
            output_json_path = doc_dir / "output.json"
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(artifacts, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 已保存 artifacts 到：{output_json_path}")
            
            # 5. 🧠 如果沒有提供 company_id，使用 LLM 從文檔中提取公司信息
            if company_id is None:
                if progress_callback:
                    progress_callback(55.0, "🧠 使用 Vision LLM 提取公司信息...")
                company_info = await self._extract_company_info_with_llm(pdf_path, artifacts, output_json_path)
                if company_info:
                    company_id = await self._find_or_create_company(company_info)
                    if company_id:
                        # 更新文檔的 company_id
                        await self._update_document_company(doc_id, company_id)
                        logger.info(f"✅ 已關聯公司: ID={company_id}, Name={company_info.get('name_en', 'N/A')}")
                    else:
                        logger.warning(f"⚠️ 無法創建公司記錄，將使用 NULL company_id")
                else:
                    logger.warning(f"⚠️ 無法從文檔中提取公司信息，將使用 NULL company_id")
            
            # 6. 保存 Raw Artifacts 並更新數據庫
            if progress_callback:
                progress_callback(60.0, f"解析完成，準備寫入資料庫 (共 {len(artifacts)} 瀦...")
            stats = await self._save_artifacts(artifacts, company_id, doc_id, progress_callback)
            logger.info(f"💾 保存完成：{stats}")
            
            # 7. 🌟 NEW: 智能結構化提取 (Revenue Breakdown, Financial Metrics 等)
            if company_id and progress_callback:
                progress_callback(86.0, "🧠 智能提取結構化財務數據...")
            
            if company_id:
                # 提取結構化財務數據
                extraction_stats = await self._smart_extract_structured_data(
                    pdf_path, company_id, doc_id, artifacts, progress_callback
                )
                stats["structured_extraction"] = extraction_stats
                logger.info(f"📊 結構化提取完成：{extraction_stats}")
            else:
                logger.warning("⚠️ company_id 為空，跳過結構化提取")
            
            # 8. 更新文檔狀態
            if progress_callback:
                progress_callback(90.0, "更新狀態與清理暫存...")
            await self._update_document_status(doc_id, "completed", stats)
            
            # 8. 觸發 Vanna 訓練 (邊做邊學)
            if progress_callback:
                progress_callback(90.0, "準備觸發 Vanna 向量模型訓練...")
            await self._trigger_vanna_training(doc_id, progress_callback)
            
            if progress_callback:
                progress_callback(100.0, "✅ 處理完成")
            
            return {
                "status": "completed",
                "doc_id": doc_id,
                "company_id": company_id,
                **stats
            }
            
        except Exception as e:
            logger.error(f"❌ 處理失敗：{e}")
            import traceback
            traceback.print_exc()
            
            # 更新文檔狀態為失敗
            await self._update_document_status(doc_id, "failed", error=str(e))
            
            return {
                "status": "failed",
                "error": str(e)
            }
    
    def _compute_file_hash(self, file_path: str) -> str:
        """計算文件 SHA256 Hash"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    async def _check_document_exists(self, doc_id: str, file_hash: str) -> bool:
        """檢查文檔是否已存在"""
        exists = await self.db_conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM documents 
                WHERE doc_id = $1 OR file_hash = $2
            )
            """,
            doc_id, file_hash
        )
        return exists
    
    async def _delete_existing_document(self, doc_id: str):
        """刪除現有文檔及其所有相關數據"""
        logger.info(f"🗑️ 正在刪除文檔 {doc_id} 的所有數據...")
        
        # 1. 刪除 raw_artifacts (document_chunks 已移除 - No RAG Option)
        artifacts_deleted = await self.db_conn.execute(
            "DELETE FROM raw_artifacts WHERE doc_id = $1",
            doc_id
        )
        logger.info(f"   📦 已刪除 raw_artifacts")
        
        # 3. 刪除 documents 主表記錄
        doc_deleted = await self.db_conn.execute(
            "DELETE FROM documents WHERE doc_id = $1",
            doc_id
        )
        logger.info(f"   📄 已刪除 documents")
        
        # 4. 刪除物理文件 (data_dir/{doc_id}/)
        doc_dir = self.data_dir / doc_id
        if doc_dir.exists():
            import shutil
            shutil.rmtree(doc_dir)
            logger.info(f"   📁 已刪除物理文件: {doc_dir}")
        
        logger.info(f"✅ 文檔 {doc_id} 已完全刪除")
    
    async def _create_document_record(self, pdf_path: str, company_id: Optional[int], doc_id: str, file_hash: str):
        """創建文檔記錄 (company_id 可為 NULL)"""
        pdf_path_obj = Path(pdf_path)
        
        await self.db_conn.execute(
            """
            INSERT INTO documents (
                doc_id, company_id, title, document_type, 
                file_path, file_hash, file_size_bytes,
                processing_status, uploaded_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (doc_id) DO UPDATE SET
                processing_status = 'pending',
                updated_at = NOW()
            """,
            doc_id,
            company_id,  # 可為 NULL
            pdf_path_obj.stem,  # 使用文件名作為標題
            "annual_report",
            str(pdf_path_obj.absolute()),
            file_hash,
            pdf_path_obj.stat().st_size,
            "pending"
        )
    
    async def _parse_with_opendataloader(self, pdf_path: str, doc_id: str, progress_callback=None) -> List[Dict[str, Any]]:
        """
        使用真實的 OpenDataLoader 解析 PDF，並將結果轉換為 Artifacts
        
        Returns:
            List[Dict[str, Any]]: Artifacts 列表
        """
        logger.info("📖 正在使用 OpenDataLoader 真實解析 PDF...")
        
        # 1. 定義一個同步的包裝函數來執行 CPU 密集的轉換工作
        def run_conversion():
            import tempfile
            from opendataloader_pdf import convert
            import traceback
            
            with tempfile.TemporaryDirectory() as temp_dir:
                out_path = Path(temp_dir) / f"{doc_id}.json"
                try:
                    # 使用位置參數呼叫，避免 WebUI 曾經遇過的 keyword 報錯
                    try:
                        convert(pdf_path, output_path=str(out_path), output_format="json", pages="all")
                    except TypeError:
                        convert(pdf_path, str(out_path))
                    
                    if out_path.exists():
                        # 判斷是檔案還是資料夾
                        if out_path.is_dir():
                            # 如果 OpenDataLoader 建立了一個資料夾，尋找裡面的 json 檔案
                            json_files = list(out_path.glob("*.json"))
                            if json_files:
                                # 讀取資料夾內找到的第一個 JSON 檔
                                logger.info(f"📂 OpenDataLoader 輸出了資料夾，找到 JSON 檔案：{json_files[0].name}")
                                with open(json_files[0], 'r', encoding='utf-8') as f:
                                    return json.load(f)
                            else:
                                logger.error(f"❌ 轉換完成，但在目錄 {out_path} 中找不到 JSON 檔案")
                                return []
                        else:
                            # 如果它正常輸出為一個檔案
                            with open(out_path, 'r', encoding='utf-8') as f:
                                return json.load(f)
                    else:
                        logger.error("❌ 轉換完成，但找不到輸出的檔案或目錄")
                        return []
                except Exception as e:
                    logger.error(f"❌ PDF 轉換引擎發生錯誤：{e}")
                    traceback.print_exc()
                    return []
        
        # 2. 由於 PDF 處理會阻塞 (Blocking)，使用 to_thread 將其放入背景執行緒
        # 報告進度：開始解析
        if progress_callback:
            progress_callback(20.0, "OpenDataLoader 解析 PDF 中 (可能需要幾分鐘)...")
        
        result_json = await asyncio.to_thread(run_conversion)
        
        # 💡 保存完整的 OpenDataLoader 原始 JSON 到 data_dir，供前端預覽使用
        output_json_path = self.data_dir / doc_id / "output.json"
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(result_json, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 已保存 OpenDataLoader 原始輸出：{output_json_path}")
        
        # 報告進度：解析完成，正在轉換
        if progress_callback:
            progress_callback(50.0, "解析完成，正在轉換資料格式...")
        
        # 3. 將解析出來的 JSON 轉換為 Artifacts 格式
        artifacts = []
        
        # 處理 OpenDataLoader 的不同輸出格式：
        # - 可能是 list: [{...}, {...}]
        # - 可能是 dict: {"kids": [{...}, {...}], "file name": "...", ...}
        # - 可能是 dict: {"content": [{...}, {...}]}
        if isinstance(result_json, list):
            # 直接是列表格式
            content_blocks = result_json
            logger.info(f"📄 OpenDataLoader 返回列表格式，共 {len(content_blocks)} 個元素")
        elif isinstance(result_json, dict):
            # 字典格式，記錄所有可用的 keys
            available_keys = list(result_json.keys())
            logger.info(f"📄 OpenDataLoader 返回字典格式，可用 keys: {available_keys}")
            
            # OpenDataLoader 實際輸出格式: {"kids": [...], "file name": "...", "number of pages": ...}
            # 優先檢查 "kids" (OpenDataLoader 標準輸出)
            if "kids" in result_json:
                content_blocks = result_json["kids"]
                logger.info(f"   ✅ 使用 'kids' 欄位，共 {len(content_blocks)} 個元素")
            elif "content" in result_json:
                content_blocks = result_json["content"]
                logger.info(f"   ✅ 使用 'content' 欄位，共 {len(content_blocks)} 個元素")
            elif "pages" in result_json:
                content_blocks = result_json["pages"]
                logger.info(f"   ✅ 使用 'pages' 欄位，共 {len(content_blocks)} 個元素")
            elif "elements" in result_json:
                content_blocks = result_json["elements"]
                logger.info(f"   ✅ 使用 'elements' 欄位，共 {len(content_blocks)} 個元素")
            else:
                logger.warning(f"   ⚠️ 未找到已知的內容欄位，嘗試從字典中提取所有值")
                content_blocks = []
        else:
            logger.error(f"❌ OpenDataLoader 返回未知格式: {type(result_json)}")
            content_blocks = []
        
        if not content_blocks:
            logger.warning(f"⚠️ 提取不到任何內容，請確認 {pdf_path} 是否為純圖片或空白。")
            logger.warning(f"   提示：如果是掃描的 PDF，請確認 OCR 功能已啟用。")
        else:
            # 統計各類型的數量
            type_counts = {}
            for block in content_blocks:
                if isinstance(block, dict):
                    block_type = block.get("type", "unknown")
                    type_counts[block_type] = type_counts.get(block_type, 0) + 1
            logger.info(f"📊 內容類型統計: {type_counts}")
        
        for i, block in enumerate(content_blocks):
            if isinstance(block, dict):
                block_type = block.get("type", "text")
                # OpenDataLoader 使用 "page number" (有空格)，也可能有 "page" 或 "page_num"
                page_num = block.get("page number", block.get("page", block.get("page_num", 1)))
                
                if block_type == "table":
                    artifacts.append({
                        "type": "table",
                        "page_num": page_num,
                        "content_json": block,
                        "metadata": {
                            "source": "opendataloader", 
                            "original_index": i,
                            "bounding_box": block.get("bounding box"),
                            "id": block.get("id")
                        }
                    })
                elif block_type == "image":
                    # OpenDataLoader 圖片格式 - 不存儲二進制數據，只存元數據
                    artifacts.append({
                        "type": "image",
                        "page_num": page_num,
                        "metadata": {
                            "source": "opendataloader",
                            "image_source": block.get("source"),
                            "bounding_box": block.get("bounding box"),
                            "id": block.get("id")
                        }
                    })
                elif block_type in ["paragraph", "heading", "header", "footer"]:
                    # 文字類型 - OpenDataLoader 使用 "content" 欄位存儲文字
                    text_content = block.get("content", "")
                    if text_content:
                        artifacts.append({
                            "type": "text_chunk",
                            "page_num": page_num,
                            "content": text_content,
                            "metadata": {
                                "source": "opendataloader", 
                                "original_index": i,
                                "block_type": block_type,
                                "level": block.get("level") or block.get("heading level"),
                                "font": block.get("font"),
                                "font_size": block.get("font size"),
                                "bounding_box": block.get("bounding box"),
                                "id": block.get("id")
                            }
                        })
                elif block_type == "list":
                    # 列表類型 - 提取 list items 中的文字
                    list_items = block.get("list items", [])
                    list_text_parts = []
                    for item in list_items:
                        if isinstance(item, dict):
                            item_text = item.get("content", item.get("text", ""))
                            if item_text:
                                list_text_parts.append(item_text)
                    
                    if list_text_parts:
                        artifacts.append({
                            "type": "text_chunk",
                            "page_num": page_num,
                            "content": " | ".join(list_text_parts),  # 用分隔符連接列表項
                            "metadata": {
                                "source": "opendataloader", 
                                "original_index": i,
                                "block_type": "list",
                                "number_of_items": block.get("number of list items", len(list_items)),
                                "bounding_box": block.get("bounding box"),
                                "id": block.get("id")
                            }
                        })
                else:
                    # 其他類型 - 嘗試提取 content 或 text
                    text_content = block.get("content", block.get("text", ""))
                    if text_content:
                        artifacts.append({
                            "type": "text_chunk",
                            "page_num": page_num,
                            "content": str(text_content),
                            "metadata": {
                                "source": "opendataloader", 
                                "original_index": i,
                                "block_type": block_type,
                                "bounding_box": block.get("bounding box"),
                                "id": block.get("id")
                            }
                        })
            else:
                # Fallback：給未知結構的資料
                artifacts.append({
                    "type": "text_chunk",
                    "page_num": 1,
                    "content": str(block),
                    "metadata": {"source": "opendataloader_raw"}
                })
        
        logger.info(f"✅ 真實解析完成：共提取了 {len(artifacts)} 個 artifacts (區塊/表格)")
        return artifacts
    
    async def _save_artifacts(self, artifacts: List[Dict[str, Any]], company_id: int, doc_id: str, progress_callback=None) -> Dict[str, int]:
        """
        保存 Artifacts 到 Docker Volume 並更新數據庫
        
        Returns:
            統計數據
        """
        stats = {
            "total_chunks": 0,
            "total_tables": 0,
            "total_images": 0,
            "total_metrics": 0
        }
        
        # 創建文檔專屬目錄
        doc_dir = self.data_dir / doc_id
        doc_dir.mkdir(exist_ok=True)
        
        total_items = len(artifacts)
        
        for idx, artifact in enumerate(artifacts):
            artifact_type = artifact.get("type")
            page_num = artifact.get("page_num")
            
            try:
                if artifact_type == "text_chunk":
                    # 保存文本塊到 document_chunks 表
                    await self._save_text_chunk(artifact, company_id, doc_id)
                    stats["total_chunks"] += 1
                
                elif artifact_type == "table":
                    # 保存表格 (JSON + 可選的圖片)
                    await self._save_table(artifact, company_id, doc_id, doc_dir, idx)
                    stats["total_tables"] += 1
                
                elif artifact_type == "image":
                    # 保存圖片到文件系統
                    await self._save_image(artifact, company_id, doc_id, doc_dir, idx)
                    stats["total_images"] += 1
                
                elif artifact_type == "financial_metric":
                    # 保存結構化財務數據
                    await self._save_financial_metric(artifact, company_id, doc_id)
                    stats["total_metrics"] += 1
            
            except Exception as e:
                logger.error(f"❌ 保存 artifact 失敗 (idx={idx}): {e}")
                continue
            
            # 🚀 計算真實進度並回報 (分配在 60.0% ~ 85.0% 之間)
            if progress_callback and total_items > 0:
                # 為了避免前端和 Log 被海量訊息淹沒，每處理 10 筆或是最後一筆時才發送一次更新
                if (idx + 1) % 10 == 0 or (idx + 1) == total_items:
                    # 計算公式：起始進度 (60) + (目前筆數 / 總筆數) * 分配的區間大小 (25)
                    current_percent = 60.0 + ((idx + 1) / total_items) * 25.0
                    progress_callback(
                        current_percent,
                        f"寫入資料庫中... ({idx + 1}/{total_items} 筆)"
                    )
        
        return stats
    
    async def _save_text_chunk(self, artifact: Dict, company_id: int, doc_id: str):
        """保存文本塊 - 文本已保存在 output.json 中 (No RAG Option: document_chunks 表已移除)"""
        # 文本塊已保存在 output.json 中，無需單獨存入數據庫
        # document_chunks 表已根據 No RAG Option 移除
        logger.debug(f"📝 文本塊已存在於 output.json (page {artifact.get('page_num')})")
    
    async def _save_table(self, artifact: Dict, company_id: int, doc_id: str, doc_dir: Path, idx: int):
        """保存表格"""
        page_num = artifact.get("page_num")
        metadata = artifact.get("metadata", {})
        
        # 1. 保存表格 JSON 到文件
        table_json_path = doc_dir / f"table_{idx:04d}.json"
        with open(table_json_path, 'w', encoding='utf-8') as f:
            json.dump(artifact.get("content_json", {}), f, ensure_ascii=False, indent=2)
        
        # 2. 記錄到 raw_artifacts 表
        artifact_id = f"{doc_id}_table_{idx:04d}"
        relative_path = str(table_json_path.relative_to(self.data_dir))
        
        await self.db_conn.execute(
            """
            INSERT INTO raw_artifacts (
                artifact_id, doc_id, company_id, file_type,
                file_path, file_size_bytes, metadata, page_num, source_file
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            artifact_id,
            doc_id,
            company_id,
            "table_json",
            relative_path,
            table_json_path.stat().st_size,
            json.dumps(metadata),
            page_num,
            doc_id
        )
        
        # raw_artifacts 記錄完成 (document_chunks 已移除 - No RAG Option)
        logger.debug(f"📊 表格已保存：{artifact_id}")
    
    async def _save_image(self, artifact: Dict, company_id: int, doc_id: str, doc_dir: Path, idx: int):
        """保存圖片"""
        page_num = artifact.get("page_num")
        metadata = artifact.get("metadata", {})
        image_data = artifact.get("image_data", b"")
        
        # 1. 保存圖片到文件
        image_format = metadata.get("format", "png")
        image_path = doc_dir / f"image_{idx:04d}.{image_format}"
        
        # 寫入真實的圖片二進制資料
        if image_data:
            with open(image_path, 'wb') as f:
                f.write(image_data)
            logger.debug(f"💾 圖片已保存：{image_path.name} ({len(image_data)} bytes)")
        else:
            logger.warning(f"⚠️ 圖片數據為空，跳過保存：{image_path.name}")
            # 創建空文件用於標記
            image_path.touch()
        
        # 2. 記錄到 raw_artifacts 表
        artifact_id = f"{doc_id}_image_{idx:04d}"
        relative_path = str(image_path.relative_to(self.data_dir))
        
        await self.db_conn.execute(
            """
            INSERT INTO raw_artifacts (
                artifact_id, doc_id, company_id, file_type,
                file_path, file_size_bytes, metadata, page_num, source_file
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            artifact_id,
            doc_id,
            company_id,
            "image",
            relative_path,
            image_path.stat().st_size if image_path.exists() else 0,
            json.dumps(metadata),
            page_num,
            doc_id
        )
    
    async def _save_financial_metric(self, artifact: Dict, company_id: int, doc_id: str):
        """保存財務指標"""
        # TODO: 實現財務指標提取邏輯
        pass
    
    async def _update_document_status(self, doc_id: str, status: str, stats: Dict = None, error: str = None):
        """更新文檔處理狀態"""
        if status == "completed" and stats:
            await self.db_conn.execute(
                """
                UPDATE documents SET
                    processing_status = 'completed',
                    processing_completed_at = NOW(),
                    total_chunks = $1,
                    total_artifacts = $2,
                    updated_at = NOW()
                WHERE doc_id = $3
                """,
                stats.get("total_chunks", 0),
                stats.get("total_tables", 0) + stats.get("total_images", 0),
                doc_id
            )
        elif status == "failed":
            await self.db_conn.execute(
                """
                UPDATE documents SET
                    processing_status = 'failed',
                    processing_error = $1,
                    updated_at = NOW()
                WHERE doc_id = $2
                """,
                error,
                doc_id
            )
    
    async def _trigger_vanna_training(self, doc_id: str, progress_callback=None):
        """
        觸發 Vanna 訓練 (邊做邊學)
        
        當新文件處理完成後，自動通知 Vanna Service 進行訓練
        """
        vanna_url = os.getenv("VANNA_SERVICE_URL", "http://vanna-service:8082")
        
        try:
            if progress_callback:
                progress_callback(90.0, "正在連線 Vanna 引擎準備訓練...")
            
            logger.info(f"🧠 正在觸發 Vanna 訓練 (doc_id: {doc_id})...")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 發送訓練請求到 Vanna Service
                response = await client.post(
                    f"{vanna_url}/api/train",
                    json={
                        "train_type": "sql",
                        "doc_id": doc_id
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ Vanna 訓練已觸發：{result.get('message', 'Success')}")
                    # 訓練成功回傳時更新進度
                    if progress_callback:
                        progress_callback(98.0, "Vanna 訓練完成，正在收尾...")
                else:
                    logger.warning(f"⚠️ Vanna 訓練請求失敗 (HTTP {response.status_code}): {response.text}")
                    if progress_callback:
                        progress_callback(90.0, "Vanna 訓練請求失敗，跳過此步驟")
        
        except httpx.RequestError as e:
            logger.warning(f"⚠️ 無法連接 Vanna Service: {e}. 跳過訓練步驟。")
            if progress_callback:
                progress_callback(90.0, "Vanna 連線超時或失敗")
        except Exception as e:
            logger.warning(f"⚠️ Vanna 訓練觸發失敗：{e}")
            if progress_callback:
                progress_callback(90.0, "Vanna 連線超時或失敗")

    async def _extract_company_info_with_llm(self, pdf_path: str, artifacts: List[Dict], output_json_path: Path) -> Optional[Dict[str, Any]]:
        """
        🌟 優先使用 Vision LLM 從封面提取公司信息
        
        流程：
        1. Vision 提取（封面圖片 → LLM）- 解決 OCR 層問題
        2. Fallback: 從 artifacts 純文字中提取
        3. Fallback: 從文件名正則提取
        
        Args:
            pdf_path: PDF 文件路徑
            artifacts: OpenDataLoader 解析出的結構化數據
            output_json_path: 輸出 JSON 路徑
            
        Returns:
            Dict with keys: stock_code, name_en, name_zh, industry, sector (all optional)
        """
        # ==========================================
        # 方案 A: Vision 提取（優先，解決封面文字被向量化問題）
        # ==========================================
        if PYMUPDF_AVAILABLE and OPENAI_SDK_AVAILABLE:
            try:
                logger.info("👁️ 正在使用 Vision LLM 從封面提取公司信息...")
                
                # 將封面轉為高解析度圖片
                cover_image_base64 = self._convert_pdf_page_to_image_base64(pdf_path, page_num=1, zoom=2.0)
                
                if cover_image_base64:
                    company_info = await self._extract_company_from_cover_image(cover_image_base64)
                    if company_info and company_info.get("stock_code"):
                        logger.info(f"✅ Vision 提取成功: Stock={company_info.get('stock_code')}, Name={company_info.get('name_en')}")
                        return company_info
                    else:
                        logger.warning("⚠️ Vision 提取未找到 stock_code，嘗試 Fallback...")
                else:
                    logger.warning("⚠️ 封面圖片轉換失敗，嘗試 Fallback...")
            except Exception as e:
                logger.warning(f"⚠️ Vision 提取失敗: {e}，嘗試 Fallback...")
        
        # ==========================================
        # 方案 B: 從 artifacts 純文字中提取（Fallback）
        # ==========================================
        try:
            text_content = []
            for artifact in artifacts[:50]:  # 只取前 50 個 artifacts
                if artifact.get("type") == "text_chunk":
                    content = artifact.get("content", "")
                    if content and len(content) > 20:
                        text_content.append(content)
            
            if text_content:
                combined_text = "\n\n".join(text_content[:10])
                if len(combined_text) > 5000:
                    combined_text = combined_text[:5000]
                
                logger.info("📄 正在從 artifacts 文字中提取公司信息...")
                
                # 調用 LLM API
                llm_api_url = os.getenv("LLM_API_URL", "http://vanna-service:8082/api/extract")
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        llm_api_url,
                        json={
                            "text": combined_text,
                            "extract_type": "company_info"
                        }
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        company_info = result.get("company_info", {})
                        if company_info.get("stock_code"):
                            logger.info(f"✅ Artifacts 文字提取成功: {company_info}")
                            return company_info
        except Exception as e:
            logger.warning(f"⚠️ Artifacts 文字提取失敗: {e}")
        
        # ==========================================
        # 方案 C: 從文件名正則提取（最後手段）
        # ==========================================
        logger.info("📄 正在從文件名提取公司信息...")
        filename = Path(pdf_path).stem
        
        # 提取 stock_code (格式: stock_XXXXX)
        stock_match = re.search(r'stock_(\d{4,5})', filename)
        if stock_match:
            stock_code = stock_match.group(1).zfill(5)
            logger.info(f"✅ 從文件名提取 stock_code: {stock_code}")
            return {"stock_code": stock_code}
        
        # 提取 year (格式: _YYYY)
        year_matches = re.findall(r'_(\d{4})(?:_|$)', filename)
        for y in year_matches:
            y_int = int(y)
            if 2000 <= y_int <= 2030:
                logger.info(f"✅ 從文件名提取 year: {y_int}")
                return {"year": y_int}
        
        logger.warning("⚠️ 所有提取方法都失敗")
        return None
    
    async def _extract_company_from_cover_image(self, base64_image: str) -> Optional[Dict[str, Any]]:
        """
        使用 Vision LLM 從封面圖片提取公司信息
        
        Args:
            base64_image: Base64 編碼的封面圖片
            
        Returns:
            Dict with keys: stock_code, year, name_en, name_zh
        """
        if not OPENAI_SDK_AVAILABLE:
            return None
        
        try:
            api_key = os.getenv("CUSTOM_API_KEY", os.getenv("OPENAI_API_KEY"))
            api_base = os.getenv("CUSTOM_API_BASE", os.getenv("OPENAI_API_BASE", "https://coding.dashscope.aliyuncs.com/v1"))
            
            if not api_key or api_key.startswith("sk-YOUR"):
                logger.error("❌ 未配置有效的 API Key")
                return None
            
            client = AsyncOpenAI(api_key=api_key, base_url=api_base)
            
            # Vision 模型映射
            model = os.getenv("VISION_MODEL", "qwen-vl-max")
            
            prompt = """你是一個精準的財報數據提取專家。請從這張港股年報封面圖片中提取 4 個核心資訊。

⚠️ 嚴格規則：
1. stock_code: 股票代碼（通常是 4-5 位純數字，例如 02359, 00001。不要包含多餘文字）
2. year: 財報年份（如 2023, 2024）
3. name_en: 公司英文名（找不到填 null）
4. name_zh: 公司中文名（找不到填 null）

請僅回傳 JSON 格式，不要包含任何其他解釋：
{
  "stock_code": "00001",
  "year": 2023,
  "name_en": "CK Hutchison Holdings Limited",
  "name_zh": "長和"
}"""
            
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.0
            )
            
            result_text = response.choices[0].message.content
            logger.debug(f"   🤖 Vision LLM 原始響應: {result_text[:300] if result_text else 'None'}...")
            
            # 清理 Markdown 標記
            if result_text and result_text.startswith("```"):
                result_text = result_text.strip()
                for prefix in ["```json", "```JSON", "```"]:
                    result_text = result_text.replace(prefix, "")
                if result_text.endswith("```"):
                    result_text = result_text[:-3]
            
            if result_text:
                try:
                    result = json.loads(result_text.strip())
                    
                    # 驗證 stock_code
                    stock_code = result.get("stock_code")
                    if stock_code:
                        stock_code = re.sub(r'[^\d]', '', str(stock_code))
                        if len(stock_code) >= 4:
                            result["stock_code"] = stock_code.zfill(5)
                        else:
                            result["stock_code"] = None
                    
                    # 驗證 year
                    year = result.get("year")
                    if year:
                        try:
                            year_int = int(year)
                            if 2000 <= year_int <= 2030:
                                result["year"] = year_int
                            else:
                                result["year"] = None
                        except:
                            result["year"] = None
                    
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON 解析失敗: {e}")
                    return None
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Vision 提取失敗: {e}")
            return None
    
    def _extract_stock_code_fallback(self, text: str) -> Optional[Dict[str, Any]]:
        """後備方案：使用正則表達式從文本中提取股票代碼"""
        # 港股格式: 00001, 00700, 0700.HK 等
        hk_pattern = r'\b(\d{4,5})(?:\.HK)?\b'
        #美股格式: AAPL, MSFT 等
        us_pattern = r'\b([A-Z]{2,5})\b'
        
        matches = re.findall(hk_pattern, text)
        if matches:
            # 過濾掉明顯不是股票代碼的數字（如年份、頁碼等）
            for match in matches:
                code_num = int(match)
                if 1 <= code_num <= 99999 and code_num > 1000:  # 股票代碼通常在 0001-99999 範圍
                    stock_code = match.zfill(5) + ".HK"
                    logger.info(f"📝 正則提取的股票代碼: {stock_code}")
                    return {"stock_code": stock_code}
        
        return None
    
    async def _find_or_create_company(self, company_info: Dict[str, Any]) -> Optional[int]:
        """
        根據公司信息查找或創建公司記錄
        
        Returns:
            company_id
        """
        stock_code = company_info.get("stock_code")
        name_en = company_info.get("name_en")
        name_zh = company_info.get("name_zh")
        
        if not stock_code and not name_en:
            logger.warning("⚠️ 缺少股票代碼和公司名稱，無法創建公司記錄")
            return None
        
        try:
            # 1. 先嘗試查找現有公司
            if stock_code:
                existing_id = await self.db_conn.fetchval(
                    "SELECT id FROM companies WHERE stock_code = $1",
                    stock_code
                )
                if existing_id:
                    logger.info(f"✅ 找到現有公司: ID={existing_id}, Stock Code={stock_code}")
                    return existing_id
            
            if name_en:
                existing_id = await self.db_conn.fetchval(
                    "SELECT id FROM companies WHERE name_en ILIKE $1",
                    f"%{name_en}%"
                )
                if existing_id:
                    logger.info(f"✅ 找到現有公司: ID={existing_id}, Name={name_en}")
                    return existing_id
            
            # 2. 創建新公司
            new_id = await self.db_conn.fetchval(
                """
                INSERT INTO companies (name_en, name_zh, stock_code, industry, sector)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                name_en or f"Company_{stock_code or 'Unknown'}",
                name_zh,
                stock_code,
                company_info.get("industry"),
                company_info.get("sector")
            )
            logger.info(f"✅ 創建新公司: ID={new_id}, Stock Code={stock_code}, Name={name_en}")
            return new_id
            
        except Exception as e:
            logger.error(f"❌ 查找/創建公司失敗: {e}")
            return None
    
    async def _update_document_company(self, doc_id: str, company_id: int):
        """更新文檔的 company_id"""
        await self.db_conn.execute(
            "UPDATE documents SET company_id = $1, updated_at = NOW() WHERE doc_id = $2",
            company_id,
            doc_id
        )
    
    # ===========================================
    # 🚀 Vision 混合解析架構 (Hybrid Parsing)
    # ===========================================
    
    @staticmethod
    def _is_complex_page(page: "fitz.Page") -> bool:
        """
        判斷該頁是否需要動用 Vision (MinerU 概念) 來解析
        
        檢測條件：
        1. 頁面內有圖片/圖表 (Pie Chart 通常會被識別為 image 或 vector drawings)
        2. 頁面內包含大量向量繪圖 (Drawings/Paths)，通常是柱狀圖或圓餅圖
        3. 包含特定的財務關鍵字
        
        Args:
            page: PyMuPDF 的 Page 對象
            
        Returns:
            bool: True 表示需要 Vision 解析，False 表示可以用快速文字抽取
        """
        if not PYMUPDF_AVAILABLE:
            return False
        
        try:
            # 條件 1: 頁面內有圖片/圖表
            image_list = page.get_images(full=True)
            if len(image_list) > 0:
                logger.debug(f"   📊 檢測到 {len(image_list)} 張圖片，需要 Vision 解析")
                return True
            
            # 條件 2: 頁面內包含大量向量繪圖 (Drawings/Paths)，通常是柱狀圖或圓餅圖
            drawings = page.get_drawings()
            if len(drawings) > 10:  # 超過 10 條線條，很可能是圖表
                logger.debug(f"   📊 檢測到 {len(drawings)} 個向量繪圖，可能是圖表")
                return True
            
            # 條件 3: 包含特定的財務關鍵字 (可選)
            text = page.get_text("text").lower()
            complex_keywords = [
                "revenue breakdown", "geographical", "chart", "pie chart",
                "收入分佈", "地區收入", "業務分佈", "breakdown by"
            ]
            for keyword in complex_keywords:
                if keyword in text:
                    logger.debug(f"   📊 檢測到關鍵字 '{keyword}'，需要 Vision 解析")
                    return True
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ 檢測頁面複雜度失敗: {e}")
            return False
    
    def _convert_pdf_page_to_image_base64(self, pdf_path: str, page_num: int, zoom: float = 2.0) -> Optional[str]:
        """
        將 PDF 特定頁面轉換為高品質 PNG 圖片並返回 Base64 字串
        
        Args:
            pdf_path: PDF 檔案路徑
            page_num: 頁碼 (1-indexed)
            zoom: 放大倍數 (2.0 = 144 DPI，適合財務數字)
            
        Returns:
            str: Base64 編碼的 PNG 圖片，或 None (失敗時)
        """
        if not PYMUPDF_AVAILABLE:
            logger.error("❌ PyMuPDF 未安裝，無法轉換 PDF 為圖片")
            return None
        
        try:
            logger.info(f"👁️ 正在將 PDF 第 {page_num} 頁轉換為圖片 (zoom={zoom})...")
            
            doc = fitz.open(pdf_path)
            
            # 檢查頁碼是否有效
            if page_num < 1 or page_num > len(doc):
                logger.error(f"❌ 頁碼 {page_num} 無效 (PDF 共 {len(doc)} 頁)")
                doc.close()
                return None
            
            page = doc.load_page(page_num - 1)  # PyMuPDF 頁碼由 0 開始
            
            # 提高清晰度
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            # 將圖片轉為 Base64
            img_bytes = pix.tobytes("png")
            base64_image = base64.b64encode(img_bytes).decode('utf-8')
            
            doc.close()
            
            logger.info(f"✅ PDF 頁面已轉換為 Base64 圖片 ({len(base64_image)} chars)")
            return base64_image
            
        except Exception as e:
            logger.error(f"❌ PDF 轉圖片失敗: {e}")
            return None
    
    async def _vision_to_markdown(
        self,
        base64_image: str,
        model: str = "qwen-vl-max"
    ) -> Optional[str]:
        """
        🌟 RAG-Anything 風格：將包含圖表的頁面轉為高質量 Markdown
        
        這是借鑒 RAG-Anything prompts_zh.py 的核心邏輯：
        - 專注於「視覺 → Markdown」轉換
        - 圖表數據化：將 Pie Chart/Bar Chart 轉為 Markdown 表格
        - 不計算，只提取肉眼可見的數字
        
        Args:
            base64_image: Base64 編碼的 PNG 圖片
            model: Vision 模型名稱
            
        Returns:
            str: Markdown 文本，或 None (失敗時)
        """
        if not OPENAI_SDK_AVAILABLE:
            logger.error("❌ OpenAI SDK 未安裝，無法呼叫 Vision LLM")
            return None
        
        try:
            # 從環境變數讀取 API 配置
            api_key = os.getenv("CUSTOM_API_KEY", os.getenv("OPENAI_API_KEY"))
            api_base = os.getenv("CUSTOM_API_BASE", os.getenv("OPENAI_API_BASE", "https://coding.dashscope.aliyuncs.com/v1"))
            
            if not api_key or api_key.startswith("sk-YOUR"):
                logger.error("❌ 未配置有效的 API Key")
                return None
            
            logger.info(f"👁️ RAG-Anything 視覺模式：轉換圖片為 Markdown...")
            
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=api_base
            )
            
            # RAG-Anything 級別的 Markdown 轉換 Prompt
            # 參考了 raganything/prompts_zh.py 精煉出來的黃金提示詞
            system_prompt = """
你是一個專業的文檔解析引擎（類似 MinerU/Docling）。
你的唯一任務是將這張 PDF 頁面的截圖，100% 忠實地轉換為 Markdown 格式。

【嚴格轉換規則】：
1. **圖表數據化 (極重要)**：如果圖片中包含圓餅圖 (Pie Chart) 或柱狀圖 (Bar Chart)，請直接讀取圖表上的標籤和百分比/數值，並將其轉化為 Markdown 表格。絕對不要自己計算，只提取肉眼可見的數字！
   例如：如果看到 Pie Chart 上有 "Canada" 和 "1%" 的標籤，請輸出：
   | 地區 | 百分比 |
   | Canada | 1% |
   
2. **表格還原**：遇到真正的表格，請使用標準 Markdown 語法 `| Column | Column |` 還原，保持行列結構。

3. **上下文保留**：保留所有標題、註腳和貨幣單位（例如 "in HK$ millions"）。

4. **數字精準**：財務數字要精確提取，包括逗號分隔符（例如 461,558）。

5. 不要輸出任何多餘的解釋或對話，只輸出 Markdown 內容。
"""
            
            # 呼叫 Vision API
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            },
                            {
                                "type": "text",
                                "text": "請將此頁面精確轉換為 Markdown："
                            }
                        ]
                    }
                ],
                temperature=0.0  # 確保不出現幻覺
            )
            
            markdown_result = response.choices[0].message.content
            logger.info(f"✅ RAG-Anything Markdown 轉換完成 ({len(markdown_result)} chars)")
            logger.debug(f"   Markdown 內容預覽:\n{markdown_result[:500]}...")
            
            return markdown_result
            
        except Exception as e:
            logger.error(f"❌ Vision Markdown 轉換失敗: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _extract_json_from_markdown(
        self,
        markdown_content: str,
        extraction_type: str = "revenue_breakdown",
        model: str = "qwen3.5-plus"
    ) -> Optional[Dict[str, Any]]:
        """
        🧠 審計師 Agent：從 Markdown 中提取結構化 JSON
        
        這是第二步驟，接收 RAG-Anything 生成的 Markdown，
        使用 LLM 做邏輯提取和驗證。
        
        Args:
            markdown_content: Markdown 文本
            extraction_type: 提取類型
            model: LLM 模型名稱
            
        Returns:
            Dict: 提取的 JSON 数据，或 None
        """
        if not OPENAI_SDK_AVAILABLE:
            logger.error("❌ OpenAI SDK 未安裝")
            return None
        
        try:
            api_key = os.getenv("CUSTOM_API_KEY", os.getenv("OPENAI_API_KEY"))
            api_base = os.getenv("CUSTOM_API_BASE", os.getenv("OPENAI_API_BASE", "https://coding.dashscope.aliyuncs.com/v1"))
            
            if not api_key or api_key.startswith("sk-YOUR"):
                logger.error("❌ 未配置有效的 API Key")
                return None
            
            logger.info(f"🧠 審計師 Agent 正在提取 {extraction_type}...")
            
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=api_base
            )
            
            # 审计师 Prompt
            if extraction_type == "revenue_breakdown":
                system_prompt = """
你是一個頂級四大會計師行的資深審計師。
我會提供一份從財務年報轉換出的 Markdown 內容。
你的唯一任務是提取「地區收入分佈 (Revenue Breakdown by Geographical Location)」。

【嚴格執行以下規則】：
1. **只讀 Markdown 表格**：從 Markdown 的表格中提取地區名稱和百分比。如果表格中有百分比列，直接使用，不要自己計算！
2. **金額提取**：同時提取絕對金額（如果有的話），注意單位。
3. **自我驗證**：提取完成後，將所有百分比相加。如果總和不在 99.0 到 101.0 之間，說明你遺漏了某些地區，請仔細重看！

【強制輸出格式】：
只輸出純 JSON，不要包含 Markdown 標記：
{
  "Canada": {"percentage": 1.0, "amount": 3862},
  "Europe": {"percentage": 50.0, "amount": 231679},
  "Asia, Australia & Others": {"percentage": 17.0, "amount": 80214}
}
"""
            else:
                system_prompt = """
你是一個專業的財務數據提取專家。
請從提供的 Markdown 內容中提取結構化數據。
以純 JSON 格式輸出，不要包含 Markdown 標記。
"""
            
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": markdown_content}
                ],
                temperature=0.0
            )
            
            result_text = response.choices[0].message.content
            
            # 清理可能的 Markdown 標記
            if result_text.startswith("```"):
                result_text = result_text.strip()
                for prefix in ["```json", "```JSON", "```"]:
                    result_text = result_text.replace(prefix, "")
                if result_text.endswith("```"):
                    result_text = result_text[:-3]
            
            try:
                result_json = json.loads(result_text.strip())
                logger.info(f"✅ JSON 提取成功: {list(result_json.keys())}")
                return result_json
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 解析失敗: {e}")
                logger.error(f"   原始返回: {result_text}")
                return None
            
        except Exception as e:
            logger.error(f"❌ JSON 提取失敗: {e}")
            return None
    
    async def _extract_with_vision_llm(
        self,
        base64_image: str,
        extraction_type: str = "revenue_breakdown",
        model: str = "qwen-vl-max"
    ) -> Optional[Dict[str, Any]]:
        """
        使用 Vision LLM (Qwen-VL 或 GPT-4o) 從圖片中提取結構化數據
        
        Args:
            base64_image: Base64 編碼的 PNG 圖片
            extraction_type: 提取類型 ("revenue_breakdown", "financial_table", etc.)
            model: Vision 模型名稱
            
        Returns:
            Dict: 提取的結構化數據，或 None (失敗時)
        """
        if not OPENAI_SDK_AVAILABLE:
            logger.error("❌ OpenAI SDK 未安裝，無法呼叫 Vision LLM")
            return None
        
        try:
            # 從環境變數或 config 讀取 API 配置
            api_key = os.getenv("CUSTOM_API_KEY", os.getenv("OPENAI_API_KEY"))
            api_base = os.getenv("CUSTOM_API_BASE", os.getenv("OPENAI_API_BASE", "https://coding.dashscope.aliyuncs.com/v1"))
            
            if not api_key or api_key.startswith("sk-YOUR"):
                logger.error("❌ 未配置有效的 API Key")
                return None
            
            logger.info(f"🧠 正在使用 Vision LLM ({model}) 提取 {extraction_type}...")
            
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=api_base
            )
            
            # 根據提取類型構建不同的 Prompt
            if extraction_type == "revenue_breakdown":
                system_prompt = """
你是一個頂級四大會計師行的資深審計師。我會提供一份財務年報的圖片。
你的唯一任務是提取「地區收入分佈 (Revenue Breakdown by Geographical Location)」。

【嚴格執行以下規則】：
1. 優先讀圖表標籤：如果圖片中的圓餅圖、柱狀圖或表格直接寫明了百分比（例如 Canada 1% 或 1.0%），絕對不可自己用絕對金額重新計算！必須提取字面上的原始百分比數字。
2. 金額單位注意：請同時提取該地區的絕對收入金額，並注意前後文的單位（例如 in HK$ millions，請直接提取數字，無需轉換為全寫）。
3. 【自我驗證】：提取完成後，請在心裡將所有 percentage 相加。如果總和不在 99.0 到 101.0 之間，說明你遺漏了某些地區（例如 Others 或 Unallocated），請仔細重看圖片！

【強制輸出格式】：
請只輸出純 JSON 格式，不要包含任何 Markdown 標記 (如 ```json) 或其他廢話。
格式範例：
{
  "Canada": {"percentage": 1.0, "amount": 3862},
  "Europe": {"percentage": 50.0, "amount": 231679},
  "Asia, Australia & Others": {"percentage": 17.0, "amount": 80214}
}
"""
            else:
                system_prompt = """
你是一個專業的財務數據數位化專家。請將這張財務報表圖片中的所有數據提取出來。
請以 JSON 格式輸出，不要包含任何 Markdown 標記或其他廢話。
"""
            
            # 呼叫 Vision API
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            },
                            {
                                "type": "text",
                                "text": f"請提取這張圖片中的 {extraction_type} 數據，以 JSON 格式輸出。"
                            }
                        ]
                    }
                ],
                temperature=0.0  # 財務數據必須是 0，禁止幻覺
            )
            
            result_text = response.choices[0].message.content
            logger.info(f"✅ Vision LLM 返回結果: {result_text[:100]}...")
            
            # 清理可能的 Markdown 標記
            if result_text.startswith("```json"):
                result_text = result_text.strip()
                result_text = result_text.replace("```json", "").replace("```", "")
            
            # 解析 JSON
            try:
                result_json = json.loads(result_text)
                return result_json
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 解析失敗: {e}")
                logger.error(f"   原始返回: {result_text}")
                return None
            
        except Exception as e:
            logger.error(f"❌ Vision LLM 提取失敗: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _validate_revenue_breakdown(self, extracted_data: Dict[str, Any]) -> Tuple[bool, float]:
        """
        驗證 Revenue Breakdown 的百分比總和是否接近 100%
        
        Args:
            extracted_data: 提取的數據 Dict
            
        Returns:
            Tuple[bool, float]: (是否通過驗證, 總百分比)
        """
        try:
            total_percentage = sum(
                item.get("percentage", 0) 
                for item in extracted_data.values()
            )
            
            logger.info(f"📊 Revenue Breakdown 總百分比: {total_percentage}%")
            logger.info(f"   提取的分類: {list(extracted_data.keys())}")
            
            # 容許 99 - 101 的捨入誤差
            is_valid = 99.0 <= total_percentage <= 101.0
            
            if is_valid:
                logger.info(f"✅ 验证通过！总和符合 100% 逻辑")
            else:
                logger.warning(f"⚠️ 验证失败！总百分比为 {total_percentage}% (不等于 100%)")
                logger.warning(f"   可能遗漏了某些地区分类")
            
            return is_valid, total_percentage
            
        except Exception as e:
            logger.error(f"❌ 验证计算失败: {e}")
            return False, 0.0
    
    async def _insert_revenue_breakdown(
        self,
        company_id: int,
        year: int,
        extracted_data: Dict[str, Any],
        source_file: str,
        source_page: int
    ) -> int:
        """
        将验证通过的 Revenue Breakdown 数据写入 PostgreSQL
        
        Args:
            company_id: 公司 ID
            year: 年份
            extracted_data: 提取的数据 Dict
            source_file: 源文件名
            source_page: 源页码
            
        Returns:
            int: 插入的记录数量
        """
        try:
            inserted_count = 0
            
            for category, data in extracted_data.items():
                percentage = data.get("percentage")
                amount = data.get("amount")
                
                # 使用 UPSERT (ON CONFLICT DO UPDATE)
                await self.db_conn.execute(
                    """
                    INSERT INTO revenue_breakdown 
                    (company_id, year, category, category_type, percentage, amount, currency, source_file, source_page)
                    VALUES ($1, $2, $3, 'Region', $4, $5, 'HKD', $6, $7)
                    ON CONFLICT (company_id, year, category, category_type) 
                    DO UPDATE SET 
                        percentage = $4, 
                        amount = $5,
                        source_file = $6,
                        source_page = $7
                    """,
                    company_id,
                    year,
                    category,
                    percentage,
                    amount,
                    source_file,
                    source_page
                )
                inserted_count += 1
            
            logger.info(f"✅ 已写入 {inserted_count} 条 Revenue Breakdown 记录")
            return inserted_count
            
        except Exception as e:
            logger.error(f"❌ Revenue Breakdown 入库失败: {e}")
            return 0
    
    async def extract_revenue_breakdown_from_page(
        self,
        pdf_path: str,
        page_num: int,
        company_id: int,
        year: int,
        max_retries: int = 2,
        use_rag_anything_mode: bool = True
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        🚀 混合解析核心：从特定页面提取 Revenue Breakdown
        
        🌟 RAG-Anything 兩步式流程：
        1. Vision → Markdown (圖表數據化)
        2. Markdown → JSON (審計師提取)
        
        Args:
            pdf_path: PDF 檔案路徑
            page_num: 頁碼 (1-indexed)
            company_id: 公司 ID
            year: 年份
            max_retries: 最大重試次數
            use_rag_anything_mode: 是否使用 RAG-Anything 兩步式流程
            
        Returns:
            Tuple[bool, Dict]: (是否成功, 提取的数据或错误信息)
        """
        if not PYMUPDF_AVAILABLE or not OPENAI_SDK_AVAILABLE:
            logger.error("❌ PyMuPDF 或 OpenAI SDK 未安裝，无法执行混合解析")
            return False, {"error": "Missing dependencies"}
        
        logger.info(f"🚀 开始混合解析 Revenue Breakdown (Page {page_num})...")
        logger.info(f"   模式: {'RAG-Anything 兩步式' if use_rag_anything_mode else '直接提取'}")
        
        try:
            # Step 1: 打开 PDF 并检测页面复杂度
            doc = fitz.open(pdf_path)
            if page_num < 1 or page_num > len(doc):
                logger.error(f"❌ 頁碼 {page_num} 無效")
                doc.close()
                return False, {"error": "Invalid page number"}
            
            page = doc.load_page(page_num - 1)
            is_complex = self._is_complex_page(page)
            doc.close()
            
            source_file = Path(pdf_path).name
            
            # Step 2: 根据复杂度选择解析方式
            for attempt in range(max_retries):
                logger.info(f"🔍 正在提取 (尝试 {attempt + 1}/{max_retries})...")
                
                if is_complex:
                    # 🌟 复杂页面：使用 RAG-Anything 兩步式流程
                    logger.info(f"📊 第 {page_num} 页检测到图表/复杂排版")
                    
                    # Step 2a: 转换为高清图片
                    base64_image = self._convert_pdf_page_to_image_base64(pdf_path, page_num)
                    if not base64_image:
                        logger.warning(f"⚠️ 图片转换失败，重试...")
                        continue
                    
                    # Step 2b: Vision → Markdown (RAG-Anything 核心)
                    markdown_content = await self._vision_to_markdown(base64_image)
                    if not markdown_content:
                        logger.warning(f"⚠️ Markdown 转换失败，重试...")
                        continue
                    
                    # 保存 Markdown 中间产物供调试
                    md_save_path = self.data_dir / "debug" / f"page_{page_num}_markdown.txt"
                    md_save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(md_save_path, 'w', encoding='utf-8') as f:
                        f.write(markdown_content)
                    logger.info(f"💾 Markdown 中间产物已保存: {md_save_path}")
                    
                    # Step 2c: Markdown → JSON (审计师提取)
                    extracted_data = await self._extract_json_from_markdown(
                        markdown_content,
                        extraction_type="revenue_breakdown"
                    )
                    
                else:
                    # 普通页面：快速文字抽取 → Markdown → JSON
                    logger.info(f"📝 第 {page_num} 页为普通文本，使用快速抽取...")
                    
                    doc = fitz.open(pdf_path)
                    fast_text = doc.load_page(page_num - 1).get_text("text")
                    doc.close()
                    
                    # 将纯文字当作 "Markdown" 发送给审计师
                    extracted_data = await self._extract_json_from_markdown(
                        fast_text,
                        extraction_type="revenue_breakdown"
                    )
                
                if not extracted_data:
                    logger.warning(f"⚠️ 提取失败，重试...")
                    continue
                
                # Step 3: 验证百分比总和
                is_valid, total_pct = self._validate_revenue_breakdown(extracted_data)
                
                if is_valid:
                    # Step 4: 入库
                    inserted = await self._insert_revenue_breakdown(
                        company_id,
                        year,
                        extracted_data,
                        source_file,
                        page_num
                    )
                    
                    return True, {
                        "data": extracted_data,
                        "total_percentage": total_pct,
                        "inserted_count": inserted
                    }
                else:
                    logger.warning(f"⚠️ 验证失败 (总和 {total_pct}%)，重试...")
            
            # 所有重试都失败
            logger.error(f"❌ 已达最大重试次数，Revenue Breakdown 提取失败")
            return False, {
                "error": "Max retries exceeded",
                "last_data": extracted_data,
                "total_percentage": total_pct if extracted_data else 0
            }
            
        except Exception as e:
            logger.error(f"❌ 混合解析失败: {e}")
            import traceback
            traceback.print_exc()
            return False, {"error": str(e)}
    
    async def _smart_extract_structured_data(
        self,
        pdf_path: str,
        company_id: int,
        doc_id: str,
        artifacts: List[Dict[str, Any]],
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        🌟 智能結構化數據提取
        
        自動扫描 PDF，找出包含財務結構化數據的頁面，並提取：
        - Revenue Breakdown (地區收入分佈)
        - Financial Metrics (關鍵財務指標)
        - Key Personnel (高層人員)
        
        Args:
            pdf_path: PDF 文件路徑
            company_id: 公司 ID
            doc_id: 文檔 ID
            artifacts: 已解析的 artifacts
            progress_callback: 进度回调
            
        Returns:
            Dict: 提取統計數據
        """
        logger.info(f"🧠 開始智能結構化提取 (company_id={company_id})...")
        
        extraction_stats = {
            "revenue_breakdown_pages_scanned": 0,
            "revenue_breakdown_extracted": 0,
            "financial_metrics_extracted": 0,
            "errors": []
        }
        
        if not PYMUPDF_AVAILABLE:
            logger.warning("⚠️ PyMuPDF 不可用，跳過智能提取")
            return extraction_stats
        
        try:
            # Step 1: 推斷年份 (從文件名或 artifacts 中)
            year = self._infer_year_from_doc(doc_id, artifacts)
            logger.info(f"   推斷年份: {year}")
            
            # Step 2: 直接在已解析的 artifacts 中搜尋目標頁面（不再重新掃描 PDF）
            revenue_pages = await self._find_revenue_breakdown_pages(artifacts)
            extraction_stats["revenue_breakdown_pages_scanned"] = len(revenue_pages)
            
            logger.info(f"   找到 {len(revenue_pages)} 個可能包含 Revenue Breakdown 的頁面: {revenue_pages}")
            
            # Step 3: 對每個候選頁面進行提取
            for page_num in revenue_pages:
                if progress_callback:
                    progress_callback(87.0 + (page_num / len(revenue_pages) * 2), f"提取 Revenue Breakdown (Page {page_num})...")
                
                logger.info(f"   📊 正在提取第 {page_num} 頁的 Revenue Breakdown...")
                
                success, result = await self.extract_revenue_breakdown_from_page(
                    pdf_path=pdf_path,
                    page_num=page_num,
                    company_id=company_id,
                    year=year,
                    max_retries=2
                )
                
                if success:
                    extraction_stats["revenue_breakdown_extracted"] += result.get("inserted_count", 0)
                    logger.info(f"   ✅ 第 {page_num} 頁提取成功: {result.get('inserted_count', 0)} 瀦記錄")
                else:
                    extraction_stats["errors"].append(f"Page {page_num}: {result.get('error', 'Unknown error')}")
                    logger.warning(f"   ⚠️ 第 {page_num} 頁提取失敗: {result.get('error')}")
            
            # Step 4: (未來可擴展) 提取其他結構化數據
            # - Financial Metrics from tables
            # - Key Personnel from text
            # - Shareholdings
            
            logger.info(f"✅ 智能結構化提取完成: {extraction_stats}")
            return extraction_stats
            
        except Exception as e:
            logger.error(f"❌ 智能結構化提取失敗: {e}")
            import traceback
            traceback.print_exc()
            extraction_stats["errors"].append(str(e))
            return extraction_stats
    
    async def _find_revenue_breakdown_pages(self, artifacts: List[Dict[str, Any]]) -> List[int]:
        """
        🌟 直接在 Artifacts 中搜尋關鍵字
        
        不再使用 PyMuPDF 重新掃描 PDF，直接遍歷 OpenDataLoader 已經解析好的 artifacts。
        
        Args:
            artifacts: OpenDataLoader 解析出的結構化數據
            
        Returns:
            List[int]: 可能包含 Revenue Breakdown 的頁碼列表 (1-indexed)
        """
        candidate_pages = set()
        
        # Revenue Breakdown 關鍵字
        keywords = [
            "revenue breakdown",
            "geographical breakdown",
            "geographical revenue",
            "geographic revenue",
            "revenue by region",
            "revenue by geography",
            "revenue by location",
            "收入分佈",
            "地區收入",
            "業務分佈",
            "breakdown by",
            "segment revenue",
            "turnover by",
            "sales by region"
        ]
        
        logger.info(f"   🔍 在 {len(artifacts)} 個 artifacts 中搜尋 Revenue Breakdown...")
        
        for artifact in artifacts:
            artifact_type = artifact.get("type")
            page_num = artifact.get("page_num")
            
            # 只在有文字或表格的區塊搜尋
            if artifact_type == "text_chunk":
                content = str(artifact.get("content", "")).lower()
                for keyword in keywords:
                    if keyword.lower() in content:
                        candidate_pages.add(page_num)
                        logger.debug(f"   Page {page_num}: text_chunk 命中 '{keyword}'")
                        break
            
            elif artifact_type == "table":
                # 表格內容可能在 content_json 中
                table_json = artifact.get("content_json", {})
                content = json.dumps(table_json, ensure_ascii=False).lower()
                for keyword in keywords:
                    if keyword.lower() in content:
                        candidate_pages.add(page_num)
                        logger.debug(f"   Page {page_num}: table 命中 '{keyword}'")
                        break
        
        result_pages = sorted(list(candidate_pages))
        logger.info(f"   🎯 找到 {len(result_pages)} 個候選頁面: {result_pages}")
        
        return result_pages
    
    def _infer_year_from_doc(self, doc_id: str, artifacts: List[Dict[str, Any]]) -> int:
        """
        從文檔 ID 或 artifacts 中推斷年份
        
        Args:
            doc_id: 文檔 ID
            artifacts: 已解析的 artifacts
            
        Returns:
            int: 推斷的年份 (默認當前年份)
        """
        import re
        
        # 方法 1: 從 doc_id 中提取年份 (例如 stock_00001_2023.pdf)
        year_match = re.search(r'(\d{4})', doc_id)
        if year_match:
            year = int(year_match.group(1))
            if 2000 <= year <= 2030:
                return year
        
        # 方法 2: 從 artifacts 的文字中找年份
        for artifact in artifacts[:20]:  # 只看前 20 個
            if artifact.get("type") == "text_chunk":
                content = artifact.get("content", "")
                # 找 "Annual Report 2023" 或 "2023 Annual Report" 模式
                year_match = re.search(r'(?:annual report|年報)\s*(\d{4})|(\d{4})\s*(?:annual report|年報)', content.lower())
                if year_match:
                    year = int(year_match.group(1) or year_match.group(2))
                    if 2000 <= year <= 2030:
                        return year
        
        # 方法 3: 找任何 4 位數年份
        for artifact in artifacts[:20]:
            if artifact.get("type") == "text_chunk":
                content = artifact.get("content", "")
                year_matches = re.findall(r'\b(20[0-2][0-9])\b', content)
                if year_matches:
                    # 取最後一個年份 (通常報告年份在最後)
                    year = int(year_matches[-1])
                    return year
        
        # 默默返回當前年份
        from datetime import datetime
        return datetime.now().year


async def main():
    """測試函數"""
    from dotenv import load_dotenv
    load_dotenv()
    
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports")
    data_dir = os.getenv("DATA_DIR", "./data/raw")
    
    processor = OpenDataLoaderProcessor(db_url, data_dir)
    
    try:
        await processor.connect()
        
        # 測試處理
        result = await processor.process_pdf(
            pdf_path="./test_report.pdf",
            company_id=1,
            doc_id="test_001"
        )
        
        logger.info(f"處理結果：{result}")
    
    finally:
        await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
