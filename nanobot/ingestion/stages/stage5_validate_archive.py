"""
Stage 5: Vector Index + Archive (v2.0)

合并了原有的 Stage 7 (VectorIndexer), Stage 8 (Archiver)
Validator 已移除 - Agent Path B 自己验证

职责：
- 文本切块 + Embedding + 向量入库
- 标记文档完成 + 清理临时文件 + 生成处理报告

🌟 v4.20: 移除 Validator，简化 Pipeline
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger


class Stage5VectorArchive:
    """Stage 5: Vector Index + Archive (v2.0)"""
    
    def __init__(self, db_client: Any = None):
        self.db_client = db_client
        # 延迟导入以避免循环依赖
        self._vector_indexer = None
    
    @property
    def vector_indexer(self):
        if self._vector_indexer is None:
            from nanobot.ingestion.stages.stage7_vector_indexer import Stage7VectorIndexer
            self._vector_indexer = Stage7VectorIndexer(db_client=self.db_client)
        return self._vector_indexer
    
    async def run(
        self,
        extraction_result: Dict[str, Any],
        company_id: int,
        year: int,
        document_id: int,
        doc_id: str,
        stage2_result: Dict[str, Any],
        stages_result: Dict[str, Any],
        data_dir: str = None
    ) -> Dict[str, Any]:
        """
        🌟 执行合并后的 Stage 5
        
        顺序执行：
        1. Validate - 数据验证与单位换算
        2. Vector Index - 文本切块 + Embedding + 向量入库
        3. Archive - 标记完成 + 清理 + 生成报告
        
        Args:
            extraction_result: Stage 4 的提取结果
            company_id: 公司 ID
            year: 年份
            document_id: 文档内部 ID
            doc_id: 文档 ID
            stage2_result: Stage 2 的结果（用于向量索引）
            stages_result: 所有 Stage 的结果（用于生成报告）
            data_dir: 数据目录
            
        Returns:
            Dict: {
                "vector_index": {...},
                "archive": {...},
                "status": "success"
            }
        """
        logger.info(f"🎯 Stage 5: Vector Index + Archive 开始...")
        
        result = {
            "vector_index": None,
            "archive": None,
            "status": "success"
        }
        
        # ===== 1. Vector Index =====
        if document_id:
            logger.info("   📋 Step 1: 向量索引...")
            try:
                vector_result = await self.vector_indexer.run(
                    document_id=document_id,
                    stage2_result=stage2_result
                )
                result["vector_index"] = vector_result
                logger.info(f"   ✅ Vector Index 完成: {vector_result.get('total_vectors', 0)} vectors")
            except Exception as e:
                logger.warning(f"   ⚠️ Vector Index 失败: {e}")
                result["vector_index"] = {"status": "failed", "error": str(e)}
        
        # ===== 2. Archive =====
        logger.info("   📋 Step 2: 归档...")
        try:
            archive_result = await self._archive(
                doc_id=doc_id,
                document_id=document_id,
                stages_result=stages_result,
                data_dir=data_dir
            )
            result["archive"] = archive_result
            logger.info(f"   ✅ Archive 完成")
        except Exception as e:
            logger.warning(f"   ⚠️ Archive 失败: {e}")
            result["archive"] = {"status": "failed", "error": str(e)}
        
        return result
    
    async def _archive(
        self,
        doc_id: str,
        document_id: int,
        stages_result: Dict[str, Any],
        data_dir: str = None
    ) -> Dict[str, Any]:
        """
        归档：标记完成 + 清理 + 生成报告
        
        注意：移除了 save_all_pages_to_fallback（Stage 2 已保存 document_pages）
        """
        result = {
            "document_marked": None,
            "cleanup_result": None,
            "report": None,
            "status": "success"
        }
        
        # 1. 标记文档完成
        if self.db_client:
            processing_stats = {
                "stages_completed": len([
                    s for s in stages_result.values() 
                    if isinstance(s, dict) and s.get("status") == "success"
                ])
            }
            
            try:
                await self.db_client.update_document_status(
                    doc_id=doc_id,
                    status="completed",
                    stats=processing_stats or {}
                )
                result["document_marked"] = {"status": "success"}
                logger.info(f"   ✅ 文档 {doc_id} 已标记完成")
            except Exception as e:
                logger.warning(f"   ⚠️ 标记文档完成失败: {e}")
                result["document_marked"] = {"status": "failed", "error": str(e)}
        
        # 2. 清理临时文件
        cleanup_result = await self._cleanup_temp_files(doc_id=doc_id, data_dir=data_dir)
        result["cleanup_result"] = cleanup_result
        
        # 3. 生成处理报告
        report = await self._generate_processing_report(
            doc_id=doc_id,
            document_id=document_id,
            stages_result=stages_result
        )
        result["report"] = report
        
        return result
    
    async def _cleanup_temp_files(
        self,
        doc_id: str,
        data_dir: str = None,
        keep_raw_output: bool = True
    ) -> Dict[str, Any]:
        """清理临时文件"""
        result = {"files_removed": 0}
        
        if not data_dir:
            return result
        
        doc_dir = Path(data_dir) / "llamaparse" / doc_id
        
        if not doc_dir.exists():
            return result
        
        for file in doc_dir.glob("*"):
            if file.is_file():
                if keep_raw_output and file.suffix in ['.json', '.md']:
                    continue
                
                try:
                    file.unlink()
                    result["files_removed"] += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ 删除文件失败: {file} - {e}")
        
        logger.info(f"   ✅ 清理临时文件: {result['files_removed']} 个")
        
        return result
    
    async def _generate_processing_report(
        self,
        doc_id: str,
        document_id: int,
        stages_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成处理报告"""
        report = {
            "doc_id": doc_id,
            "document_id": document_id,
            "generated_at": datetime.now().isoformat(),
            "stages_summary": {},
            "overall_status": "success",
            "issues": []
        }
        
        for stage_name, stage_result in stages_result.items():
            if isinstance(stage_result, dict):
                status = stage_result.get("status", "unknown")
                
                if status == "failed":
                    report["overall_status"] = "partial_failure"
                    report["issues"].append({
                        "stage": stage_name,
                        "error": stage_result.get("error", "Unknown error")
                    })
                
                report["stages_summary"][stage_name] = {
                    "status": status,
                    "key_metrics": {
                        k: v for k, v in stage_result.items()
                        if k in ["pages_saved", "images_saved", "inserted_count", "vectors_stored", "total_vectors"]
                    }
                }
        
        # 保存报告到 DB
        if self.db_client:
            try:
                await self.db_client.insert_raw_artifact(
                    artifact_id=f"report_{doc_id}",
                    document_id=document_id,
                    doc_id=doc_id,
                    artifact_type="processing_report",
                    page_num=-1,
                    content_json=report,
                    content=json.dumps(report, indent=2)
                )
            except Exception as e:
                logger.warning(f"   ⚠️ 保存报告失败: {e}")
        
        return report