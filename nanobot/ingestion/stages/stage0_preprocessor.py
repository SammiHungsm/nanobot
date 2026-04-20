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
        confirmed_doc_industry: str = None,
        images: list = None,  # 🌟 v4.7 新增：從 parse_result.images 傳入
        raw_output_dir: str = None  # 🌟 v4.7 新增：用於讀取下載的圖片
    ) -> Dict[str, Any]:
        """
        🌟 v4.6 新增: 從 LlamaParse artifacts 提取 Page 1 公司信息
        🌟 v4.7 改進: 正確處理 artifacts（字典格式）和 images
        
        Args:
            artifacts: LlamaParse 解析的 artifacts 列表（字典格式）
            page_num: 頁碼（默認第 1 頁）
            doc_id: 文檔 ID
            vision_model: Vision 模型名稱
            is_index_report: 是否為指數報告
            confirmed_doc_industry: 確認的文檔行業
            images: 🌟 從 parse_result.images 傳入的圖片列表
            raw_output_dir: 🌟 圖片下載目錄
            
        Returns:
            Dict: {"stock_code", "year", "name_en", "name_zh"}
        """
        logger.info(f"📋 Stage 0: Vision 分析 Page {page_num} (基於 LlamaParse artifacts)...")
        
        if not artifacts:
            logger.warning("   ⚠️ 沒有 artifacts，無法分析")
            return {"stock_code": None, "year": 2025}
        
        # Step 1: 找到 Page 1 的 Markdown（artifacts 是字典列表）
        page1_artifacts = [
            a for a in artifacts 
            if isinstance(a, dict) and a.get("page") == page_num
        ]
        
        if not page1_artifacts:
            # 嘗試使用 page_number 屬性（向後兼容）
            page1_artifacts = [
                a for a in artifacts 
                if isinstance(a, dict) and a.get("page_number") == page_num
            ]
        
        if not page1_artifacts and artifacts:
            # Fallback: 使用第一個 artifact
            logger.warning(f"   ⚠️ 沒有找到 Page {page_num} 的 artifacts，使用第一個")
            page1_artifacts = [artifacts[0]]
        
        # Step 2: 收集 Page 1 的 Markdown 文字
        page1_text = ""
        for artifact in page1_artifacts:
            if isinstance(artifact, dict):
                # artifacts 字典格式：{"type": "text", "page": 1, "content": "..."}
                page1_text += artifact.get("content", "") + "\n"
                page1_text += artifact.get("markdown", "") + "\n"
            elif hasattr(artifact, 'content'):
                page1_text += artifact.content + "\n"
            elif hasattr(artifact, 'markdown'):
                page1_text += artifact.markdown + "\n"
        
        # Step 3: 🌟 v4.7 新增：從 images 參數獲取 Page 1 的圖片
        page1_images = []
        
        # 方法 1: 從傳入的 images 參數獲取
        if images:
            for img in images:
                if isinstance(img, dict):
                    img_page = img.get("page", 0)
                    if img_page == page_num:
                        # 檢查是否有本地路徑
                        local_path = img.get("local_path")
                        if local_path:
                            try:
                                with open(local_path, 'rb') as f:
                                    img_base64 = base64.b64encode(f.read()).decode('utf-8')
                                    page1_images.append(img_base64)
                                    logger.info(f"   🖼️ 讀取圖片成功: {local_path}")
                            except Exception as e:
                                logger.warning(f"   ⚠️ 無法讀取圖片 {local_path}: {e}")
        
        # 方法 2: 🌟 從 raw_output_dir/images/ 目錄讀取 Page 1 的圖片
        if not page1_images and raw_output_dir:
            import os
            import glob as glob_module
            
            images_dir = os.path.join(raw_output_dir, "images")
            if os.path.exists(images_dir):
                # 🌟 v4.8.4 修復：精確匹配 Page 1 的圖片，避免匹配 Page 10, 11, 19 等
                # 問題：img_p1_*.jpg 會匹配 img_p10_1.jpg, img_p19_1.jpg 等
                # 解決：先列出所有文件，再過濾
                
                all_images = glob_module.glob(os.path.join(images_dir, "*.png")) + \
                             glob_module.glob(os.path.join(images_dir, "*.jpg"))
                
                # 🌟 精確過濾：只保留 Page 1 的圖片
                # 格式 1: img_p1_*.jpg (Page 1 的嵌入圖片)
                # 格式 2: page_1_*.jpg (舊格式)
                # 格式 3: page_1.jpg (整頁截圖)
                import re
                
                # 精確匹配 Page 1：img_p1_X.jpg 而不是 img_p10_X.jpg
                page1_pattern_1 = re.compile(rf'img_p{page_num}_(\d+)\.(png|jpg)$')  # img_p1_1.jpg
                page1_pattern_2 = re.compile(rf'page_{page_num}_image_(\d+)\.(png|jpg)$')  # page_1_image_1.jpg
                page1_pattern_3 = re.compile(rf'page_{page_num}\.(png|jpg)$')  # page_1.jpg
                
                for img_path in all_images:
                    basename = os.path.basename(img_path)
                    if page1_pattern_1.search(basename) or \
                       page1_pattern_2.search(basename) or \
                       page1_pattern_3.search(basename):
                        try:
                            with open(img_path, 'rb') as f:
                                img_base64 = base64.b64encode(f.read()).decode('utf-8')
                                page1_images.append(img_base64)
                                logger.info(f"   🖼️ 從目錄讀取圖片: {basename}")
                        except Exception as e:
                            logger.warning(f"   ⚠️ 無法讀取圖片 {img_path}: {e}")
        
        logger.info(f"   📝 Page 1 Markdown 長度: {len(page1_text)} 字符")
        logger.info(f"   🖼️ Page 1 圖片數量: {len(page1_images)}")
        
        # Step 4: 🌟 v4.8 改進：每張圖片調用 Vision，然後合併結果
        if not page1_images and not page1_text:
            logger.warning("   ⚠️ 沒有圖片也沒有 Markdown，無法分析")
            return {"stock_code": None, "year": 2025}
        
        # 構建 Vision prompt
        if is_index_report:
            prompt_template = """
分析這份指數/行業報告，提取以下信息：

## 請提取:
1. **年份** (year): 報告年份
2. **主題** (theme): 報告主題

⚠️ 請使用繁體中文回答。只返回 JSON，不要其他文字。

返回 JSON 格式：
```json
{{
  "year": 2023,
  "theme": "恆生指數成份股"
}}
```
"""
        else:
            prompt_template = """
分析這份財務報告，提取公司基本信息。

## 請提取:
1. **股票代碼** (stock_code): 香港股票代碼，5位數字
2. **年份** (year): 報告年份
3. **公司名稱英文** (name_en): 完整公司英文名稱
4. **公司名稱中文** (name_zh): 完整公司中文名稱，使用繁體中文

⚠️ 重要：
- 從圖片和文字中提取信息
- 如果找不到某個字段，設為 null
- 所有中文名稱必須使用繁體中文
- 只返回 JSON，不要其他文字

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
        
        # 收集所有 Vision 結果
        vision_results = []
        
        try:
            # 🌟 v4.8: 對每張圖片調用 Vision API
            if page1_images:
                logger.info(f"   🔄 開始處理 {len(page1_images)} 張圖片...")
                
                for i, img_base64 in enumerate(page1_images, 1):
                    logger.info(f"   🖼️ 處理圖片 {i}/{len(page1_images)}...")
                    
                    try:
                        response = await llm_core.vision(
                            image_base64=img_base64,
                            prompt=prompt_template,
                            model=vision_model
                        )
                        
                        # 解析響應
                        if isinstance(response, str):
                            content = response
                        elif isinstance(response, dict):
                            content = response.get("content", "")
                        elif hasattr(response, 'content'):
                            content = response.content
                        else:
                            content = str(response)
                        
                        logger.debug(f"      🔍 圖片 {i} 響應: {content[:200]}...")
                        
                        # 解析 JSON
                        result = Stage0Preprocessor._parse_vision_response(content)
                        if result:
                            vision_results.append(result)
                            logger.info(f"      ✅ 圖片 {i} 提取成功: {result}")
                        
                    except Exception as e:
                        logger.warning(f"      ⚠️ 圖片 {i} Vision 失敗: {e}")
            
            # 🌟 v4.8: 如果有 Markdown 但沒有圖片，用 Chat API
            if page1_text and not page1_images:
                logger.info(f"   📝 使用純 Markdown 分析...")
                
                prompt = f"""{prompt_template}

## Page 1 Markdown 內容:
```
{page1_text[:3000]}
```
"""
                try:
                    response = await llm_core.chat([{"role": "user", "content": prompt}])
                    
                    if isinstance(response, str):
                        content = response
                    elif isinstance(response, dict):
                        content = response.get("content", "")
                    else:
                        content = str(response)
                    
                    result = Stage0Preprocessor._parse_vision_response(content)
                    if result:
                        vision_results.append(result)
                        logger.info(f"   ✅ Markdown 提取成功: {result}")
                
                except Exception as e:
                    logger.warning(f"   ⚠️ Markdown Chat 失敗: {e}")
            
            # 🌟 v4.8: 合併多個 Vision 結果
            if not vision_results:
                logger.warning("   ⚠️ 所有 Vision 調用都失敗")
                return {"stock_code": None, "year": 2025}
            
            # 合併策略：優先選擇非空值
            merged_result = Stage0Preprocessor._merge_vision_results(vision_results)
            
            logger.info(f"   ✅ Vision 合併結果: {merged_result}")
            return merged_result
            
        except Exception as e:
            logger.error(f"   ❌ Vision API 失敗: {e}")
            return {"stock_code": None, "year": 2025}
    
    @staticmethod
    def _merge_vision_results(results: list) -> Dict[str, Any]:
        """
        🌟 v4.8 新增：合併多個 Vision 結果
        
        策略：
        1. 對於每個字段，優先選擇非空值
        2. 如果多個結果都有值，選擇最常見的
        
        Args:
            results: Vision 結果列表
            
        Returns:
            合併後的結果
        """
        if not results:
            return {}
        
        if len(results) == 1:
            return results[0]
        
        # 合併邏輯
        merged = {}
        fields = ['stock_code', 'year', 'name_en', 'name_zh', 'theme']
        
        for field in fields:
            # 收集所有非空值
            values = [r.get(field) for r in results if r.get(field)]
            
            if not values:
                merged[field] = None
            elif len(values) == 1:
                merged[field] = values[0]
            else:
                # 多個值：選擇最常見的
                from collections import Counter
                counter = Counter(str(v) for v in values)
                most_common = counter.most_common(1)[0][0]
                # 找到原始值（保持類型）
                for v in values:
                    if str(v) == most_common:
                        merged[field] = v
                        break
        
        return merged
    
    @staticmethod
    def _parse_vision_response(content: str) -> Dict[str, Any]:
        """解析 Vision/Chat 響應，支持 JSON 和 Markdown 格式"""
        import json
        import re
        
        # 方法 1: 提取 ```json ... ``` 中的內容
        json_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', content)
        if json_block_match:
            try:
                result = json.loads(json_block_match.group(1).strip())
                # 🌟 Bug fix: 確保 year 是整數
                if 'year' in result and result['year'] is not None:
                    try:
                        result['year'] = int(result['year'])
                    except (ValueError, TypeError):
                        pass
                return result
            except json.JSONDecodeError:
                pass
        
        # 方法 2: 直接提取 JSON 對象
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                result = json.loads(json_match.group().strip())
                # 🌟 Bug fix: 確保 year 是整數
                if 'year' in result and result['year'] is not None:
                    try:
                        result['year'] = int(result['year'])
                    except (ValueError, TypeError):
                        pass
                return result
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
                # 🌟 Bug fix: 確保 year 是整數
                if 'year' in result and result['year'] is not None:
                    try:
                        result['year'] = int(result['year'])
                    except (ValueError, TypeError):
                        pass
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