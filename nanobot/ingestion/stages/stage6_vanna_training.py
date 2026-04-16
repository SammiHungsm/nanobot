"""
Stage 6: Vanna 训练与后续处理 (v3.2)

职责：
- 触发 Vanna Text-to-SQL 训练
- 文档标记完成
- 清理临时文件

🌟 v3.2: 独立的 Stage 6
"""

import os
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger


class Stage6VannaTraining:
    """Stage 6: Vanna 训练与后续处理"""
    
    @staticmethod
    async def train_vanna(
        doc_id: str,
        company_id: int = None,
        year: int = None,
        db_client: Any = None,
        max_retries: int = 3,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        🌟 触发 Vanna Text-to-SQL 训练
        
        Vanna 会学习文档的 SQL 查询模式，以便后续的 Text-to-SQL 查询
        
        Args:
            doc_id: 文档 ID
            company_id: 公司 ID
            year: 年份
            db_client: DB 客户端
            max_retries: 最大重试次数
            timeout: 超时时间（秒）
            
        Returns:
            Dict: 训练结果
        """
        logger.info(f"🎯 Stage 6: Vanna 训练...")
        
        vanna_url = os.environ.get("VANNA_URL", "http://vanna-service:8000")
        vanna_model = os.environ.get("VANNA_MODEL", "financial-sql")
        
        training_result = {
            "doc_id": doc_id,
            "company_id": company_id,
            "year": year,
            "model": vanna_model,
            "status": "pending",
            "attempts": 0
        }
        
        try:
            import httpx
            
            # 🌟 训练请求
            training_payload = {
                "doc_id": doc_id,
                "company_id": company_id,
                "year": year,
                "model": vanna_model
            }
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                for attempt in range(max_retries):
                    training_result["attempts"] = attempt + 1
                    
                    try:
                        response = await client.post(
                            f"{vanna_url}/train",
                            json=training_payload
                        )
                        
                        if response.status_code == 200:
                            training_result["status"] = "success"
                            training_result["response"] = response.json()
                            logger.info(f"   ✅ Vanna 训练成功: {doc_id}")
                            break
                        else:
                            logger.warning(f"   ⚠️ Vanna 训练失败 (attempt {attempt + 1}): HTTP {response.status_code}")
                            await asyncio.sleep(2)
                            
                    except httpx.TimeoutException:
                        logger.warning(f"   ⚠️ Vanna 训练超时 (attempt {attempt + 1})")
                        await asyncio.sleep(3)
                        
                    except Exception as e:
                        logger.warning(f"   ⚠️ Vanna 训练失败 (attempt {attempt + 1}): {e}")
                        await asyncio.sleep(2)
            
            if training_result["status"] != "success":
                training_result["status"] = "failed"
                training_result["error"] = "max_retries_exceeded"
                logger.warning(f"   ❌ Vanna 训练最终失败: {doc_id}")
            
        except Exception as e:
            training_result["status"] = "failed"
            training_result["error"] = str(e)
            logger.warning(f"   ⚠️ Vanna 训练触发失败: {e}")
        
        return training_result
    
    @staticmethod
    async def mark_document_complete(
        doc_id: str,
        db_client: Any = None,
        completion_time: datetime = None
    ) -> Dict[str, Any]:
        """
        🌟 标记文档处理完成
        
        Args:
            doc_id: 文档 ID
            db_client: DB 客户端
            completion_time: 完成时间
            
        Returns:
            Dict: 更新结果
        """
        if not db_client:
            return {"status": "skipped", "reason": "no_db_client"}
        
        completion_time = completion_time or datetime.now()
        
        try:
            await db_client.update_document_status(
                doc_id=doc_id,
                status="completed",
                completed_at=completion_time.isoformat()
            )
            
            logger.info(f"   ✅ 文档标记完成: {doc_id}")
            
            return {
                "status": "success",
                "doc_id": doc_id,
                "completed_at": completion_time.isoformat()
            }
            
        except Exception as e:
            logger.warning(f"   ⚠️ 文档标记失败: {e}")
            return {"status": "failed", "error": str(e)}
    
    @staticmethod
    async def cleanup_temp_files(
        doc_id: str,
        data_dir: str = None,
        keep_raw_output: bool = True
    ) -> Dict[str, Any]:
        """
        🌟 清理临时文件
        
        Args:
            doc_id: 文档 ID
            data_dir: 数据目录
            keep_raw_output: 是否保留 raw output（默认保留）
            
        Returns:
            Dict: 清理结果
        """
        data_dir = Path(data_dir or os.environ.get("DATA_DIR", "/app/data/raw"))
        
        cleanup_result = {
            "doc_id": doc_id,
            "cleaned_files": 0,
            "kept_files": 0
        }
        
        try:
            # 🌟 临时文件目录（如果存在）
            temp_dir = data_dir / "temp" / doc_id
            
            if temp_dir.exists():
                import shutil
                
                if keep_raw_output:
                    # 保留 raw output，只删除临时文件
                    for temp_file in temp_dir.glob("*.tmp"):
                        temp_file.unlink()
                        cleanup_result["cleaned_files"] += 1
                else:
                    # 删除整个临时目录
                    shutil.rmtree(temp_dir)
                    cleanup_result["cleaned_files"] = 1
            
            # 🌟 统计保留的 raw output 文件
            raw_output_dir = data_dir / "llamaparse" / doc_id
            if raw_output_dir.exists():
                cleanup_result["kept_files"] = len(list(raw_output_dir.glob("*")))
            
            logger.info(f"   ✅ 临时文件清理完成: cleaned={cleanup_result['cleaned_files']}, kept={cleanup_result['kept_files']}")
            
        except Exception as e:
            logger.warning(f"   ⚠️ 临时文件清理失败: {e}")
            cleanup_result["error"] = str(e)
        
        return cleanup_result
    
    @staticmethod
    async def run_complete_stage(
        doc_id: str,
        company_id: int = None,
        year: int = None,
        db_client: Any = None,
        data_dir: str = None,
        progress_callback: Any = None
    ) -> Dict[str, Any]:
        """
        🌟 完整的 Stage 6 流程
        
        Args:
            doc_id: 文档 ID
            company_id: 公司 ID
            year: 年份
            db_client: DB 客户端
            data_dir: 数据目录
            progress_callback: 进度回调
            
        Returns:
            Dict: Stage 6 结果
        """
        logger.info(f"🚀 Stage 6 开始: {doc_id}")
        
        if progress_callback:
            progress_callback(95.0, "Stage 6: Vanna 训练")
        
        result = {
            "stage": "stage6",
            "doc_id": doc_id,
            "sub_stages": {}
        }
        
        # 1. Vanna 训练
        vanna_result = await Stage6VannaTraining.train_vanna(
            doc_id=doc_id,
            company_id=company_id,
            year=year,
            db_client=db_client
        )
        result["sub_stages"]["vanna_training"] = vanna_result
        
        # 2. 标记完成
        if progress_callback:
            progress_callback(98.0, "Stage 6: 标记完成")
        
        mark_result = await Stage6VannaTraining.mark_document_complete(
            doc_id=doc_id,
            db_client=db_client
        )
        result["sub_stages"]["mark_complete"] = mark_result
        
        # 3. 清理临时文件
        cleanup_result = await Stage6VannaTraining.cleanup_temp_files(
            doc_id=doc_id,
            data_dir=data_dir,
            keep_raw_output=True
        )
        result["sub_stages"]["cleanup"] = cleanup_result
        
        if progress_callback:
            progress_callback(100.0, "Stage 6 完成")
        
        logger.info(f"✅ Stage 6 完成: {doc_id}")
        
        return result