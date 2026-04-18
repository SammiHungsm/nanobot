"""
Stage 7: Vector Indexer (v4.1)

职责：
- 文本切块 (Semantic Chunking)
- Embedding 生成（本地 sentence-transformers，无需 API Key）
- 向量入库 (PgVector)
- 多模态 RAG 准备（图片 + 文本）

🌟 v4.1: 使用本地 embedding（sentence-transformers），无需 OpenAI API Key
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from nanobot.core.llm_core import llm_core

# 🌟 v4.1: 本地 Embedding 模型（懒加载）
_LOCAL_EMBEDDING_MODEL = None


def _get_local_embedding_model():
    """获取本地 embedding 模型（懒加载）"""
    global _LOCAL_EMBEDDING_MODEL
    
    if _LOCAL_EMBEDDING_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            # 使用多语言模型（支持中文）
            model_name = os.environ.get("LOCAL_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
            logger.info(f"   📦 加载本地 Embedding 模型: {model_name}")
            _LOCAL_EMBEDDING_MODEL = SentenceTransformer(model_name)
            logger.info(f"   ✅ Embedding 模型加载成功: {_LOCAL_EMBEDDING_MODEL.get_sentence_embedding_dimension()} 维")
        except Exception as e:
            logger.warning(f"   ⚠️ 加载本地 Embedding 模型失败: {e}")
            _LOCAL_EMBEDDING_MODEL = None
    
    return _LOCAL_EMBEDDING_MODEL


class Stage7VectorIndexer:
    """Stage 7: Vector Indexer"""
    
    def __init__(
        self,
        db_client: Any = None,
        embedding_model: str = "text-embedding-3-small",
        chunk_size: int = 512,
        chunk_overlap: int = 50
    ):
        """
        初始化
        
        Args:
            db_client: DB 客户端
            embedding_model: Embedding 模型
            chunk_size: 切块大小（tokens）
            chunk_overlap: 切块重叠
        """
        self.db = db_client
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def _semantic_chunking(
        self,
        text: str,
        min_chunk_size: int = 200
    ) -> List[Dict[str, Any]]:
        """
        语义切块
        
        🌟 简化版：按段落 + 句子边界切块
        未来可以用更智能的方法（如语义边界检测）
        
        Args:
            text: 文本内容
            min_chunk_size: 最小切块大小
            
        Returns:
            List[Dict]: 切块列表 [{"text": str, "start": int, "end": int}]
        """
        chunks = []
        
        # 按段落分割
        paragraphs = text.split("\n\n")
        
        current_chunk = ""
        chunk_start = 0
        
        for para in paragraphs:
            if not para.strip():
                continue
            
            # 如果当前块 + 新段落 > chunk_size，保存当前块
            if len(current_chunk) + len(para) > self.chunk_size and len(current_chunk) >= min_chunk_size:
                chunks.append({
                    "text": current_chunk.strip(),
                    "char_count": len(current_chunk.strip()),
                    "paragraph_count": current_chunk.count("\n\n") + 1
                })
                current_chunk = para
            else:
                # 继续累积
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
        
        # 最后一块
        if current_chunk.strip():
            chunks.append({
                "text": current_chunk.strip(),
                "char_count": len(current_chunk.strip()),
                "paragraph_count": current_chunk.count("\n\n") + 1
            })
        
        logger.debug(f"   📊 切块完成: {len(chunks)} 块, 平均长度={sum(c['char_count'] for c in chunks) / len(chunks):.0f}")
        
        return chunks
    
    async def _generate_embedding(
        self,
        text: str
    ) -> Optional[List[float]]:
        """
        生成 Embedding
        
        🌟 v4.1: 优先使用本地 sentence-transformers，无需 API Key
        
        Args:
            text: 文本内容
            
        Returns:
            Optional[List[float]]: Embedding 向量
        """
        try:
            # 🌟 v4.1: 优先使用本地 embedding
            local_model = _get_local_embedding_model()
            
            if local_model:
                # 本地模型生成 embedding
                embedding = local_model.encode(text[:2000], convert_to_numpy=True)  # 限制长度
                logger.debug(f"   ✅ 本地 Embedding 生成成功: {len(embedding)} 维")
                return embedding.tolist()
            
            # 🌟 Fallback: 如果本地模型不可用，尝试 API
            api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMBEDDING_API_KEY")
            api_base = os.environ.get("EMBEDDING_API_BASE", "https://api.openai.com/v1")
            
            if not api_key:
                logger.warning("   ⚠️ 本地模型和 API Key 都不可用，跳过 embedding")
                return None
            
            import httpx
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{api_base}/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": self.embedding_model,
                        "input": text[:8000]
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    embedding = data["data"][0]["embedding"]
                    logger.debug(f"   ✅ API Embedding 生成成功: {len(embedding)} 维")
                    return embedding
                else:
                    logger.warning(f"   ⚠️ Embedding API 失败: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.warning(f"   ⚠️ Embedding 生成失败: {e}")
            return None
    
    async def index_document_pages(
        self,
        document_id: int,
        pages_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        索引文档页面
        
        Args:
            document_id: 文档 ID
            pages_data: 页面数据列表
            
        Returns:
            Dict: {"chunks_created", "embeddings_generated", "vectors_stored"}
        """
        logger.info(f"📊 Stage 8: 索引文档页面 (document_id={document_id})...")
        
        result = {
            "chunks_created": 0,
            "embeddings_generated": 0,
            "vectors_stored": 0
        }
        
        if not self.db:
            logger.warning("   ⚠️ DB 客户端未初始化，跳过向量入库")
            return result
        
        for page in pages_data:
            page_num = page.get("page_num", 0)
            content = page.get("content", "") or page.get("markdown_content", "")
            
            if not content or len(content) < 50:
                continue
            
            # 1. 切块
            chunks = self._semantic_chunking(content)
            result["chunks_created"] += len(chunks)
            
            for i, chunk in enumerate(chunks):
                chunk_text = chunk["text"]
                
                # 2. 生成 Embedding
                embedding = await self._generate_embedding(chunk_text)
                
                if not embedding:
                    continue
                
                result["embeddings_generated"] += 1
                
                # 3. 写入向量库（假设使用 PgVector）
                try:
                    await self.db.insert_document_chunk(
                        document_id=document_id,
                        page_num=page_num,
                        chunk_index=i,
                        chunk_text=chunk_text,
                        embedding=embedding,
                        metadata={
                            "char_count": chunk["char_count"],
                            "paragraph_count": chunk["paragraph_count"]
                        }
                    )
                    result["vectors_stored"] += 1
                    
                except Exception as e:
                    logger.warning(f"   ⚠️ 向量入库失败 (page {page_num}, chunk {i}): {e}")
        
        logger.info(f"✅ Stage 8 页面索引完成: chunks={result['chunks_created']}, embeddings={result['embeddings_generated']}")
        
        return result
    
    async def index_vision_artifacts(
        self,
        document_id: int,
        vision_artifacts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        索引 Vision 分析结果
        
        🌟 多模态 RAG：图片 + 文本一起索引
        
        Args:
            document_id: 文档 ID
            vision_artifacts: Vision 分析结果列表
            
        Returns:
            Dict: {"vision_embeddings": int}
        """
        logger.info(f"🖼️ Stage 8: 索引 Vision Artifacts...")
        
        result = {"vision_embeddings": 0}
        
        if not self.db:
            return result
        
        for artifact in vision_artifacts:
            analysis = artifact.get("analysis", {})
            
            # 🌟 组合图片描述 + 上下文关系
            vision_text = f"""
图片类型: {analysis.get('type', 'unknown')}
描述: {analysis.get('description', '')}
与上下文的关系: {analysis.get('relation_to_context', '')}
关键指标: {', '.join(analysis.get('key_metrics', []))}
"""
            
            # 生成 Embedding
            embedding = await self._generate_embedding(vision_text)
            
            if embedding:
                try:
                    await self.db.insert_document_chunk(
                        document_id=document_id,
                        page_num=artifact.get("page_num", 0),
                        chunk_index=-1,  # -1 表示图片类型
                        chunk_text=vision_text,
                        embedding=embedding,
                        metadata={
                            "type": "vision_analysis",
                            "filename": artifact.get("filename"),
                            "local_path": artifact.get("local_path")
                        }
                    )
                    result["vision_embeddings"] += 1
                    
                except Exception as e:
                    logger.warning(f"   ⚠️ Vision 向量入库失败: {e}")
        
        logger.info(f"✅ Stage 8 Vision 索引完成: {result['vision_embeddings']} embeddings")
        
        return result
    
    async def run(
        self,
        document_id: int,
        stage2_result: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        🌟 执行完整向量索引
        
        Args:
            document_id: 文档 ID
            stage2_result: Stage 2 的结果（包含页面数据和 Vision 分析）
            
        Returns:
            Dict: {"pages_indexed", "vision_indexed", "total_vectors"}
        """
        logger.info(f"🎯 Stage 8: Vector Indexer 开始...")
        
        result = {
            "pages_indexed": None,
            "vision_indexed": None,
            "total_vectors": 0,
            "status": "success"
        }
        
        if not self.db:
            result["status"] = "skipped"
            result["reason"] = "no_db_client"
            logger.warning("⚠️ DB 客户端未初始化，跳过 Stage 8")
            return result
        
        # 1. 获取页面数据
        try:
            pages_data = await self.db.get_document_pages(document_id)
            
            if pages_data:
                pages_result = await self.index_document_pages(
                    document_id=document_id,
                    pages_data=pages_data
                )
                result["pages_indexed"] = pages_result
                result["total_vectors"] += pages_result.get("vectors_stored", 0)
                
        except Exception as e:
            logger.warning(f"   ⚠️ 页面索引失败: {e}")
        
        # 2. 索引 Vision 分析结果
        if stage2_result:
            vision_artifacts = []
            
            # 从 raw_artifacts 提取 vision_analysis 类型
            try:
                artifacts = await self.db.fetch_all(
                    """
                    SELECT artifact_id, content, page_num, metadata
                    FROM raw_artifacts
                    WHERE document_id = $1 AND artifact_type = 'vision_analysis'
                    """,
                    document_id
                )
                
                for artifact in artifacts:
                    content_json = artifact.get("content", {})
                    if isinstance(content_json, str):
                        try:
                            content_json = json.loads(content_json)
                        except:
                            content_json = {}
                    
                    vision_artifacts.append({
                        "artifact_id": artifact.get("artifact_id"),
                        "page_num": artifact.get("page_num"),
                        "analysis": content_json.get("analysis", {}),
                        "filename": content_json.get("filename"),
                        "local_path": content_json.get("local_path")
                    })
                
                if vision_artifacts:
                    vision_result = await self.index_vision_artifacts(
                        document_id=document_id,
                        vision_artifacts=vision_artifacts
                    )
                    result["vision_indexed"] = vision_result
                    result["total_vectors"] += vision_result.get("vision_embeddings", 0)
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Vision 索引失败: {e}")
        
        logger.info(f"✅ Stage 8 完成: total_vectors={result['total_vectors']}")
        
        return result