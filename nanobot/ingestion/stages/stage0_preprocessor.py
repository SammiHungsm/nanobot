"""
Stage 0: 预处理与公司元数据提取

职责：
- 从 PDF 封面提取公司信息 (stock_code, year, name)
- 只用 Vision API（不依赖 artifacts）
"""

import os
import json
import re
import fitz  # PyMuPDF
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List
from loguru import logger

from nanobot.core.llm_core import llm_core


class Stage0Preprocessor:
    """Stage 0: 封面预处理与公司元数据提取"""
    
    @staticmethod
    async def extract_cover_metadata(
        pdf_path: str,
        doc_id: str = None,
        vision_model: str = None,
        db_client: Any = None
    ) -> Dict[str, Any]:
        """
        从 PDF 封面提取公司元数据
        
        只用 Vision API
        
        Args:
            pdf_path: PDF 文件路径
            doc_id: 文档 ID
            vision_model: Vision 模型名称
            db_client: DB 客户端
            
        Returns:
            Dict: {"stock_code": str, "year": int, "name_en": str, "name_zh": str, "company_id": int}
        """
        logger.info(f"🎯 Stage 0: Vision API 提取封面...")
        
        stock_code = None
        year = None
        name_en = None
        name_zh = None
        
        # 只用 Vision API
        vision_result = await Stage0Preprocessor._extract_with_vision(
            pdf_path, 
            vision_model or llm_core.vision_model
        )
        
        if vision_result:
            vision_stock = vision_result.get("stock_code")
            vision_year = vision_result.get("year")
            vision_name_en = vision_result.get("name_en")
            vision_name_zh = vision_result.get("name_zh")
            
            if vision_name_en or vision_name_zh:
                name_en = vision_name_en
                name_zh = vision_name_zh
                logger.info(f"   ✅ Vision 提取 name: {name_en or name_zh}")
            
            if vision_year:
                try:
                    year = int(vision_year)
                    logger.info(f"   ✅ Vision 提取 year: {year}")
                except ValueError:
                    logger.warning(f"   ⚠️ Vision year 无法转为整数: {vision_year}")
            
            if vision_stock:
                stock_code = vision_stock
                logger.info(f"   ✅ Vision 提取 stock_code: {stock_code}")
        
        # 验证必要字段
        if not stock_code:
            logger.error(f"❌ Stage 0 失败：找不到 Stock Code！PDF: {pdf_path}")
            return {"stock_code": None, "year": None, "company_id": None}
        
        logger.info(f"✅ Stage 0 完成: Stock={stock_code}, Year={year}, Name={name_en or name_zh or 'N/A'}")
        
        # Upsert 公司信息
        company_id = None
        if db_client:
            company_id = await db_client.upsert_company(
                stock_code=stock_code,
                name_en=name_en,
                name_zh=name_zh,
                name_source="extracted",
                sector="BioTech"
            )
            
            if year and company_id and doc_id:
                try:
                    await db_client.update_document_company_id(doc_id, company_id, int(year))
                    logger.info(f"✅ 文档 {doc_id} 已关联公司 ID={company_id}, Year={year}")
                except ValueError:
                    pass
        
        return {
            "stock_code": stock_code,
            "year": year,
            "name_en": name_en,
            "name_zh": name_zh,
            "company_id": company_id
        }
    
    @staticmethod
    async def _extract_with_vision(
        pdf_path: str,
        vision_model: str
    ) -> Optional[Dict]:
        """使用 Vision API 提取封面信息"""
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_num in [1, 2]:
                if page_num > len(doc):
                    continue
                
                logger.info(f"   🎨 Vision 分析 Page {page_num}...")
                
                page = doc.load_page(page_num - 1)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                
                prompt = """
提取封面中的公司信息，返回 JSON 格式：
{"stock_code": "股票代码", "year": "年份", "name_en": "英文公司名称", "name_zh": "中文公司名称"}
只返回 JSON，不要其他解释。
"""
                
                vision_response = await llm_core.vision(
                    img_base64,
                    prompt,
                    model=vision_model
                )
                
                vision_result = Stage0Preprocessor._parse_vision_response(vision_response)
                
                if vision_result and vision_result.get("stock_code"):
                    doc.close()
                    return vision_result
            
            doc.close()
            
        except Exception as e:
            logger.warning(f"   ⚠️ Vision 提取异常: {e}")
        
        return None
    
    @staticmethod
    def _parse_vision_response(response: str) -> Optional[Dict]:
        """解析 Vision API 响应"""
        
        md_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if md_match:
            try:
                return json.loads(md_match.group(1).strip())
            except json.JSONDecodeError:
                pass
        
        brace_count = 0
        start_idx = None
        for i, char in enumerate(response):
            if char == '{':
                if start_idx is None:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx is not None:
                    try:
                        return json.loads(response[start_idx:i+1])
                    except json.JSONDecodeError:
                        start_idx = None
        
        return None