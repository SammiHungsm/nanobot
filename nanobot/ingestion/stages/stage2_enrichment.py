"""
Stage 2: 多模態富文本擴充 (v3.6 PyMuPDF Removed)

職責：
- 從 LlamaParse Cloud 下載圖片
- RAG-Anything：滑動視窗提取精準上下文 (Title, Caption, 前後文)
- Vision 分析圖片內容 + 實體關係，輸出完美 Markdown Representation
- 寫入資料庫 (raw_artifacts, document_pages)

🌟 v3.6: PyMuPDF 已移除，表格防禦性截圖功能已停用
"""

import os
import json
import base64
import httpx
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from nanobot.core.llm_core import llm_core


class Stage2Enrichment:
    """Stage 2: 多模態富文本擴充 (v3.6 PyMuPDF Removed)"""

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
        模擬 RAG-Anything 的精準上下文提取：
        尋找最接近的標題 (Title)、前文 (Intro) 與後文 (Explanation)
        """
        context = {
            "closest_heading": "無明確標題",
            "previous_text": "",
            "caption": "",
            "next_text": ""
        }

        # 1. 往前找 (尋找標題和前文)
        for i in range(target_idx - 1, -1, -1):
            artifact = artifacts[i]
            if artifact is None or artifact.get("type") != "text":
                continue

            content = str(artifact.get("content", "")).strip()
            if not content:
                continue

            # 判斷是否為標題 (Markdown 標題如 #, ##, 或全大寫短句)
            if content.startswith("#") or (len(content) < 50 and content.isupper()):
                if context["closest_heading"] == "無明確標題":
                    context["closest_heading"] = content

            # 判斷是否為圖說 (如 Figure 1:, Table 2:)
            elif "Figure" in content[:15] or "Table" in content[:15] or "圖" in content[:10]:
                if not context["caption"]:
                    context["caption"] = content

            # 一般前文 (只取最靠近的兩個段落)
            elif not context["previous_text"] and len(content) > 20:
                context["previous_text"] = content

            # 如果標題和前文都找到了，就停止往前找
            if context["closest_heading"] != "無明確標題" and context["previous_text"]:
                break

        # 2. 往後找 (尋找圖表後的解釋分析)
        for i in range(target_idx + 1, min(target_idx + 5, len(artifacts))):
            artifact = artifacts[i]
            if artifact is None or artifact.get("type") != "text":
                continue

            content = str(artifact.get("content", "")).strip()
            if content and len(content) > 20:
                context["next_text"] = content
                break  # 找到第一段有意義的後文就停止

        return context

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

        stats = {"tables_saved": 0, "images_saved": 0, "pages_saved": 0, "vision_analyzed": 0}

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
        for artifact in text_artifacts:
            page_num = artifact.get("page", 0)
            content = artifact.get("content", "")
            if db_client:
                try:
                    await db_client.insert_document_page(
                        document_id=document_id,
                        page_num=page_num,
                        markdown_content=content,
                        has_images=(page_num in pages_with_images),  # ✅ 動態判斷
                        has_tables=(page_num in pages_with_tables),   # ✅ Bug 修復：使用 has_tables
                        has_charts=(page_num in pages_with_charts)    # 🆕 新增：圖表判斷
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

                # 🌟 v3.6: 防禦性檢查（PyMuPDF 已移除）
                # 如果表格解析混亂，記錄警告，但繼續使用原始內容
                if Stage2Enrichment._is_messy_table(table_content_str):
                    logger.warning(f" ⚠️ 發現混亂表格 (Page {page_num})，PyMuPDF 已移除，無法使用 Vision 修復")
                    logger.warning(f"    建議：檢查 LlamaParse 解析結果或手動修復表格")

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
            # 處理 Image (RAG-Anything 上下文對齊)
            # ---------------------------
            elif art_type == "image":
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
                        logger.debug(f"   ⏭️ 圖片太小 ({file_size_kb:.1f}KB)，疑似 Logo/裝飾，跳過 Vision 分析")
                        stats["images_saved"] += 1
                        if db_client:
                            await db_client.insert_raw_artifact(
                                artifact_id=f"img_{doc_id}_p{page_num}_{i}",
                                document_id=document_id,
                                artifact_type="image",
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

                        vision_result = await Stage2Enrichment._analyze_image_with_precise_context(
                            image_base64=image_base64,
                            context_data=precise_context,
                            vision_model=vision_model or llm_core.vision_model
                        )

                        if db_client:
                            await db_client.insert_raw_artifact(
                                artifact_id=f"vision_{doc_id}_p{page_num}_{i}",
                                document_id=document_id,
                                artifact_type="vision_analysis",
                                page_num=page_num,
                                content_json={
                                    "filename": filename,
                                    "local_path": local_path,
                                    "url": url,
                                    "analysis": vision_result,
                                    "structural_context": precise_context
                                },
                                content=vision_result.get("markdown_representation", "")
                            )

                        stats["vision_analyzed"] += 1
                        stats["images_saved"] += 1

                    except Exception as e:
                        logger.warning(f" ⚠️ Vision 分析失敗: {e}")
                        # 失敗也保存元數據
                        if db_client:
                            await db_client.insert_raw_artifact(
                                artifact_id=f"img_{doc_id}_p{page_num}_{i}",
                                document_id=document_id,
                                artifact_type="image",
                                page_num=page_num,
                                content_json={"filename": filename, "local_path": local_path},
                                content=filename
                            )
                            stats["images_saved"] += 1
                elif local_path:
                    stats["images_saved"] += 1
                    if db_client:
                        await db_client.insert_raw_artifact(
                            artifact_id=f"img_{doc_id}_p{page_num}_{i}",
                            document_id=document_id,
                            artifact_type="image",
                            page_num=page_num,
                            content_json={"filename": filename, "local_path": local_path},
                            content=filename
                        )

        logger.info(f"✅ Stage 2 完成: {stats['pages_saved']} 頁, {stats['tables_saved']} 表格, {stats['images_saved']} 圖片, {stats['vision_analyzed']} Vision 分析")
        return stats

    @staticmethod
    async def _analyze_image_with_precise_context(
        image_base64: str,
        context_data: Dict[str, str],
        vision_model: str
    ) -> Dict[str, Any]:
        """
        🌟 RAG-Anything 高階 Vision 提取：結合層級結構化上下文
        """
        prompt = f"""
你是一個專業的數據分析 Agent，負責將文件中的圖片/圖表轉換為高質量的 RAG 向量資料庫 Raw Data。

我們擷取了該圖表在文件中的【結構化上下文 (Structural Context)】：
- 所屬章節標題：{context_data['closest_heading']}
- 圖表標籤/圖說：{context_data['caption']}
- 圖表前的引言：{context_data['previous_text']}
- 圖表後的分析：{context_data['next_text']}

請仔細觀察圖片，並結合上述邏輯上下文，過濾幻覺，輸出一個高精度的 JSON：
1. "type": 判斷這是 chart(圖表), table(表格掃描件), diagram(架構圖), 還是 photo(普通照片)。
2. "title": 綜合上下文給這張圖表一個精確的標題。
3. "markdown_representation": 🌟 最重要！
   - 如果是 Table，請轉換為標準 Markdown 表格。
   - 如果是 Chart (圓餅圖/柱狀圖)，請轉換為條列式的數據描述 (e.g., - 2023年: 45%)。
   這將直接進入向量資料庫。
4. "key_entities": 提取圖表中提及的重要實體 (如公司、地區、指標)。

輸出格式必須是純 JSON，不要包含 ```json 標籤：
{{
 "type": "chart",
 "title": "2023年各區域收入分佈",
 "markdown_representation": "- 香港：45%\\n- 歐洲：30%",
 "key_entities": ["香港", "歐洲", "收入"]
}}
"""
        try:
            response = await llm_core.vision(
                image_base64=image_base64,
                prompt=prompt,
                model=vision_model
            )

            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())

            return {"markdown_representation": response, "title": "未命名"}

        except Exception as e:
            logger.warning(f"Vision call error: {e}")
            return {"markdown_representation": "", "error": str(e)}