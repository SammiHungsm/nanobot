"""
Stage 0.5: Document Registrar (v1.0)

职责：
- 计算 PDF Hash（重复检查）
- 注册 Document 到 Database
- 从封面 Metadata 创建 Company 记录
- Deduplication（防止重复处理）

🌟 将 pipeline.py 中的硬编码 DB 操作抽离出来
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger


class Stage0_5_Registrar:
    """Stage 0.5: Document Registrar"""
    
    @staticmethod
    def compute_file_hash(file_path: str, algorithm: str = "sha256") -> str:
        """
        计算文件 Hash
        
        Args:
            file_path: 文件路径
            algorithm: Hash 算法（sha256, md5）
            
        Returns:
            str: Hash 字串
        """
        hash_func = hashlib.new(algorithm)
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    @staticmethod
    async def check_duplicate(
        file_hash: str,
        db_client: Any
    ) -> Optional[Dict[str, Any]]:
        """
        检查文件是否已存在（Deduplication）
        
        Args:
            file_hash: 文件 Hash
            db_client: DB 客户端
            
        Returns:
            Optional[Dict]: 如果存在，返回已有文档信息；否则返回 None
        """
        if not db_client:
            return None
        
        try:
            existing_doc = await db_client.check_document_exists(file_hash)
            
            if existing_doc:
                logger.info(f"   ⚠️ 文件已存在: doc_id={existing_doc.get('doc_id')}")
                return existing_doc
            
            return None
            
        except Exception as e:
            logger.warning(f"   ⚠️ 检查重复失败: {e}")
            return None
    
    @staticmethod
    async def register_document(
        doc_id: str,
        file_path: str,
        file_hash: str,
        company_id: Optional[int] = None,
        db_client: Any = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        注册文档到 Database
        
        Args:
            doc_id: 文档 ID
            file_path: 文件路径
            file_hash: 文件 Hash
            company_id: 公司 ID
            db_client: DB 客户端
            metadata: 其他元数据
            
        Returns:
            Dict: 注册结果 {"document_id": int, "status": str}
        """
        if not db_client:
            logger.warning("   ⚠️ DB 客户端未初始化，跳过注册")
            return {"status": "skipped", "reason": "no_db_client"}
        
        try:
            # 获取文件大小
            file_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
            
            # 创建文档记录
            doc_result = await db_client.create_document(
                doc_id=doc_id,
                filename=Path(file_path).name,
                file_path=file_path,
                file_hash=file_hash,
                file_size_bytes=file_size,
                owner_company_id=company_id,
                processing_status="pending"
            )
            
            document_id = doc_result.get("id") if doc_result else None
            
            logger.info(f"   ✅ 文档注册成功: doc_id={doc_id}, id={document_id}")
            
            return {
                "status": "success",
                "document_id": document_id,
                "doc_id": doc_id,
                "file_hash": file_hash,
                "file_size": file_size
            }
            
        except Exception as e:
            logger.error(f"   ❌ 文档注册失败: {e}")
            return {"status": "failed", "error": str(e)}
    
    @staticmethod
    async def register_company_from_metadata(
        metadata: Dict[str, Any],
        db_client: Any = None
    ) -> Optional[int]:
        """
        从封面 Metadata 创建/更新公司记录
        
        Args:
            metadata: Stage 0 提取的封面 Metadata
            db_client: DB 客户端
            
        Returns:
            Optional[int]: 公司 ID
        """
        if not db_client:
            logger.warning("   ⚠️ DB 客户端未初始化，跳过公司注册")
            return None
        
        stock_code = metadata.get("stock_code")
        company_name = metadata.get("company_name")
        company_name_zh = metadata.get("company_name_zh")
        
        if not stock_code and not company_name:
            logger.warning("   ⚠️ 缺少 stock_code 和 company_name，无法创建公司")
            return None
        
        try:
            # 🌟 生成 stock_code（如果没有）
            if not stock_code:
                import uuid
                stock_code = f"UNKNOWN_{uuid.uuid4().hex[:6]}"
                logger.warning(f"   ⚠️ 使用临时 stock_code: {stock_code}")
            
            # Upsert 公司
            company_result = await db_client.upsert_company(
                stock_code=stock_code,
                name_en=company_name,
                name_zh=company_name_zh,
                industry=metadata.get("industry")
            )
            
            company_id = company_result.get("id") if company_result else None
            
            logger.info(f"   ✅ 公司注册成功: stock_code={stock_code}, id={company_id}")
            
            return company_id
            
        except Exception as e:
            logger.error(f"   ❌ 公司注册失败: {e}")
            return None
    
    @staticmethod
    async def run(
        pdf_path: str,
        doc_id: str,
        metadata: Dict[str, Any],
        db_client: Any = None,
        skip_duplicate: bool = True
    ) -> Dict[str, Any]:
        """
        🌟 执行 Stage 0.5
        
        完整流程：
        1. 计算 Hash
        2. 检查重复
        3. 注册文档
        4. 注册公司
        
        Args:
            pdf_path: PDF 路径
            doc_id: 文档 ID
            metadata: Stage 0 提取的 Metadata
            db_client: DB 客户端
            skip_duplicate: 是否跳过重复文件
            
        Returns:
            Dict: {"file_hash", "is_duplicate", "document_id", "company_id"}
        """
        logger.info(f"📋 Stage 0.5: Registrar 开始...")
        
        result = {
            "file_hash": None,
            "is_duplicate": False,
            "document_id": None,
            "company_id": None,
            "status": "success"
        }
        
        # Step 1: 计算 Hash
        file_hash = Stage0_5_Registrar.compute_file_hash(pdf_path)
        result["file_hash"] = file_hash
        logger.info(f"   📄 文件 Hash: {file_hash[:16]}...")
        
        # Step 2: 检查重复
        if skip_duplicate and db_client:
            existing_doc = await Stage0_5_Registrar.check_duplicate(file_hash, db_client)
            
            if existing_doc:
                result["is_duplicate"] = True
                result["document_id"] = existing_doc.get("id")
                result["status"] = "duplicate"
                logger.info(f"   ⚠️ 文件已处理过，跳过")
                return result
        
        # Step 3: 注册公司（从 Metadata）
        company_id = await Stage0_5_Registrar.register_company_from_metadata(
            metadata=metadata,
            db_client=db_client
        )
        result["company_id"] = company_id
        
        # Step 4: 注册文档
        doc_result = await Stage0_5_Registrar.register_document(
            doc_id=doc_id,
            file_path=pdf_path,
            file_hash=file_hash,
            company_id=company_id,
            db_client=db_client,
            metadata=metadata
        )
        result["document_id"] = doc_result.get("document_id")
        
        if doc_result.get("status") != "success":
            result["status"] = "failed"
            result["error"] = doc_result.get("error")
        
        logger.info(f"✅ Stage 0.5 完成: document_id={result['document_id']}, company_id={result['company_id']}")
        
        return result