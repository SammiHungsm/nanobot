"""
Vanna Service 啟動腳本

功能：
1. 初始化 Vanna AI
2. 自動訓練 Schema
3. 保持服務運行
"""

import os
import time
from pathlib import Path
from loguru import logger
import sys

# 配置日誌
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

def train_vanna_on_startup():
    """啟動時自動訓練 Vanna"""
    try:
        from nanobot.agent.tools.vanna_tool import VannaSQL
        
        logger.info("初始化 Vanna AI...")
        vanna = VannaSQL(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports"
            ),
            model_name=os.getenv("VANNA_MODEL", "financial-sql")
        )
        
        logger.info("訓練 Schema...")
        stats = vanna.train_schema(force=False)
        
        if stats.get('status') == 'trained':
            logger.info(f"✅ Vanna 訓練完成：{stats}")
        elif stats.get('status') == 'skipped':
            logger.info(f"ℹ️ 跳過訓練（已訓練過）：{stats.get('reason')}")
        else:
            logger.warning(f"⚠️ 訓練狀態未知：{stats}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Vanna 訓練失敗：{e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函數"""
    logger.info("="*60)
    logger.info("Vanna Service 啟動中...")
    logger.info("="*60)
    
    # 等待數據庫就緒
    max_retries = 30
    retry_delay = 2
    
    for i in range(max_retries):
        try:
            logger.info(f"嘗試連接數據庫 (第 {i+1}/{max_retries} 次)...")
            from nanobot.agent.tools.vanna_tool import VannaSQL
            vanna = VannaSQL()
            
            # 測試連接
            test_result = vanna.execute("SELECT 1")
            logger.info("✅ 數據庫連接成功")
            break
            
        except Exception as e:
            logger.warning(f"數據庫未就緒：{e}")
            if i < max_retries - 1:
                logger.info(f"等待 {retry_delay} 秒後重試...")
                time.sleep(retry_delay)
            else:
                logger.error("❌ 無法連接數據庫，退出")
                sys.exit(1)
    
    # 訓練 Vanna
    if train_vanna_on_startup():
        logger.info("✅ Vanna 服務準備就緒")
    else:
        logger.warning("⚠️ Vanna 訓練失敗，但服務仍會運行")
    
    # 保持容器運行
    logger.info("Vanna Service 運行中 (按 Ctrl+C 停止)...")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("收到停止信號，關閉服務")

if __name__ == "__main__":
    main()
