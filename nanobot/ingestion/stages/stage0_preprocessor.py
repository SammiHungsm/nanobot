"""
Stage 0: 预处理与公司元数据提取 (v4.3 - Vision 必须成功)

职责：
- 🌟 独立运行，不等待 LlamaParse
- 用 PyMuPDF 截取 page 1 封面图片
- Vision Model 提取公司信息
- 立即插入数据库（注册公司）

流程：
1. PyMuPDF 截取 page_1.jpg（封面）
2. Vision Model 提取 → stock_code, year, name_en, name_zh
3. 插入数据库（companies 表）
4. 返回 company_id

🌟 v4.3: Vision 必须成功，不使用 Filename Fallback
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
    """Stage 0: 封面预处理与公司元数据提取（独立运行，Vision 必须成功）"""
    
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

返回 JSON 格式：
```json
{
  "year": 2023,
  "theme": "恒生指数成份股"
}
```
"""
        else:
            prompt = """
分析这份财务报告封面，提取以下信息：

1. **股票代码** (stock_code): 例如 "02359", "00001", "00700"（香港股票代码格式）
2. **年份** (year): 报告年份，例如 2023, 2024
3. **公司名称英文** (name_en): 例如 "Pharmaron", "CK Hutchison"
4. **公司名称中文** (name_zh): 例如 "康龙化成", "长和"

⚠️ 股票代码通常是 5 位数字，例如 00001, 00700, 02359

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
            content = response if isinstance(response, str) else response.get("content", "")
            
            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                result = json.loads(json_match.group())
                logger.info(f"   ✅ Vision 解析成功: {result}")
                return result
            
            logger.warning(f"   ⚠️ Vision 返回非 JSON: {content[:100]}")
            return {}
            
        except Exception as e:
            logger.error(f"   ❌ Vision API 失败: {e}")
            return {}