"""
Stage 2: 多模态富文本扩充 (v3.4 RAGAnything 上下文)

职责：
- 从 LlamaParse Cloud 下载图片（不使用 PyMuPDF）
- Vision 分析图片内容 + 实体关系
- 🌟 RAGAnything：把同一页的文字作为 Context 一起喂给 Vision LLM
- 写入数据库 (raw_artifacts, document_pages)
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
    """Stage 2: 多模态富文本扩充 (v3.4 RAGAnything 上下文)"""
    
    @staticmethod
    async def save_all_artifacts(
        artifacts: List[Dict[str, Any]],
        doc_id: str,
        company_id: Optional[int],
        document_id: Any,
        data_dir: Path,
        pdf_path: str = None,  # 不再使用，但保留参数兼容
        vision_model: str = None,
        db_client: Any = None,
        vision_limit: int = 20
    ) -> Dict[str, Any]:
        """
        保存所有 LlamaParse Artifacts
        
        🌟 v3.4 新特性：
        - 使用 LlamaParse Cloud 提供的 URL 下载图片
        - Vision 分析时带入同一页的文字作为 Context
        - RAGAnything 概念：图 + 文一起分析
        
        Args:
            artifacts: Artifacts 列表（来自 LlamaParse）
            doc_id: 文档 ID (字符串)
            company_id: 公司 ID
            document_id: 文档内部 ID
            data_dir: 数据目录
            pdf_path: 不再使用（保留兼容）
            vision_model: Vision 模型
            db_client: DB 客户端
            vision_limit: Vision 分析数量限制
            
        Returns:
            Dict: {"tables_saved": int, "images_saved": int, "pages_saved": int, "vision_analyzed": int}
        """
        logger.info(f"🎨 Stage 2: 開始保存 Artifacts + RAGAnything 上下文分析...")
        
        doc_dir = Path(data_dir) / "llamaparse" / str(doc_id)
        doc_dir.mkdir(parents=True, exist_ok=True)
        
        images_dir = doc_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        stats = {"tables_saved": 0, "images_saved": 0, "pages_saved": 0, "vision_analyzed": 0}
        
        # 1. 預先整理每頁的文本 (作為 RAGAnything 的 Context)
        page_texts = {}
        for a in artifacts:
            if a is None:
                continue
            if a.get("type") == "text":
                p = a.get("page", 0)
                content = a.get("content", "") or ""
                page_texts[p] = page_texts.get(p, "") + "\n" + content
        
        # ===== 保存文本页面 =====
        text_artifacts = [a for a in artifacts if a is not None and a.get("type") == "text"]
        
        for artifact in text_artifacts:
            page_num = artifact.get("page", 0)
            content = artifact.get("content", "")
            
            if db_client:
                try:
                    await db_client.insert_document_page(
                        document_id=doc_id,
                        page_number=page_num,
                        content=content,
                        has_tables=False,
                        has_images=False
                    )
                    stats["pages_saved"] += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ 保存页面 {page_num} 失败: {e}")
        
        # ===== 保存表格 =====
        table_artifacts = [a for a in artifacts if a is not None and a.get("type") == "table"]
        
        for artifact in table_artifacts:
            page_num = artifact.get("page", 0)
            table_content = artifact.get("content", {})
            
            if db_client:
                try:
                    await db_client.insert_raw_artifact(
                        document_id=doc_id,
                        artifact_type="table",
                        page_number=page_num,
                        content_json=table_content,
                        raw_text=str(table_content)
                    )
                    stats["tables_saved"] += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ 保存表格 {page_num} 失败: {e}")
        
        # ===== 下载并分析图片 =====
        image_artifacts = [a for a in artifacts if a is not None and a.get("type") == "image"]
        logger.info(f"   📷 找到 {len(image_artifacts)} 個圖片 Artifacts")
        
        for artifact in image_artifacts:
            page_num = artifact.get("page", 0)
            content_dict = artifact.get("content", {})
            
            if content_dict is None:
                content_dict = {}
            
            filename = content_dict.get("name") or content_dict.get("filename") or f"image_{page_num}.png"
            url = content_dict.get("url")
            local_path = None
            
            # 🌟 从 LlamaParse Cloud URL 下载图片
            if url:
                try:
                    async with httpx.AsyncClient(timeout=60) as client:
                        response = await client.get(url)
                        if response.status_code == 200:
                            img_path = images_dir / filename
                            with open(img_path, "wb") as f:
                                f.write(response.content)
                            local_path = str(img_path)
                            logger.debug(f"   ✅ 下载图片: {filename} (page {page_num})")
                        else:
                            logger.warning(f"   ⚠️ 下载失败: HTTP {response.status_code}")
                except Exception as e:
                    logger.warning(f"   ⚠️ 下载图片失败: {e}")
            
            # 🌟 核心：啟動 Agent 進行帶上下文的 Vision 分析 (RAGAnything 模式)
            if local_path and stats["vision_analyzed"] < vision_limit:
                try:
                    with open(local_path, "rb") as f:
                        image_base64 = base64.b64encode(f.read()).decode("utf-8")
                    
                    # 獲取同一頁的文字作為 Context
                    context_text = page_texts.get(page_num, "")[:2000]  # 取前2000字避免爆Token
                    
                    vision_result = await Stage2Enrichment._analyze_image_with_context(
                        image_base64=image_base64,
                        context_text=context_text,
                        vision_model=vision_model or llm_core.vision_model
                    )
                    
                    if db_client:
                        # 存入原始資料表
                        await db_client.insert_raw_artifact(
                            document_id=doc_id,
                            artifact_type="vision_analysis",
                            page_number=page_num,
                            content_json={
                                "filename": filename,
                                "local_path": local_path,
                                "url": url,
                                "analysis": vision_result
                            },
                            raw_text=vision_result.get("description", "") if vision_result else ""
                        )
                    
                    stats["vision_analyzed"] += 1
                    stats["images_saved"] += 1
                    
                except Exception as e:
                    logger.warning(f" ⚠️ Vision 分析失敗: {e}")
                    # 即使 Vision 失败，也要保存图片元数据
                    if db_client:
                        try:
                            await db_client.insert_raw_artifact(
                                document_id=doc_id,
                                artifact_type="image",
                                page_number=page_num,
                                content_json={
                                    "filename": filename,
                                    "local_path": local_path,
                                    "url": url
                                },
                                raw_text=filename
                            )
                            stats["images_saved"] += 1
                        except Exception as e2:
                            logger.warning(f" ⚠️ 保存图片元数据失败: {e2}")
            elif local_path:
                # 没有 Vision 分析，只保存图片
                stats["images_saved"] += 1
                if db_client:
                    try:
                        await db_client.insert_raw_artifact(
                            document_id=doc_id,
                            artifact_type="image",
                            page_number=page_num,
                            content_json={
                                "filename": filename,
                                "local_path": local_path,
                                "url": url
                            },
                            raw_text=filename
                        )
                    except Exception as e:
                        logger.warning(f" ⚠️ 保存图片元数据失败: {e}")
        
        logger.info(f"✅ Stage 2 完成: {stats['pages_saved']} 页, {stats['tables_saved']} 表格, {stats['images_saved']} 图片, {stats['vision_analyzed']} Vision 分析")
        return stats

    @staticmethod
    async def _analyze_image_with_context(
        image_base64: str,
        context_text: str,
        vision_model: str
    ) -> Dict[str, Any]:
        """
        🌟 Agent 核心：Vision 分析圖片 (結合周圍文本 Context)
        
        RAGAnything 概念：让 Vision LLM 知道图片与上下文的关联
        
        Args:
            image_base64: 图片 base64
            context_text: 同一页的文字上下文
            vision_model: Vision 模型
            
        Returns:
            Dict: {"type", "description", "relation_to_context", "key_metrics"}
        """
        prompt = f"""
你是一個專業的金融數據分析 Agent。
請觀察提供的圖片，並參考以下從圖片周圍擷取的【文本上下文】，進行深度解析。

【文本上下文 (Context)】:
{context_text}

請返回 JSON 格式的解析結果：
```json
{
  "type": "chart/table/photo/other",
  "description": "簡潔描述圖片的表面內容",
  "relation_to_context": "這張圖表與上下文的關聯是什麼？它在證明或補充上下文中的哪個論點？",
  "key_metrics": ["提取圖表中最重要的數據或實體"]
}
```
只返回 JSON，不要有其他文字。
"""
        
        try:
            # 🌟 修正：使用正確的方法名稱 vision，而不是 vision_chat
            # llm_core.vision() 返回 str，不需要再做 isinstance 判断
            response = await llm_core.vision(
                image_base64=image_base64,
                prompt=prompt,
                model=vision_model
            )
            
            # response 已經是 str
            content = response
            
            # 提取 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
            
            return {"description": content, "relation_to_context": "JSON parsing failed"}
            
        except Exception as e:
            logger.warning(f"Vision call error: {e}")
            return {"description": "", "error": str(e)}
    
    @staticmethod
    async def _analyze_image(
        image_base64: str,
        vision_model: str
    ) -> Dict[str, Any]:
        """
        Vision 分析图片（简化版，不带 Context）
        
        Args:
            image_base64: 图片 base64
            vision_model: Vision 模型
            
        Returns:
            Dict: {"description": str, "entities": List, "type": str}
        """
        prompt = """
分析这张图片，提取以下信息：

1. **图片类型** (type): "chart", "table", "graph", "logo", "photo", "diagram"
2. **描述** (description): 简洁描述图片内容
3. **关键实体** (entities): 如果是图表，提取关键数据点或公司名称

返回 JSON 格式：
```json
{
  "type": "chart",
  "description": "Revenue breakdown by geography",
  "entities": ["Hong Kong", "Europe", "North America"]
}
```
"""
        
        try:
            # 🌟 修正：使用正確的方法名稱 vision
            response = await llm_core.vision(
                image_base64=image_base64,
                prompt=prompt,
                model=vision_model
            )
            
            # response 已經是 str
            content = response
            
            # 提取 JSON
            import re
            json_match = re.search(r'\{[^{}]*\}', content)
            if json_match:
                return json.loads(json_match.group())
            
            return {"description": content}
            
        except Exception as e:
            logger.warning(f"   ⚠️ Vision 分析失败: {e}")
            return {}