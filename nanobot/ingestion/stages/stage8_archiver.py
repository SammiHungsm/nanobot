"""
Stage 8: Archiver (v1.0)

职责：
- 保存所有页面到 document_pages 表（兜底）
- 清理临时文件
- 标记文档处理完成
- 生成处理报告

🌟 独立的归档阶段，确保数据完整性
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger


class Stage8Archiver:
    """Stage 8: Archiver - 归档与清理"""
    
    @staticmethod
    async def save_all_pages_to_fallback(
        artifacts: List[Dict[str, Any]],
        doc_id: str,
        document_id: int,
        db_client: Any = None
    ) -> Dict[str, Any]:
        """
        保存所有页面到 document_pages 表
        
        🌟 兜底机制：即使结构化提取失败，页面数据也能被保存
        
        Args:
            artifacts: Artifacts 列表
            doc_id: 文档 ID
            document_id: 文档内部 ID
            db_client: DB 客户端
            
        Returns:
            Dict: {"pages_saved": int, "tables_saved": int}
        """
        logger.info(f"📦 Stage 8: 保存页面到 document_pages 表...")
        
        result = {
            "pages_saved": 0,
            "tables_saved": 0,
            "status": "success"
        }
        
        if not db_client:
            logger.warning("   ⚠️ DB 客户端未初始化，跳过保存")
            result["status"] = "skipped"
            return result
        
        # 保存文本页面
        text_artifacts = [a for a in artifacts if a is not None and a.get("type") == "text"]
        
        for artifact in text_artifacts:
            page_num = artifact.get("page", 0)
            content = artifact.get("content", "") or ""
            
            if not content:
                continue
            
            try:
                # 检查是否有表格/图片/图表 🌟 恢复 has_charts 逻辑
                has_tables = any(
                    a is not None and a.get("type") == "table" and a.get("page") == page_num
                    for a in artifacts
                )
                has_images = any(
                    a is not None and a.get("type") == "image" and a.get("page") == page_num
                    for a in artifacts
                )
                has_charts = any(
                    a is not None and a.get("type") == "chart" and a.get("page") == page_num
                    for a in artifacts
                )
                
                await db_client.insert_document_page(
                    document_id=document_id,
                    page_num=page_num,  # 🌟 v1.1: 修正参数名 - page_number -> page_num
                    markdown_content=content,  # 🌟 v1.1: 修正参数名 - content -> markdown_content
                    has_images=has_images,
                    has_tables=has_tables,
                    has_charts=has_charts  # 🌟 恢复 has_charts 参数传递
                )
                result["pages_saved"] += 1
                
            except Exception as e:
                logger.warning(f"   ⚠️ 页面 {page_num} 保存失败: {e}")
        
        # 保存表格元数据
        table_artifacts = [a for a in artifacts if a is not None and a.get("type") == "table"]
        
        for artifact in table_artifacts:
            page_num = artifact.get("page", 0)
            table_content = artifact.get("content", {})
            
            # 🌟 v1.2: 同时写入 document_tables 表（结构化表格数据）
            if db_client:
                try:
                    await db_client.insert_document_table(
                        document_id=document_id,
                        page_num=page_num,
                        table_index=0,  # 简化：每页一个表格
                        table_json=table_content  # 🌟 v1.2: 使用正确的参数名
                    )
                    result["tables_saved"] += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ 表格 {page_num} 保存到 document_tables 失败: {e}")
            
            # 同时写入 raw_artifacts
            if db_client:
                try:
                    await db_client.insert_raw_artifact(
                        artifact_id=f"table_{doc_id}_p{page_num}",
                        document_id=document_id,
                        artifact_type="table",
                        page_num=page_num,
                        content_json=table_content,
                        content=str(table_content)
                    )
                except Exception as e:
                    logger.warning(f"   ⚠️ 表格 {page_num} 保存到 raw_artifacts 失败: {e}")
        
        logger.info(f"✅ Stage 8 完成: pages={result['pages_saved']}, tables={result['tables_saved']}")
        
        return result
    
    @staticmethod
    async def mark_document_complete(
        document_id: int,
        doc_id: str = None,  # 🌟 v1.1: 新增参数 - doc_id（与 DBClient 对齐）
        db_client: Any = None,
        processing_stats: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        标记文档处理完成
        
        Args:
            document_id: 文档内部 ID
            doc_id: 文档 ID（doc_id 字段）
            db_client: DB 客户端
            processing_stats: 处理统计数据
            
        Returns:
            Dict: {"status": str}
        """
        if not db_client or not doc_id:
            return {"status": "skipped"}
        
        try:
            # 🌟 v1.1: 使用 doc_id 参数（与 DBClient.update_document_status 对齐）
            await db_client.update_document_status(
                doc_id=doc_id,
                status="completed",
                stats=processing_stats or {}
            )
            
            logger.info(f"   ✅ 文档 {doc_id} 已标记完成")
            return {"status": "success"}
            
        except Exception as e:
            logger.warning(f"   ⚠️ 标记文档完成失败: {e}")
            return {"status": "failed", "error": str(e)}
    
    @staticmethod
    async def cleanup_temp_files(
        doc_id: str,
        data_dir: str = None,
        keep_raw_output: bool = True
    ) -> Dict[str, Any]:
        """
        清理临时文件
        
        Args:
            doc_id: 文档 ID
            data_dir: 数据目录
            keep_raw_output: 是否保留 raw output
            
        Returns:
            Dict: {"files_removed": int}
        """
        result = {"files_removed": 0}
        
        if not data_dir:
            return result
        
        doc_dir = Path(data_dir) / "llamaparse" / doc_id
        
        if not doc_dir.exists():
            return result
        
        # 保留 raw output，删除其他临时文件
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
    
    @staticmethod
    async def generate_processing_report(
        doc_id: str,
        stages_result: Dict[str, Any],
        db_client: Any = None
    ) -> Dict[str, Any]:
        """
        生成处理报告
        
        Args:
            doc_id: 文档 ID
            stages_result: 各 Stage 的结果
            db_client: DB 客户端
            
        Returns:
            Dict: 处理报告
        """
        report = {
            "doc_id": doc_id,
            "generated_at": datetime.now().isoformat(),
            "stages_summary": {},
            "overall_status": "success",
            "issues": []
        }
        
        # 汇总各 Stage 结果
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
                        if k in ["pages_saved", "images_saved", "inserted_count", "vectors_stored"]
                    }
                }
        
        # 保存报告到 DB
        if db_client:
            try:
                await db_client.insert_raw_artifact(
                    artifact_id=f"report_{doc_id}",  # 🌟 v1.1: 添加 artifact_id
                    document_id=stages_result.get("document_id"),  # 🌟 v1.1: 使用整数 document_id
                    artifact_type="processing_report",
                    page_num=-1,  # 🌟 v1.1: 修正参数名 - page_number -> page_num
                    content_json=report,
                    content=json.dumps(report, indent=2)  # 🌟 v1.1: 修正参数名 - raw_text -> content
                )
            except Exception as e:
                logger.warning(f"   ⚠️ 保存报告失败: {e}")
        
        return report
    
    @staticmethod
    async def run(
        artifacts: List[Dict[str, Any]],
        doc_id: str,
        document_id: int,
        stages_result: Dict[str, Any],
        db_client: Any = None,
        data_dir: str = None
    ) -> Dict[str, Any]:
        """
        🌟 执行完整归档流程
        
        Args:
            artifacts: Artifacts 列表
            doc_id: 文档 ID
            document_id: 文档内部 ID
            stages_result: 各 Stage 的结果
            db_client: DB 客户端
            data_dir: 数据目录
            
        Returns:
            Dict: {"pages_saved", "document_marked", "cleanup_result", "report"}
        """
        logger.info(f"🎯 Stage 8: Archiver 开始...")
        
        result = {
            "pages_saved": None,
            "document_marked": None,
            "cleanup_result": None,
            "report": None,
            "status": "success"
        }
        
        # 1. 保存页面到 document_pages（兜底）
        pages_result = await Stage8Archiver.save_all_pages_to_fallback(
            artifacts=artifacts,
            doc_id=doc_id,
            document_id=document_id,
            db_client=db_client
        )
        result["pages_saved"] = pages_result
        
        # 2. 标记文档完成
        processing_stats = {
            "pages_saved": pages_result.get("pages_saved", 0),
            "stages_completed": len([s for s in stages_result.values() if isinstance(s, dict) and s.get("status") == "success"])
        }
        
        mark_result = await Stage8Archiver.mark_document_complete(
            document_id=document_id,
            doc_id=doc_id,  # 🌟 v1.1: 传递 doc_id（与 DBClient 对齐）
            db_client=db_client,
            processing_stats=processing_stats
        )
        result["document_marked"] = mark_result
        
        # 3. 清理临时文件
        cleanup_result = await Stage8Archiver.cleanup_temp_files(
            doc_id=doc_id,
            data_dir=data_dir,
            keep_raw_output=True
        )
        result["cleanup_result"] = cleanup_result
        
        # 4. 生成处理报告
        report = await Stage8Archiver.generate_processing_report(
            doc_id=doc_id,
            stages_result=stages_result,
            db_client=db_client
        )
        result["report"] = report
        
        logger.info(f"✅ Stage 8 完成: pages={pages_result.get('pages_saved', 0)}, status={result['status']}")
        
        return result