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
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from loguru import logger


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


def get_raw_output_dir(pdf_filename: str = None) -> Path:
    """
    获取 LlamaParse Raw Output 存储目录
    
    🌟 v3.2: 按 PDF 文件名创建文件夹
    
    结构：
    data/raw/
    └── llamaparse/
        └── report.pdf/              ← 按 PDF 文件名
            ├── job_xxx.json         ← 完整的 API 响应
            ├── job_xxx_meta.json    ← 元数据
            ├── markdown.md          ← 完整 Markdown（方便查看）
            ├── markdown_page1.md    ← 每页 Markdown
            ├── markdown_page2.md
            └── images/              ← 图片文件夹
                ├── screenshot_page1.png
                ├── embedded_page2.jpg
                └── ...
        └── another.pdf/
            └── job_yyy/
            └── ...
    
    Args:
        pdf_filename: PDF 文件名（不含路径）
        
    Returns:
        Path: data/raw/llamaparse/{pdf_filename} 目录
    """
    data_dir = Path(get_data_dir())
    raw_output_dir = data_dir / "llamaparse"
    
    if pdf_filename:
        # 🌟 按 PDF 文件名创建子文件夹
        # 移除扩展名，避免文件夹名称重复
        pdf_name = Path(pdf_filename).stem  # report.pdf → report
        raw_output_dir = raw_output_dir / pdf_name
    
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
            self.client = LlamaCloud(api_key=self.api_key)
            self.async_client = AsyncLlamaCloud(api_key=self.api_key)
            logger.info(f"✅ PDFParser 初始化完成 (tier={self.tier}, save_raw={save_raw_output}, download_images={download_images})")
        except ImportError:
            raise ImportError(
                "❌ llama_cloud SDK 未安装！\n"
                "请运行: pip install llama_cloud>=2.3.0"
            )
    
    # ===========================================
    # 同步方法
    # ===========================================
    
    def parse(self, file_path: str) -> PDFParseResult:
        """
        解析本地 PDF 文件
        
        🌟 自动保存所有 raw output 到 data/raw/llamaparse/{pdf_filename}/
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            PDFParseResult
        """
        logger.info(f"🚀 LlamaParse 解析: {file_path}")
        
        # 1. 上传文件
        file_obj = self.client.files.create(
            file=Path(file_path),
            purpose="parse"
        )
        file_id = file_obj.id
        logger.info(f"   ✅ 文件上传成功: file_id={file_id}")
        
        # 2. 创建解析任务
        job = self.client.parsing.create(
            tier=self.tier,
            version="latest",
            file_id=file_id
        )
        job_id = job.id
        logger.info(f"   🔍 解析任务创建: job_id={job_id}")
        
        # 3. 等待解析完成
        response = self._wait_for_completion(job_id)
        
        # 4. 🌟 保存完整的 raw output（按 PDF 文件名）
        pdf_filename = Path(file_path).name
        raw_output_dir = self._save_full_raw_output(response, pdf_filename)
        
        # 5. 🌟 下载图片到本地
        if self.download_images:
            self._download_images(response, raw_output_dir)
        
        # 6. 提取结果
        result = self._extract_result(response, file_path)
        result.raw_output_dir = str(raw_output_dir)
        
        # 7. 更新图片路径为本地路径
        result = self._update_image_paths(result, raw_output_dir)
        
        logger.info(
            f"✅ 解析完成: {result.total_pages} 页, "
            f"{len(result.tables)} 个表格, {len(result.images)} 张图片, "
            f"raw output 已保存: {raw_output_dir}"
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
        job = self.client.parsing.create(
            tier=self.tier,
            version="latest",
            source_url=url
        )
        job_id = job.id
        logger.info(f"   🔍 解析任务创建: job_id={job_id}")
        
        # 等待解析完成
        response = self._wait_for_completion(job_id)
        
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
    
    async def parse_async(self, file_path: str) -> PDFParseResult:
        """
        异步解析本地 PDF 文件
        
        🌟 自动保存所有 raw output
        """
        logger.info(f"🚀 LlamaParse 异步解析: {file_path}")
        
        # 1. 上传文件
        file_obj = await self.async_client.files.create(
            file=Path(file_path),
            purpose="parse"
        )
        file_id = file_obj.id
        logger.info(f"   ✅ 文件上传成功: file_id={file_id}")
        
        # 2. 创建解析任务
        job = await self.async_client.parsing.create(
            tier=self.tier,
            version="latest",
            file_id=file_id
        )
        job_id = job.id
        logger.info(f"   🔍 解析任务创建: job_id={job_id}")
        
        # 3. 异步等待完成
        response = await self._wait_for_completion_async(job_id)
        
        # 4. 🌟 保存完整的 raw output
        pdf_filename = Path(file_path).name
        raw_output_dir = self._save_full_raw_output(response, pdf_filename)
        
        # 5. 🌟 异步下载图片
        if self.download_images:
            await self._download_images_async(response, raw_output_dir)
        
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
    
    async def parse_url_async(self, url: str) -> PDFParseResult:
        """
        异步解析 URL PDF
        
        🌟 自动保存所有 raw output
        """
        logger.info(f"🚀 LlamaParse 异步解析 URL: {url}")
        
        url_filename = Path(url).name or "url_document.pdf"
        
        # 创建解析任务
        job = await self.async_client.parsing.create(
            tier=self.tier,
            version="latest",
            source_url=url
        )
        job_id = job.id
        logger.info(f"   🔍 解析任务创建: job_id={job_id}")
        
        # 异步等待完成
        response = await self._wait_for_completion_async(job_id)
        
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
    
    def _save_full_raw_output(self, response: Any, pdf_filename: str) -> Path:
        """
        保存完整的 API 响应到 data/raw/llamaparse/{pdf_filename}/
        
        🌟 v3.2: 按 PDF 文件名创建文件夹，保存所有字段
        
        保存结构：
        data/raw/llamaparse/{pdf_filename}/
        ├── {job_id}.json          ← 完整的 ParsingGetResponse（所有字段）
        ├── {job_id}_meta.json     ← 元数据（file_path, created_at）
        ├── markdown.md            ← 完整 Markdown（方便查看）
        ├── markdown_page{n}.md    ← 每页 Markdown
        └── images/                ← 图片文件夹（稍后下载）
        
        Args:
            response: LlamaParse ParsingGetResponse
            pdf_filename: PDF 文件名
            
        Returns:
            Path: 保存的目录路径
        """
        if not self.save_raw_output:
            return None
        
        job_id = response.job.id
        
        # 🌟 按 PDF 文件名创建目录
        raw_output_dir = get_raw_output_dir(pdf_filename)
        
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
            json.dump(raw_dict, f, ensure_ascii=False, indent=2)
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
        
        # 4. 🌟 保存每页 Markdown（方便查看）
        markdown_pages = raw_dict.get("markdown", {}).get("pages", [])
        for page in markdown_pages:
            if page.get("success") and page.get("markdown"):
                page_num = page.get("page_number", 0)
                page_markdown_path = raw_output_dir / f"markdown_page{page_num}.md"
                with open(page_markdown_path, 'w', encoding='utf-8') as f:
                    f.write(page.get("markdown", ""))
        
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
        
        # 10. job_metadata
        result["job_metadata"] = getattr(response, 'job_metadata', None)
        
        # 11. raw_parameters
        result["raw_parameters"] = getattr(response, 'raw_parameters', None)
        
        return result
    
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
        异步下载图片到本地
        """
        images_dir = raw_output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        if not hasattr(response, 'images_content_metadata') or not response.images_content_metadata:
            return
        
        images = response.images_content_metadata.images
        if not images:
            return
        
        logger.info(f"   📥 异步下载 {len(images)} 张图片...")
        
        downloaded = 0
        async with httpx.AsyncClient(timeout=60) as client:
            for img in images:
                url = getattr(img, 'presigned_url', None)
                filename = getattr(img, 'filename', f"image_{getattr(img, 'index', 0)}.png")
                
                if not url:
                    continue
                
                try:
                    response_http = await client.get(url)
                    if response_http.status_code == 200:
                        img_path = images_dir / filename
                        with open(img_path, 'wb') as f:
                            f.write(response_http.content)
                        downloaded += 1
                        logger.debug(f"      ✅ {filename}")
                except Exception as e:
                    logger.warning(f"      ⚠️ 下载失败 {filename}: {e}")
        
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
            filename = img.get("filename", "")
            if filename:
                local_path = images_dir / filename
                if local_path.exists():
                    img["local_path"] = str(local_path)
        
        return result
    
    # ===========================================
    # 🌟 从 Raw Output 加载（不扣费）
    # ===========================================
    
    def load_from_raw_output(self, pdf_filename: str, job_id: str = None) -> PDFParseResult:
        """
        从已保存的 raw output 加载结果（完全不扣费）
        
        🌟 v3.2: 按 PDF 文件名查找
        
        Args:
            pdf_filename: PDF 文件名
            job_id: 任务 ID（可选，如果不提供则自动查找最新的）
            
        Returns:
            PDFParseResult
            
        Raises:
            FileNotFoundError: 如果 raw output 文件不存在
        """
        logger.info(f"📂 从 raw output 加载: {pdf_filename}")
        
        # 1. 按 PDF 文件名获取目录
        raw_output_dir = get_raw_output_dir(pdf_filename)
        
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
    
    def _wait_for_completion(self, job_id: str, max_wait: int = 300) -> Any:
        """等待解析任务完成（同步）"""
        import time
        
        start_time = time.time()
        
        while True:
            response = self.client.parsing.get(job_id=job_id)
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
                time.sleep(2)
            
            elif status == "CANCELLED":
                raise ValueError(f"解析任务已取消: job_id={job_id}")
            
            else:
                raise ValueError(f"未知状态: {status}")
    
    async def _wait_for_completion_async(self, job_id: str, max_wait: int = 300) -> Any:
        """等待解析任务完成（异步）"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            response = await self.async_client.parsing.get(job_id=job_id)
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
                
                logger.debug(f"   ⏳ 异步等待中... status={status}")
                await asyncio.sleep(2)
            
            elif status == "CANCELLED":
                raise ValueError(f"解析任务已取消: job_id={job_id}")
            
            else:
                raise ValueError(f"未知状态: {status}")
    
    # ===========================================
    # 提取结果
    # ===========================================
    
    def _extract_result(self, response: Any, file_path: str) -> PDFParseResult:
        """从 ParsingGetResponse 提取结构化结果"""
        job = response.job
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
        
        # 提取图片（从 images_content_metadata）
        images = []
        if self.enable_images and response.images_content_metadata:
            for img_meta in response.images_content_metadata.images:
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
        job = raw_data.get("job", {})
        job_id = job.get("id", "")
        
        markdown_full = raw_data.get("markdown_full", "")
        
        markdown_data = raw_data.get("markdown", {})
        pages = markdown_data.get("pages", [])
        total_pages = len(pages)
        
        artifacts = []
        for page in pages:
            if page.get("success") and page.get("markdown"):
                artifacts.append({
                    "type": "text",
                    "page": page.get("page_number", 0),
                    "content": page.get("markdown", ""),
                    "parser": "llamaparse"
                })
        
        tables = []
        items_data = raw_data.get("items", {})
        items_pages = items_data.get("pages", [])
        for page in items_pages:
            if page.get("success"):
                for item in page.get("items", []):
                    if item.get("type") == "table":
                        tables.append({
                            "type": "table",
                            "page": page.get("page_number", 0),
                            "content": item,
                            "rows": item.get("rows", 0)
                        })
        
        images = []
        images_meta = raw_data.get("images_content_metadata", {})
        images_list = images_meta.get("images", [])
        for img in images_list:
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
                "status": job.get("status", "COMPLETED"),
                "char_count": len(markdown_full),
                "table_count": len(tables),
                "image_count": len(images),
                "loaded_from": "raw_output"
            },
            job_id=job_id,
            tier=self.tier
        )


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