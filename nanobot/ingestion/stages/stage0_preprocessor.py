"""
Stage 0: 预处理与公司元数据提取 (v3.2)

职责：
- 从 PDF 封面提取公司信息 (stock_code, year, name)
- 🌟 v3.2: 从 LlamaParse 的第一页图片提取（移除 PyMuPDF）
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
        confirmed_doc_industry: str = None  # 🌟 新增：确认的行业
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
        
        parser = PDFParser(tier="agentic")
        
        # 尝试从已保存的 raw output 加载
        pdf_filename = Path(pdf_path).name
        try:
            result = parser.load_from_raw_output(pdf_filename)
        except FileNotFoundError:
            # 没有保存的结果，需要解析
            logger.info("   没有保存的 raw output，开始解析...")
            result = await parser.parse_async(pdf_path)
        
        # 🌟 从 images 中找到封面图片
        cover_image = None
        images = result.images
        
        # 尝试找到第一页的截图或 embedded 图片
        for img in images:
            if img.get("page", 0) == 0 or img.get("page", 0) == 1:
                cover_image = img
                break
        
        if not cover_image and images:
            cover_image = images[0]
        
        # 🌟 Vision 提取
        vision_result = None
        if cover_image:
            image_url = cover_image.get("url")
            local_path = cover_image.get("local_path")
            
            if local_path and Path(local_path).exists():
                # 从本地文件读取图片
                with open(local_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
                
                vision_result = await Stage0Preprocessor._call_vision(
                    image_base64=image_base64,
                    vision_model=vision_model or llm_core.vision_model
                )
            elif image_url:
                # 从 URL 下载图片
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(image_url)
                    if response.status_code == 200:
                        image_base64 = base64.b64encode(response.content).decode("utf-8")
                        vision_result = await Stage0Preprocessor._call_vision(
                            image_base64=image_base64,
                            vision_model=vision_model or llm_core.vision_model
                        )
        
        # 🌟 从 Vision 结果或 Markdown 提取
        stock_code = None
        year = None
        name_en = None
        name_zh = None
        
        if vision_result:
            stock_code = vision_result.get("stock_code")
            year = vision_result.get("year")
            name_en = vision_result.get("name_en")
            name_zh = vision_result.get("name_zh")
        
        # 🌟 如果 Vision 没提取到，从 Markdown 正则提取
        if not stock_code:
            markdown = result.markdown
            stock_code, year, name_en = Stage0Preprocessor._extract_from_text(markdown)
        
        # 🌟 如果还是没有，从文件名提取
        if not stock_code:
            stock_code, year = Stage0Preprocessor._extract_from_filename(pdf_path)
        
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
            "raw_output_dir": result.raw_output_dir
        }
        
        logger.info(f"✅ Stage 0 完成: stock_code={stock_code}, year={year}")
        
        return result_data
    
    @staticmethod
    async def _call_vision(
        image_base64: str,
        vision_model: str
    ) -> Dict[str, Any]:
        """
        调用 Vision API 提取封面信息
        
        Args:
            image_base64: 图片 base64
            vision_model: Vision 模型
            
        Returns:
            Dict: {"stock_code": str, "year": int, "name_en": str, "name_zh": str}
        """
        prompt = """
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
            response = await llm_core.vision_chat(
                prompt=prompt,
                image_base64=image_base64,
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
    
    @staticmethod
    def _extract_from_text(text: str) -> tuple:
        """
        从文本中正则提取
        
        Returns:
            (stock_code, year, name_en)
        """
        stock_code = None
        year = None
        name_en = None
        
        # 提取 stock_code (港股格式: 5位数字)
        stock_match = re.search(r'(?:stock\s*code|股票代码)[\s:]*([0-9]{5})', text, re.IGNORECASE)
        if stock_match:
            stock_code = stock_match.group(1)
        
        # 如果没有明确标注，尝试直接匹配 5 位数字
        if not stock_code:
            stock_match = re.search(r'([0-9]{5})', text)
            if stock_match:
                stock_code = stock_match.group(1)
        
        # 提取年份
        year_match = re.search(r'(?:year|年度|年)[\s:]*(20[0-9]{2})', text, re.IGNORECASE)
        if year_match:
            year = int(year_match.group(1))
        
        if not year:
            year_match = re.search(r'(20[0-9]{2})', text)
            if year_match:
                year = int(year_match.group(1))
        
        return stock_code, year, name_en
    
    @staticmethod
    def _extract_from_filename(pdf_path: str) -> tuple:
        """
        从文件名提取
        
        Returns:
            (stock_code, year)
        """
        filename = Path(pdf_path).name
        
        stock_code = None
        year = None
        
        # 尝试匹配 ar_2025, report_2024 等格式
        year_match = re.search(r'(20[0-9]{2})', filename)
        if year_match:
            year = int(year_match.group(1))
        
        # 尝试匹配股票代码
        stock_match = re.search(r'([0-9]{5})', filename)
        if stock_match:
            stock_code = stock_match.group(1)
        
        return stock_code, year