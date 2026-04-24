"""
Stage 2: 多模態富文本擴充 (v4.3 統一 Vision 分析)

職責：
- 從 LlamaParse Cloud 下載圖片
- RAG-Anything：滑動視窗提取精準上下文 (Title, Caption, 前後文)
- Vision 分析圖片內容 + 實體關係，輸出完美 Markdown Representation
- 寫入資料庫 (raw_artifacts, document_pages)

黃金分工架構：
✅ LlamaParse 可靠的：純文字、格式良好的 Markdown 表格
⚠️ 需要 Vision 補強的：圖片 (image)、圖表 (chart)、混亂表格 (messy table)

🌟 v4.3 重大優化：
- 合併兩次 Vision 調用為一次，節省 50% API cost
- 一次輸出：type, title, markdown_representation, key_entities, semantic_description
- 語意描述 + 結構化表格完美組合

🌟 v4.2: 圖表 content = 語意描述 + 結構化表格
"""

import os
import json
import base64
import httpx
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from nanobot.core.llm_core import llm_core
from nanobot.ingestion.utils.rag_context import extract_precise_context


class Stage2Enrichment:
    """Stage 2: 多模態富文本擴充 (v4.3 統一 Vision 分析) 🌟
    
    v4.3 核心優化 (Cost 優化)：
    - 合併兩次 Vision 調用為一次，節省 50% API cost
    - 一次輸出：type, title, markdown_representation, key_entities, semantic_description
    - 語意描述 + 結構化表格完美組合
    """

    @staticmethod
    def _should_use_vision_enrichment(artifact: Dict[str, Any]) -> tuple[bool, str]:
        """🌟 v4.0 新增：黃金法則決策樹 - 判斷 artifact 是否需要 Vision 補強
        
        規則：
        ✅ Vision 加強：image, chart, messy table
        ❌ 直接信任 LlamaParse：text, well-formed table
        
        Returns:
            tuple: (是否需要 Vision, 原因描述)
        """
        art_type = artifact.get("type")
        
        # ✅ 這些交給 Vision Model（LlamaParse 不靠譜）
        if art_type == "image":
            return True, "LlamaParse OCR 不穩定，需要 Vision 重新翻譯"
        
        if art_type == "chart":
            return True, "Chart 圖表數據需要 Vision 提取"
        
        # ⚠️ 混亂表格也需要 Vision
        if art_type == "table":
            content = artifact.get("content", "")
            if Stage2Enrichment._is_messy_table(content):
                return True, "表格解析失敗，需要 Vision 修復"
        
        # ❌ 這些直接信 LlamaParse
        if art_type == "text":
            return False, "純文字，LlamaParse 精準"
        
        if art_type == "table":
            return False, "表格格式良好，直接使用 LlamaParse"
        
        return False, "未知類型，跳過"

    @staticmethod
    def _is_messy_table(md_content: str) -> bool:
        """
        防禦性檢查：判斷 Markdown 表格是否解析失敗、排版混亂或誤判為圖表
        🌟 v3.6: 新增 HTML 表格檢測（LlamaParse 返回 <table> 標籤）
        """
        if not md_content or not isinstance(md_content, str):
            return True

        # 🌟 0. 如果是 HTML 表格，直接返回 False（不算是混亂）
        if "<table" in md_content.lower() or "</table>" in md_content.lower():
            logger.debug("檢測到 HTML 表格格式，視為有效表格")
            return False

        # 1. 檢查是否有過多空儲存格 (通常是把 Chart 誤判為 Table 的特徵)
        empty_cells = md_content.count("| |") + md_content.count("||") + md_content.count("| |")
        if empty_cells > 10:
            return True

        # 2. 檢查結構是否嚴重殘缺 (沒有換行，但字數很多)
        if len(md_content) > 300 and md_content.count("\n") < 3:
            return True

        # 3. 檢查是否缺乏 Markdown 表格的特徵 (例如沒有 --- 分隔線)
        if "|" in md_content and "---" not in md_content and len(md_content) > 100:
            return True

        return False

    @staticmethod
    def _html_table_to_markdown(html_content: str) -> str:
        """
        🌟 新增：將 HTML 表格轉換為 Markdown 格式
        支持複雜表格結構，保留數據完整性
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("⚠️ BeautifulSoup 未安裝，無法轉換 HTML 表格，返回原始 HTML")
            return html_content

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            tables = soup.find_all('table')
            
            if not tables:
                return html_content
            
            markdown_tables = []
            
            for table in tables:
                rows = table.find_all('tr')
                if not rows:
                    continue
                
                md_rows = []
                header_row = None
                
                # 處理表頭
                first_row = rows[0]
                headers = first_row.find_all(['th', 'td'])
                if headers:
                    header_row = [cell.get_text(strip=True) for cell in headers]
                    md_rows.append("| " + " | ".join(header_row) + " |")
                    md_rows.append("| " + " | ".join(["---"] * len(header_row)) + " |")
                
                # 處理數據行
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if cells:
                        cell_data = [cell.get_text(strip=True) for cell in cells]
                        md_rows.append("| " + " | ".join(cell_data) + " |")
                
                markdown_tables.append("\n".join(md_rows))
            
            return "\n\n".join(markdown_tables)
            
        except Exception as e:
            logger.warning(f"⚠️ HTML 表格轉換失敗: {e}，返回原始 HTML")
            return html_content

    @staticmethod
    def _get_precise_context(artifacts: List[Dict[str, Any]], target_idx: int) -> Dict[str, str]:
        """
        🌟 v4.10: 已迁移到 utils/rag_context.py
        
        此方法保留用于向后兼容，新代码应直接使用：
        from nanobot.ingestion.utils.rag_context import extract_precise_context
        
        模拟 RAG-Anything 的精準上下文提取：
        尋找最接近的標題 (Title)、前文 (Intro) 與後文 (Explanation)
        """
        return extract_precise_context(artifacts, target_idx)

    @staticmethod
    async def _find_nearby_image_for_table(
        artifacts: List[Dict[str, Any]],
        table_idx: int,
        downloaded_images: Dict[str, Dict],
        images_dir: Path,
        doc_id: str,
        page_num: int
    ) -> Optional[str]:
        """🌟 v4.0 新增：為混亂表格尋找附近的圖片截圖
        
        策略：
        1. 優先尋找同一頁的 image artifact
        2. 如果沒有，尋找前後頁的 image artifact
        3. 返回本地圖片路徑，或 None
        
        Args:
            artifacts: 所有 artifact 列表
            table_idx: 當前表格 artifact 的索引
            downloaded_images: 已下載的圖片字典 {filename: info}
            images_dir: 圖片目錄
            doc_id: 文檔 ID
            page_num: 表格所在頁碼
            
        Returns:
            Optional[str]: 圖片的本地路徑，或 None
        """
        # 策略 1：同一頁的 image artifact（前後 3 個位置）
        for offset in range(-3, 4):
            idx = table_idx + offset
            if 0 <= idx < len(artifacts):
                artifact = artifacts[idx]
                if artifact and artifact.get("type") == "image":
                    filename = artifact.get("filename") or artifact.get("name")
                    if filename:
                        # 優先從 downloaded_images 找
                        cached = downloaded_images.get(filename, {})
                        local_path = cached.get("local_path") or artifact.get("local_path")
                        if local_path and os.path.exists(local_path):
                            return local_path
                        # 嘗試在 images_dir 找
                        img_path = images_dir / filename
                        if img_path.exists():
                            return str(img_path)
        
        # 策略 2：同一頁的其他 artifact（掃描所有）
        for artifact in artifacts:
            if artifact and artifact.get("type") == "image" and artifact.get("page") == page_num:
                filename = artifact.get("filename") or artifact.get("name")
                if filename:
                    cached = downloaded_images.get(filename, {})
                    local_path = cached.get("local_path") or artifact.get("local_path")
                    if local_path and os.path.exists(local_path):
                        return local_path
                    img_path = images_dir / filename
                    if img_path.exists():
                        return str(img_path)
        
        return None

    @staticmethod
    async def save_all_artifacts(
        artifacts: List[Dict[str, Any]],
        images: List[Dict[str, Any]] = None,
        doc_id: str = None,
        company_id: Optional[int] = None,
        document_id: Any = None,
        data_dir: Path = None,
        raw_output_dir: str = None,
        pdf_path: str = None,
        vision_model: str = None,
        db_client: Any = None,
        vision_limit: int = 2000
    ) -> Dict[str, Any]:

        logger.info(f"🎨 Stage 2: 開始保存 Artifacts + RAG-Anything 精準上下文分析...")

        # 🌟 v3.6: PyMuPDF 已移除，表格防禦性截圖功能已停用
        # 如需此功能，請考慮使用其他 PDF 庫或重新安裝 PyMuPDF

        if raw_output_dir:
            doc_dir = Path(raw_output_dir)
        else:
            doc_dir = Path(data_dir) / "llamaparse" / str(doc_id)
            doc_dir.mkdir(parents=True, exist_ok=True)

        images_dir = doc_dir / "images"
        if not images_dir.exists():
            images_dir.mkdir(parents=True, exist_ok=True)

        stats = {"tables_saved": 0, "images_saved": 0, "charts_saved": 0, "pages_saved": 0, "vision_analyzed": 0}

        # ===== 1. 預先掃描：找出含有圖片和表格的頁碼 =====
        pages_with_images = set()
        pages_with_tables = set()
        pages_with_charts = set()  # 🆕 新增：頁面是否有圖表
        for a in artifacts:
            if a is not None:
                p_num = a.get("page", 0)
                a_type = a.get("type")
                if a_type == "image":
                    pages_with_images.add(p_num)
                elif a_type == "table":
                    pages_with_tables.add(p_num)
                elif a_type == "chart":  # 🆕 新增：處理圖表類型
                    pages_with_charts.add(p_num)
                # 🌟 Bug 修復：檢測 text artifact 中的 HTML 表格
                elif a_type == "text":
                    content = str(a.get("content", ""))
                    if "<table" in content.lower() or "</table>" in content.lower():
                        pages_with_tables.add(p_num)
                    # 🆕 新增：檢測文本中的圖表提及
                    if any(kw in content.lower() for kw in ["figure", "chart", "graph", "diagram", "圖", "圖表", "圖形"]):
                        pages_with_charts.add(p_num)

        logger.info(f"   📊 頁面分布: {len(pages_with_images)} 頁有圖片, {len(pages_with_tables)} 頁有表格, {len(pages_with_charts)} 頁有圖表")

        # ===== 2. 處理並保存所有純文字頁面 =====
        text_artifacts = [a for a in artifacts if a is not None and a.get("type") == "text"]
        for idx, artifact in enumerate(text_artifacts):
            page_num = artifact.get("page", 0)
            content = artifact.get("content", "")
            if db_client:
                try:
                    # 🌟 v4.4: 同時保存到 document_pages 和 raw_artifacts (for artifact_relations)
                    await db_client.insert_document_page(
                        document_id=document_id,
                        page_num=page_num,
                        markdown_content=content,
                        has_images=(page_num in pages_with_images),  # ✅ 動態判斷
                        has_tables=(page_num in pages_with_tables),   # ✅ Bug 修復：使用 has_tables
                        has_charts=(page_num in pages_with_charts)    # 🆕 新增：圖表判斷
                    )
                    # 🌟 v4.4: 同時保存到 raw_artifacts 表 (for artifact_relations)
                    artifact_id = f"text_chunk_{doc_id}_p{page_num}_{idx}"
                    await db_client.insert_raw_artifact(
                        artifact_id=artifact_id,
                        document_id=document_id,
                        artifact_type="text_chunk",  # 🌟 新增：保存為 text_chunk 類型
                        page_num=page_num,
                        content=content[:5000] if content else None,  # 截取前 5000 字符
                        raw_text=content
                    )
                    stats["pages_saved"] += 1
                except Exception as e:
                    logger.warning(f" ⚠️ 保存頁面 {page_num} 失敗: {e}")

        # 整理已下載的圖片以供比對
        downloaded_images = {img.get("filename") or img.get("name"): img for img in (images or [])}

        # ===== 2. 遍歷所有 Artifacts，處理 Table 與 Image =====
        for i, artifact in enumerate(artifacts):
            if artifact is None:
                continue

            art_type = artifact.get("type")
            page_num = artifact.get("page", 0)

            # 🌟 新增：判斷這個 "text" Artifact 是否暗藏了 HTML 表格
            is_html_table_in_text = False
            if art_type == "text":
                content_lower = str(artifact.get("content", "")).lower()
                if "<table" in content_lower or "</table>" in content_lower:
                    is_html_table_in_text = True

            # ---------------------------
            # 處理 Table (加入防禦性截圖修復 + HTML 表格轉換)
            # ---------------------------
            # 🌟 修正：如果類型是 table，或者文本中包含 HTML 表格，都進入處理！
            if art_type == "table" or is_html_table_in_text:
                raw_table_content = artifact.get("content", "")
                table_content_str = str(raw_table_content)
                final_content = raw_table_content

                # 🌟 新增：檢測並轉換 HTML 表格為 Markdown
                if "<table" in table_content_str.lower():
                    logger.info(f" 🔍 檢測到 HTML 表格 (Page {page_num})，轉換為 Markdown...")
                    final_content = Stage2Enrichment._html_table_to_markdown(table_content_str)
                    logger.info(f" ✅ HTML 表格轉換完成 (Page {page_num})")

                # 🌟 v4.0: 混亂表格 → 嘗試 Vision 自動修復
                messy_table_repaired = False
                if Stage2Enrichment._is_messy_table(table_content_str):
                    logger.warning(f" ⚠️ 發現混亂表格 (Page {page_num})，嘗試 Vision 自動修復...")
                    # 🌟 嘗試獲取表格圖片（如果在附近有 image artifact）
                    table_image_path = await Stage2Enrichment._find_nearby_image_for_table(
                        artifacts, i, downloaded_images, images_dir, doc_id, page_num
                    )
                    if table_image_path and os.path.exists(table_image_path):
                        try:
                            logger.info(f" 📸 找到表格截圖，開始 Vision 修復: {table_image_path}")
                            with open(table_image_path, "rb") as f:
                                image_base64 = base64.b64encode(f.read()).decode("utf-8")
                            
                            # 🌟 獲取上下文
                            precise_context = Stage2Enrichment._get_precise_context(artifacts, i)
                            
                            # 🌟 Vision 提取表格結構
                            vision_result = await Stage2Enrichment._analyze_image_with_precise_context(
                                image_base64=image_base64,
                                context_data=precise_context,
                                vision_model=vision_model or llm_core.vision_model
                            )
                            
                            # 🌟 從 Vision 結果提取 Markdown 表格
                            if vision_result.get("markdown_representation") and vision_result.get("type") in ["table", "chart"]:
                                final_content = vision_result["markdown_representation"]
                                messy_table_repaired = True
                                logger.info(f" ✅ Vision 成功修復混亂表格 (Page {page_num})")
                                logger.debug(f" 修復後內容: {final_content[:200]}...")
                            else:
                                logger.warning(f" ⚠️ Vision 無法修復表格，回退使用原始內容")
                        except Exception as e:
                            logger.warning(f" ⚠️ Vision 修復表格失敗: {e}")
                    else:
                        logger.warning(f" ⚠️ 無法找到表格截圖，混亂表格無法自動修復")
                        logger.warning(f" 建議：手動檢查 LlamaParse 解析結果")

                # 寫入最終表格結果
                if db_client:
                    try:
                        await db_client.insert_raw_artifact(
                            artifact_id=f"table_{doc_id}_p{page_num}_{i}",
                            document_id=document_id,
                            artifact_type="table",
                            page_num=page_num,
                            content_json={"original": raw_table_content, "fixed": final_content} if final_content != raw_table_content else final_content,
                            raw_text=str(final_content)
                        )
                        stats["tables_saved"] += 1
                        
                        # 🌟 同時寫入 document_tables 表（正式表格存儲）
                        if hasattr(db_client, 'insert_document_table'):
                            try:
                                await db_client.insert_document_table(
                                    document_id=document_id,
                                    page_num=page_num,
                                    table_index=i,
                                    table_json={"content": str(final_content)},  # 🌟 修正参数名
                                    table_markdown=str(final_content)  # 🌟 新增参数
                                )
                                logger.debug(f"   ✅ 表格寫入 document_tables: page {page_num}")
                            except Exception as e2:
                                logger.warning(f"   ⚠️ 寫入 document_tables 失敗: {e2}")
                                
                    except Exception as e:
                        logger.warning(f" ⚠️ 保存表格 {page_num} 失敗: {e}")

            # ---------------------------
            # 處理 Image 和 Chart (RAG-Anything 上下文對齊)
            # 🌟 v4.0: chart 類型也需要 Vision 分析
            # ---------------------------
            elif art_type in ["image", "chart"]:
                filename = artifact.get("filename") or artifact.get("name") or f"image_{page_num}_{i}.png"

                # 從 downloaded_images 找本地路徑，若無則看 artifact 本身
                cached_img = downloaded_images.get(filename, {})
                local_path = cached_img.get("local_path") or artifact.get("local_path")
                url = cached_img.get("presigned_url") or artifact.get("url") or artifact.get("presigned_url")

                # Fallback 下載
                if not local_path and url:
                    try:
                        async with httpx.AsyncClient(timeout=60) as client:
                            resp = await client.get(url)
                            if resp.status_code == 200:
                                img_path = images_dir / filename
                                with open(img_path, "wb") as f:
                                    f.write(resp.content)
                                local_path = str(img_path)
                    except Exception as e:
                        logger.warning(f" ⚠️ Fallback 下載圖片失敗: {e}")

                if local_path and os.path.exists(local_path):
                    file_size_kb = os.path.getsize(local_path) / 1024
                    
                    if file_size_kb < 15.0:
                        logger.debug(f"   ⏭️ {art_type} 太小 ({file_size_kb:.1f}KB)，疑似 Logo/裝飾，跳過 Vision 分析")
                        stats["images_saved"] += 1
                        if db_client:
                            await db_client.insert_raw_artifact(
                                artifact_id=f"{art_type}_{doc_id}_p{page_num}_{i}",
                                document_id=document_id,
                                artifact_type=art_type,
                                page_num=page_num,
                                content_json={"filename": filename, "local_path": local_path},
                                content=filename
                            )
                        continue  # 🌟 跳過 Vision，直接處理下一個 Artifact

                if local_path and stats["vision_analyzed"] < vision_limit:
                    try:
                        with open(local_path, "rb") as f:
                            image_base64 = base64.b64encode(f.read()).decode("utf-8")

                        # 🌟 獲取精準層級上下文 (RAG-Anything 核心)
                        precise_context = Stage2Enrichment._get_precise_context(artifacts, i)

                        # 🌟 v4.3: 統一 Vision 分析 - 一次調用輸出所有內容
                        # 合併原本兩次調用，節省 50% API cost
                        vision_result = await Stage2Enrichment._analyze_image_unified(
                            image_base64=image_base64,
                            context_data=precise_context,
                            vision_model=vision_model or llm_core.vision_model
                        )

                        if db_client:
                            # 🌟 v4.3: 從統一結果中提取
                            md_repr = vision_result.get("markdown_representation", "")
                            semantic_desc = vision_result.get("semantic_description", "")
                            vision_type = vision_result.get("type", art_type)
                            vision_title = vision_result.get("title", "")
                            
                            # 🌟 v4.12: 完美組合 + 元數據標籤（解決上下文丟失問題）
                            if md_repr and semantic_desc:
                                primary_content = f"""[圖表語意描述]
{semantic_desc}

[結構化數據 - 可直接查詢]
{md_repr}

[元數據]
- 原始類型: {vision_type}
- 頁碼: {page_num}
- 上下文標題: {precise_context.get('closest_heading', 'N/A')}
- 圖表標題: {vision_title}
- 檔案名: {filename}
"""
                            else:
                                primary_content = md_repr or semantic_desc or ""
                            
                            content_json = {
                                "filename": filename,
                                "local_path": local_path,
                                "url": url,
                                "analysis": vision_result,
                                "structural_context": precise_context,
                                "semantic_description": semantic_desc,
                                "markdown_representation": md_repr
                            }
                            
                            await db_client.insert_raw_artifact(
                                artifact_id=f"vision_{doc_id}_p{page_num}_{i}",
                                document_id=document_id,
                                artifact_type="vision_analysis",
                                page_num=page_num,
                                content_json=content_json,
                                content=primary_content
                            )

                        stats["vision_analyzed"] += 1
                        stats["images_saved"] += 1
                        stats["charts_saved"] = stats.get("charts_saved", 0) + (1 if art_type == "chart" else 0)

                        # 🌟 v4.3: 打印日誌
                        if semantic_desc:
                            logger.info(f"   ✅ {art_type.upper()} Vision 分析完成: {filename}")
                            logger.debug(f"      Summary: {semantic_desc[:100]}...")

                    except Exception as e:
                        logger.warning(f" ⚠️ Vision 分析失敗: {e}")
                        # 失敗也保存元數據
                        if db_client:
                            await db_client.insert_raw_artifact(
                                artifact_id=f"{art_type}_{doc_id}_p{page_num}_{i}",
                                document_id=document_id,
                                artifact_type=art_type,
                                page_num=page_num,
                                content_json={"filename": filename, "local_path": local_path},
                                content=filename
                            )
                            stats["images_saved"] += 1
                elif local_path:
                    stats["images_saved"] += 1
                    if db_client:
                        await db_client.insert_raw_artifact(
                            artifact_id=f"{art_type}_{doc_id}_p{page_num}_{i}",
                            document_id=document_id,
                            artifact_type=art_type,
                            page_num=page_num,
                            content_json={"filename": filename, "local_path": local_path},
                            content=filename
                        )

        logger.info(f"✅ Stage 2 完成: {stats['pages_saved']} 頁, {stats['tables_saved']} 表格, {stats['images_saved']} 圖片, {stats.get('charts_saved', 0)} 圖表, {stats['vision_analyzed']} Vision 分析")
        return stats

    @staticmethod
    async def _analyze_image_unified(
        image_base64: str,
        context_data: Dict[str, str],
        vision_model: str
    ) -> Dict[str, Any]:
        """
        🌟 v4.3: 統一 Vision 分析 - 一次調用輸出所有內容
        
        合併原本兩次調用：
        1. _analyze_image_with_precise_context() → 結構化 JSON
        2. _generate_chart_summary() → 語意描述
        
        現在一次過輸出：
        - type, title, markdown_representation, key_entities
        - semantic_description (語意描述，用於 Vector Search)
        """
        prompt = f"""
你是一個專業的數據分析 Agent，負責將文件中的圖片/圖表轉換為高質量的可搜索數據庫。

【結構化上下文】
- 所屬章節標題：{context_data['closest_heading']}
- 圖表標籤/圖說：{context_data['caption']}
- 圖表前的引言：{context_data['previous_text']}
- 圖表後的分析：{context_data['next_text']}

請仔細觀察圖片，輸出一個高精度的 JSON：

1. "type": chart(圖表), table(表格), diagram(架構圖), photo(照片)

2. "title": 精確標題

3. "markdown_representation": 直接可查詢的結構化格式：
   - Chart: | 類別 | 數值 |\n|---|---|\n   - Table: | 列名 | 列名 |\n|---|---|\n   - 折線圖: | 年份 | 數值 |\n|---|---|\n   - Diagram: 用條列式描述結構

4. "key_entities": 重要實體列表 (公司、地區、指標)

5. "semantic_description": 🌟 高可搜索性描述，包含：
   - 年份 + 數據類型 + 關鍵詞（讓「2023年營收」「Canada percentage」可以匹配）
   - 例如：「2023年全球營收分佈圓餅圖，Asia佔15%最高，Canada佔1%，Europe佔8%」

6. "search_keywords": 🌟 显式搜索關鍵詞陣列（確保各種查詢方式都能命中）：
   - 包括標題、年份、指標、數值、佔比、趨勢等
   - 例如：["2023", "營收", "分佈", "圓餅圖", "Canada 1%", "Asia 15%", "收入比例", "區域佔比"]

7. "qa_pairs": 🌟 預先生成常見關係性問題 Q&A（覆蓋「邊個最大」「佔幾多」「趨勢」等問題）：
   - 每個 chart 至少生成 3-5 個 Q&A
   - 格式：[{{"Q": "問題", "A": "答案"}}]
   - 例如：[{{"Q": "Canada 佔幾多百分比？", "A": "1%"}}, {{"Q": "邊個地區佔比最高？", "A": "Asia (15%)"}}]

輸出格式（純 JSON）：
{{
 "type": "chart",
 "title": "2023年各區域收入分佈",
 "markdown_representation": "| 地區 | 百分比 |\\n|---|---|\n| Asia | 15% |\\n| Canada | 1% |",
 "key_entities": ["Asia", "Canada", "Europe", "營收"],
 "semantic_description": "2023年全球營收分佈圓餅圖，Asia佔15%最高，Canada佔1%...",
 "search_keywords": ["2023", "營收", "分佈", "圓餅圖", "Canada 1%", "Asia 15%", "收入比例", "區域佔比"],
 "qa_pairs": [{{"Q": "Canada 佔幾多百分比？", "A": "1%"}}, {{"Q": "邊個地區佔比最高？", "A": "Asia (15%)"}}]
}}
""""""
        try:
            response = await llm_core.vision(
                image_base64=image_base64,
                prompt=prompt,
                model=vision_model
            )

            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                # 🌟 確保有 semantic_description
                if "semantic_description" not in result:
                    result["semantic_description"] = f"{result.get('title', '未命名圖表')}: {result.get('type', 'unknown')} 類型"
                return result

            return {"markdown_representation": response, "title": "未命名", "semantic_description": response[:200]}

        except Exception as e:
            logger.warning(f"Vision call error: {e}")
            return {"markdown_representation": "", "error": str(e), "semantic_description": ""}

    @staticmethod
    async def _analyze_image_with_precise_context(
        image_base64: str,
        context_data: Dict[str, str],
        vision_model: str
    ) -> Dict[str, Any]:
        """
        🌟 v4.3: 向後兼容包裝器 - 調用統一方法
        """
        return await Stage2Enrichment._analyze_image_unified(image_base64, context_data, vision_model)

    @staticmethod
    async def _generate_chart_summary(
        image_base64: str,
        vision_model: str
    ) -> str:
        """
        🌟 v4.3: 已廢棄 - 不再需要單獨調用
        
        語意描述已整合到 _analyze_image_unified() 的 semantic_description 字段
        """
        logger.warning("⚠️ _generate_chart_summary 已廢棄，請使用 _analyze_image_unified")
        return ""