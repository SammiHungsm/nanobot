"""
Vision API Client - 统一的 Vision API 呼叫器

🌟 策略：全面使用云端 API（Qwen-VL-Max），放弃本地 Ollama Vision
优势：
1. 解放本地 GPU VRAM
2. 图表解析精度更高
3. 架构更简洁

支持的任务类型：
- cover_extraction: 提取封面 stock_code, year, name_en, name_zh
- chart_to_table: 图表转 Markdown 表格

API 配置：
- DashScope (阿里云): qwen-vl-max, qwen-vl-plus
- OpenAI: gpt-4o, gpt-4o-mini
"""

import os
import io
import json
import base64
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from loguru import logger
import aiohttp


class VisionAPIClient:
    """
    统一的 Vision API 呼叫器
    
    支持：
    - DashScope (Qwen-VL-Max)
    - OpenAI (GPT-4o)
    """
    
    # API 配置
    DASHSCOPE_API_BASE = os.getenv("DASHSCOPE_API_BASE", "https://coding.dashscope.aliyuncs.com/v1")
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # 🌟 推荐模型（图表解析精度高）
    DEFAULT_MODEL = "qwen-vl-max"  # 或 gpt-4o
    
    # 任务类型对应的 Prompt
    TASK_PROMPTS = {
        "cover_extraction": """
你是一个精準的財報封面解析器。请从这张港股年报封面图片中提取以下信息：

请提取：
1. stock_code: 股票代碼（4-5位数字，如 "00001"）
2. year: 财报年份（如 "2023"）
3. name_en: 公司英文名
4. name_zh: 公司中文名

⚠️ 规则：
- stock_code 必须是纯数字（不要带 ".HK"）
- 如果找不到某项，填 null
- 只输出 JSON，不要解释

输出格式：
{
  "stock_code": "00001",
  "year": 2023,
  "name_en": "CK Hutchison Holdings Limited",
  "name_zh": "長江和記實業有限公司"
}
""",
        "chart_to_table": """
你是一个極度嚴謹的金融數據錄入專家。
请仔细观察这张图表，并将图表中的所有数据转换成 Markdown 表格格式。

⚠️ 嚴格规则：
1. 绝对不允许猜测或捏造数据。如果你看不清楚某个数值，请填入 "N/A" 或 "无法辨識"。
2. 必须包含准确的表头（如年份、项目、金额、百分比）。
3. 如果是饼图/环形图，要包含所有分类及其百分比。
4. 如果是折线图/柱状图，要包含所有数据点的数值。
5. 只输出 Markdown 表格，不需要任何解释。

示例输出格式：
| 年份 | 项目 | 金额 (HKD) | 百分比 |
|------|------|-----------|--------|
| 2023 | 欧洲 | 231,679 | 50% |
| 2023 | 亚洲 | 80,214 | 17% |
| 2023 | 加拿大 | 3,862 | 1% |
""",
        "page_summary": """
请观察这张财务报告页面，并提取以下关键信息：

1. 页面主题：这页主要讲什么内容？
2. 关键数据：如果有表格或图表，请提取主要数据
3. 重要数字：营收、利润、资产等关键数值

请以结构化的方式输出。
"""
    }
    
    def __init__(self, model: str = None, api_base: str = None, api_key: str = None):
        """
        初始化
        
        Args:
            model: Vision 模型名称（默认 qwen-vl-max）
            api_base: API endpoint（默认 DashScope）
            api_key: API key（默认从环境变量读取）
        """
        self.model = model or self.DEFAULT_MODEL
        self.api_base = api_base or self.DASHSCOPE_API_BASE
        self.api_key = api_key or self.DASHSCOPE_API_KEY
        
        if not self.api_key:
            logger.warning("⚠️ Vision API Key 未配置，请设置 DASHSCOPE_API_KEY 环境变量")
        
        logger.info(f"🤖 Vision API Client 初始化: model={self.model}, api_base={self.api_base}")
    
    def pdf_page_to_image(self, pdf_path: str, page_num: int = 1) -> Optional[str]:
        """
        将 PDF 页面转换为 Base64 图片
        
        Args:
            pdf_path: PDF 文件路径
            page_num: 页码
            
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
            
            page = doc[page_num - 1]
            
            # 🌟 zoom=2.0 高分辨率（重要！确保 OCR 准确率）
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            
            img_bytes = pix.tobytes("png")
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
    
    async def analyze_image(
        self,
        image_base64: str,
        task_type: str = "cover_extraction",
        custom_prompt: str = None,
        timeout: int = 60
    ) -> Optional[Dict[str, Any]]:
        """
        统一的 Vision API 呼叫
        
        Args:
            image_base64: Base64 编码的图片
            task_type: 任务类型（cover_extraction / chart_to_table）
            custom_prompt: 自定义 Prompt（可选）
            timeout: 超时时间（秒）
            
        Returns:
            Dict: 解析结果
        """
        if not self.api_key:
            logger.error("❌ API Key 未配置")
            return None
        
        # 获取对应任务的 Prompt
        prompt = custom_prompt or self.TASK_PROMPTS.get(task_type)
        
        if not prompt:
            logger.error(f"❌ 未知的任务类型: {task_type}")
            return None
        
        logger.info(f"   🤖 正在调用 Vision API ({self.model}) 处理 {task_type}...")
        
        try:
            # 🌟 使用 OpenAI 兼容格式（DashScope 支持）
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                        ]
                    }
                ],
                "temperature": 0.0,
                "max_tokens": 2000
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"❌ API 错误 ({resp.status}): {error_text[:500]}")
                        return None
                    
                    data = await resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    if not content:
                        logger.error("❌ API 未返回内容")
                        return None
                    
                    logger.debug(f"   📝 API 响应: {content[:300]}")
                    
                    # 🌟 根据任务类型处理结果
                    if task_type == "cover_extraction":
                        return self._parse_cover_result(content)
                    elif task_type == "chart_to_table":
                        return self._parse_chart_result(content)
                    else:
                        return {"raw_content": content}
                        
        except asyncio.TimeoutError:
            logger.error(f"❌ API 超时 ({timeout}s)")
            return None
        except Exception as e:
            logger.error(f"❌ API 调用失败: {e}")
            return None
    
    def _parse_cover_result(self, content: str) -> Optional[Dict[str, Any]]:
        """解析封面提取结果"""
        try:
            # 清理 markdown 标记
            content_clean = content.strip()
            if content_clean.startswith("```json"):
                content_clean = content_clean[7:]
            if content_clean.startswith("```"):
                content_clean = content_clean[3:]
            if content_clean.endswith("```"):
                content_clean = content_clean[:-3]
            content_clean = content_clean.strip()
            
            result = json.loads(content_clean)
            
            # 验证和清理
            if result.get("stock_code"):
                stock_code = str(result["stock_code"])
                stock_code = ''.join(c for c in stock_code if c.isdigit())
                result["stock_code"] = stock_code.zfill(5) if len(stock_code) >= 4 else None
            
            if result.get("year"):
                year = result["year"]
                if isinstance(year, str):
                    result["year"] = int(year) if year.isdigit() else None
            
            logger.info(f"   ✅ 封面提取成功: stock={result.get('stock_code')}, year={result.get('year')}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失败: {e}")
            return None
    
    def _parse_chart_result(self, content: str) -> Dict[str, Any]:
        """解析图表提取结果"""
        # 图表结果通常是 Markdown 表格，直接返回
        logger.info(f"   ✅ 图表提取成功 (Markdown)")
        return {
            "markdown_table": content,
            "type": "chart_to_table"
        }
    
    async def extract_cover_from_pdf(
        self,
        pdf_path: str,
        max_page: int = 2,
        timeout: int = 120
    ) -> Optional[Dict[str, Any]]:
        """
        从 PDF 封面提取信息
        
        🌟 改进：先尝试 Page 1，失败才 fallback 到 Page 2
        
        Args:
            pdf_path: PDF 文件路径
            max_page: 最大尝试页码
            timeout: API 超时时间
            
        Returns:
            Dict: {stock_code, year, name_en, name_zh}
        """
        logger.info(f"🎯 开始 Vision API 提取封面...")
        
        # 🌟 先尝试 Page 1
        for page_num in range(1, max_page + 1):
            logger.info(f"   📄 正在尝试 Page {page_num}...")
            
            # PDF → 图片
            image_base64 = self.pdf_page_to_image(pdf_path, page_num)
            
            if not image_base64:
                logger.warning(f"   ⚠️ Page {page_num} 切割失败，尝试下一页...")
                continue
            
            # Vision API 提取
            result = await self.analyze_image(
                image_base64,
                task_type="cover_extraction",
                timeout=timeout
            )
            
            if result:
                stock_code = result.get("stock_code")
                year = result.get("year")
                name_en = result.get("name_en")
                name_zh = result.get("name_zh")
                
                # 检查是否有有效数据
                if stock_code or year or name_en or name_zh:
                    logger.info(f"   ✅ Page {page_num} 提取成功: stock={stock_code}, year={year}")
                    return result
                else:
                    logger.warning(f"   ⚠️ Page {page_num} 返回空数据，尝试下一页...")
        
        logger.warning(f"⚠️ Page 1-{max_page} Vision API 提取全部失败")
        return None
    
    async def extract_chart_from_pdf_page(
        self,
        pdf_path: str,
        page_num: int,
        timeout: int = 120
    ) -> Optional[Dict[str, Any]]:
        """
        从 PDF 页面提取图表数据
        
        Args:
            pdf_path: PDF 文件路径
            page_num: 页码
            timeout: API 超时时间
            
        Returns:
            Dict: {markdown_table, type}
        """
        logger.info(f"📊 开始 Vision API 提取图表 Page {page_num}...")
        
        # PDF → 图片
        image_base64 = self.pdf_page_to_image(pdf_path, page_num)
        
        if not image_base64:
            logger.error(f"❌ Page {page_num} 切割失败")
            return None
        
        # Vision API 提取图表
        result = await self.analyze_image(
            image_base64,
            task_type="chart_to_table",
            timeout=timeout
        )
        
        if result:
            logger.info(f"   ✅ Page {page_num} 图表提取成功")
        else:
            logger.warning(f"   ⚠️ Page {page_num} 图表提取失败")
        
        return result


# ============================================================
# 使用示例
# ============================================================

async def demo_usage():
    """示例：如何使用 VisionAPIClient"""
    
    client = VisionAPIClient(model="qwen-vl-max")
    
    # 测试封面提取
    pdf_path = "/app/data/uploads/stock_00001_2023.pdf"
    result = await client.extract_cover_from_pdf(pdf_path)
    print(f"封面提取结果: {result}")
    
    # 测试图表提取
    chart_result = await client.extract_chart_from_pdf_page(pdf_path, page_num=54)
    print(f"图表提取结果: {chart_result}")


if __name__ == "__main__":
    asyncio.run(demo_usage())