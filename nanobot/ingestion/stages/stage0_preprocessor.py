"""
Stage 0: 预处理与公司元数据提取 (v3.9)

职责：
- 从 PDF 封面和第二页提取公司信息 (stock_code, year, name)
- 🌟 v3.9: 只使用 Vision Model（移除所有 fallback）
- 🌟 v3.9: 不依赖文件名、Markdown 正则

流程：
1. Vision 提取 page_1.jpg（封面） → stock_code, year, name_en, name_zh
2. Vision 提取 page_2.jpg（如果封面没有公司名称） → name_en, name_zh

⚠️ 如果 Vision 失败，Stage 0 返回 None（不 fallback）
"""

import os
import json
import re
import httpx
import base64
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from nanobot.core.llm_core import llm_core


class Stage0Preprocessor:
    """Stage 0: 封面预处理与公司元数据提取"""
    
    @staticmethod
    async def extract_cover_metadata(
        pdf_path: str,
        doc_id: str = None,
        vision_model: str = None,
        db_client: Any = None,
        is_index_report: bool = False,  # 🌟 新增：是否为指数报告
        confirmed_doc_industry: str = None,  # 🌟 新增：确认的行业
        parser: Any = None  # 🌟 新增：传入已有的 parser（避免重复创建）
    ) -> Dict[str, Any]:
        """
        从 PDF 封面提取公司元数据
        
        🌟 v3.2: 根据 is_index_report 使用不同的提取策略
        
        Args:
            pdf_path: PDF 文件路径
            doc_id: 文档 ID
            vision_model: Vision 模型名称
            db_client: DB 客户端
            is_index_report: 是否为指数报告（影响提取策略）
            confirmed_doc_industry: 报告定义的行业
            
        Returns:
            Dict: {"stock_code": str, "year": int, "name_en": str, "name_zh": str, "industry": str}
        """
        logger.info(f"🎯 Stage 0: Vision API 提取封面...")
        
        # 🌟 指数报告的提取策略不同
        if is_index_report:
            logger.info(f"   📊 指数报告模式（行业: {confirmed_doc_industry or 'Unknown'}）")
            # 指数报告没有单一 stock_code，封面提取主题和年份
            extraction_prompt = """
分析这份指数/行业报告封面，提取以下信息：

1. **年份** (year): 报告年份，例如 2023, 2024
2. **主题** (theme): 报告主题，例如 "恒生指数", "科技行业", "金融业"
3. **行业** (industry): 报告覆盖的行业

返回 JSON 格式：
```json
{
  "year": 2023,
  "theme": "恒生指数成份股",
  "industry": "综合企业"
}
```
"""
        else:
            # 年报提取策略
            extraction_prompt = """
分析这份财务报告封面，提取以下信息：

1. **股票代码** (stock_code): 例如 "02359", "00001", "00700"
2. **年份** (year): 报告年份，例如 2023, 2024
3. **公司名称英文** (name_en): 例如 "Pharmaron", "CK Hutchison"
4. **公司名称中文** (name_zh): 例如 "康龙化成", "长和"

返回 JSON 格式：
```json
{
  "stock_code": "02359",
  "year": 2023,
  "name_en": "Pharmaron",
  "name_zh": "康龙化成"
}
```
"""
        
        # 🌟 从 LlamaParse 的 raw output 加载封面图片
        # 如果没有 raw output，先解析 PDF（但只解析第一页）
        from nanobot.core.pdf_core import PDFParser
        
        # 🌟 v3.4: 优先使用传入的 parser（避免重复创建）
        if parser is None:
            parser = PDFParser(tier="agentic")
        
        # 尝试从已保存的 raw output 加载
        pdf_filename = Path(pdf_path).name
        try:
            result = parser.load_from_raw_output(pdf_filename)
        except FileNotFoundError:
            # 没有保存的结果，需要解析
            logger.info("   没有保存的 raw output，开始解析...")
            result = await parser.parse_async(pdf_path)
        
        # 🌟 v3.6: 从 images 或 raw_output_dir/images 中找到封面图片
        cover_image = None
        images = getattr(result, 'images', []) or []  # 🌟 v3.5: 安全访问
        
        # 🌟 v3.6: LlamaParse 图片命名是 page_1.jpg（第一页），而不是 page_0.jpg
        # 所以需要检查 filename 或直接读取本地文件
        raw_output_dir = getattr(result, 'raw_output_dir', None)
        if raw_output_dir:
            images_dir = Path(raw_output_dir) / "images"
            if images_dir.exists():
                # 🌟 直接读取本地封面图片
                cover_path = images_dir / "page_1.jpg"  # 第一页截图
                if cover_path.exists():
                    cover_image = {"local_path": str(cover_path), "filename": "page_1.jpg"}
                    logger.info(f"   ✅ 从本地加载封面: {cover_path}")
                else:
                    # 🌟 Fallback: 尝试 page_2.jpg（第二页，可能包含公司信息）
                    cover_path = images_dir / "page_2.jpg"
                    if cover_path.exists():
                        cover_image = {"local_path": str(cover_path), "filename": "page_2.jpg"}
                        logger.info(f"   ✅ 从本地加载第二页: {cover_path}")
        
        # 🌟 如果本地没有图片，从 images list 中查找
        if not cover_image:
            for img in images:
                if img is None:
                    continue
                filename = img.get("filename", "")
                # 🌟 v3.6: 匹配 page_1.jpg 或 page_1_image_*.jpg
                if filename.startswith("page_1") or filename.startswith("page_2"):
                    cover_image = img
                    break
        
        # 🌟 Vision 提取（v3.7: 支持本地图片路径）
        vision_result = None
        if cover_image:
            # 🌟 v3.7: 优先从本地路径读取（避免重复下载）
            local_path = cover_image.get("local_path")
            if not local_path and cover_image.get("filename"):
                # 🌟 如果有 filename，尝试从 raw_output_dir/images 中查找
                if raw_output_dir:
                    images_dir = Path(raw_output_dir) / "images"
                    potential_path = images_dir / cover_image.get("filename")
                    if potential_path.exists():
                        local_path = str(potential_path)
            
            if local_path and Path(local_path).exists():
                # 从本地文件读取图片
                logger.info(f"   🎨 Vision 提取封面: {local_path}")
                with open(local_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
                
                vision_result = await Stage0Preprocessor._call_vision(
                    image_base64=image_base64,
                    vision_model=vision_model or llm_core.vision_model
                )
                logger.info(f"   ✅ Vision 结果: {vision_result}")
            
            # 🌟 如果本地路径不存在，从 URL 下载
            elif cover_image.get("url"):
                image_url = cover_image.get("url")
                logger.info(f"   🌐 Vision 从 URL 下载: {image_url[:50]}...")
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(image_url)
                    if response.status_code == 200:
                        image_base64 = base64.b64encode(response.content).decode("utf-8")
                        vision_result = await Stage0Preprocessor._call_vision(
                            image_base64=image_base64,
                            vision_model=vision_model or llm_core.vision_model
                        )
        
        # 🌟 v3.9: Stage 0 只使用 Vision Model（移除所有 fallback）
        # 不依赖文件名、Markdown 正则，确保使用视觉理解
        stock_code = None
        year = None
        name_en = None
        name_zh = None
        
        # 🌟 Vision 结果是唯一来源
        if vision_result:
            stock_code = vision_result.get("stock_code")
            year = vision_result.get("year")
            name_en = vision_result.get("name_en")
            name_zh = vision_result.get("name_zh")
            logger.info(f"   ✅ Vision 提取结果: stock_code={stock_code}, year={year}, name_en={name_en}")
        
        # 🌟 v3.9: 如果 Vision 失败，记录警告（不 fallback）
        if not stock_code:
            logger.warning("   ⚠️ Vision 未提取到 stock_code（请检查封面图片或 Vision API）")
        
        if not year:
            logger.warning("   ⚠️ Vision 未提取到 year（请检查封面图片或 Vision API）")
        
        # 🌟 v3.9: 如果封面没有公司名称，尝试从第二页 Vision
        if not name_en and not name_zh and raw_output_dir:
            # 🌟 尝试 Vision 第二页（如果第一页封面没有公司名称）
            images_dir = Path(raw_output_dir) / "images"
            page2_path = images_dir / "page_2.jpg"
            
            if page2_path.exists():
                logger.info(f"   🎨 Vision 提取第二页（获取公司名称）: {page2_path}")
                with open(page2_path, "rb") as f:
                    page2_base64 = base64.b64encode(f.read()).decode("utf-8")
                
                # 🌟 使用简化的 Prompt 只提取公司名称
                name_prompt = """
分析这份财务报告页面，提取以下信息：

1. **公司名称英文** (name_en): 例如 "CK Hutchison", "Pharmaron"
2. **公司名称中文** (name_zh): 例如 "长和", "康龙化成"

返回 JSON 格式：
```json
{
  "name_en": "CK Hutchison",
  "name_zh": "长和"
}
```

如果没有找到某个字段，设为 null。
"""
                
                try:
                    name_result = await Stage0Preprocessor._call_vision(
                        image_base64=page2_base64,
                        vision_model=vision_model or llm_core.vision_model,
                        prompt_override=name_prompt  # 🌟 v3.8: 自定义 Prompt
                    )
                    if name_result:
                        name_en = name_result.get("name_en")
                        name_zh = name_result.get("name_zh")
                        logger.info(f"   ✅ 第二页 Vision 提取: name_en={name_en}, name_zh={name_zh}")
                except Exception as e:
                    logger.warning(f"   ⚠️ 第二页 Vision 失败: {e}")
        
        # 保存到数据库
        if db_client and stock_code:
            try:
                company = await db_client.get_company_by_stock_code(stock_code)
                if company:
                    logger.info(f"   ✅ 找到公司: stock_code={stock_code}, company_id={company.get('id')}")
            except Exception as e:
                logger.warning(f"   ⚠️ 查询公司失败: {e}")
        
        result_data = {
            "stock_code": stock_code,
            "year": year,
            "name_en": name_en,
            "name_zh": name_zh,
            "vision_result": vision_result,
            "raw_output_dir": getattr(result, 'raw_output_dir', None)  # 🌟 v3.5: 安全访问
        }
        
        logger.info(f"✅ Stage 0 完成: stock_code={stock_code}, year={year}")
        
        return result_data
    
    @staticmethod
    async def _call_vision(
        image_base64: str,
        vision_model: str,
        prompt_override: str = None  # 🌟 v3.8: 自定义 Prompt
    ) -> Dict[str, Any]:
        """
        调用 Vision API 提取封面信息
        
        Args:
            image_base64: 图片 base64
            vision_model: Vision 模型
            prompt_override: 自定义 Prompt（可选）
            
        Returns:
            Dict: {"stock_code": str, "year": int, "name_en": str, "name_zh": str}
        """
        # 🌟 v3.8: 支持自定义 Prompt
        prompt = prompt_override or """
分析这份财务报告封面，提取以下信息：

1. **股票代码** (stock_code): 例如 "02359", "00001", "00700"
2. **年份** (year): 报告年份，例如 2023, 2024
3. **公司名称英文** (name_en): 例如 "Pharmaron", "CK Hutchison"
4. **公司名称中文** (name_zh): 例如 "康龙化成", "长和"

返回 JSON 格式：
```json
{
  "stock_code": "02359",
  "year": 2023,
  "name_en": "Pharmaron",
  "name_zh": "康龙化成"
}
```

如果没有找到某个字段，设为 null。
"""
        
        try:
            response = await llm_core.vision(
                image_base64=image_base64,
                prompt=prompt,
                model=vision_model
            )
            
            # 解析 JSON
            content = response.get("content", "")
            
            # 提取 JSON
            json_match = re.search(r'\{[^{}]*\}', content)
            if json_match:
                return json.loads(json_match.group())
            
            return {}
            
        except Exception as e:
            logger.warning(f"   ⚠️ Vision API 失败: {e}")
            return {}
    
    