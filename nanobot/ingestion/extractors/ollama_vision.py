"""
Ollama Vision Extractor - 使用本地 Ollama Vision 模型提取封面信息

优势：
1. 不需要额外安装 OpenDataLoader Hybrid
2. 使用已有的 Ollama qwen3-vl:4b (3.3GB)
3. Docker 通过 host.docker.internal 访问

使用场景：
- 提取封面 stock_code, year, company_name
- 当 OpenDataLoader 抓不到 Page 1 时触发

注意：
- 需要 PyMuPDF 切割 PDF 第一页为图片
- 但这只是切割，不是解析整个 PDF
"""

import os
import io
import json
import base64
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

# Ollama API endpoint (Docker 内部访问 host)
OLLAMA_API_BASE = "http://host.docker.internal:11434/v1"
OLLAMA_API_TAGS = "http://host.docker.internal:11434/api"


class OllamaVisionExtractor:
    """
    Ollama Vision 提取器
    
    使用 qwen3-vl:4b 模型从图片中提取结构化信息
    """
    
    def __init__(self, model: str = "qwen3-vl:4b", api_base: str = None):
        """
        初始化
        
        Args:
            model: Vision 模型名称（默认 qwen3-vl:4b）
            api_base: API endpoint（默认 Docker 配置）
        """
        self.model = model
        self.api_base = api_base or OLLAMA_API_BASE
        
        logger.info(f"🤖 Ollama Vision Extractor 初始化: model={model}")
    
    async def check_model_available(self) -> bool:
        """
        检查模型是否可用
        
        Returns:
            bool: 模型是否存在
        """
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{OLLAMA_API_TAGS}/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = data.get("models", [])
                        for m in models:
                            if m.get("name") == self.model:
                                logger.info(f"✅ Vision 模型可用: {self.model}")
                                return True
                        
                        logger.warning(f"⚠️ 模型 {self.model} 不存在")
                        return False
        except Exception as e:
            logger.error(f"❌ 检查模型失败: {e}")
            return False
    
    def pdf_page_to_image(self, pdf_path: str, page_num: int = 1) -> Optional[str]:
        """
        将 PDF 页面转换为 Base64 图片
        
        使用 PyMuPDF (fitz) 只切割指定页面
        
        Args:
            pdf_path: PDF 文件路径
            page_num: 页码（默认第一页）
            
        Returns:
            str: Base64 编码的 PNG 图片
        """
        try:
            import fitz  # PyMuPDF
            
            logger.info(f"📄 正在切割 PDF Page {page_num}...")
            
            doc = fitz.open(pdf_path)
            
            if page_num < 1 or page_num > len(doc):
                logger.error(f"❌ 页码无效: {page_num} (总页数: {len(doc)})")
                doc.close()
                return None
            
            # 获取指定页面
            page = doc[page_num - 1]
            
            # 转换为图片（高分辨率）
            # 🌟 zoom = 2.0 高分辨率，重要！确保 OCR 准确率
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            
            # 转换为 PNG bytes
            img_bytes = pix.tobytes("png")
            
            # Base64 编码
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")
            
            doc.close()
            
            logger.info(f"   ✅ Page {page_num} 已转为图片 ({len(img_base64)} chars base64)")
            return img_base64
            
        except ImportError:
            logger.error("❌ PyMuPDF (fitz) 未安装")
            return None
        except Exception as e:
            logger.error(f"❌ PDF 切割失败: {e}")
            return None
    
    async def extract_from_image(
        self,
        image_base64: str,
        prompt: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        使用 Vision LLM 提取图片中的信息
        
        Args:
            image_base64: Base64 编码的图片
            prompt: 自定义 prompt
            
        Returns:
            Dict: 提取的结构化数据
        """
        try:
            import aiohttp
            
            # 默认 prompt（封面提取）
            if not prompt:
                prompt = """
你是一个精準的財報封面解析器。请从这张港股年报封面图片中提取以下信息：

请提取：
1. stock_code: 股票代碼（4-5位数字，如 "00001"）
2. year: 财报年份（如 "2023"）
3. name_en: 公司英文名
4. name_zh: 公司中文名

⚠️ 规则：
- stock_code 必须是纯数字（不要带 ".HK"）
- 如果找不到某项，填 null

只返回 JSON，不要解释：
{
  "stock_code": "00001",
  "year": 2023,
  "name_en": "CK Hutchison Holdings Limited",
  "name_zh": "長江和記實業有限公司"
}
"""
            
            # 🌟 使用 Ollama 原生 API (/api/chat)
            # qwen3-vl 在原生 API 上支持更好
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_base64]  # 🌟 Ollama 原生格式
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0.0
                }
            }
            
            logger.info(f"   🤖 正在调用 Vision LLM (Ollama 原生 API): {self.model}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{OLLAMA_API_TAGS}/chat",  # 🌟 使用原生 API
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=600)  # 🌟 10 分钟（高分辨率 zoom=2.0）
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"❌ Ollama API 错误: {resp.status}")
                        text = await resp.text()
                        logger.debug(f"   响应: {text[:500]}")
                        return None
                    
                    data = await resp.json()
                    
                    # 解析响应（Ollama 原生格式）
                    content = data.get("message", {}).get("content", "")
                    
                    if not content:
                        logger.error("❌ Vision LLM 未返回内容")
                        return None
                    
                    logger.debug(f"   📝 Vision LLM 响应: {content[:500]}")
                    
                    # 尝试解析 JSON
                    # 清理可能的 markdown 标记
                    content_clean = content.strip()
                    if content_clean.startswith("```json"):
                        content_clean = content_clean[7:]
                    if content_clean.startswith("```"):
                        content_clean = content_clean[3:]
                    if content_clean.endswith("```"):
                        content_clean = content_clean[:-3]
                    content_clean = content_clean.strip()
                    
                    # 解析 JSON
                    result = json.loads(content_clean)
                    
                    # 验证和清理
                    if result.get("stock_code"):
                        stock_code = str(result["stock_code"])
                        # 清理：移除非数字
                        stock_code = ''.join(c for c in stock_code if c.isdigit())
                        # 补零至 5 位
                        result["stock_code"] = stock_code.zfill(5) if len(stock_code) >= 4 else None
                    
                    if result.get("year"):
                        year = result["year"]
                        if isinstance(year, str):
                            result["year"] = int(year) if year.isdigit() else None
                    
                    logger.info(f"   ✅ 提取成功: stock={result.get('stock_code')}, year={result.get('year')}")
                    
                    return result
                    
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失败: {e}")
            logger.debug(f"   原始内容: {content}")
            return None
        except Exception as e:
            logger.error(f"❌ Vision 提取失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def extract_cover_from_pdf(
        self,
        pdf_path: str,
        max_page: int = 2  # 🌟 最多尝试 Page 1 和 Page 2
    ) -> Optional[Dict[str, Any]]:
        """
        从 PDF 封面提取信息（完整流程）
        
        🌟 改进：先用 Page 1，失败才 fallback 到 Page 2
        不会超过 Page 2
        
        Args:
            pdf_path: PDF 文件路径
            max_page: 最大尝试页码（默认 2）
            
        Returns:
            Dict: {stock_code, year, name_en, name_zh}
        """
        logger.info(f"🎯 开始 Vision 提取封面...")
        
        # Step 1: 检查模型可用
        if not await self.check_model_available():
            logger.error("❌ Vision 模型不可用，跳过提取")
            return None
        
        # Step 2: 🌟 先尝试 Page 1
        for page_num in range(1, max_page + 1):
            logger.info(f"   📄 正在尝试 Page {page_num}...")
            
            # PDF → 图片
            image_base64 = self.pdf_page_to_image(pdf_path, page_num)
            
            if not image_base64:
                logger.warning(f"   ⚠️ Page {page_num} 切割失败，尝试下一页...")
                continue
            
            # Vision LLM 提取
            result = await self.extract_from_image(image_base64)
            
            if result:
                stock_code = result.get("stock_code")
                year = result.get("year")
                name_en = result.get("name_en")
                name_zh = result.get("name_zh")
                
                # 🌟 检查是否有有效数据
                if stock_code or year or name_en or name_zh:
                    logger.info(f"   ✅ Page {page_num} 提取成功: stock={stock_code}, year={year}, name={name_en or name_zh}")
                    return result
                else:
                    logger.warning(f"   ⚠️ Page {page_num} 返回空数据，尝试下一页...")
            else:
                logger.warning(f"   ⚠️ Page {page_num} Vision 提取失败，尝试下一页...")
        
        # 所有页面都失败
        logger.warning(f"⚠️ Page 1-{max_page} Vision 提取全部失败")
        return None


# ============================================================
# 使用示例
# ============================================================

async def demo_usage():
    """示例：如何使用 OllamaVisionExtractor"""
    
    extractor = OllamaVisionExtractor()
    
    # 测试提取
    pdf_path = "/app/data/uploads/20260413_013147_stock_00001_2023.pdf"
    
    result = await extractor.extract_cover_from_pdf(pdf_path)
    
    print(f"提取结果: {result}")


if __name__ == "__main__":
    asyncio.run(demo_usage())