"""
Stage 0: Preprocessor + Registrar Combined (v1.0)

合并了原有的 Stage 0 (Vision) + Stage 0.5 (Registrar)

职责：
- Vision 分析 Page 1，提取公司元数据
- 计算 PDF Hash（重复检查）
- 注册 Document 到 Database
- 从封面 Metadata 创建 Company 记录

🌟 单一入口：run() 方法完成所有初始化工作
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from nanobot.core.llm_core import llm_core


class Stage0Preprocessor:
    """Stage 0: 预处理 + 注册（合并版）"""
    
    # ===========================================
    # 🌟 静态方法：Vision 提取（原有逻辑）
    # ===========================================
    
    @staticmethod
    async def extract_company_from_page1(
        artifacts: list,
        page_num: int = 1,
        doc_id: str = None,
        vision_model: str = None,
        is_index_report: bool = False,
        confirmed_doc_industry: str = None,
        images: list = None,
        raw_output_dir: str = None,
        pdf_filename: str = None
    ) -> Dict[str, Any]:
        """
        🌟 从 LlamaParse artifacts 提取 Page 1 公司信息
        
        Args:
            artifacts: LlamaParse 解析的 artifacts 列表
            page_num: 頁碼
            doc_id: 文檔 ID
            vision_model: Vision 模型名稱
            is_index_report: 是否為指數報告
            confirmed_doc_industry: 確認的文檔行業
            images: 從 parse_result.images 傳入的圖片列表
            raw_output_dir: 圖片下載目錄
            
        Returns:
            Dict: {"stock_code", "year", "name_en", "name_zh"}
        """
        logger.info(f"📋 Stage 0: Vision 分析 Page {page_num}...")
        
        if not artifacts:
            logger.warning("   ⚠️ 沒有 artifacts，無法分析")
            return {"stock_code": None, "year": 2025}
        
        # Step 1: 找到 Page 1 的 Markdown
        page1_artifacts = [
            a for a in artifacts 
            if isinstance(a, dict) and a.get("page") == page_num
        ]
        
        if not page1_artifacts:
            page1_artifacts = [
                a for a in artifacts 
                if isinstance(a, dict) and a.get("page_number") == page_num
            ]
        
        if not page1_artifacts and artifacts:
            # 找第一頁
            page1_artifacts = [a for a in artifacts if isinstance(a, dict)]
        
        if not page1_artifacts:
            return {"stock_code": None, "year": 2025}
        
        # Step 2: 收集 Page 1 的文本内容
        page1_text = ""
        for artifact in page1_artifacts:
            content = artifact.get("content", "")
            if content and isinstance(content, str):
                page1_text += content + "\n\n"
        
        # Step 3: 找到 Page 1 的图片
        page1_images = []
        if images:
            for img in images:
                if isinstance(img, dict):
                    img_page = img.get("page") or img.get("page_num")
                    if img_page == page_num or img_page == 1:
                        page1_images.append(img)
        
        # Step 4: Vision 分析（如果找到图片）
        vision_result = {"stock_code": None, "year": 2025}
        
        if page1_images:
            try:
                first_image = page1_images[0]
                image_path = first_image.get("path") or first_image.get("local_path") or first_image.get("url")
                
                if image_path and Path(image_path).exists():
                    logger.info(f"   🖼️ 分析 Page 1 图片: {image_path}")
                    
                    prompt = Stage0Preprocessor._build_vision_prompt(is_index_report, confirmed_doc_industry)
                    
                    result = await llm_core.vision(
                        image_path=image_path,
                        prompt=prompt,
                        model=vision_model
                    )
                    
                    vision_result = Stage0Preprocessor._parse_vision_result(result)
                    logger.info(f"   ✅ Vision 结果: stock_code={vision_result.get('stock_code')}, year={vision_result.get('year')}")
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Vision 分析失败: {e}")
        
        # Step 5: 文本提取 fallback（如果没有图片或 Vision 失败）
        if not vision_result.get("stock_code") and page1_text:
            text_result = Stage0Preprocessor._extract_from_text(page1_text)
            if text_result.get("stock_code"):
                vision_result.update(text_result)
                logger.info(f"   ✅ 文本提取结果: stock_code={vision_result.get('stock_code')}")
        
        # Step 6: 确保有默认值
        vision_result.setdefault("year", 2025)
        
        return vision_result
    
    @staticmethod
    def _build_vision_prompt(is_index_report: bool, confirmed_doc_industry: str) -> str:
        """构建 Vision prompt"""
        industry_hint = f"Document industry: {confirmed_doc_industry}" if confirmed_doc_industry else ""
        
        if is_index_report:
            return f"""Analyze this index report cover page. Extract:
1. Index name (e.g., "Hang Seng Index", "CSI 300")
2. Report year/date
3. Publisher

Return JSON: {{"stock_code": null, "year": 2025, "name_en": "<index_name>", "name_zh": "<index_name_cn>"}}
{industry_hint}"""
        else:
            return f"""Analyze this annual report cover page. Extract:
1. Stock code (6-digit, e.g., "00001")
2. Company name in English
3. Company name in Chinese
4. Report year (4-digit)

Return JSON: {{"stock_code": "00001", "year": 2023, "name_en": "...", "name_zh": "..."}}
{industry_hint}"""
    
    @staticmethod
    def _parse_vision_result(result: str) -> Dict[str, Any]:
        """解析 Vision 结果"""
        import json
        import re
        
        # 尝试 JSON 解析
        json_match = re.search(r'\{[^{}]*\}', result, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return {
                    "stock_code": data.get("stock_code"),
                    "year": int(data.get("year", 2025)),
                    "name_en": data.get("name_en"),
                    "name_zh": data.get("name_zh"),
                    "industry": data.get("industry")
                }
            except:
                pass
        
        # 备用解析
        stock_match = re.search(r'stock_code["\s:]+([0-9A-Za-z]+)', result, re.IGNORECASE)
        year_match = re.search(r'year["\s:]+(20\d{2})', result)
        
        return {
            "stock_code": stock_match.group(1) if stock_match else None,
            "year": int(year_match.group(1)) if year_match else 2025
        }
    
    @staticmethod
    def _extract_from_text(text: str) -> Dict[str, Any]:
        """从文本中提取公司信息"""
        import re
        
        result = {"stock_code": None, "year": None, "name_en": None, "name_zh": None}
        
        # 股票代码
        code_patterns = [
            r'stock\s*code[:\s]+([0-9]{4,6})',
            r'股份[代号碼][:：\s]+([0-9]{4,6})',
            r'Stock\s*Code[:\s]+([0-9]{4,6})',
        ]
        for pattern in code_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["stock_code"] = match.group(1)
                break
        
        # 年份
        year_patterns = [
            r'(20\d{2})\s*年',
            r'Annual\s*Report\s*(20\d{2})',
            r'(20\d{2})\s*年度',
        ]
        for pattern in year_patterns:
            match = re.search(pattern, text)
            if match:
                result["year"] = int(match.group(1))
                break
        
        return result
    
    # ===========================================
    # 🌟 静态方法：Registrar（原有逻辑）
    # ===========================================
    
    @staticmethod
    def compute_file_hash(file_path: str, algorithm: str = "sha256") -> str:
        """计算文件 Hash"""
        hash_func = hashlib.new(algorithm)
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    @staticmethod
    async def check_duplicate(file_hash: str, db_client: Any) -> Optional[Dict[str, Any]]:
        """检查文件是否已存在"""
        if not db_client:
            return None
        
        try:
            existing_doc = await db_client.check_document_exists(doc_id="", file_hash=file_hash)
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
        original_filename: str = None,
        db_client: Any = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """注册文档到 Database"""
        if not db_client:
            logger.warning("   ⚠️ DB 客户端未初始化，跳过注册")
            return {"status": "skipped", "reason": "no_db_client"}
        
        try:
            file_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
            filename_to_save = original_filename or Path(file_path).name
            
            year = metadata.get("year") if metadata else None
            if year is not None:
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    year = None
            
            doc_result = await db_client.create_document(
                doc_id=doc_id,
                filename=filename_to_save,
                file_path=file_path,
                file_hash=file_hash,
                file_size=file_size,
                company_id=company_id,
                document_type=(metadata or {}).get("doc_type", "annual_report"),
                year=year
            )
            
            document_id = await db_client.get_document_internal_id(doc_id) if doc_result else None
            
            # 更新 owner_company_id
            if company_id:
                try:
                    await db_client.update_document_company_id(
                        doc_id=doc_id,
                        company_id=company_id,
                        year=year
                    )
                    logger.info(f"   ✅ owner_company_id 已更新: doc_id={doc_id}, company_id={company_id}")
                except Exception as e:
                    logger.warning(f"   ⚠️ update_document_company_id 失败: {e}")
                
                # 写入 document_companies
                try:
                    if not document_id:
                        document_id = await db_client.get_document_internal_id(doc_id)
                    
                    if document_id:
                        await db_client.add_mentioned_company(
                            document_id=document_id,
                            company_id=company_id,
                            relation_type="primary",
                            extracted_industries=[metadata.get("industry")] if metadata and metadata.get("industry") else [],
                            extraction_source="vision_cover"
                        )
                        logger.info(f"   ✅ 文档-公司关联已建立: doc={document_id}, company={company_id}")
                except Exception as e:
                    logger.warning(f"   ⚠️ 文档-公司关联失败: {e}")
            
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
        """从封面 Metadata 创建/更新公司记录"""
        if not db_client:
            logger.warning("   ⚠️ DB 客户端未初始化，跳过公司注册")
            return None
        
        stock_code = metadata.get("stock_code")
        name_en = metadata.get("name_en") or metadata.get("company_name")
        name_zh = metadata.get("name_zh") or metadata.get("company_name_zh")
        
        logger.info(f"   📋 register_company_from_metadata: stock_code={stock_code}, name_en={name_en}")
        
        if not stock_code and not name_en:
            logger.warning("   ⚠️ 缺少 stock_code 和 name_en，无法创建公司")
            return None
        
        try:
            if not stock_code:
                import uuid
                stock_code = f"UNKNOWN_{uuid.uuid4().hex[:6]}"
                logger.warning(f"   ⚠️ 使用临时 stock_code: {stock_code}")
            
            company_result = await db_client.upsert_company(
                stock_code=stock_code,
                name_en=name_en,
                name_zh=name_zh,
                industry=metadata.get("industry")
            )
            
            company_id = company_result if company_result else None
            logger.info(f"   ✅ 公司注冊成功: stock_code={stock_code}, id={company_id}")
            
            return company_id
            
        except Exception as e:
            logger.error(f"   ❌ 公司注冊失敗: {e}")
            return None
    
    # ===========================================
    # 🌟 合并后的 run() 方法
    # ===========================================
    
    @staticmethod
    async def run(
        artifacts: list,
        pdf_path: str,
        doc_id: str,
        original_filename: str = None,
        db_client: Any = None,
        skip_duplicate: bool = True,
        is_index_report: bool = False,
        confirmed_doc_industry: str = None,
        images: list = None,
        raw_output_dir: str = None,
        pdf_filename: str = None
    ) -> Dict[str, Any]:
        """
        🌟 合并后的 Stage 0 执行流程
        
        步骤：
        1. Vision 提取 Page 1 公司信息
        2. 计算 Hash
        3. 检查重复
        4. 注册公司
        5. 注册文档
        
        Args:
            artifacts: LlamaParse artifacts
            pdf_path: PDF 文件路径
            doc_id: 文档 ID
            original_filename: 原始文件名
            db_client: DB 客户端
            skip_duplicate: 是否跳过重复文件
            is_index_report: 是否为指数报告
            confirmed_doc_industry: 确认的行业
            images: 图片列表
            raw_output_dir: 图片目录
            pdf_filename: PDF 文件名
            
        Returns:
            Dict: {
                "stage0_vision": {...},
                "file_hash": str,
                "is_duplicate": bool,
                "document_id": int,
                "company_id": int,
                "status": str
            }
        """
        logger.info(f"🎯 Stage 0: Preprocessor + Registrar 开始...")
        
        result = {
            "stage0_vision": None,
            "file_hash": None,
            "is_duplicate": False,
            "document_id": None,
            "company_id": None,
            "status": "success"
        }
        
        # ===== Step 1: Vision 提取 =====
        vision_result = await Stage0Preprocessor.extract_company_from_page1(
            artifacts=artifacts,
            page_num=1,
            doc_id=doc_id,
            is_index_report=is_index_report,
            confirmed_doc_industry=confirmed_doc_industry,
            images=images,
            raw_output_dir=raw_output_dir,
            pdf_filename=pdf_filename
        )
        result["stage0_vision"] = vision_result
        logger.info(f"   ✅ Vision 提取完成: stock_code={vision_result.get('stock_code')}, year={vision_result.get('year')}")
        
        # ===== Step 2: 计算 Hash =====
        file_hash = Stage0Preprocessor.compute_file_hash(pdf_path)
        result["file_hash"] = file_hash
        logger.info(f"   📄 文件 Hash: {file_hash[:16]}...")
        
        # ===== Step 3: 检查重复 =====
        existing_doc = None
        if db_client:
            existing_doc = await Stage0Preprocessor.check_duplicate(file_hash, db_client)
        
        if existing_doc:
            if skip_duplicate:
                result["is_duplicate"] = True
                result["document_id"] = existing_doc.get("id")
                result["status"] = "duplicate"
                logger.info(f"   ⚠️ 文件已处理过，中止后续 Pipeline (skip_duplicate=True)")
                return result
            else:
                logger.info(f"   ♻️ 发现重复文件，启动【重新处理模式】！沿用旧 DB 记录 ID: {existing_doc.get('id')}")
                result["is_duplicate"] = True
                result["document_id"] = existing_doc.get("id")
                
                # 依然更新公司资料
                company_id = await Stage0Preprocessor.register_company_from_metadata(
                    metadata=vision_result,
                    db_client=db_client
                )
                result["company_id"] = company_id
                
                logger.info(f"✅ Stage 0 完成 (继承旧档): document_id={result['document_id']}, company_id={result['company_id']}")
                return result
        
        # ===== Step 4: 注册公司 =====
        company_id = await Stage0Preprocessor.register_company_from_metadata(
            metadata=vision_result,
            db_client=db_client
        )
        result["company_id"] = company_id
        
        # ===== Step 5: 注册文档 =====
        doc_result = await Stage0Preprocessor.register_document(
            doc_id=doc_id,
            file_path=pdf_path,
            file_hash=file_hash,
            company_id=company_id,
            original_filename=original_filename,
            db_client=db_client,
            metadata=vision_result
        )
        result["document_id"] = doc_result.get("document_id")
        
        if doc_result.get("status") != "success":
            result["status"] = "failed"
            result["error"] = doc_result.get("error")
        
        logger.info(f"✅ Stage 0 完成: document_id={result['document_id']}, company_id={result['company_id']}")
        
        return result