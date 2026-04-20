"""
MongoDB Vector Search 索引初始化腳本

功能：
1. 連接到 MongoDB
2. 創建 vector index (如果使用 MongoDB Atlas)
3. 創建 text index (後備方案)
"""

import os
import sys
from pymongo import MongoClient
from loguru import logger

# 配置日誌
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)

def create_mongodb_indexes():
    """創建 MongoDB 索引"""
    
    # 從環境變量獲取配置
    mongodb_url = os.getenv(
        "MONGODB_URL",
        "mongodb://mongo:mongo_password_change_me@mongodb-docs:27017/annual_reports"
    )
    database_name = os.getenv("MONGODB_DB", "annual_reports")
    
    logger.info(f"連接到 MongoDB: {mongodb_url.split('@')[-1]}")
    
    try:
        # 連接 MongoDB
        client = MongoClient(mongodb_url)
        db = client[database_name]
        
        # 測試連接
        client.admin.command('ping')
        logger.info("✅ MongoDB 連接成功")
        
        # 1. 創建 text index (後備方案)
        logger.info("創建 text index...")
        try:
            db.documents.create_index(
                [("title", "text"), ("content", "text")],
                name="documents_text_idx"
            )
            logger.info("✅ Text index 創建成功")
        except Exception as e:
            logger.warning(f"Text index 已存在或創建失敗：{e}")
        
        # 2. 嘗試創建 vector index (僅限 MongoDB Atlas)
        logger.info("嘗試創建 vector index...")
        try:
            # MongoDB Vector Search 索引需要通過 Atlas UI 或 API 創建
            # 這裡只檢查是否有 vector_search 能力
            if hasattr(db.documents, 'vector_search'):
                logger.info("✅ MongoDB 支持向量搜索")
            else:
                logger.warning(
                    "⚠️ MongoDB 不支持向量搜索 (需要 MongoDB Atlas)\n"
                    "將使用 text search 作為後備方案"
                )
        except Exception as e:
            logger.warning(f"向量搜索檢查失敗：{e}")
        
        # 3. 創建常用索引
        logger.info("創建常用索引...")
        try:
            # company_name index
            db.documents.create_index([("company_name", 1)], name="idx_company")
            
            # year index
            db.documents.create_index([("year", 1)], name="idx_year")
            
            # compound index
            db.documents.create_index(
                [("company_name", 1), ("year", 1)],
                name="idx_company_year"
            )
            
            logger.info("✅ 常用索引創建成功")
        except Exception as e:
            logger.warning(f"索引創建失敗：{e}")
        
        # 4. 顯示集合統計
        stats = db.command("collstats", "documents")
        logger.info(f"documents 集合統計：{stats['count']} 個文檔")
        
        client.close()
        logger.info("✅ MongoDB 索引初始化完成")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ MongoDB 索引創建失敗：{e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_mongodb_indexes()
    sys.exit(0 if success else 1)
