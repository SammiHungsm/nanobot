"""
Stage 7: Vector Indexer (v4.3 結構化圖表索引)

职责：
- 文本切块 (Semantic Chunking)
- Embedding 生成（通过 Vanna Service API，无需本地模型）
- 向量入库 (PgVector)
- 多模态 RAG 准备（图片 + 文本）

🌟 v4.3: 配合 Stage 2 v4.1 的結構化圖表數據
- 優先讀取 markdown_representation 作為核心數據
- 添加 [結構化數據 - 可直接查詢] 段落，確保精確匹配

🌟 v4.2: 使用 Vanna Service 的 Embedding API
- 无需在 nanobot-webui 安装 sentence-transformers
- 复用 Vanna 的 embedding model，避免重复
- 通过 HTTP 调用 vanna-service:8000/api/embed
"""

import os
import json
import asyncio
import httpx
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from nanobot.core.llm_core import llm_core

# 🌟 v4.2: Vanna Service URL (Docker network)
VANNA_SERVICE_URL = os.environ.get("VANNA_SERVICE_URL", "http://vanna-service:8082")  # 🌟 使用正確端口


class Stage7VectorIndexer:
    """Stage 7: Vector Indexer"""
    
    def __init__(
        self,
        db_client: Any = None,
        embedding_model: str = "vanna-service",  # 🌟 v4.2: Use Vanna Service
        chunk_size: int = 512,
        chunk_overlap: int = 50
    ):
        """
        初始化
        
        Args:
            db_client: DB 客户端
            embedding_model: Embedding 模型 (default: vanna-service)
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
        
        🌟 v4.2: 调用 Vanna Service 的 Embedding API
        - 无需本地安装 sentence-transformers
        - 复用 Vanna 的 embedding model
        
        Args:
            text: 文本内容
            
        Returns:
            Optional[List[float]]: Embedding 向量
        """
        try:
            # 🌟 v4.2: 调用 Vanna Service API
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{VANNA_SERVICE_URL}/api/embed",
                    json={"texts": [text[:2000]]}  # 限制长度
                )
                
                if response.status_code == 200:
                    result = response.json()
                    embedding = result["embeddings"][0]
                    logger.debug(f"   ✅ Vanna Service Embedding: {len(embedding)} 维")
                    return embedding
                else:
                    logger.warning(f"   ⚠️ Vanna Service 返回错误: {response.status_code}")
                    return None
                    
        except httpx.ConnectError:
            logger.warning(f"   ⚠️ 无法连接 Vanna Service: {VANNA_SERVICE_URL}")
            return None
        except Exception as e:
            logger.warning(f"   ⚠️ Embedding 生成失败: {e}")
            return None
                    
        except httpx.ConnectError:
            logger.warning(f"   ⚠️ 无法连接 Vanna Service: {VANNA_SERVICE_URL}")
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
        logger.info(f"📊 Stage 7: 索引文档页面 (document_id={document_id})...")
        
        result = {
            "chunks_created": 0,
            "embeddings_generated": 0,
            "vectors_stored": 0
        }
        
        if not self.db:
            logger.warning("   ⚠️ DB 客户端未初始化，跳过向量入库")
            return result
        
        # 🌟 添加调试日志：检查 pages_data 是否为空
        logger.info(f"   📄 收到 {len(pages_data)} 页数据")
        
        for page in pages_data:
            page_num = page.get("page_num", 0)
            content = page.get("content", "") or page.get("markdown_content", "")
            
            # 🌟 添加调试日志：检查每页内容长度
            if content:
                logger.debug(f"   Page {page_num}: 内容长度={len(content)}")
            
            if not content or len(content) < 50:
                logger.debug(f"   ⚠️ Page {page_num}: 内容太短或为空，跳过")
                continue
            
            # 1. 切块
            chunks = self._semantic_chunking(content)
            result["chunks_created"] += len(chunks)
            
            for i, chunk in enumerate(chunks):
                chunk_text = chunk["text"]
                result["chunks_created"] += 1
                
                # 2. 生成 Embedding
                embedding = await self._generate_embedding(chunk_text)
                
                # 🌟 添加调试日志：检查 embedding 是否成功
                logger.info(f"   📍 Chunk {i}: Embedding={len(embedding) if embedding else 'None'}维")
                
                if not embedding:
                    logger.warning(f"   ⚠️ Chunk {i}: Embedding 生成失败，跳过写入")
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
                    logger.debug(f"   ✅ Chunk {i} 写入成功")
                    
                except Exception as e:
                    logger.warning(f"   ⚠️ 向量入库失败 (page {page_num}, chunk {i}): {e}")
        
        logger.info(f"✅ Stage 7 页面索引完成: chunks={result['chunks_created']}, embeddings={result['embeddings_generated']}, vectors={result['vectors_stored']}")
        
        return result
    
    async def index_vision_artifacts(
        self,
        document_id: int,
        vision_artifacts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        索引 Vision 分析结果
        
        🌟 多模態 RAG：使用 Stage 2 提煉的 RAG-Anything 精準上下文進行 Embedding
        
        Args:
            document_id: 文檔 ID
            vision_artifacts: Vision 分析結果列表
            
        Returns:
            Dict: {"vision_embeddings": int}
        """
        logger.info(f"🖼️ Stage 7: 索引 Vision Artifacts (RAG-Anything 上下文)...")
        
        result = {"vision_embeddings": 0}
        
        if not self.db:
            return result
        
        for artifact in vision_artifacts:
            # 取得 Stage 2 處理的 JSON 結果
            analysis = artifact.get("analysis", {})
            context = artifact.get("structural_context", {})  # 🌟 取得結構化上下文
            
            # 🌟 v4.1: 組合 RAG-Anything 的高質量文字塊
            # 優先使用 markdown_representation，確保結構化數據完整呈現
            md_repr = analysis.get('markdown_representation', '')
            
            vision_text = f"""
[圖表標題]: {analysis.get('title', '未命名圖表')}
[數據類型]: {analysis.get('type', 'unknown')}
[所屬章節]: {context.get('closest_heading', '無明確標題')}
[圖表標籤]: {context.get('caption', '無')}
[關聯前文]: {context.get('previous_text', '')[:100]}...
[核心數據表格]:
{md_repr or analysis.get('description', '無數據')}
[關鍵實體]: {', '.join(analysis.get('key_entities', analysis.get('key_metrics', [])))}
"""
            
            # 🌟 v4.1: 如果有明確的 markdown_representation，額外添加純數據段落
            # 這樣可以確保「Canada percentage」等精確查詢能匹配到
            if md_repr and '|' in md_repr:
                vision_text += f"""\n\n[結構化數據 - 可直接查詢]:
{md_repr}
"""
            # 清理過多的空行
            vision_text = "\n".join([line for line in vision_text.split('\n') if line.strip()])
            
            # 生成 Embedding
            embedding = await self._generate_embedding(vision_text)
            
            if embedding:
                try:
                    await self.db.insert_document_chunk(
                        document_id=document_id,
                        page_num=artifact.get("page_num", 0),
                        chunk_index=-1,  # -1 表示這是一個由 Vision 處理的多模態區塊
                        chunk_text=vision_text,
                        embedding=embedding,
                        metadata={
                            "type": "vision_analysis",
                            "filename": artifact.get("filename"),
                            "local_path": artifact.get("local_path"),
                            "is_table_fix": artifact.get("is_table_fix", False)
                        }
                    )
                    result["vision_embeddings"] += 1
                    
                except Exception as e:
                    logger.warning(f"   ⚠️ Vision 向量入庫失敗: {e}")
        
        logger.info(f"✅ Stage 7 Vision 索引完成: {result['vision_embeddings']} embeddings")
        
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
                    
                    # 🌟 v4.1: 確保傳遞所有關鍵字段（RAG-Anything 上下文 + 結構化數據）
                    analysis = content_json.get("analysis", {})
                    # 🆕 優先從頂層讀取 markdown_representation（Fix 1 後新增）
                    md_repr = content_json.get("markdown_representation") or analysis.get("markdown_representation", "")
                    
                    vision_artifacts.append({
                        "artifact_id": artifact.get("artifact_id"),
                        "page_num": artifact.get("page_num"),
                        "analysis": {
                            **analysis,
                            "markdown_representation": md_repr  # 🌟 確保有值
                        },
                        "structural_context": content_json.get("structural_context", {}),
                        "is_table_fix": content_json.get("is_table_fix", False),
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