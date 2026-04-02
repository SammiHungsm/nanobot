"""
OpenDataLoader Integration Module

功能：
1. 解析 Annual Report PDF
2. 提取所有 Raw Data (文字、表格、圖片)
3. 保存檔案到 Docker Volume
4. 將路徑和元數據寫入 PostgreSQL
"""

import os
import json
import hashlib
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger
import asyncpg
import httpx


class OpenDataLoaderProcessor:
    """
    OpenDataLoader 處理器
    
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
    
    async def process_pdf(self, pdf_path: str, company_id: int, doc_id: str, progress_callback=None, replace: bool = False) -> Dict[str, Any]:
        """
        處理單一 PDF 文檔
        
        Args:
            pdf_path: PDF 檔案路徑
            company_id: 公司 ID
            doc_id: 文檔唯一標識
            progress_callback: 進度回調函數 (percent: float, message: str)
            replace: 是否強制重新處理 (跳過去重檢查，刪除舊數據)
            
        Returns:
            處理結果統計
        """
        logger.info(f"🚀 開始處理 PDF: {pdf_path}")
        logger.info(f"   Company ID: {company_id}, Doc ID: {doc_id}, Replace: {replace}")
        
        try:
            # 1. 計算文件 Hash (用於去重)
            if progress_callback:
                progress_callback(10.0, "計算 Hash 與檢查重複...")
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
            
            # 3. 創建文檔記錄
            await self._create_document_record(pdf_path, company_id, doc_id, file_hash)
            logger.info("✅ 文檔記錄已創建")
            
            # 4. 使用 OpenDataLoader 解析 PDF (這是最花時間的一步)
            artifacts = await self._parse_with_opendataloader(pdf_path, doc_id, progress_callback)
            logger.info(f"📊 解析完成：{len(artifacts)} 個 artifacts")
            
            # 🚀 把解析出來的 Raw Data (artifacts) 存成 output.json 給 WebUI 讀取
            doc_dir = self.data_dir / doc_id
            doc_dir.mkdir(parents=True, exist_ok=True)
            output_json_path = doc_dir / "output.json"
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(artifacts, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 已保存 artifacts 到：{output_json_path}")
            
            # 5. 保存 Raw Artifacts 並更新數據庫
            if progress_callback:
                progress_callback(60.0, f"解析完成，準備寫入資料庫 (共 {len(artifacts)} 筆)...")
            stats = await self._save_artifacts(artifacts, company_id, doc_id, progress_callback)
            logger.info(f"💾 保存完成：{stats}")
            
            # 6. 更新文檔狀態
            if progress_callback:
                progress_callback(86.0, "更新狀態與清理暫存...")
            await self._update_document_status(doc_id, "completed", stats)
            
            # 7. 觸發 Vanna 訓練 (邊做邊學)
            if progress_callback:
                progress_callback(90.0, "準備觸發 Vanna 向量模型訓練...")
            await self._trigger_vanna_training(doc_id, progress_callback)
            
            if progress_callback:
                progress_callback(100.0, "✅ 處理完成")
            
            return {
                "status": "completed",
                "doc_id": doc_id,
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
        
        # 1. 刪除 document_chunks
        chunks_deleted = await self.db_conn.execute(
            "DELETE FROM document_chunks WHERE doc_id = $1",
            doc_id
        )
        logger.info(f"   📝 已刪除 document_chunks")
        
        # 2. 刪除 raw_artifacts
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
    
    async def _create_document_record(self, pdf_path: str, company_id: int, doc_id: str, file_hash: str):
        """創建文檔記錄"""
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
            company_id,
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
        """保存文本塊"""
        await self.db_conn.execute(
            """
            INSERT INTO document_chunks (
                doc_id, company_id, chunk_index, page_num, 
                chunk_type, content, metadata, source_file
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            doc_id,
            company_id,
            0,  # chunk_index
            artifact.get("page_num"),
            "text",
            artifact.get("content"),
            json.dumps(artifact.get("metadata", {})),
            doc_id
        )
    
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
        
        # 3. 同時保存到 document_chunks (用于全文搜索)
        content_json = artifact.get("content_json", {})
        content_text = json.dumps(content_json, ensure_ascii=False)
        
        await self.db_conn.execute(
            """
            INSERT INTO document_chunks (
                doc_id, company_id, chunk_index, page_num,
                chunk_type, content, content_json, metadata, source_file
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            doc_id,
            company_id,
            idx,
            page_num,
            "table",
            content_text,
            json.dumps(content_json),
            json.dumps(metadata),
            doc_id
        )
    
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
