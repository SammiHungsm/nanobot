"""
PDF Core - LlamaParse 统一封装层 (v3.2)

🎯 简化架构：
- 移除 OpenDataLoader Hybrid
- 移除 Docling GPU/CPU
- 只使用 LlamaParse Cloud API

优势：
- ✅ 支持 130+ 格式（PDF, DOCX, PPTX 等）
- ✅ 支持本地文件上传
- ✅ Agentic OCR（高精度）
- ✅ 内置异步支持
- ✅ job_id 缓存（避免重复扣费）
- ✅ **完整 Raw Output 保存（按 PDF 文件名分文件夹）**
- ✅ **图片下载并保存到本地**

Usage:
    from nanobot.core.pdf_core import PDFParser
    
    # 同步解析（自动保存所有 raw output）
    parser = PDFParser()
    result = parser.parse("report.pdf")
    
    # 异步解析
    result = await parser.parse_async("report.pdf")
    
    # URL 解析
    result = parser.parse_url("https://example.com/report.pdf")
    
    # 从已保存的 raw output 加载（不扣费）
    result = parser.load_from_raw_output("report.pdf", "job_xxx")
"""

import os
import json
import asyncio
import tempfile
import httpx
import re  # 🌟 v3.8: 用于修正 Markdown 图片路径
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from loguru import logger


# ===========================================
# DateTimeEncoder - 处理 datetime 序列化
# ===========================================

class DateTimeEncoder(json.JSONEncoder):
    """自定义 JSON Encoder，处理 datetime 对象"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# ===========================================
# 环境变量
# ===========================================

def get_llamaparse_api_key() -> Optional[str]:
    """获取 Llama Cloud API Key"""
    return os.environ.get("LLAMA_CLOUD_API_KEY")


def get_llamaparse_tier() -> str:
    """获取解析层级（默认 agentic）"""
    return os.environ.get("LLAMAPARSE_TIER", "agentic")


def get_data_dir() -> str:
    """
    获取 Raw Data 存储目录
    
    Returns:
        str: data/raw 目录路径
    """
    return os.environ.get("DATA_DIR", "/app/data/raw")


def get_raw_output_dir(pdf_filename: str = None, doc_id: str = None) -> Path:
    """
    获取 LlamaParse Raw Output 存储目录
    
    🌟 v4.0: 优先使用 doc_id 命名文件夹（统一命名逻辑）
    
    结构：
    data/raw/
    └── llamaparse/
        └── 3SBIO_8875691f/          ← 按 doc_id（统一命名）
            ├── job_xxx.json         ← 完整的 API 响应
            ├── job_xxx_meta.json    ← 元数据
            ├── markdown.md          ← 完整 Markdown（方便查看）
            ├── markdown_page1.md    ← 每页 Markdown
            ├── images/              ← 图片文件夹
                ├── page_1.jpg
                ├── page_2.jpg
                └── ...
    
    Args:
        pdf_filename: PDF 文件名（不含路径）- 用于向后兼容
        doc_id: 🌟 文档 ID（优先使用，统一命名）
        
    Returns:
        Path: data/raw/llamaparse/{doc_id or pdf_filename} 目录
    """
    data_dir = Path(get_data_dir())
    raw_output_dir = data_dir / "llamaparse"
    
    # 🌟 v4.0: 优先使用 doc_id 命名（统一命名逻辑）
    folder_name = doc_id or (Path(pdf_filename).stem if pdf_filename else None)
    
    if folder_name:
        raw_output_dir = raw_output_dir / folder_name
    
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    return raw_output_dir


# ===========================================
# 统一的输出结构
# ===========================================

@dataclass
class PDFParseResult:
    """
    🎯 统一的 PDF 解析结果结构
    
    与 OpenDataLoader 的旧结构保持兼容，便于现有代码迁移。
    """
    file_path: str
    total_pages: int
    markdown: str  # 完整的 Markdown 文本
    artifacts: List[Dict[str, Any]]  # 页面级别的 artifacts
    tables: List[Dict[str, Any]]  # 表格列表
    images: List[Dict[str, Any]]  # 图片列表（包含本地路径）
    metadata: Dict[str, Any]  # 元数据
    
    # 🌟 LlamaParse 特有
    job_id: Optional[str] = None  # 保存 job_id 避免重复扣费
    tier: str = "agentic"
    
    # 🌟 Raw Output 路径
    raw_output_dir: Optional[str] = None  # 保存原始 API 响应的目录


# ===========================================
# PDF Parser 类（LlamaParse only）
# ===========================================

class PDFParser:
    """
    PDF Parser - LlamaParse only
    
    🌟 简化架构，移除所有 Hybrid/Docling/OpenDataLoader 依赖
    
    🌟 **完整保存 Raw Output 到 data/raw/llamaparse/{pdf_filename}/**
    
    使用方式：
    1. 同步解析：parser.parse("file.pdf")
    2. 异步解析：await parser.parse_async("file.pdf")
    3. URL 解析：parser.parse_url("https://...")
    4. 从 raw output 加载：parser.load_from_raw_output("report.pdf", "job_xxx")（不扣费）
    """
    
    def __init__(
        self,
        api_key: str = None,
        tier: str = None,
        enable_images: bool = True,
        enable_tables: bool = True,
        save_raw_output: bool = True,  # 🌟 默认保存 raw output
        download_images: bool = True   # 🌟 默认下载图片到本地
    ):
        """
        初始化
        
        Args:
            api_key: Llama Cloud API Key（默认从环境变量）
            tier: 解析层级（默认从环境变量，或 "agentic"）
                - "agentic": Agentic OCR（高精度）
                - "cost_effective": 平衡模式
                - "fast": 快速模式
            enable_images: 是否提取图片
            enable_tables: 是否提取表格
            save_raw_output: 是否保存原始 API 响应到 data/raw（默认 True）
            download_images: 是否下载图片到本地（默认 True）
        """
        self.api_key = api_key or get_llamaparse_api_key()
        self.tier = tier or get_llamaparse_tier()
        self.enable_images = enable_images
        self.enable_tables = enable_tables
        self.save_raw_output = save_raw_output
        self.download_images = download_images
        
        if not self.api_key:
            raise ValueError(
                "❌ LLAMA_CLOUD_API_KEY 未设置！\n"
                "请在 .env 文件中添加：\n"
                "LLAMA_CLOUD_API_KEY=llx-your-api-key\n"
                "获取 API Key: https://cloud.llamaindex.ai"
            )
        
        # 导入 LlamaParse SDK
        try:
            from llama_cloud import LlamaCloud, AsyncLlamaCloud
            from llama_cloud.types.parsing_create_params import OutputOptions
            import httpx
            
            # 🌟 v3.16: 使用 httpx.Timeout 确保长超时
            http_timeout = httpx.Timeout(
                connect=60.0,
                read=600.0,
                write=600.0,
                pool=60.0
            )
            
            self.client = LlamaCloud(
                api_key=self.api_key,
                timeout=http_timeout,
                max_retries=2
            )
            self.async_client = AsyncLlamaCloud(
                api_key=self.api_key,
                timeout=http_timeout,
                max_retries=2
            )
            
            # 🌟 v3.16: OutputOptions 强制保存图片
            self.output_options = OutputOptions(
                images_to_save=["embedded", "screenshot"]  # 强制保存嵌入图片和截图
            )
            
            logger.info(f"✅ PDFParser 初始化完成 (tier={self.tier}, images_to_save=[embedded,screenshot], timeout=600s)")
        except ImportError as e:
            raise ImportError(
                f"❌ llama_cloud SDK 未安装！\n"
                "请运行: pip install llama-cloud>=2.4.0\n"
                f"错误: {e}"
            )
    
    # ===========================================
    # 同步方法
    # ===========================================
    
    def parse(self, file_path: str, doc_id: str = None) -> PDFParseResult:
        """
        解析本地 PDF 文件
        
        🌟 v4.0: 接受 doc_id 参数，统一文件夹命名
        
        Args:
            file_path: PDF 文件路径
            doc_id: 🌟 文档 ID（用于文件夹命名，统一命名逻辑）
            
        Returns:
            PDFParseResult
        """
        import httpx
        
        logger.info(f"🚀 LlamaParse 解析: {file_path} (doc_id={doc_id})")
        
        # 1. 上传文件
        file_obj = self.client.files.create(
            file=Path(file_path),
            purpose="parse"
        )
        file_id = file_obj.id
        logger.info(f"   ✅ 文件上传成功: file_id={file_id}")
        
        # 2. 创建解析任务（🌟 强制保存图片）
        job = self.client.parsing.create(
            tier=self.tier,
            version="latest",
            file_id=file_id,
            output_options=self.output_options
        )
        job_id = job.id
        logger.info(f"   🔍 解析任务创建: job_id={job_id}")
        
        # 3. 等待完成
        logger.info("   ⏳ 等待解析完成...")
        self.client.parsing.wait_for_completion(
            job_id=job_id,
            polling_interval=2.0,
            max_interval=10.0,
            timeout=600.0,
            verbose=True
        )
        logger.info(f"   ✅ 解析完成")
        
        # 4. 获取结果（🌟 v3.18: 使用 expand 参数获取图片元数据）
        response = self.client.parsing.get(
            job_id=job_id,
            expand=["text", "markdown", "items", "images_content_metadata"]  # 🌟 必须包含 images_content_metadata
        )
        logger.info(f"   ✅ 结果获取完成")
        
        # 5. 保存 raw output
        pdf_filename = Path(file_path).name
        # 🌟 v4.0: 传入 doc_id，统一文件夹命名
        raw_output_dir = self._save_full_raw_output(response, pdf_filename, doc_id=doc_id)
        
        # 6. 提取结果
        result = self._extract_result(response, file_path)
        result.raw_output_dir = str(raw_output_dir)
        
        # 7. 更新图片路径
        result = self._update_image_paths(result, raw_output_dir)
        
        logger.info(
            f"✅ 解析完成: {result.total_pages} 页, "
            f"{len(result.tables)} 个表格, {len(result.images)} 张图片"
        )
        
        return result
    
    def parse_url(self, url: str) -> PDFParseResult:
        """
        解析 URL PDF
        
        🌟 自动保存所有 raw output
        
        Args:
            url: PDF URL
            
        Returns:
            PDFParseResult
        """
        logger.info(f"🚀 LlamaParse 解析 URL: {url}")
        
        # 从 URL 提取文件名
        url_filename = Path(url).name or "url_document.pdf"
        
        # 创建解析任务
        # 🌟 v3.12: 添加 output_options.images_to_save 以获取实际图片
        from llama_cloud.types.parsing_create_params import OutputOptions
        
        output_opts = OutputOptions(
            images_to_save=["screenshot", "embedded"]  # 🌟 获取截图和嵌入图片
        )
        
        job = self.client.parsing.create(
            tier=self.tier,
            version="latest",
            source_url=url,
            output_options=output_opts  # 🌟 v3.12: 启用图片保存
        )
        job_id = job.id
        logger.info(f"   🔍 解析任务创建: job_id={job_id}, images_to_save=[screenshot,embedded]")
        
        # 🌟 v3.6: 使用 SDK 内置的 wait_for_completion
        response = self.client.parsing.wait_for_completion(
            job_id=job_id,
            polling_interval=2.0,
            max_interval=10.0,
            timeout=600.0,
            verbose=True
        )
        
        # 🌟 获取完整结果
        response = self.client.parsing.get(
            job_id=job_id,
            expand=["text", "markdown", "items"]
        )
        
        # 🌟 保存完整的 raw output
        raw_output_dir = self._save_full_raw_output(response, url_filename)
        
        # 🌟 下载图片
        if self.download_images:
            self._download_images(response, raw_output_dir)
        
        # 提取结果
        result = self._extract_result(response, url)
        result.raw_output_dir = str(raw_output_dir)
        
        # 更新图片路径
        result = self._update_image_paths(result, raw_output_dir)
        
        logger.info(
            f"✅ 解析完成: {result.total_pages} 页, "
            f"{len(result.tables)} 个表格, {len(result.images)} 张图片"
        )
        
        return result
    
    # ===========================================
    # 异步方法
    # ===========================================
    
    async def parse_async(self, file_path: str, doc_id: str = None) -> PDFParseResult:
        """
        异步解析本地 PDF 文件
        
        🌟 v4.0: 接受 doc_id 参数，统一文件夹命名
        
        Args:
            file_path: PDF 文件路径
            doc_id: 🌟 文档 ID（用于文件夹命名，统一命名逻辑）
            
        Returns:
            PDFParseResult
        """
        import httpx
        
        logger.info(f"🚀 LlamaParse 异步解析: {file_path} (doc_id={doc_id})")
        
        # 1. 上传文件
        file_obj = await self.async_client.files.create(
            file=Path(file_path),
            purpose="parse"
        )
        file_id = file_obj.id
        logger.info(f"   ✅ 文件上传成功: file_id={file_id}")
        
        # 2. 创建解析任务（🌟 强制保存图片）
        job = await self.async_client.parsing.create(
            tier=self.tier,
            version="latest",
            file_id=file_id,
            output_options=self.output_options  # 🌟 v3.16: images_to_save=[embedded, screenshot]
        )
        job_id = job.id
        logger.info(f"   🔍 解析任务创建: job_id={job_id}")
        
        # 3. 等待完成
        logger.info("   ⏳ 等待解析完成...")
        try:
            await self.async_client.parsing.wait_for_completion(
                job_id=job_id,
                polling_interval=2.0,
                max_interval=10.0,
                timeout=600.0,
                verbose=True
            )
            logger.info(f"   ✅ 解析完成")
        except Exception as e:
            logger.error(f"   ❌ wait_for_completion 失败: {e}")
            raise
        
        # 4. 获取结果（🌟 v3.18: 使用 expand 参数获取图片元数据）
        response = await self.async_client.parsing.get(
            job_id=job_id,
            expand=["text", "markdown", "items", "images_content_metadata"]  # 🌟 必须包含 images_content_metadata
        )
        logger.info(f"   ✅ 结果获取完成")
        
        # 5. 保存 raw output
        pdf_filename = Path(file_path).name
        # 🌟 v4.0: 传入 doc_id，统一文件夹命名
        raw_output_dir = self._save_full_raw_output(response, pdf_filename, doc_id=doc_id)
        logger.info(f"   ✅ Raw output 目录: {raw_output_dir}")
        
        # 6. 🌟 v3.17: 下载图片（使用纯 HTTP requests 调用 API endpoint）
        images_dir = raw_output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        images_result = []
        image_path_map = {}  # 🌟 新增：Markdown 路径 → 实际文件名映射
        
        if self.download_images and self.enable_images:
            logger.info(f"   📸 开始下载图片...")
            images_result, image_path_map = await self._download_images_from_response(response, images_dir, job_id)
            logger.info(f"   ✅ 成功下载 {len(images_result)} 张图片")
        
        # 🌟 新增：修复 Markdown 中的图片路径
        if image_path_map:
            logger.info(f"   🔧 修复 Markdown 图片路径...")
            self._fix_markdown_image_paths(raw_output_dir, image_path_map)
        
        # 7. 提取结果
        result = self._extract_result(response, file_path)
        result.images = images_result  # 🌟 使用下载后的图片列表
        result.raw_output_dir = str(raw_output_dir)
        
        logger.info(
            f"✅ 解析完成: {result.total_pages} 页, "
            f"{len(result.tables)} 个表格, {len(result.images)} 张图片"
        )
        
        return result
    
    async def _download_images_from_response(
        self, 
        response: Any, 
        images_dir: Path,
        job_id: str
    ) -> tuple[List[Dict], Dict[str, str]]:
        """
        🌟 v3.20: 异步并行下载图片并返回路径映射
        
        使用 asyncio.gather() 并行执行所有 HTTP 请求
        将原本串行的下载时间 (n x 单张时间) 缩短到只取最慢的那张
        
        Args:
            response: ParsingGetResponse
            images_dir: 图片保存目录
            job_id: LlamaParse job_id
            
        Returns:
            tuple: (图片列表, Markdown路径→实际文件名映射)
        """
        import httpx
        import re
        import asyncio
        
        images = []
        image_path_map = {}  # 🌟 Markdown 中引用的路径 → 实际保存的文件名
        
        # 1. 检查 API 是否有回传图片元数据
        if not hasattr(response, 'images_content_metadata') or not response.images_content_metadata:
            logger.warning("   ⚠️ 找不到 images_content_metadata（请确定 expand 有包含该栏位）")
            return images, image_path_map
        
        image_list = response.images_content_metadata.images
        if not image_list:
            logger.warning("   ⚠️ 图片列表为空")
            return images, image_path_map

        logger.info(f"   📸 找到 {len(image_list)} 个图片，开始并行下载...")
        
        # 🌟 从 Markdown 中提取所有图片引用路径
        markdown_full = getattr(response, 'markdown_full', '') or ''
        # 將原本搵 images/ 嘅 regex 換成呢個，去 match 原始嘅 LlamaParse 格式
        markdown_refs = re.findall(r'!\[.*?\]\((page_[^\)]+)\)', markdown_full)
        logger.info(f"   📝 Markdown 中引用了 {len(markdown_refs)} 个图片路径")

        # 🌟 定义单一图片下载任务
        async def download_single_image(client: httpx.AsyncClient, img: Any, idx: int) -> Optional[Dict]:
            """下载单张图片"""
            actual_filename = getattr(img, 'filename', f'img_{idx}.jpg')
            url = getattr(img, 'presigned_url', None)
            # 🌟 v4.3: 尝试多种属性名获取页码（LlamaParse API 版本差异）
            # 优先尝试 page_number，然后 page，最后从文件名提取
            page_number = getattr(img, 'page_number', None)
            if page_number is None:
                page_number = getattr(img, 'page', None)
            if page_number is None:
                # 🌟 从文件名提取页码（如 page_123.png, img_p45.jpg）
                import re as re_module
                match = re_module.search(r'(?:page|p)[_\-]?(\d+)', actual_filename, re_module.IGNORECASE)
                if match:
                    page_number = int(match.group(1))
            # 🌟 如果都找不到，默认 0
            if page_number is None:
                page_number = 0
            
            if not url:
                return None
            
            try:
                # 🌟 异步 HTTP GET
                resp = await client.get(url)
                
                if resp.status_code == 200:
                    local_path = images_dir / actual_filename
                    with open(local_path, 'wb') as f:
                        f.write(resp.content)
                    
                    logger.debug(f"      ✅ 下载成功: {actual_filename}")
                    return {
                        "type": "image",
                        "page": page_number,
                        "filename": actual_filename,
                        "local_path": str(local_path),
                        "downloaded": True,
                        "source": "presigned_url"
                    }
                else:
                    logger.warning(f"      ⚠️ HTTP {resp.status_code}: {actual_filename}")
                    return None
                    
            except Exception as e:
                logger.warning(f"      ⚠️ 下载异常 {actual_filename}: {e}")
                return None

        # 🌟 使用 asyncio.gather 并行执行所有 HTTP 请求
        async with httpx.AsyncClient(timeout=60) as client:
            # 创建所有下载任务
            tasks = [
                download_single_image(client, img, idx) 
                for idx, img in enumerate(image_list) 
                if img is not None
            ]
            
            # 🌟 并行执行（所有请求同时发出）
            results = await asyncio.gather(*tasks)
        
        # 🌟 整理结果并建立 mapping
        for res in results:
            if res:
                images.append(res)
                page_number = res["page"]
                actual_filename = res["filename"]
                
                # 创建映射：Markdown 引用路径 → 实际文件名
                for ref in markdown_refs:
                    if f'page_{page_number}' in ref or f'p{page_number}' in ref:
                        image_path_map[ref] = actual_filename
        
        # 🌟 智能映射（如果没有匹配到）
        if not image_path_map and markdown_refs and images:
            logger.info("   🔧 创建智能图片路径映射...")
            for idx, ref in enumerate(markdown_refs):
                if idx < len(images):
                    actual_filename = images[idx]["filename"]
                    image_path_map[ref] = actual_filename
        
        logger.info(f"   ✅ 成功下载 {len(images)} 张图片")
        logger.info(f"   🗺️ 创建了 {len(image_path_map)} 个路径映射")
        
        return images, image_path_map
    
    def _fix_markdown_image_paths(
        self,
        raw_output_dir: Path,
        image_path_map: Dict[str, str]
    ) -> None:
        """
        🌟 v3.19: 修复 Markdown 文件中的图片路径
        
        确保 Markdown 文件可以正确引用 images/ 目录下的图片
        
        Args:
            raw_output_dir: Raw output 目录
            image_path_map: Markdown 路径 → 实际文件名映射
        """
        if not image_path_map:
            return
        
        # 🌟 使用相对路径（Markdown 和 images 在同一层级）
        # 结构：
        # raw_output_dir/
        # ├── markdown.md
        # ├── images/
        # │   └── img_p10_1.jpg
        
        # 修复完整 Markdown
        markdown_full_path = raw_output_dir / "markdown.md"
        if markdown_full_path.exists():
            content = markdown_full_path.read_text(encoding='utf-8')
            
            # 🌟 替换所有旧的图片引用为实际路径
            for old_path, actual_filename in image_path_map.items():
                # 相对路径（Markdown 和 images 同层）
                new_path = f"images/{actual_filename}"
                content = content.replace(old_path, new_path)
            
            markdown_full_path.write_text(content, encoding='utf-8')
            logger.info(f"   ✅ 已修复 {markdown_full_path}")
        
        # 修复每页 Markdown
        for md_file in raw_output_dir.glob("markdown_page*.md"):
            content = md_file.read_text(encoding='utf-8')
            
            for old_path, actual_filename in image_path_map.items():
                # 🌟 相对路径（同一层级）
                new_path = f"images/{actual_filename}"
                content = content.replace(old_path, new_path)
            
            md_file.write_text(content, encoding='utf-8')
            logger.debug(f"   ✅ 已修复 {md_file.name}")
        
        # 🌟 新增：验证图片是否真实存在
        images_dir = raw_output_dir / "images"
        actual_images = list(images_dir.glob("*"))
        logger.info(f"   📸 images 目录实际有 {len(actual_images)} 个文件")
        
        # 🌟 检查 Markdown 中的所有图片引用是否都存在
        if markdown_full_path.exists():
            import re
            refs = re.findall(r'!\[.*?\]\((images/[^\)]+)\)', markdown_full_path.read_text(encoding='utf-8'))
            missing = []
            for ref in refs:
                img_name = ref.replace('images/', '')
                img_path = images_dir / img_name
                if not img_path.exists():
                    missing.append(img_name)
            
            if missing:
                logger.warning(f"   ⚠️ 缺少 {len(missing)} 个图片: {missing[:5]}...")
            else:
                logger.info(f"   ✅ 所有 {len(refs)} 个图片引用都存在")
    
    async def parse_url_async(self, url: str) -> PDFParseResult:
        """
        异步解析 URL PDF
        
        🌟 自动保存所有 raw output
        """
        logger.info(f"🚀 LlamaParse 异步解析 URL: {url}")
        
        url_filename = Path(url).name or "url_document.pdf"
        
        # 创建解析任务
        # 🌟 v3.12: 添加 output_options.images_to_save 以获取实际图片
        from llama_cloud.types.parsing_create_params import OutputOptions
        
        output_opts = OutputOptions(
            images_to_save=["screenshot", "embedded"]  # 🌟 获取截图和嵌入图片
        )
        
        job = await self.async_client.parsing.create(
            tier=self.tier,
            version="latest",
            source_url=url,
            output_options=output_opts  # 🌟 v3.12: 启用图片保存
        )
        job_id = job.id
        logger.info(f"   🔍 解析任务创建: job_id={job_id}, images_to_save=[screenshot,embedded]")
        
        # 🌟 v3.6: 使用 SDK 内置的 wait_for_completion
        response = await self.async_client.parsing.wait_for_completion(
            job_id=job_id,
            polling_interval=2.0,
            max_interval=10.0,
            timeout=600.0,
            verbose=True
        )
        
        # 🌟 获取完整结果
        response = await self.async_client.parsing.get(
            job_id=job_id,
            expand=["text", "markdown", "items"]
        )
        
        # 🌟 保存完整的 raw output
        raw_output_dir = self._save_full_raw_output(response, url_filename)
        
        # 🌟 异步下载图片
        if self.download_images:
            await self._download_images_async(response, raw_output_dir)
        
        # 提取结果
        result = self._extract_result(response, url)
        result.raw_output_dir = str(raw_output_dir)
        
        # 更新图片路径
        result = self._update_image_paths(result, raw_output_dir)
        
        logger.info(
            f"✅ 解析完成: {result.total_pages} 页, "
            f"{len(result.tables)} 个表格, {len(result.images)} 张图片"
        )
        
        return result
    
    # ===========================================
    # 🌟 完整保存 Raw Output（按 PDF 文件名）
    # ===========================================
    
    def _save_full_raw_output(self, response: Any, pdf_filename: str, doc_id: str = None) -> Path:
        """
        保存完整的 API 响应到 data/raw/llamaparse/{doc_id}/
        
        🌟 v4.0: 优先使用 doc_id 命名文件夹（统一命名逻辑）
        
        保存结构：
        data/raw/llamaparse/{doc_id}/
        ├── {job_id}.json          ← 完整的 ParsingGetResponse（所有字段）
        ├── {job_id}_meta.json     ← 元数据（file_path, created_at）
        ├── markdown.md            ← 完整 Markdown（方便查看）
        ├── markdown_page{n}.md    ← 每页 Markdown
        └── images/                ← 图片文件夹（稍后下载）
        
        Args:
            response: LlamaParse ParsingGetResponse
            pdf_filename: PDF 文件名（用于向后兼容）
            doc_id: 🌟 文档 ID（优先使用，统一命名）
            
        Returns:
            Path: 保存的目录路径
        """
        if not self.save_raw_output:
            return None
        
        job_id = response.job.id
        
        # 🌟 v4.0: 优先使用 doc_id 创建目录（统一命名逻辑）
        raw_output_dir = get_raw_output_dir(pdf_filename, doc_id=doc_id)
        
        # 🌟 使用 model_dump() 获取完整的 API 响应
        try:
            if hasattr(response, 'model_dump'):
                raw_dict = response.model_dump()
            elif hasattr(response, 'dict'):
                raw_dict = response.dict()
            else:
                raw_dict = self._manual_serialize_full_response(response)
        except Exception as e:
            logger.warning(f"   ⚠️ model_dump() 失败，使用手动序列化: {e}")
            raw_dict = self._manual_serialize_full_response(response)
        
        # 1. 保存完整的 API 响应 JSON
        raw_json_path = raw_output_dir / f"{job_id}.json"
        with open(raw_json_path, 'w', encoding='utf-8') as f:
            json.dump(raw_dict, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
        logger.info(f"   💾 完整 API 响应已保存: {raw_json_path}")
        
        # 2. 保存元数据
        meta_json_path = raw_output_dir / f"{job_id}_meta.json"
        meta_data = {
            "job_id": job_id,
            "pdf_filename": pdf_filename,
            "tier": self.tier,
            "created_at": datetime.now().isoformat(),
            "parser": "llamaparse",
            "fields_saved": list(raw_dict.keys())  # 🌟 记录保存的所有字段
        }
        with open(meta_json_path, 'w', encoding='utf-8') as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)
        
        # 3. 🌟 保存完整 Markdown（方便查看）
        markdown_full = raw_dict.get("markdown_full", "")
        if markdown_full:
            markdown_path = raw_output_dir / "markdown.md"
            with open(markdown_path, 'w', encoding='utf-8') as f:
                f.write(markdown_full)
            logger.info(f"   💾 Markdown 已保存: {markdown_path}")
        
        # 4. 🌟 保存每页 Markdown（v3.8: 修正图片路径）
        markdown_pages = raw_dict.get("markdown", {}).get("pages", [])
        for page in markdown_pages:
            if page.get("success") and page.get("markdown"):
                page_num = page.get("page_number", 0)
                page_markdown_path = raw_output_dir / f"markdown_page{page_num}.md"
                
                # 🌟 v3.8: 修正图片路径（添加 images/ 前缀）
                markdown_content = page.get("markdown", "")
                # 替换 ![...](page_X_...) 为 ![...](images/page_X_...)
                markdown_content = re.sub(
                    r'!\[([^\]]*)\]\((page_[^)]+)\)',
                    r'![\1](images/\2)',
                    markdown_content
                )
                
                with open(page_markdown_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
        
        # 5. 🌟 保存完整纯文本
        text_full = raw_dict.get("text_full", "")
        if text_full:
            text_path = raw_output_dir / "text.txt"
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(text_full)
            logger.info(f"   💾 Text 已保存: {text_path}")
        
        # 6. 创建图片文件夹
        images_dir = raw_output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"   ✅ Raw output 保存完成: {raw_output_dir}")
        
        return raw_output_dir
    
    def _manual_serialize_full_response(self, response: Any) -> Dict:
        """
        手动序列化完整的 ParsingGetResponse
        
        🌟 保存所有字段（不只是 job 和 markdown_full）
        
        官方 API 返回的字段：
        - job: Job → id, status, tier, created_at, error_message
        - markdown_full: str → 完整 Markdown
        - markdown: Markdown → pages（每页 Markdown）
        - text_full: str → 完纯文本
        - text: Text → pages（每页文本）
        - items: Items → pages（结构化 items，包含表格、标题等）
        - images_content_metadata: ImagesContentMetadata → images（图片元数据）
        - metadata: Metadata → pages（页面元数据）
        - result_content_metadata: Dict → 结果文件元数据
        - job_metadata: Dict → 任务执行元数据
        - raw_parameters: Dict → 原始参数
        """
        result = {}
        
        # 🌟 保存所有字段
        # 1. job
        if hasattr(response, 'job') and response.job:
            job = response.job
            result["job"] = {
                "id": job.id,
                "status": job.status,
                "tier": getattr(job, 'tier', self.tier),
                "created_at": str(job.created_at) if hasattr(job, 'created_at') and job.created_at else None,
                "error_message": getattr(job, 'error_message', None),
                "name": getattr(job, 'name', None),
                "project_id": getattr(job, 'project_id', None),
                "updated_at": str(job.updated_at) if hasattr(job, 'updated_at') and job.updated_at else None,
            }
        
        # 2. markdown_full
        result["markdown_full"] = getattr(response, 'markdown_full', "") or ""
        
        # 3. markdown.pages
        if hasattr(response, 'markdown') and response.markdown:
            markdown_obj = response.markdown
            if hasattr(markdown_obj, 'pages'):
                result["markdown"] = {
                    "pages": [
                        {
                            "page_number": p.page_number,
                            "markdown": getattr(p, 'markdown', "") or "",
                            "success": getattr(p, 'success', True),
                            "error": getattr(p, 'error', None),
                            "header": getattr(p, 'header', None),
                            "footer": getattr(p, 'footer', None),
                        }
                        for p in markdown_obj.pages
                    ]
                }
        
        # 4. text_full
        result["text_full"] = getattr(response, 'text_full', "") or ""
        
        # 5. text.pages
        if hasattr(response, 'text') and response.text:
            text_obj = response.text
            if hasattr(text_obj, 'pages'):
                result["text"] = {
                    "pages": [
                        {
                            "page_number": p.page_number,
                            "text": getattr(p, 'text', "") or "",
                        }
                        for p in text_obj.pages
                    ]
                }
        
        # 6. items.pages（结构化数据）
        if hasattr(response, 'items') and response.items:
            items_obj = response.items
            if hasattr(items_obj, 'pages'):
                result["items"] = {
                    "pages": [
                        self._serialize_items_page(p)
                        for p in items_obj.pages
                    ]
                }
        
        # 7. images_content_metadata（图片元数据）
        if hasattr(response, 'images_content_metadata') and response.images_content_metadata:
            images_meta = response.images_content_metadata
            if hasattr(images_meta, 'images'):
                result["images_content_metadata"] = {
                    "images": [
                        {
                            "filename": img.filename,
                            "index": getattr(img, 'index', 0),
                            "presigned_url": getattr(img, 'presigned_url', None),
                            "category": getattr(img, 'category', None),
                            "content_type": getattr(img, 'content_type', None),
                            "size_bytes": getattr(img, 'size_bytes', None),
                            "bbox": {
                                "x": img.bbox.x if img.bbox else None,
                                "y": img.bbox.y if img.bbox else None,
                                "w": img.bbox.w if img.bbox else None,
                                "h": img.bbox.h if img.bbox else None,
                            } if img.bbox else None,
                        }
                        for img in images_meta.images
                    ],
                    "total_count": getattr(images_meta, 'total_count', 0),
                }
        
        # 8. metadata（页面元数据）
        if hasattr(response, 'metadata') and response.metadata:
            metadata_obj = response.metadata
            if hasattr(metadata_obj, 'pages'):
                result["metadata"] = {
                    "pages": [
                        {
                            "page_number": p.page_number,
                            "confidence": getattr(p, 'confidence', None),
                            "cost_optimized": getattr(p, 'cost_optimized', None),
                            "original_orientation_angle": getattr(p, 'original_orientation_angle', None),
                            "printed_page_number": getattr(p, 'printed_page_number', None),
                            "slide_section_name": getattr(p, 'slide_section_name', None),
                            "speaker_notes": getattr(p, 'speaker_notes', None),
                            "triggered_auto_mode": getattr(p, 'triggered_auto_mode', None),
                        }
                        for p in metadata_obj.pages
                    ]
                }
        
        # 9. result_content_metadata（结果文件元数据）
        if hasattr(response, 'result_content_metadata') and response.result_content_metadata:
            result["result_content_metadata"] = {
                key: {
                    "exists": getattr(meta, 'exists', None),
                    "size_bytes": getattr(meta, 'size_bytes', 0),
                    "presigned_url": getattr(meta, 'presigned_url', None),
                }
                for key, meta in response.result_content_metadata.items()
            }
        
        # 10. job_metadata（🌟 递归处理 datetime）
        job_metadata = getattr(response, 'job_metadata', None)
        if job_metadata:
            result["job_metadata"] = self._serialize_nested_dict(job_metadata)
        else:
            result["job_metadata"] = None
        
        # 11. raw_parameters（🌟 递归处理 datetime）
        raw_parameters = getattr(response, 'raw_parameters', None)
        if raw_parameters:
            result["raw_parameters"] = self._serialize_nested_dict(raw_parameters)
        else:
            result["raw_parameters"] = None
        
        return result
    
    def _serialize_nested_dict(self, obj: Any) -> Any:
        """
        🌟 递归序列化嵌套对象，处理所有 datetime
        
        Args:
            obj: 任意对象（dict, list, datetime, 等）
            
        Returns:
            JSON 可序列化的对象
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._serialize_nested_dict(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._serialize_nested_dict(item) for item in obj]
        elif hasattr(obj, 'model_dump'):
            # Pydantic 对象
            return self._serialize_nested_dict(obj.model_dump())
        elif hasattr(obj, '__dict__'):
            # 普通 Python 对象
            return self._serialize_nested_dict(obj.__dict__)
        else:
            # 基本类型（str, int, float, bool, None）
            return obj
    
    def _serialize_items_page(self, page: Any) -> Dict:
        """
        序列化 items.pages 中的单个页面
        
        🌟 items 包含结构化数据：
        - TextItem: 文本
        - HeadingItem: 标题
        - ListItem: 列表
        - TableItem: 表格
        - ImageItem: 图片
        - CodeItem: 代码
        - LinkItem: 链接
        """
        result = {
            "page_number": page.page_number,
            "success": getattr(page, 'success', True),
            "error": getattr(page, 'error', None),
            "page_width": getattr(page, 'page_width', None),
            "page_height": getattr(page, 'page_height', None),
            "items": [],
        }
        
        if hasattr(page, 'items') and page.items:
            for item in page.items:
                item_dict = {}
                if hasattr(item, 'model_dump'):
                    item_dict = item.model_dump()
                elif hasattr(item, '__dict__'):
                    item_dict = {
                        "type": getattr(item, 'type', 'unknown'),
                        "value": str(item),
                    }
                    # 尝试提取更多字段
                    for attr in ['text', 'level', 'rows', 'cols', 'bbox', 'url', 'src']:
                        if hasattr(item, attr):
                            item_dict[attr] = getattr(item, attr)
                else:
                    item_dict = {"type": "unknown", "value": str(item)}
                
                result["items"].append(item_dict)
        
        return result
    
    # ===========================================
    # 🌟 下载图片到本地
    # ===========================================
    
    def _download_images(self, response: Any, raw_output_dir: Path) -> None:
        """
        同步下载图片到本地
        
        Args:
            response: LlamaParse ParsingGetResponse
            raw_output_dir: Raw output 目录
        """
        images_dir = raw_output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        if not hasattr(response, 'images_content_metadata') or not response.images_content_metadata:
            return
        
        images = response.images_content_metadata.images
        if not images:
            return
        
        logger.info(f"   📥 开始下载 {len(images)} 张图片...")
        
        downloaded = 0
        for img in images:
            # 🌟 v3.5: 跳过 None 元素
            if img is None:
                continue
            url = getattr(img, 'presigned_url', None)
            filename = getattr(img, 'filename', f"image_{getattr(img, 'index', 0)}.png")
            
            if not url:
                continue
            
            try:
                # 下载图片
                response_http = httpx.get(url, timeout=60)
                if response_http.status_code == 200:
                    img_path = images_dir / filename
                    with open(img_path, 'wb') as f:
                        f.write(response_http.content)
                    downloaded += 1
                    logger.debug(f"      ✅ {filename} ({len(response_http.content)} bytes)")
            except Exception as e:
                logger.warning(f"      ⚠️ 下载失败 {filename}: {e}")
        
        logger.info(f"   ✅ 图片下载完成: {downloaded}/{len(images)} 张")
    
    async def _download_images_async(self, response: Any, raw_output_dir: Path) -> None:
        """
        🌟 v3.20: 异步并行下载图片到本地
        
        使用 asyncio.gather() 并行执行所有 HTTP 请求
        """
        import asyncio
        import httpx
        
        images_dir = raw_output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        if not hasattr(response, 'images_content_metadata') or not response.images_content_metadata:
            return
        
        images = response.images_content_metadata.images
        if not images:
            return
        
        logger.info(f"   📥 异步并行下载 {len(images)} 张图片...")

        # 🌟 定义单张图片下载任务
        async def fetch_image(client: httpx.AsyncClient, img: Any) -> int:
            """下载单张图片，返回 1 表示成功，0 表示失败"""
            if img is None:
                return 0
            
            url = getattr(img, 'presigned_url', None)
            filename = getattr(img, 'filename', f"image_{getattr(img, 'index', 0)}.png")
            
            if not url:
                return 0
            
            try:
                response_http = await client.get(url)
                if response_http.status_code == 200:
                    img_path = images_dir / filename
                    with open(img_path, 'wb') as f:
                        f.write(response_http.content)
                    logger.debug(f"      ✅ {filename}")
                    return 1
                else:
                    logger.warning(f"      ⚠️ HTTP {response_http.status_code}: {filename}")
                    return 0
            except Exception as e:
                logger.warning(f"      ⚠️ 下载失败 {filename}: {e}")
                return 0

        # 🌟 使用 asyncio.gather 并行执行所有 HTTP 请求
        async with httpx.AsyncClient(timeout=60) as client:
            tasks = [fetch_image(client, img) for img in images if img is not None]
            results = await asyncio.gather(*tasks)
            downloaded = sum(results)
        
        logger.info(f"   ✅ 图片下载完成: {downloaded}/{len(images)} 张")
    
    def _update_image_paths(self, result: PDFParseResult, raw_output_dir: Path) -> PDFParseResult:
        """
        更新图片路径为本地路径
        
        Args:
            result: PDFParseResult
            raw_output_dir: Raw output 目录
            
        Returns:
            PDFParseResult（更新后的）
        """
        images_dir = raw_output_dir / "images"
        
        for img in result.images:
            # 🌟 v3.5: 跳过 None 元素
            if img is None:
                continue
            filename = img.get("filename", "")
            if filename:
                local_path = images_dir / filename
                if local_path.exists():
                    img["local_path"] = str(local_path)
        
        return result
    
    # ===========================================
    # 🌟 从 Raw Output 加载（不扣费）
    # ===========================================
    
    def load_from_raw_output(self, pdf_filename: str, job_id: str = None, doc_id: str = None) -> PDFParseResult:
        """
        从已保存的 raw output 加载结果（完全不扣费）
        
        🌟 v4.0: 优先使用 doc_id 查找
        
        Args:
            pdf_filename: PDF 文件名（向后兼容）
            job_id: 任务 ID（可选，如果不提供则自动查找最新的）
            doc_id: 🌟 文档 ID（优先使用，统一命名）
            
        Returns:
            PDFParseResult
            
        Raises:
            FileNotFoundError: 如果 raw output 文件不存在
        """
        logger.info(f"📂 从 raw output 加载: {doc_id or pdf_filename}")
        
        # 🌟 v4.0: 优先使用 doc_id 获取目录
        raw_output_dir = get_raw_output_dir(pdf_filename, doc_id=doc_id)
        
        # 2. 如果没有提供 job_id，查找最新的
        if not job_id:
            job_ids = sorted([
                f.stem for f in raw_output_dir.glob("*.json")
                if not f.stem.endswith("_meta")
            ])
            if not job_ids:
                raise FileNotFoundError(f"没有找到 raw output: {raw_output_dir}")
            job_id = job_ids[-1]  # 最新的 job_id
            logger.info(f"   🔍 自动查找最新 job_id: {job_id}")
        
        # 3. 加载 raw JSON
        raw_json_path = raw_output_dir / f"{job_id}.json"
        if not raw_json_path.exists():
            raise FileNotFoundError(f"Raw output 文件不存在: {raw_json_path}")
        
        with open(raw_json_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # 4. 加载元数据
        meta_json_path = raw_output_dir / f"{job_id}_meta.json"
        if meta_json_path.exists():
            with open(meta_json_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)
        else:
            meta_data = {}
        
        # 5. 构建 PDFParseResult
        result = self._build_result_from_raw(raw_data, meta_data.get("pdf_filename", pdf_filename))
        result.raw_output_dir = str(raw_output_dir)
        
        # 6. 更新图片路径
        result = self._update_image_paths(result, raw_output_dir)
        
        logger.info(
            f"✅ 加载完成（不扣费）: {result.total_pages} 页, "
            f"from: {raw_json_path}"
        )
        
        return result
    
    # ===========================================
    # 等待解析完成
    # ===========================================
    
    def _wait_for_completion(self, job_id: str, max_wait: int = 600) -> Any:
        """等待解析任务完成（同步）"""
        import time
        
        start_time = time.time()
        
        while True:
            # 🌟 v3.6: 使用 expand 参数获取完整结果
            response = self.client.parsing.get(
                job_id=job_id,
                expand=["text", "markdown", "items"]  # 🌟 获取完整内容
            )
            status = response.job.status
            
            if status == "COMPLETED":
                logger.info(f"   ✅ 解析完成: job_id={job_id}")
                return response
            
            elif status == "FAILED":
                error_msg = response.job.error_message or "未知错误"
                raise ValueError(f"LlamaParse 解析失败: {error_msg}")
            
            elif status in ["PENDING", "RUNNING"]:
                elapsed = time.time() - start_time
                if elapsed > max_wait:
                    raise TimeoutError(f"解析超时: {max_wait}s")
                
                logger.debug(f"   ⏳ 等待中... status={status}, elapsed={elapsed:.1f}s")
                time.sleep(3)  # 🌟 v3.6: 增加间隔到 3 秒
            
            elif status == "CANCELLED":
                raise ValueError(f"解析任务已取消: job_id={job_id}")
            
            else:
                raise ValueError(f"未知状态: {status}")
    
    async def _wait_for_completion_async(self, job_id: str, max_wait: int = 600) -> Any:
        """等待解析任务完成（异步）"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            # 🌟 v3.6: 使用 expand 参数获取完整结果
            response = await self.async_client.parsing.get(
                job_id=job_id,
                expand=["text", "markdown", "items"]  # 🌟 获取完整内容
            )
            status = response.job.status
            
            if status == "COMPLETED":
                logger.info(f"   ✅ 解析完成: job_id={job_id}")
                return response
            
            elif status == "FAILED":
                error_msg = response.job.error_message or "未知错误"
                raise ValueError(f"LlamaParse 解析失败: {error_msg}")
            
            elif status in ["PENDING", "RUNNING"]:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > max_wait:
                    raise TimeoutError(f"解析超时: {max_wait}s")
                
                logger.debug(f"   ⏳ 异步等待中... status={status}, elapsed={elapsed:.1f}s")
                await asyncio.sleep(3)  # 🌟 v3.6: 增加间隔到 3 秒，减少请求频率
            
            elif status == "CANCELLED":
                raise ValueError(f"解析任务已取消: job_id={job_id}")
            
            else:
                raise ValueError(f"未知状态: {status}")
    
    # ===========================================
    # 提取结果
    # ===========================================
    
    def _extract_result(self, response: Any, file_path: str) -> PDFParseResult:
        """从 ParsingGetResponse 提取结构化结果"""
        # 🌟 v3.5: 安全检查 response
        if response is None:
            raise ValueError("Response is None")
        job = response.job
        if job is None:
            raise ValueError("Job is None in response")
        job_id = job.id
        
        # 提取完整 Markdown
        markdown_full = response.markdown_full or ""
        
        # 如果没有 markdown_full，从 pages 拼接
        if not markdown_full and response.markdown:
            markdown_full = "\n\n".join(
                page.markdown for page in response.markdown.pages
                if hasattr(page, 'markdown') and page.success
            )
        
        # 提取页数
        total_pages = 0
        if response.markdown and response.markdown.pages:
            total_pages = len(response.markdown.pages)
        elif response.items and response.items.pages:
            total_pages = len(response.items.pages)
        
        # 提取 Artifacts（页面级别）
        artifacts = []
        if response.markdown and response.markdown.pages:
            for page in response.markdown.pages:
                if hasattr(page, 'markdown') and page.success and page.markdown:
                    artifacts.append({
                        "type": "text",
                        "page": page.page_number,
                        "content": page.markdown,
                        "parser": "llamaparse"
                    })
        elif response.text and response.text.pages:
            for page in response.text.pages:
                if page.text:
                    artifacts.append({
                        "type": "text",
                        "page": page.page_number,
                        "content": page.text,
                        "parser": "llamaparse"
                    })
        
        # 提取表格（从 items.pages）
        tables = []
        if self.enable_tables and response.items and response.items.pages:
            for page in response.items.pages:
                if hasattr(page, 'items') and page.success:
                    for item in page.items:
                        if hasattr(item, 'type') and item.type == 'table':
                            tables.append({
                                "type": "table",
                                "page": page.page_number,
                                "content": item.__dict__ if hasattr(item, '__dict__') else str(item),
                                "rows": getattr(item, 'rows', 0)
                            })
        
        # 提取图片（从 items.pages 中的 image items）
        images = []
        if self.enable_images:
            # 🌟 v3.11: 从 items.pages 中提取图片（而不是 images_content_metadata）
            if response.items and response.items.pages:
                for page in response.items.pages:
                    if hasattr(page, 'items') and page.success:
                        for item in page.items:
                            # 🌟 v3.11: 检查是否是图片类型
                            if hasattr(item, 'type') and item.type == 'image':
                                images.append({
                                    "type": "image",
                                    "page": page.page_number,
                                    "filename": getattr(item, 'url', ''),
                                    "caption": getattr(item, 'caption', ''),
                                    "bbox": getattr(item, 'bbox', [{}])[0] if hasattr(item, 'bbox') and item.bbox else {},
                                    "md": getattr(item, 'md', ''),  # Markdown 引用
                                })
            
            # 🌟 v3.11: 也检查 images_content_metadata（兼容旧版本）
            if response.images_content_metadata and hasattr(response.images_content_metadata, 'images'):
                for img_meta in response.images_content_metadata.images:
                    if img_meta is None:
                        continue
                    images.append({
                        "type": "image",
                        "filename": img_meta.filename,
                        "page": getattr(img_meta, 'page_number', 0),
                        "url": img_meta.presigned_url,
                        "category": img_meta.category,
                        "size_bytes": img_meta.size_bytes,
                        "bbox": img_meta.bbox.__dict__ if img_meta.bbox else None
                    })
        
        return PDFParseResult(
            file_path=file_path,
            total_pages=total_pages,
            markdown=markdown_full,
            artifacts=artifacts,
            tables=tables,
            images=images,
            metadata={
                "parser": "llamaparse",
                "tier": self.tier,
                "version": "latest",
                "job_id": job_id,
                "status": job.status,
                "char_count": len(markdown_full),
                "table_count": len(tables),
                "image_count": len(images)
            },
            job_id=job_id,
            tier=self.tier
        )
    
    def _build_result_from_raw(self, raw_data: Dict, pdf_filename: str) -> PDFParseResult:
        """从 raw dict 构建 PDFParseResult"""
        # 🌟 v3.9: 添加安全检查，防止 None.get() 错误
        job = raw_data.get("job") or {}
        job_id = job.get("id", "") if isinstance(job, dict) else ""
        
        markdown_full = raw_data.get("markdown_full", "") or ""
        
        # 🌟 v3.9: 安全处理 None
        markdown_data = raw_data.get("markdown") or {}
        pages = markdown_data.get("pages", []) if isinstance(markdown_data, dict) else []
        total_pages = len(pages)
        
        artifacts = []
        for page in pages:
            # 🌟 v3.9: 跳过 None 元素
            if page is None:
                continue
            if page.get("success") and page.get("markdown"):
                artifacts.append({
                    "type": "text",
                    "page": page.get("page_number", 0),
                    "content": page.get("markdown", ""),
                    "parser": "llamaparse"
                })
        
        tables = []
        items_data = raw_data.get("items") or {}
        items_pages = items_data.get("pages", []) if isinstance(items_data, dict) else []
        for page in items_pages:
            # 🌟 v3.9: 跳过 None 元素
            if page is None:
                continue
            if page.get("success"):
                for item in page.get("items", []):
                    # 🌟 v3.9: 跳过 None 元素
                    if item is None:
                        continue
                    if item.get("type") == "table":
                        tables.append({
                            "type": "table",
                            "page": page.get("page_number", 0),
                            "content": item,
                            "rows": item.get("rows", 0)
                        })
        
        images = []
        # 🌟 v3.11: 从 items.pages 中提取图片（而不是 images_content_metadata）
        items_data = raw_data.get("items") or {}
        items_pages = items_data.get("pages", []) if isinstance(items_data, dict) else []
        for page in items_pages:
            # 🌟 v3.9: 跳过 None 元素
            if page is None:
                continue
            if page.get("success"):
                for item in page.get("items", []):
                    # 🌟 v3.9: 跳过 None 元素
                    if item is None:
                        continue
                    # 🌟 v3.11: 检查是否是图片类型
                    if item.get("type") == "image":
                        images.append({
                            "type": "image",
                            "page": page.get("page_number", 0),
                            "filename": item.get("url", ""),
                            "caption": item.get("caption", ""),
                            "md": item.get("md", ""),
                            "bbox": item.get("bbox", [{}])[0] if item.get("bbox") else {}
                        })
        
        # 🌟 v3.11: 也检查 images_content_metadata（兼容旧版本）
        images_meta = raw_data.get("images_content_metadata") or {}
        images_list = images_meta.get("images", []) if isinstance(images_meta, dict) else []
        for img in images_list:
            # 🌟 v3.5: 跳过 None 元素
            if img is None:
                continue
            images.append({
                "type": "image",
                "filename": img.get("filename", ""),
                "url": img.get("presigned_url", ""),
                "category": img.get("category", ""),
                "size_bytes": img.get("size_bytes", 0),
                "bbox": img.get("bbox"),
            })
        
        return PDFParseResult(
            file_path=pdf_filename,
            total_pages=total_pages,
            markdown=markdown_full,
            artifacts=artifacts,
            tables=tables,
            images=images,
            metadata={
                "parser": "llamaparse",
                "tier": self.tier,
                "job_id": job_id,
                "status": job.get("status", "COMPLETED") if isinstance(job, dict) else "COMPLETED",
                "char_count": len(markdown_full),
                "table_count": len(tables),
                "image_count": len(images),
                "loaded_from": "raw_output"
            },
            job_id=job_id,
            tier=self.tier
        )


# ===========================================
# 便捷函数
# ===========================================

def parse_pdf(file_path: str, **kwargs) -> PDFParseResult:
    """便捷函数：同步解析 PDF"""
    parser = PDFParser()
    return parser.parse(file_path, **kwargs)

async def parse_pdf_async(file_path: str, **kwargs) -> PDFParseResult:
    """便捷函数：异步解析 PDF"""
    parser = PDFParser()
    return await parser.parse_async(file_path, **kwargs)

def parse_pdf_url(url: str, **kwargs) -> PDFParseResult:
    """便捷函数：解析 URL PDF"""
    parser = PDFParser()
    return parser.parse_url(url, **kwargs)

def load_from_raw_output(pdf_filename: str, job_id: str) -> PDFParseResult:
    """便捷函数：从 raw output 加载"""
    parser = PDFParser()
    return parser.load_from_raw_output(pdf_filename, job_id)


# ===========================================
# 导出
# ===========================================

__all__ = [
    "PDFParser",
    "PDFParseResult",
    "parse_pdf",
    "parse_pdf_async",
    "parse_pdf_url",
    "load_from_raw_output",
    "get_llamaparse_api_key",
    "get_llamaparse_tier",
    "get_data_dir",
    "get_raw_output_dir",
]