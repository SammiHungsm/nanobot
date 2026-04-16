"""
Stage 2: 多模态富文本扩充 (v3.2)

职责：
- 保存图片到本地
- Vision 分析图片内容 + 实体关系
- 写入数据库 (raw_artifacts, document_pages)
- 🌟 v3.2: 从 LlamaParse 结果处理（移除 OpenDataLoader）
"""

import os
import json
import base64
import httpx
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from nanobot.core.llm_core import llm_core


class Stage2Enrichment:
    """Stage 2: 多模态富文本扩充"""
    
    @staticmethod
    async def save_all_artifacts(
        artifacts: List[Dict[str, Any]],
        doc_id: str,
        company_id: Optional[int],
        document_id: int,
        data_dir: Path,
        vision_model: str = None,
        db_client: Any = None,
        vision_limit: int = 20
    ) -> Dict[str, Any]:
        """
        保存所有 LlamaParse Artifacts
        
        Args:
            artifacts: Artifacts 列表（来自 LlamaParse）
            doc_id: 文档 ID (字符串)
            company_id: 公司 ID
            document_id: 文档内部 ID (整数)
            data_dir: 数据目录
            vision_model: Vision 模型
            db_client: DB 客户端
            vision_limit: Vision 分析数量限制
            
        Returns:
            Dict: {"tables_saved": int, "images_saved": int, "pages_saved": int}
        """
        logger.info(f"🎨 Stage 2: 保存 Artifacts...")
        
        doc_dir = Path(data_dir) / "llamaparse" / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        
        images_dir = doc_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        stats = {"tables_saved": 0, "images_saved": 0, "pages_saved": 0}
        
        # ===== 保存文本页面 =====
        text_artifacts = [a for a in artifacts if a.get("type") == "text"]
        
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
        table_artifacts = [a for a in artifacts if a.get("type") == "table"]
        
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
        
        # ===== 保存图片 =====
        image_artifacts = [a for a in artifacts if a.get("type") == "image"]
        
        for artifact in image_artifacts:
            page_num = artifact.get("page", 0)
            filename = artifact.get("content", {}).get("filename", f"image_{page_num}.png")
            url = artifact.get("content", {}).get("url")
            local_path = artifact.get("content", {}).get("local_path")
            
            # 🌟 如果有 URL，下载图片
            if url and not local_path:
                try:
                    async with httpx.AsyncClient(timeout=30) as client:
                        response = await client.get(url)
                        if response.status_code == 200:
                            img_path = images_dir / filename
                            with open(img_path, "wb") as f:
                                f.write(response.content)
                            local_path = str(img_path)
                            logger.debug(f"   ✅ 下载图片: {filename}")
                except Exception as e:
                    logger.warning(f"   ⚠️ 下载图片失败: {e}")
            
            if db_client:
                try:
                    await db_client.insert_raw_artifact(
                        document_id=doc_id,
                        artifact_type="image",
                        page_number=page_num,
                        content_json={
                            "filename": filename,
                            "url": url,
                            "local_path": local_path,
                            "category": artifact.get("content", {}).get("category")
                        },
                        raw_text=filename
                    )
                    stats["images_saved"] += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ 保存图片元数据失败: {e}")
        
        # ===== Vision 分析（可选）=====
        if vision_limit > 0 and image_artifacts:
            logger.info(f"   🔍 Vision 分析图片（限制: {vision_limit}）...")
            
            vision_count = 0
            for artifact in image_artifacts[:vision_limit]:
                local_path = artifact.get("content", {}).get("local_path")
                
                if local_path and Path(local_path).exists():
                    try:
                        with open(local_path, "rb") as f:
                            image_base64 = base64.b64encode(f.read()).decode("utf-8")
                        
                        vision_result = await Stage2Enrichment._analyze_image(
                            image_base64=image_base64,
                            vision_model=vision_model or llm_core.vision_model
                        )
                        
                        # 保存 Vision 分析结果
                        if vision_result and db_client:
                            await db_client.insert_raw_artifact(
                                document_id=doc_id,
                                artifact_type="vision_analysis",
                                page_number=artifact.get("page", 0),
                                content_json=vision_result,
                                raw_text=vision_result.get("description", "")
                            )
                        
                        vision_count += 1
                        
                    except Exception as e:
                        logger.warning(f"   ⚠️ Vision 分析失败: {e}")
            
            logger.info(f"   ✅ Vision 分析完成: {vision_count} 张图片")
        
        logger.info(f"✅ Stage 2 完成: {stats['pages_saved']} 页, {stats['tables_saved']} 表格, {stats['images_saved']} 图片")
        
        return stats
    
    @staticmethod
    async def _analyze_image(
        image_base64: str,
        vision_model: str
    ) -> Dict[str, Any]:
        """
        Vision 分析图片
        
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
            response = await llm_core.vision_chat(
                prompt=prompt,
                image_base64=image_base64,
                model=vision_model
            )
            
            content = response.get("content", "")
            
            # 提取 JSON
            import re
            json_match = re.search(r'\{[^{}]*\}', content)
            if json_match:
                return json.loads(json_match.group())
            
            return {"description": content}
            
        except Exception as e:
            logger.warning(f"   ⚠️ Vision 分析失败: {e}")
            return {}