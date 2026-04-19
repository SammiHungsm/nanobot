"""
Stage 0: Preprocessing and Company Metadata Extraction (v4.6 - Vision After LlamaParse)

Responsibilities:
- 🌟 v4.6 重構: 在 Stage 1 (LlamaParse) 之後運行
- 分析 Page 1 的 Markdown + 圖片，提取公司信息
- 比單獨看封面圖片更準確

Flow:
1. Stage 1 (LlamaParse) 解析 PDF → artifacts (包含 Markdown + 圖片)
2. Stage 0: Vision 分析 Page 1 artifacts
3. 提取: stock_code, year, name_en, name_zh
4. Stage 0.5: 插入資料庫

🌟 v4.6: Vision 有 Markdown + 圖片上下文，提取更準確
"""

import os
import json
import re
import base64
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

# 🌟 PyMuPDF import - must be installed in the runtime
try:
    import fitz  # PyMuPDF（pip install pymupdf，但 import fitz）
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.error("❌ PyMuPDF (fitz) 未安装！Stage 0 无法独立截取封面图片。")
    logger.error("   请在项目环境执行: pip install PyMuPDF>=1.24.0")
    logger.error("   或确保 Docker 容器已安装 PyMuPDF")

from nanobot.core.llm_core import llm_core


class Stage0Preprocessor:
    """Stage 0: 封面預處理與公司元數據提取（v4.6 - Vision After LlamaParse）"""
    
    @staticmethod
    async def extract_company_from_page1(
        artifacts: list,
        page_num: int = 1,
        doc_id: str = None,
        vision_model: str = None,
        is_index_report: bool = False,
        confirmed_doc_industry: str = None
    ) -> Dict[str, Any]:
        """
        🌟 v4.6 新增: 從 LlamaParse artifacts 提取 Page 1 公司信息
        
        優勢：
        - 有 Page 1 的 Markdown 文字（OCR 結果）
        - 有 Page 1 的所有圖片
        - Vision 提取更準確
        
        Args:
            artifacts: LlamaParse 解析的 artifacts 列表
            page_num: 頁碼（默認第 1 頁）
            doc_id: 文檔 ID
            vision_model: Vision 模型名稱
            is_index_report: 是否為指數報告
            confirmed_doc_industry: 確認的文檔行業
            
        Returns:
            Dict: {"stock_code", "year", "name_en", "name_zh"}
        """
        logger.info(f"📋 Stage 0: Vision 分析 Page {page_num} (基於 LlamaParse artifacts)...")
        
        if not artifacts:
            logger.warning("   ⚠️ 沒有 artifacts，無法分析")
            return {"stock_code": None, "year": 2025}
        
        # Step 1: 找到 Page 1 的 artifacts
        page1_artifacts = [a for a in artifacts if getattr(a, 'page_number', 0) == page_num]
        
        if not page1_artifacts:
            # 嘗試使用 page_num 屬性（不同格式）
            page1_artifacts = [a for a in artifacts if getattr(a, 'page_num', 0) == page_num]
        
        if not page1_artifacts:
            logger.warning(f"   ⚠️ 沒有找到 Page {page_num} 的 artifacts")
            # Fallback: 使用第一個 artifact
            if artifacts:
                page1_artifacts = [artifacts[0]]
                logger.info(f"   📄 使用第一個 artifact 作為 Page 1")
        
        # Step 2: 收集 Page 1 的 Markdown 文字
        page1_text = ""
        page1_images = []
        
        for artifact in page1_artifacts:
            # 獲取 Markdown 文字
            if hasattr(artifact, 'markdown') and artifact.markdown:
                page1_text += artifact.markdown + "\n"
            elif hasattr(artifact, 'text') and artifact.text:
                page1_text += artifact.text + "\n"
            
            # 獲取圖片
            if hasattr(artifact, 'images') and artifact.images:
                for img in artifact.images:
                    if hasattr(img, 'image_base64') and img.image_base64:
                        page1_images.append(img.image_base64)
                    elif hasattr(img, 'path') and img.path:
                        # 讀取圖片文件
                        try:
                            with open(img.path, 'rb') as f:
                                img_base64 = base64.b64encode(f.read()).decode('utf-8')
                                page1_images.append(img_base64)
                        except Exception as e:
                            logger.warning(f"   ⚠️ 無法讀取圖片: {e}")
        
        # Step 3: 構建 Vision prompt（包含 Markdown 上下文）
        if is_index_report:
            prompt = f"""
分析這份指數/行業報告的第一頁內容，提取以下信息：

## Page 1 Markdown 內容:
```
{page1_text[:2000]}
```

## 請提取:
1. **年份** (year): 報告年份
2. **主題** (theme): 報告主題

⚠️ 請使用繁體中文回答。

返回 JSON 格式：
```json
{{
  "year": 2023,
  "theme": "恆生指數成份股"
}}
```
"""
        else:
            prompt = f"""
分析這份財務報告的第一頁內容，提取公司基本信息。

## Page 1 Markdown 內容:
```
{page1_text[:2000]}
```

## 請提取:
1. **股票代碼** (stock_code): 香港股票代碼，5位數字
2. **年份** (year): 報告年份
3. **公司名稱英文** (name_en): 完整公司英文名稱
4. **公司名稱中文** (name_zh): 完整公司中文名稱，使用繁體中文

⚠️ 重要：
- 從上面的 Markdown 內容中提取信息
- 如果找不到某個字段，設為 null
- 所有中文名稱必須使用繁體中文

返回 JSON 格式：
```json
{{
  "stock_code": "00001",
  "year": 2023,
  "name_en": "CK Hutchison Holdings Limited",
  "name_zh": "長江和記實業有限公司"
}}
```
"""
        
        # Step 4: 調用 Vision API（如果有圖片）
        try:
            if page1_images:
                # 使用第一張圖片 + Markdown 上下文
                logger.info(f"   🖼️ 找到 {len(page1_images)} 張圖片，使用 Vision + Markdown 分析")
                
                response = await llm_core.vision(
                    image_base64=page1_images[0],
                    prompt=prompt,
                    model=vision_model
                )
            else:
                # 沒有圖片，只用 Markdown（使用 chat 而不是 vision）
                logger.info(f"   📝 沒有圖片，使用純 Markdown 分析")
                # 🌟 v2.6.2 修復：chat() 需要 messages 格式
                response = await llm_core.chat([{"role": "user", "content": prompt}])
            
            # 解析響應 - 🌟 v2.6.1 修復：更健壯的響應解析
            if isinstance(response, str):
                content = response
            elif isinstance(response, dict):
                content = response.get("content", "")
            elif hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
            
            logger.debug(f"   🔍 Vision/Chat 響應: {content[:300]}...")
            
            # 解析 JSON
            result = Stage0Preprocessor._parse_vision_response(content)
            
            if result:
                logger.info(f"   ✅ Vision 解析成功: {result}")
                return result
            
            logger.warning(f"   ⚠️ Vision 返回無效內容")
            return {"stock_code": None, "year": 2025}
            
        except Exception as e:
            logger.error(f"   ❌ Vision API 失敗: {e}")
            return {"stock_code": None, "year": 2025}
    
    @staticmethod
    def _parse_vision_response(content: str) -> Dict[str, Any]:
        """解析 Vision/Chat 響應，支持 JSON 和 Markdown 格式"""
        import json
        import re
        
        # 方法 1: 提取 ```json ... ``` 中的內容
        json_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', content)
        if json_block_match:
            try:
                return json.loads(json_block_match.group(1).strip())
            except json.JSONDecodeError:
                pass
        
        # 方法 2: 直接提取 JSON 對象
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group().strip())
            except json.JSONDecodeError:
                pass
        
        # 方法 3: 解析 Markdown 格式
        markdown_pattern = r'\*\*([^*]+):\*\*\s*(.+?)(?=\n|\*\*|$)'
        markdown_matches = re.findall(markdown_pattern, content)
        
        if markdown_matches:
            field_mapping = {
                'stock code': 'stock_code',
                '股票代碼': 'stock_code',
                'year': 'year',
                '年份': 'year',
                'company name (english)': 'name_en',
                '公司名稱英文': 'name_en',
                'company name (chinese)': 'name_zh',
                '公司名稱中文': 'name_zh',
            }
            
            result = {}
            for key, value in markdown_matches:
                key_lower = key.lower().strip()
                if key_lower in field_mapping:
                    result[field_mapping[key_lower]] = value.strip()
            
            if result:
                return result
        
        return {}
    
    @staticmethod
    async def extract_cover_metadata(
        pdf_path: str,
        doc_id: str = None,
        vision_model: str = None,
        db_client: Any = None,
        is_index_report: bool = False,
        confirmed_doc_industry: str = None,
        parser: Any = None,  # 🌟 不再需要，保留兼容
        artifacts: list = None,  # 🌟 不再需要，保留兼容
        raw_output_dir: str = None  # 🌟 不再需要，保留兼容
    ) -> Dict[str, Any]:
        """
        🌟 v4.3: Vision 必须成功，不使用 Filename Fallback
        
        直接用 PyMuPDF 截取封面，Vision 提取公司信息，插入数据库
        
        Args:
            pdf_path: PDF 文件路径
            doc_id: 文档 ID
            vision_model: Vision 模型名称
            db_client: DB 客户端
            is_index_report: 是否为指数报告
            confirmed_doc_industry: 报告定义的行业
            
        Returns:
            Dict: {"stock_code": str, "year": int, "name_en": str, "name_zh": str, "company_id": int}
            
        Raises:
            RuntimeError: 如果 PyMuPDF 未安装或无法截取封面
        """
        logger.info(f"🎯 Stage 0: Vision 提取封面（独立运行，不等待 LlamaParse）...")
        
        # 🌟 Step 1: 检查 PyMuPDF 是否可用
        if not PYMUPDF_AVAILABLE:
            raise RuntimeError(
                "❌ PyMuPDF (fitz) 未安装！Stage 0 无法独立截取封面图片。\n"
                "   请在项目环境执行: pip install PyMuPDF>=1.24.0\n"
                "   或确保 Docker 容器已安装 PyMuPDF。\n"
                "   Stage 0 需要 PyMuPDF 来截取 PDF 封面供 Vision 分析。"
            )
        
        # 🌟 Step 2: PyMuPDF 截取封面
        cover_image_path = await Stage0Preprocessor._extract_cover_image(pdf_path, doc_id)
        
        if not cover_image_path:
            raise RuntimeError(
                f"❌ 无法从 PDF 截取封面图片: {pdf_path}\n"
                "   Vision LLM 需要封面图片才能提取公司信息。\n"
                "   请检查 PDF 文件是否损坏或是否为空文件。"
            )
        
        # 🌟 Step 3: Vision 提取公司信息
        vision_result = await Stage0Preprocessor._vision_extract_company(
            cover_image_path=cover_image_path,
            vision_model=vision_model or llm_core.vision_model,
            is_index_report=is_index_report
        )
        
        stock_code = vision_result.get("stock_code")
        year = vision_result.get("year")
        name_en = vision_result.get("name_en")
        name_zh = vision_result.get("name_zh")
        
        logger.info(f"   ✅ Vision 提取结果: stock_code={stock_code}, year={year}, name_en={name_en}")
        
        # 🌟 Step 4: 立即插入数据库（注册公司）
        company_id = None
        if db_client and stock_code:
            try:
                company_result = await db_client.upsert_company(
                    stock_code=stock_code,
                    name_en=name_en,
                    name_zh=name_zh,
                    industry=confirmed_doc_industry if is_index_report else None
                )
                # 🌟 v1.1: 修正：upsert_company 返回 int（公司 ID），不是 dict
                company_id = company_result if company_result else None
                logger.info(f"   ✅ 公司已注册: stock_code={stock_code}, company_id={company_id}")
            except Exception as e:
                logger.warning(f"   ⚠️ 注册公司失败: {e}")
        
        result_data = {
            "stock_code": stock_code,
            "year": year,
            "name_en": name_en,
            "name_zh": name_zh,
            "company_id": company_id,
            "vision_result": vision_result
        }
        
        logger.info(f"✅ Stage 0 完成: stock_code={stock_code}, year={year}, company_id={company_id}")
        
        return result_data
    
    @staticmethod
    async def _extract_cover_image(pdf_path: str, doc_id: str = None) -> Optional[str]:
        """
        🌟 PyMuPDF 截取封面（必须成功）
        
        Args:
            pdf_path: PDF 文件路径
            doc_id: 文档 ID
            
        Returns:
            str: 封面图片路径
            
        Raises:
            RuntimeError: 如果 PyMuPDF 未安装
        """
        if not PYMUPDF_AVAILABLE:
            raise RuntimeError("❌ PyMuPDF (fitz) 未安装！")
        
        try:
            # 打开 PDF
            doc = fitz.open(pdf_path)
            
            if len(doc) == 0:
                logger.warning("   ⚠️ PDF 没有页面")
                return None
            
            # 截取第一页（封面）
            page = doc[0]
            
            # 🌟 高 DPI 截图（300 DPI 确保清晰）
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), dpi=300)
            
            # 保存路径
            data_dir = Path(os.environ.get("DATA_DIR", "/app/data/raw"))
            images_dir = data_dir / "stage0_images"
            images_dir.mkdir(parents=True, exist_ok=True)
            
            # 文件名
            pdf_name = Path(pdf_path).stem
            cover_path = images_dir / f"{pdf_name}_cover.jpg"
            
            # 保存
            pix.save(str(cover_path))
            
            doc.close()
            
            logger.info(f"   ✅ 封面已截取: {cover_path}")
            return str(cover_path)
            
        except Exception as e:
            logger.error(f"   ❌ 截取封面失败: {e}")
            return None
    
    @staticmethod
    async def _vision_extract_company(
        cover_image_path: str,
        vision_model: str,
        is_index_report: bool = False
    ) -> Dict[str, Any]:
        """
        Vision 提取公司信息（必须成功）
        
        Args:
            cover_image_path: 封面图片路径
            vision_model: Vision 模型
            is_index_report: 是否为指数报告
            
        Returns:
            Dict: {"stock_code": str, "year": int, "name_en": str, "name_zh": str}
        """
        # 读取图片
        with open(cover_image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")
        
        # 🌟 根据报告类型使用不同的 Prompt
        if is_index_report:
            prompt = """
分析这份指数/行业报告封面，提取以下信息：

1. **年份** (year): 报告年份，例如 2023, 2024
2. **主题** (theme): 报告主题，例如 "恒生指数", "科技行业"

⚠️ 請使用繁體中文回答。

返回 JSON 格式：
```json
{
  "year": 2023,
  "theme": "恒生指數成份股"
}
```
"""
        else:
            prompt = """
分析這份財務報告封面，提取以下信息：

## 封面常見字段（必填）
1. **股票代碼** (stock_code): 香港股票代碼，5位數字，例如 "00001", "00700", "02359"
2. **年份** (year): 報告年份，例如 2023, 2024
3. **公司名稱英文** (name_en): 完整公司英文名稱
4. **公司名稱中文** (name_zh): 完整公司中文名稱，使用繁體中文

⚠️ 重要：
- 只提取封面上明確顯示的信息
- 如果封面上沒有某個字段，設為 null
- 不要推測或填寫封面上沒有的信息
- 所有中文名稱必須使用繁體中文

返回 JSON 格式：
```json
{
  "stock_code": "00001",
  "year": 2023,
  "name_en": "CK Hutchison Holdings Limited",
  "name_zh": "長江和記實業有限公司"
}
```
"""
        
        try:
            response = await llm_core.vision(
                image_base64=image_base64,
                prompt=prompt,
                model=vision_model
            )
            
            # 解析 JSON
            content = response if isinstance(response, str) else response.get("content", "")
            
            # 🌟 v2.4 改进：打印原始响应以便调试
            logger.debug(f"   🔍 Vision 原始响应: {content}")
            
            # 🌟 v2.5 改进：支持多种格式解析
            result = {}
            
            # 方法 1: 尝试提取 ```json ... ``` 中的内容
            json_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', content)
            if json_block_match:
                json_str = json_block_match.group(1).strip()
                logger.debug(f"   🔍 提取的 JSON 块: {json_str}")
                try:
                    result = json.loads(json_str)
                    logger.info(f"   ✅ Vision 解析成功 (JSON 块): {result}")
                    return result
                except json.JSONDecodeError:
                    pass
            
            # 方法 2: 尝试直接提取 JSON 对象
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group().strip()
                try:
                    result = json.loads(json_str)
                    logger.info(f"   ✅ Vision 解析成功 (JSON 对象): {result}")
                    return result
                except json.JSONDecodeError:
                    pass
            
            # 🌟 v2.5 新增：方法 3: 解析 Markdown 格式 (**Key:** Value)
            # 例如: **Stock Code:** 00001
            markdown_pattern = r'\*\*([^*]+):\*\*\s*(.+?)(?=\n|\*\*|$)'
            markdown_matches = re.findall(markdown_pattern, content)
            
            if markdown_matches:
                field_mapping = {
                    'stock code': 'stock_code',
                    '股票代碼': 'stock_code',
                    'year': 'year',
                    '年份': 'year',
                    'company name (english)': 'name_en',
                    '公司名稱英文': 'name_en',
                    'company name (chinese)': 'name_zh',
                    '公司名稱中文': 'name_zh',
                    # 🌟 v2.6: 移除 auditor, address, chairman - 這些應由 Stage 4 Agent 提取
                }
                
                for key, value in markdown_matches:
                    key_lower = key.lower().strip()
                    if key_lower in field_mapping:
                        mapped_key = field_mapping[key_lower]
                        result[mapped_key] = value.strip()
                
                if result:
                    logger.info(f"   ✅ Vision 解析成功 (Markdown): {result}")
                    return result
            
            logger.warning(f"   ⚠️ Vision 返回非 JSON/Markdown: {content[:200]}")
            return {}
            
        except Exception as e:
            logger.error(f"   ❌ Vision API 失败: {e}")
            return {}