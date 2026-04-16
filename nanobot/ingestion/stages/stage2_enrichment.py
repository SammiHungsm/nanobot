"""
Stage 2: RAGAnything 多模态富文本扩充

职责：
- 保存图片 PNG 文件 (从 metadata.data base64)
- Vision 分析图片内容 + 实体关系
- 写入 entity_relations (结构化 - 给 Vanna/SQL)
- 写入 artifact_relations (图文关联)
- 🔥 生成 Enriched Markdown 存入 raw_artifacts.content (给 Agent/Vector 检索用)
"""

import os
import json
import base64
import re
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from nanobot.core.llm_core import llm_core


class Stage2Enrichment:
    """Stage 2: RAGAnything 多模态富文本扩充"""
    
    @staticmethod
    async def save_all_artifacts(
        artifacts: List[Dict[str, Any]],
        doc_id: str,
        company_id: Optional[int],
        document_id: int,
        data_dir: Path,
        vision_model: str = None,
        db_client: Any = None,
        vision_limit: int = 20  # 限制 Vision 分析数量
    ) -> Dict[str, Any]:
        """
        保存所有 OpenDataLoader Artifacts
        
        Args:
            artifacts: Artifacts 列表
            doc_id: 文档 ID (字符串)
            company_id: 公司 ID
            document_id: 文档内部 ID (整数)
            data_dir: 数据目录
            vision_model: Vision 模型
            db_client: DB 客户端
            vision_limit: Vision 分析数量限制
            
        Returns:
            Dict: {"tables_saved": int, "images_saved": int, "entities_extracted": int}
        """
        logger.info(f"🎨 Stage 2: 保存 OpenDataLoader Artifacts...")
        
        doc_dir = Path(data_dir) / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        
        stats = {"tables_saved": 0, "images_saved": 0, "entities_extracted": 0}
        
        vision_processed = 0
        
        for idx, artifact in enumerate(artifacts):
            # 🌟 FIX: Docling 用 "page number"，不是 "page_num"
            artifact_type = artifact.get("type")
            page_num = artifact.get("page_num") or artifact.get("page number")
            metadata = artifact.get("metadata", {})
            
            try:
                if artifact_type == "table":
                    # 保存表格 JSON
                    saved = await Stage2Enrichment._save_table_artifact(
                        artifact, doc_dir, doc_id, document_id, 
                        company_id, page_num, metadata, idx, db_client
                    )
                    if saved:
                        stats["tables_saved"] += 1
                
                elif artifact_type == "image":
                    # 保存图片 + Vision 分析
                    saved, entities = await Stage2Enrichment._save_image_artifact(
                        artifact, doc_dir, doc_id, document_id,
                        company_id, page_num, metadata, idx, 
                        data_dir, vision_model, db_client,
                        do_vision=(vision_processed < vision_limit)
                    )
                    if saved:
                        stats["images_saved"] += 1
                    stats["entities_extracted"] += len(entities)
                    if entities:
                        vision_processed += 1
                
            except Exception as e:
                logger.warning(f"   ⚠️ Artifact {idx} 保存失败: {e}")
                continue
        
        logger.info(f"   ✅ Stage 2 完成: {stats['tables_saved']} 表格, {stats['images_saved']} 图片, {stats['entities_extracted']} 实体")
        return stats
    
    @staticmethod
    async def _save_table_artifact(
        artifact: Dict,
        doc_dir: Path,
        doc_id: str,
        document_id: int,
        company_id: int,
        page_num: int,
        metadata: Dict,
        idx: int,
        db_client: Any
    ) -> bool:
        """保存表格 artifact"""
        
        # 保存表格 JSON 文件
        table_json_path = doc_dir / f"table_{idx:04d}.json"
        # 🌟 FIX: Docling 輸出的 artifacts 直接有表格數據，冇 content_json
        # 保存整個 artifact（除去 data 屬性，太大了）
        table_content = {k: v for k, v in artifact.items() if k != "data"}
        with open(table_json_path, 'w', encoding='utf-8') as f:
            json.dump(table_content, f, ensure_ascii=False, indent=2)
        
        # 记录到 raw_artifacts
        if db_client:
            await db_client.insert_raw_artifact(
                artifact_id=f"{doc_id}_table_{idx:04d}",
                document_id=document_id,
                company_id=company_id,
                file_type="table_json",
                file_path=str(table_json_path),
                page_num=page_num,
                metadata=json.dumps(metadata)
            )
        
        logger.debug(f"   ✅ 表格已保存: table_{idx:04d}.json")
        return True
    
    @staticmethod
    async def _save_image_artifact(
        artifact: Dict,
        doc_dir: Path,
        doc_id: str,
        document_id: int,
        company_id: int,
        page_num: int,
        metadata: Dict,
        idx: int,
        data_dir: Path,
        vision_model: str,
        db_client: Any,
        do_vision: bool = True
    ) -> tuple[bool, List[Dict]]:
        """保存图片 artifact + Vision 分析"""
        
        image_dir = doc_dir / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        
        image_filename = f"image_{idx:04d}.png"
        image_path = image_dir / image_filename
        image_saved = False
        image_data_source = None
        
        # 🌟 优先检查 metadata.data（OpenDataLoader Hybrid 模式的图片输出位置）
        metadata_dict = artifact.get("metadata", {})
        image_data_source = metadata_dict.get("data")
        
        if image_data_source and isinstance(image_data_source, str):
            image_saved = Stage2Enrichment._save_base64_image(image_data_source, image_path)
        
        # 🌟 尝试外部图片文件路径
        if not image_saved:
            image_path_source = artifact.get("image_path")
            if image_path_source and Path(image_path_source).exists():
                try:
                    shutil.copy2(image_path_source, str(image_path))
                    image_saved = True
                except Exception as e:
                    logger.warning(f"   ⚠️ 图片复制失败: {e}")
        
        # 🌟 尝试 artifact.image_data
        if not image_saved:
            image_data = artifact.get("image_data")
            if image_data:
                image_saved = Stage2Enrichment._save_base64_image(image_data, image_path)
        
        if not image_saved:
            logger.warning(f"   ⚠️ OpenDataLoader 未提供图片数据: {image_filename}")
        
        # 🌟 Vision 分析 + entity_relations
        enriched_content = ""
        entities_extracted = []
        vision_result = None
        
        if image_saved and image_data_source and do_vision:
            vision_result, entities_extracted = await Stage2Enrichment._analyze_image_with_vision(
                image_data_source, image_filename, document_id, doc_id, idx,
                vision_model or llm_core.vision_model, db_client
            )
            
            if vision_result:
                # 🔥 生成 Enriched Markdown
                enriched_content = Stage2Enrichment._generate_enriched_markdown(vision_result, entities_extracted)
        
        # 记录到 raw_artifacts
        artifact_content = enriched_content if enriched_content else artifact.get("content", "")
        
        if db_client:
            # 🌟 修复：把 content 合并到 metadata 中（insert_raw_artifact 没有 content 参数）
            full_metadata = {
                **metadata,
                "content": artifact_content,  # Enriched Markdown 存入 metadata
                "image_saved": image_saved,
                "vision_extracted": len(entities_extracted) > 0,
                "entities_count": len(entities_extracted),
                "figure_number": vision_result.get("figure_number", "") if vision_result else ""
            }
            await db_client.insert_raw_artifact(
                artifact_id=f"{doc_id}_image_{idx:04d}",
                document_id=document_id,
                company_id=company_id,
                file_type="image",
                file_path=str(image_path.relative_to(data_dir)) if image_saved else f"{doc_id}/images/{image_filename}",
                page_num=page_num,
                metadata=json.dumps(full_metadata)
            )
        
        return image_saved, entities_extracted
    
    @staticmethod
    def _save_base64_image(image_data: str, image_path: Path) -> bool:
        """从 base64 数据保存图片"""
        
        try:
            if image_data.startswith("data:image"):
                base64_data = image_data.split(",", 1)[1] if "," in image_data else image_data
            elif len(image_data) > 100:
                base64_data = image_data
            else:
                return False
            
            image_bytes = base64.b64decode(base64_data)
            with open(image_path, 'wb') as f:
                f.write(image_bytes)
            
            logger.debug(f"   ✅ 图片已保存: {image_path}")
            return True
            
        except Exception as e:
            logger.warning(f"   ⚠️ 图片保存失败: {e}")
            return False
    
    @staticmethod
    async def _analyze_image_with_vision(
        image_data: str,
        image_filename: str,
        document_id: int,
        doc_id: str,
        idx: int,
        vision_model: str,
        db_client: Any
    ) -> tuple[Optional[Dict], List[Dict]]:
        """Vision 分析图片，提取内容和实体关系"""
        
        logger.info(f"   🎨 Vision 分析图片 {image_filename}...")
        
        # 提取纯 base64
        if image_data.startswith("data:image"):
            base64_data = image_data.split(",", 1)[1] if "," in image_data else image_data
        else:
            base64_data = image_data
        
        # Vision Prompt
        vision_prompt = """
分析这张财务报表图片，提取以下信息：

1. Markdown 表格：将图片中的表格转换为 Markdown 格式
2. 实体关系：识别图中涉及的公司、人物、地点等实体及其关系

请返回严格 JSON 格式：
{"markdown_table": "...", "entities": [{"source": "...", "type": "company", "relation": "...", "target": "...", "target_type": "..."}], "context": "...", "figure_number": "..."}
只返回 JSON，不要其他文字。
"""
        
        try:
            vision_response = await llm_core.vision(base64_data, vision_prompt, model=vision_model)
            
            # 解析 JSON
            vision_result = Stage2Enrichment._parse_vision_response(vision_response)
            
            if not vision_result:
                return None, []
            
            entities = vision_result.get("entities", [])
            
            # 🌟 不在此处写入 entity_relations（FK 约束要求先插入 artifact）
            # entity_relations 将在 insert_raw_artifact 之后由调用者处理
            
            logger.info(f"   ✅ Vision 提取完成: {len(entities)} 个实体")
            return vision_result, entities
            
        except Exception as e:
            logger.warning(f"   ⚠️ Vision 分析失败: {e}")
            return None, []
    
    @staticmethod
    def _parse_vision_response(response: str) -> Optional[Dict]:
        """解析 Vision 响应"""
        
        # Markdown ```json ... ```
        md_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if md_match:
            try:
                return json.loads(md_match.group(1).strip())
            except json.JSONDecodeError:
                pass
        
        # 括号平衡
        brace_count = 0
        start_idx = None
        for i, char in enumerate(response):
            if char == '{':
                if start_idx is None:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx is not None:
                    try:
                        return json.loads(response[start_idx:i+1])
                    except json.JSONDecodeError:
                        start_idx = None
        
        return None
    
    @staticmethod
    def _generate_enriched_markdown(vision_result: Dict, entities: List[Dict]) -> str:
        """🔥 生成 Enriched Markdown"""
        
        markdown_table = vision_result.get("markdown_table", "")
        context = vision_result.get("context", "")
        
        enriched_content = markdown_table
        
        if context:
            enriched_content = f"**图表描述**: {context}\n\n" + enriched_content
        
        if entities:
            enriched_content += "\n\n**【图表关联实体 (Knowledge Graph)】**\n"
            for ent in entities:
                enriched_content += f"- {ent.get('source', '')} --[{ent.get('relation', '')}]--> {ent.get('target', '')}\n"
        
        return enriched_content