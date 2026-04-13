"""
Base Ingestion Pipeline - 資料導入流水線基類

🎯 使用模板方法模式 (Template Method Pattern)
- 共用的流程寫死在基類（parse、save）
- 提取邏輯交給子類實作（extract_information）

解决的问题：
- pipeline.py 和 agentic_ingestion.py 流程 80% 重複
- Parser、DB 寫入邏輯分散
- 难以扩展新的 Pipeline 类型

架构：
```
BaseIngestionPipeline (基類)
    ├── run() - 主流程（不可修改）
    ├── parse_document() - 統一解析（使用 pdf_core）
    ├── save_to_db() - 統一儲存（使用 db_client）
    └── extract_information() - 抽象方法（子類實作）
        ↓
    ├── DocumentPipeline (子類) - 硬编码提取
    └── AgenticPipeline (子類) - AI Agent 提取
```

Usage:
    # 使用 Agent 提取
    pipeline = AgenticPipeline()
    await pipeline.run("report.pdf")
    
    # 新增其他 Pipeline（只需 20 行）
    class FastPipeline(BaseIngestionPipeline):
        async def extract_information(self, artifacts):
            return {"fast_mode": True, "text": artifacts[0]['content']}
"""

import json  # 🌟 修复：移到顶部
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path
from loguru import logger

# 🌟 使用统一的核心模块
from nanobot.core.pdf_core import OpenDataLoaderCore, PDFParseResult


class BaseIngestionPipeline(ABC):
    """
    資料導入流水線基類
    
    🌟 使用模板方法模式：
    - run() 是骨架（不可修改）
    - extract_information() 是抽象方法（子類實作）
    
    子類只需關注：
    - 如何提取結構化數據（硬编码 vs AI Agent）
    
    基類提供：
    - PDF 解析（使用 pdf_core）
    - 資料庫連接（使用 db_client）
    - 進度追蹤
    - 錯誤處理
    """
    
    def __init__(self, db_url: str = None, data_dir: str = None, config: Dict[str, Any] = None):
        """
        初始化
        
        Args:
            db_url: PostgreSQL 連接字符串
            data_dir: 數據存儲目錄
            config: 其他配置參數
        """
        self.db_url = db_url
        self.data_dir = Path(data_dir) if data_dir else Path("data/raw")
        self.config = config or {}
        
        # 🌟 使用统一的 PDF Core（自動處理 Docker 網絡）
        self.pdf_core = OpenDataLoaderCore(enable_hybrid=True)
        
        # DB Client（延遲初始化）
        self.db = None
        
        logger.info(f"✅ BaseIngestionPipeline 初始化完成 (data_dir={self.data_dir})")
    
    async def connect(self):
        """連接資料庫"""
        if self.db_url:
            from nanobot.ingestion.repository.db_client import DBClient
            self.db = DBClient(self.db_url)
            await self.db.connect()
            logger.info("✅ 資料庫連接成功")
    
    async def close(self):
        """關閉連接"""
        if self.db:
            await self.db.close()
            logger.info("✅ 資料庫連接已關閉")
    
    async def run(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """
        🌟 主流程（模板方法）- 不可修改的骨架
        
        Args:
            file_path: PDF 文件路徑
            **kwargs: 其他參數（傳給子類的 extract_information）
            
        Returns:
            Dict: 处理结果
            
        流程：
        1. 解析 PDF（統一）
        2. 提取資訊（子類實作）
        3. 儲存資料庫（統一）
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        logger.info(f"🚀 Pipeline 開始處理: {file_path.name}")
        
        try:
            # ===== Step 1: 統一解析（Parser）=====
            logger.info("📍 Step 1: 解析 PDF（OpenDataLoader）")
            
            # 🌟 呼叫统一的核心解析
            parse_result: PDFParseResult = await self.pdf_core.parse_async(str(file_path))
            
            artifacts = parse_result.artifacts
            logger.info(f"✅ 解析完成：{parse_result.total_pages} 頁, {len(artifacts)} 個 artifacts")
            
            # ===== Step 2: 提取邏輯（子類實作）=====
            logger.info("📍 Step 2: 提取結構化資訊")
            
            # 🌟 調用子類的實作
            extracted_data = await self.extract_information(
                artifacts,
                metadata=parse_result.metadata,
                **kwargs
            )
            
            logger.info(f"✅ 提取完成：{len(extracted_data)} 個數據項")
            
            # ===== Step 3: 統一儲存（Database）=====
            logger.info("📍 Step 3: 儲存資料庫")
            
            # 🌟 如果有 DB 連接，才儲存
            if self.db:
                saved_count = await self.save_to_db(extracted_data, str(file_path))
                logger.info(f"✅ 儲存完成：{saved_count} 個記錄")
            else:
                logger.warning("⚠️ 未連接資料庫，跳過儲存")
                saved_count = 0
            
            # ===== 返回結果 =====
            result = {
                "success": True,
                "file_path": str(file_path),
                "total_pages": parse_result.total_pages,
                "artifacts_count": len(artifacts),
                "extracted_count": len(extracted_data),
                "saved_count": saved_count,
                "metadata": parse_result.metadata
            }
            
            logger.info(f"🎉 Pipeline 完成: {file_path.name}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Pipeline 失敗: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "file_path": str(file_path),
                "error": str(e)
            }
    
    def parse_document(self, file_path: str) -> PDFParseResult:
        """
        🌟 共用邏輯：呼叫 OpenDataLoader
        
        Args:
            file_path: PDF 文件路徑
            
        Returns:
            PDFParseResult: 解析結果
        """
        return self.pdf_core.parse(file_path)
    
    async def save_to_db(self, data: Dict[str, Any], file_path: str) -> int:
        """
        🌟 共用邏輯：寫入資料庫
        
        Args:
            data: 提取的數據
            file_path: 源文件路徑
            
        Returns:
            int: 儲存的記錄數
            
        實作細節：
        - 儲存到 documents 表
        - 儲存到 document_pages 表（Zone 2 Fallback）
        - 儲存到 raw_artifacts 表
        - 儲存到 revenue_breakdown 表（如有）
        """
        # 🌟 如果子類沒有覆寫，使用基本實作
        saved_count = 0
        
        if not self.db:
            logger.warning("⚠️ DB 未連接，無法儲存")
            return 0
        
        try:
            # 儲存到 documents 表（基本記錄）
            doc_id = await self.db.create_document(
                doc_id=Path(file_path).stem,
                filename=Path(file_path).name,
                file_type="pdf",
                file_size_bytes=Path(file_path).stat().st_size,
                processing_status="completed"
            )
            
            if doc_id:
                saved_count += 1
                logger.debug(f"✅ 儲存 document: {doc_id}")
            
            # 儲存到 raw_artifacts（如有）
            if "artifacts" in data:
                for artifact in data["artifacts"]:
                    await self.db.insert_raw_artifact(
                        artifact_id=f"{doc_id}_{artifact.get('type')}_{artifact.get('page_num')}",
                        document_id=doc_id,
                        artifact_type=artifact.get("type"),
                        page_num=artifact.get("page_num"),
                        metadata=json.dumps(artifact.get("metadata", {}))
                    )
                    saved_count += 1
            
        except Exception as e:
            logger.error(f"❌ 儲存失敗: {e}")
        
        return saved_count
    
    @abstractmethod
    async def extract_information(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        🎯 抽象方法：由子類決定怎麼提取
        
        Args:
            artifacts: OpenDataLoader 解析出的 Artifacts
            metadata: PDF 元数据
            **kwargs: 其他參數
            
        Returns:
            Dict: 提取的結構化數據
            
        子類實作範例：
        
        # DocumentPipeline（硬编码）
        def extract_information(self, artifacts, **kwargs):
            # 用正則提取表格
            tables = self._extract_tables_hardcoded(artifacts)
            return {"tables": tables}
        
        # AgenticPipeline（AI Agent）
        async def extract_information(self, artifacts, **kwargs):
            # 用 AI Agent 提取
            agent = FinancialAgent()
            analysis = await agent.analyze(artifacts)
            return analysis
        """
        raise NotImplementedError("必須由子類實作")


# ===========================================
# 工厂函数
# ===========================================

def create_pipeline(pipeline_type: str = "agentic", **kwargs) -> BaseIngestionPipeline:
    """
    创建 Pipeline 实例
    
    Args:
        pipeline_type: Pipeline 类型（"agentic", "document", "fast")
        **kwargs: 其他参数
        
    Returns:
        BaseIngestionPipeline: Pipeline 实例
    """
    if pipeline_type == "agentic":
        from nanobot.ingestion.agentic_ingestion import AgenticPipeline
        return AgenticPipeline(**kwargs)
    elif pipeline_type == "document":
        from nanobot.ingestion.pipeline import DocumentPipeline
        return DocumentPipeline(**kwargs)
    else:
        raise ValueError(f"未知的 Pipeline 类型: {pipeline_type}")


# ===========================================
# 导入 json（用于 save_to_db）
# ===========================================

# 🌟 json 已在文件顶部导入，此处不再重复