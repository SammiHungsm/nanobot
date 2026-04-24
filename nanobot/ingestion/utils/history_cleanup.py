"""
Processing History Cleanup - 定時清理過期的處理歷史 (v4.16)

提供：
1. cleanup_old_history() - 清理指定天數之前的歷史記錄
2. cleanup_orphaned_records() - 清理孤兒記錄（文檔已刪除但歷史還在）
3. HistoryCleanupCron - Cron Job 包裝類

使用方式：
    # 直接調用
    await cleanup_old_history(db_client, days=30)
    
    # 作為 Cron Job
    cleanup_job = HistoryCleanupCron()
    cron.add(job=cleanup_job.to_cron_job())
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger


class HistoryCleanup:
    """
    Processing History 清理器
    
    功能：
    1. 清理指定天數之前的歷史記錄
    2. 清理孤兒記錄（文檔已刪除但歷史還在）
    3. 統計清理結果
    """
    
    def __init__(
        self,
        retention_days: int = 90,
        batch_size: int = 1000
    ):
        """
        初始化
        
        Args:
            retention_days: 保留天數（默認 90 天）
            batch_size: 每批刪除的記錄數
        """
        self.retention_days = retention_days
        self.batch_size = batch_size
    
    async def cleanup_old_history(
        self,
        db_client: Any,
        days: Optional[int] = None
    ) -> dict:
        """
        清理過期的歷史記錄
        
        Args:
            db_client: DBClient 實例
            days: 保留天數（如果為 None，使用 self.retention_days）
            
        Returns:
            dict: 清理結果統計
        """
        days = days or self.retention_days
        cutoff_date = datetime.now() - timedelta(days=days)
        
        logger.info(f"🧹 開始清理 {days} 天前的 Processing History...")
        
        try:
            async with db_client.connection() as conn:
                # 1. 先統計即將刪除的記錄數
                count_sql = """
                    SELECT COUNT(*) FROM processing_history
                    WHERE created_at < $1
                """
                total_to_delete = await conn.fetchval(count_sql, cutoff_date)
                
                if total_to_delete == 0:
                    logger.info(f"✅ 沒有需要清理的歷史記錄（{days} 天內無記錄）")
                    return {
                        "status": "success",
                        "deleted_count": 0,
                        "total_before": 0,
                        "days": days
                    }
                
                logger.info(f"   準備刪除 {total_to_delete} 條記錄...")
                
                # 2. 分批刪除
                deleted_total = 0
                batch_num = 0
                
                while True:
                    batch_num += 1
                    delete_sql = """
                        DELETE FROM processing_history
                        WHERE id IN (
                            SELECT id FROM processing_history
                            WHERE created_at < $1
                            LIMIT $2
                        )
                    """
                    
                    deleted = await conn.execute(delete_sql, cutoff_date, self.batch_size)
                    batch_deleted = int(deleted.split()[0]) if deleted else 0
                    deleted_total += batch_deleted
                    
                    if batch_deleted == 0:
                        break
                    
                    logger.debug(f"   批次 {batch_num}: 刪除 {batch_deleted} 條")
                    
                    # 小延遲避免鎖表
                    if batch_deleted == self.batch_size:
                        await asyncio.sleep(0.1)
                
                logger.info(
                    f"✅ 清理完成: 刪除 {deleted_total}/{total_to_delete} 條 "
                    f"({days} 天前的記錄)"
                )
                
                return {
                    "status": "success",
                    "deleted_count": deleted_total,
                    "total_before": total_to_delete,
                    "days": days,
                    "batches": batch_num
                }
                
        except Exception as e:
            logger.error(f"❌ 清理失敗: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "days": days
            }
    
    async def cleanup_orphaned_history(
        self,
        db_client: Any
    ) -> dict:
        """
        清理孤兒記錄
        
        刪除那些文檔記錄已不存在的歷史（外鍵約束可能不夠嚴格）
        
        Args:
            db_client: DBClient 實例
            
        Returns:
            dict: 清理結果統計
        """
        logger.info("🧹 開始清理孤兒 Processing History...")
        
        try:
            async with db_client.connection() as conn:
                # 1. 統計孤兒記錄
                count_sql = """
                    SELECT COUNT(*) FROM processing_history ph
                    LEFT JOIN documents d ON ph.document_id = d.id
                    WHERE d.id IS NULL AND ph.document_id IS NOT NULL
                """
                orphaned_count = await conn.fetchval(count_sql)
                
                if orphaned_count == 0:
                    logger.info("✅ 沒有孤兒記錄")
                    return {
                        "status": "success",
                        "deleted_count": 0,
                        "orphaned_before": 0
                    }
                
                logger.info(f"   準備刪除 {orphaned_count} 條孤兒記錄...")
                
                # 2. 刪除孤兒記錄
                delete_sql = """
                    DELETE FROM processing_history ph
                    WHERE NOT EXISTS (
                        SELECT 1 FROM documents d WHERE d.id = ph.document_id
                    )
                    AND ph.document_id IS NOT NULL
                """
                await conn.execute(delete_sql)
                
                logger.info(f"✅ 清理完成: 刪除 {orphaned_count} 條孤兒記錄")
                
                return {
                    "status": "success",
                    "deleted_count": orphaned_count,
                    "orphaned_before": orphaned_count
                }
                
        except Exception as e:
            logger.error(f"❌ 清理失敗: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def get_history_stats(
        self,
        db_client: Any
    ) -> dict:
        """
        獲取歷史記錄統計
        
        Args:
            db_client: DBClient 實例
            
        Returns:
            dict: 統計信息
        """
        try:
            async with db_client.connection() as conn:
                # 總記錄數
                total = await conn.fetchval("SELECT COUNT(*) FROM processing_history")
                
                # 按天統計
                by_day_sql = """
                    SELECT 
                        DATE(created_at) as date,
                        COUNT(*) as count
                    FROM processing_history
                    WHERE created_at > NOW() - INTERVAL '30 days'
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                    LIMIT 10
                """
                by_day = await conn.fetch(by_day_sql)
                
                # 按 stage 統計
                by_stage_sql = """
                    SELECT 
                        stage,
                        COUNT(*) as count
                    FROM processing_history
                    GROUP BY stage
                    ORDER BY count DESC
                """
                by_stage = await conn.fetch(by_stage_sql)
                
                # 計算儲存空間估算
                size_sql = """
                    SELECT pg_size_pretty(
                        pg_total_relation_size('processing_history')
                    )
                """
                size = await conn.fetchval(size_sql)
                
                return {
                    "total_records": total,
                    "size": size,
                    "by_day": [dict(row) for row in by_day],
                    "by_stage": [dict(row) for row in by_stage]
                }
                
        except Exception as e:
            logger.error(f"❌ 獲取統計失敗: {e}")
            return {"error": str(e)}
    
    async def run_cleanup(
        self,
        db_client: Any,
        cleanup_orphaned: bool = True
    ) -> dict:
        """
        運行完整清理流程
        
        Args:
            db_client: DBClient 實例
            cleanup_orphaned: 是否清理孤兒記錄
            
        Returns:
            dict: 清理結果
        """
        logger.info("🚀 開始 Processing History 完整清理...")
        
        results = {}
        
        # 1. 清理過期記錄
        old_result = await self.cleanup_old_history(db_client)
        results["old_history"] = old_result
        
        # 2. 清理孤兒記錄
        if cleanup_orphaned:
            orphan_result = await self.cleanup_orphaned_history(db_client)
            results["orphaned"] = orphan_result
        
        # 3. 最終統計
        final_stats = await self.get_history_stats(db_client)
        results["final_stats"] = final_stats
        
        total_deleted = (
            results["old_history"].get("deleted_count", 0) +
            results.get("orphaned", {}).get("deleted_count", 0)
        )
        
        logger.info(
            f"✅ 清理完成: 總共刪除 {total_deleted} 條記錄，"
            f"剩餘 {final_stats.get('total_records', 'N/A')} 條"
        )
        
        return results


# ============================================================
# Cron Job 包裝
# ============================================================

class HistoryCleanupCron:
    """
    Processing History 清理 Cron Job 包裝類
    
    使用方式：
        cleanup_job = HistoryCleanupCron(retention_days=30)
        cron.add(job=cleanup_job.to_cron_job())
    """
    
    def __init__(
        self,
        retention_days: int = 90,
        batch_size: int = 1000,
        cleanup_orphaned: bool = True,
        schedule_expr: str = "0 2 * * *"  # 每天凌晨 2 點
    ):
        """
        初始化
        
        Args:
            retention_days: 保留天數
            batch_size: 每批刪除的記錄數
            cleanup_orphaned: 是否清理孤兒記錄
            schedule_expr: Cron 表達式
        """
        self.retention_days = retention_days
        self.batch_size = batch_size
        self.cleanup_orphaned = cleanup_orphaned
        self.schedule_expr = schedule_expr
    
    def to_cron_job(self) -> dict:
        """
        轉換為 Cron Job 格式
        
        Returns:
            dict: Cron Job 配置
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        # 創建異步執行函數
        async def execute_cleanup():
            db = DBClient.get_instance()
            if not db.pool:
                await db.connect()
            
            try:
                cleaner = HistoryCleanup(
                    retention_days=self.retention_days,
                    batch_size=self.batch_size
                )
                result = await cleaner.run_cleanup(db, cleanup_orphaned=self.cleanup_orphaned)
                return result
            finally:
                # 不關閉 Singleton，讓它繼續被使用
                pass
        
        return {
            "name": "processing_history_cleanup",
            "schedule": {
                "kind": "cron",
                "expr": self.schedule_expr
            },
            "payload": {
                "kind": "agentTurn",
                "message": "執行 Processing History 清理任務"
            },
            "description": f"清理 {self.retention_days} 天前的 Processing History 記錄"
        }
