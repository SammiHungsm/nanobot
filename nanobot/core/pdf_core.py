"""
PDF Core - OpenDataLoader 统一封装层

🎯 解决的问题：
1. 代码重复：Agent/Ingestion/WebUI 三处各自实现
2. Docker 网络问题：localhost:5002 在容器内指向错误
3. API 参数不一致：format 参数一个是 List，一个是 String
4. JSON 结构预期冲突：不同 Parser 预期不同的 JSON Schema

统一架构：
- 所有底层 API 调用集中在这一个文件
- 使用环境变量处理 Hybrid URL
- 统一 format 参数为字符串格式
- 提供 normalize_output() 函数统一 JSON 结构

Usage:
    from nanobot.core.pdf_core import OpenDataLoaderCore
    
    # 统一的调用方式
    core = OpenDataLoaderCore()
    result = core.parse(pdf_path, enable_hybrid=True)
    
    # 自动标准化 JSON 结构
    normalized = core.normalize_output(result)
"""

import os
import json
import asyncio
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
from loguru import logger


# ===========================================
# 环境变量配置（解决 Docker 网络问题）
# ===========================================

def get_hybrid_url() -> str:
    """
    获取 Hybrid 服务器 URL（支持 Docker 环境）
    
    Docker 环境中：
    - 如果 HYBRID_URL 未设置，自动检测是否在容器内
    - 在容器内：使用 http://nanobot-webui:5002（容器间通信）
    - 本地开发：使用 http://localhost:5002
    
    Returns:
        str: Hybrid 服务器 URL
    """
    hybrid_url = os.environ.get("HYBRID_URL")
    
    if hybrid_url:
        return hybrid_url
    
    # 🌟 自动检测是否在 Docker 容器内
    # 方法 1: 检查 /.dockerenv 文件是否存在
    # 方法 2: 检查环境变量 HOSTNAME 或容器特有的变量
    is_docker = os.path.exists("/.dockerenv") or \
                os.environ.get("HOSTNAME") or \
                os.environ.get("KUBERNETES_SERVICE_HOST")
    
    if is_docker:
        # 在 Docker 容器内，使用服务名（容器间通信）
        default_url = "http://nanobot-webui:5002"
        logger.info(f"🐳 Docker 环境：Hybrid URL = {default_url}")
    else:
        # 本地开发，使用 localhost
        default_url = "http://localhost:5002"
        logger.info(f"💻 本地环境：Hybrid URL = {default_url}")
    
    return default_url


def get_cuda_enabled() -> bool:
    """获取是否启用 CUDA"""
    return os.environ.get("USE_CUDA", "false").lower() == "true"


# ===========================================
# 统一的输出结构（标准化 JSON Schema）
# ===========================================

@dataclass
class PDFParseResult:
    """
    🎯 统一的 PDF 解析结果结构
    
    无论 OpenDataLoader 原始输出是什么格式，都标准化为这个结构。
    """
    file_path: str
    total_pages: int
    markdown: str  # 完整的 Markdown 文本
    artifacts: List[Dict[str, Any]]  # 标准化的 Artifacts 列表
    tables: List[Dict[str, Any]]  # 表格列表
    images: List[Dict[str, Any]]  # 图片列表
    metadata: Dict[str, Any]  # 元数据（文件名、解析时间等）
    
    # 🌟 新增：Hybrid 模式信息
    hybrid_enabled: bool = False
    hybrid_device: str = "CPU"


# ===========================================
# 核心类：OpenDataLoader 统一封装
# ===========================================

class OpenDataLoaderCore:
    """
    OpenDataLoader-PDF 统一封装
    
    🎯 解决所有架构问题：
    1. 统一 API 调用（所有参数格式一致）
    2. 自动处理 Hybrid URL（Docker/本地环境）
    3. 统一输出结构（标准化 JSON Schema）
    """
    
    def __init__(self, enable_hybrid: bool = False, hybrid_url: str = None):
        """
        初始化
        
        Args:
            enable_hybrid: 是否启用 Hybrid AI 视觉模式
            hybrid_url: Hybrid 服务器 URL（默认从环境变量获取）
        """
        self.enable_hybrid = enable_hybrid
        self.hybrid_url = hybrid_url or get_hybrid_url()
        self.use_cuda = get_cuda_enabled()
        
        # 检查安装
        self._check_installation()
        
        logger.info(
            f"✅ OpenDataLoaderCore 初始化完成 "
            f"(hybrid={enable_hybrid}, device={self.hybrid_url}, cuda={self.use_cuda})"
        )
    
    def _check_installation(self):
        """检查 opendataloader_pdf 是否安装"""
        try:
            import opendataloader_pdf
            self.module = opendataloader_pdf
            logger.info("✅ opendataloader_pdf 已安装")
        except ImportError:
            logger.error("❌ opendataloader_pdf 未安装。请运行: pip install opendataloader-pdf")
            raise
    
    def parse(
        self,
        pdf_path: str,
        output_dir: str = None,
        pages: Union[List[int], str] = None,
        enable_hybrid: bool = None,
        image_output: str = "embedded",
        image_format: str = "png"
    ) -> PDFParseResult:
        """
        🎯 统一的 PDF 解析方法
        
        Args:
            pdf_path: PDF 文件路径
            output_dir: 输出目录（默认使用临时目录）
            pages: 要解析的页码（可以是 list 或逗号分隔的字符串）
            enable_hybrid: 是否启用 Hybrid（默认使用初始化时的设置）
            image_output: 图片输出方式（"embedded" 或 "external"）
            image_format: 图片格式（"png", "jpg" 等）
            
        Returns:
            PDFParseResult: 统一的解析结果
            
        Example:
            # 基础解析（纯 Java）
            result = core.parse("report.pdf")
            
            # Hybrid AI 视觉解析
            result = core.parse("report.pdf", enable_hybrid=True)
            
            # 只解析特定页面（快速模式）
            result = core.parse("report.pdf", pages=[1, 2])
            # 或
            result = core.parse("report.pdf", pages="1,2")
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
        
        # 使用传入的 enable_hybrid 或初始化时的设置
        use_hybrid = enable_hybrid if enable_hybrid is not None else self.enable_hybrid
        
        # 🌟 使用临时目录或指定的输出目录
        if output_dir is None:
            with tempfile.TemporaryDirectory() as temp_dir:
                return self._parse_internal(
                    str(pdf_path), temp_dir, pages, use_hybrid, image_output, image_format
                )
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            return self._parse_internal(
                str(pdf_path), str(output_dir), pages, use_hybrid, image_output, image_format
            )
    
    def _parse_internal(
        self,
        pdf_path: str,
        output_dir: str,
        pages: Union[List[int], str],
        use_hybrid: bool,
        image_output: str,
        image_format: str
    ) -> PDFParseResult:
        """内部解析逻辑"""
        
        logger.info(f"📄 开始解析 PDF: {pdf_path}")
        logger.info(f"   输出目录: {output_dir}")
        logger.info(f"   Hybrid 模式: {use_hybrid}")
        
        # 🌟 统一参数格式：format 使用字符串（逗号分隔）
        format_str = "markdown,json"
        
        # 🌟 统一参数格式：pages 使用字符串（逗号分隔）
        if pages is not None:
            if isinstance(pages, list):
                pages_str = ",".join(str(p) for p in pages)
            else:
                pages_str = pages
            logger.info(f"   页码范围: {pages_str}")
        else:
            pages_str = None
        
        # 构建 convert() 参数
        convert_kwargs = {
            'input_path': pdf_path,
            'output_dir': output_dir,
            'format': format_str,  # 🌟 统一使用字符串格式
            'image_output': image_output,
            'image_format': image_format,
        }
        
        # 🌟 如果指定了特定页面，只使用纯 Java 解析（快速模式）
        if pages_str:
            convert_kwargs['pages'] = pages_str
            use_hybrid = False  # 🌟 强制禁用 Hybrid（特定页面不需要 AI）
            logger.info(f"⚡ 快速模式：只解析 Page {pages_str}（纯 Java，不启动 Hybrid）")
        
        # 🌟 启用 Hybrid AI 视觉模式
        if use_hybrid:
            device = "CUDA GPU" if self.use_cuda else "CPU"
            logger.info(f"🚀 Hybrid AI 视觉模式：启动 {device} 解析（Docling 模型）")
            
            convert_kwargs['hybrid'] = "docling-fast"
            # 🎯 修正：改为 "full"，确保表格/图片/扫描件全部强制交给 Backend 处理
            convert_kwargs['hybrid_mode'] = "full"  
            convert_kwargs['hybrid_url'] = self.hybrid_url  # 🌟 从环境变量获取
            # 🎯 修正：必须是 Integer (整数)，不能是 String
            convert_kwargs['hybrid_timeout'] = 600000  
            convert_kwargs['hybrid_fallback'] = True  # Hybrid 失败时 fallback 到 Java
        
        # 🚀 调用 OpenDataLoader
        try:
            logger.debug(f"🔧 调用 opendataloader_pdf.convert()")
            logger.debug(f"   参数: {json.dumps(convert_kwargs, indent=2)}")
            
            self.module.convert(**convert_kwargs)
            
        except Exception as e:
            logger.error(f"❌ OpenDataLoader 解析失败: {e}")
            if use_hybrid and convert_kwargs.get('hybrid_fallback'):
                logger.warning("⚠️ Hybrid 失败，尝试 fallback 到纯 Java 解析...")
                # 移除 Hybrid 参数，重新尝试
                for key in ['hybrid', 'hybrid_mode', 'hybrid_url', 'hybrid_timeout', 'hybrid_fallback']:
                    convert_kwargs.pop(key, None)
                self.module.convert(**convert_kwargs)
            else:
                raise
        
        # 🎯 读取输出文件并标准化
        result = self._read_and_normalize(output_dir, pdf_path, use_hybrid)
        
        logger.info(
            f"✅ 解析完成: {result.total_pages} 页, "
            f"{len(result.tables)} 个表格, {len(result.images)} 张图片"
        )
        
        return result
    
    def _read_and_normalize(
        self,
        output_dir: str,
        pdf_path: str,
        use_hybrid: bool
    ) -> PDFParseResult:
        """
        🎯 读取输出文件并标准化为统一结构
        
        解决问题：不同 Parser 预期的 JSON Schema 不同
        """
        output_path = Path(output_dir)
        
        # 查找输出文件
        md_files = list(output_path.glob("*.md"))
        json_files = list(output_path.glob("*.json"))
        
        # 读取 Markdown
        markdown = ""
        for md_file in sorted(md_files):
            markdown += md_file.read_text(encoding='utf-8') + "\n\n"
        
        # 🎯 读取 JSON 并标准化
        tables = []
        images = []
        artifacts = []
        metadata = {
            "filename": Path(pdf_path).name,
            "hybrid_enabled": use_hybrid,
            "hybrid_device": "CUDA" if self.use_cuda else "CPU"
        }
        total_pages = 0
        
        # 🌟 检查是否有外部图片文件（OpenDataLoader image_output="external"）
        image_files = list(output_path.glob("images/*")) + \
                      list(output_path.glob("*.png")) + \
                      list(output_path.glob("*.jpg")) + \
                      list(output_path.glob("*.jpeg"))
        
        if image_files:
            logger.info(f"📸 发现 {len(image_files)} 个外部图片文件")
        
        for json_file in sorted(json_files):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 🎯 标准化 JSON 结构（兼容多种 Schema）
                normalized = self._normalize_json(data)
                
                tables.extend(normalized['tables'])
                images.extend(normalized['images'])
                artifacts.extend(normalized['artifacts'])
                
                if 'total_pages' in normalized['metadata']:
                    total_pages = normalized['metadata']['total_pages']
                
                metadata.update(normalized['metadata'])
                
            except Exception as e:
                logger.warning(f"⚠️ 读取 JSON 文件失败 {json_file}: {e}")
        
        # 🌟 如果 JSON 中没有图片数据，检查外部图片文件
        if not images and image_files:
            import base64
            logger.info(f"📸 从外部文件加载图片数据...")
            for idx, img_file in enumerate(sorted(image_files)):
                try:
                    # 读取图片文件为 base64
                    with open(img_file, 'rb') as f:
                        img_bytes = f.read()
                    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                    
                    # 推测图片 MIME 类型
                    img_ext = img_file.suffix.lower()
                    mime_type = {
                        '.png': 'image/png',
                        '.jpg': 'image/jpeg',
                        '.jpeg': 'image/jpeg',
                        '.gif': 'image/gif',
                        '.webp': 'image/webp'
                    }.get(img_ext, 'image/png')
                    
                    # 构造 data URI
                    img_data_uri = f"data:{mime_type};base64,{img_base64}"
                    
                    # 尝试从文件名提取页码（如 image_page1.png）
                    page_num = 0
                    for part in img_file.stem.split('_'):
                        if 'page' in part.lower():
                            try:
                                page_num = int(part.replace('page', '').replace('Page', '').replace('PAGE', ''))
                            except:
                                pass
                    
                    images.append({
                        'page_num': page_num,
                        'image_data': img_data_uri,
                        'image_path': str(img_file),
                        'metadata': {'source': 'external_file'}
                    })
                    artifacts.append({
                        'type': 'image',
                        'image_data': img_data_uri,
                        'image_path': str(img_file),
                        'page_num': page_num,
                        'metadata': {'source': 'external_file'}
                    })
                    logger.debug(f"✅ 加载图片: {img_file.name} (page {page_num})")
                except Exception as e:
                    logger.warning(f"⚠️ 图片文件读取失败 {img_file}: {e}")
        
        # 🎯 修正 2：防止 TempDir 被刪除導致圖片黑洞！
        # 趁 temp_dir 仲未被自動刪除，強制將所有實體圖片轉成 Base64 塞入 image_data
        import base64
        import mimetypes
        
        for artifact in artifacts:
            if artifact.get('type') == 'image' and not artifact.get('image_data'):
                img_path = artifact.get('image_path')
                if img_path and Path(img_path).exists():
                    try:
                        with open(img_path, 'rb') as f:
                            img_bytes = f.read()
                        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                        mime_type = mimetypes.guess_type(img_path)[0] or 'image/png'
                        artifact['image_data'] = f"data:{mime_type};base64,{img_base64}"
                        
                        # 同步更新 images 列表
                        for img in images:
                            if img.get('image_path') == img_path:
                                img['image_data'] = artifact['image_data']
                        
                        logger.debug(f"✅ TempDir 图片转换 Base64: {img_path}")
                    except Exception as e:
                        logger.warning(f"⚠️ 臨時目錄圖片轉換 Base64 失敗 {img_path}: {e}")
        
        return PDFParseResult(
            file_path=str(pdf_path),
            total_pages=total_pages,
            markdown=markdown,
            artifacts=artifacts,
            tables=tables,
            images=images,
            metadata=metadata,
            hybrid_enabled=use_hybrid,
            hybrid_device="CUDA" if self.use_cuda else "CPU"
        )
    
    def _normalize_json(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🎯 标准化 JSON 结构
        
        OpenDataLoader 可能返回以下几种结构：
        1. {"pages": [...]} - 每页包含内容
        2. {"kids": [...]} - 类似 PDF 结构
        3. {"content": [...]} - 内容列表
        4. {"tables": [...], "images": [...], "elements": [...]} - 已分类
        
        统一标准化为：
        {
            "tables": [...],
            "images": [...],
            "artifacts": [...],
            "metadata": {...}
        }
        """
        normalized = {
            'tables': [],
            'images': [],
            'artifacts': [],
            'metadata': {}
        }
        
        # 🌟 情况 1: 已经是分类结构
        if 'tables' in data:
            normalized['tables'] = data['tables']
            # 🎯 修正 1：將 tables 塞入 artifacts
            for table in data['tables']:
                normalized['artifacts'].append({
                    'type': 'table',
                    'content_json': table,
                    'page_num': table.get('page', table.get('page_num', 0)),
                    'metadata': table.get('metadata', {})
                })
        
        if 'images' in data:
            normalized['images'] = data['images']
            # 🎯 修正 1：將 images 塞入 artifacts
            for img in data['images']:
                normalized['artifacts'].append({
                    'type': 'image',
                    'image_data': img.get('image_data'),
                    'image_path': img.get('image_path') or img.get('path'),
                    'page_num': img.get('page', img.get('page_num', 0)),
                    'metadata': img.get('metadata', {})
                })
        
        if 'elements' in data:
            for elem in data['elements']:
                normalized['artifacts'].append({
                    'type': elem.get('type', 'unknown'),
                    'content': elem.get('content', ''),
                    'page_num': elem.get('page', 0),
                    'bbox': elem.get('bbox'),
                    'metadata': elem.get('metadata', {})
                })
        
        # 🌟 情况 2: pages 结构
        if 'pages' in data:
            normalized['metadata']['total_pages'] = len(data['pages'])
            for page_idx, page in enumerate(data['pages']):
                page_num = page.get('page_num', page_idx + 1)
                
                # 从页面提取表格、图片、文字
                if 'tables' in page:
                    for table in page['tables']:
                        table['page_num'] = page_num
                        normalized['tables'].append(table)
                        normalized['artifacts'].append({
                            'type': 'table',
                            'content_json': table,
                            'page_num': page_num,
                            'metadata': table.get('metadata', {})
                        })
                
                if 'images' in page:
                    for img in page['images']:
                        img['page_num'] = page_num
                        normalized['images'].append(img)
                        normalized['artifacts'].append({
                            'type': 'image',
                            'image_data': img.get('image_data'),
                            'page_num': page_num,
                            'metadata': img.get('metadata', {})
                        })
                
                if 'text' in page:
                    normalized['artifacts'].append({
                        'type': 'text_chunk',
                        'content': page['text'],
                        'page_num': page_num,
                        'metadata': {}
                    })
        
        # 🌟 情况 3: kids 结构（OpenDataLoader 实际结构）
        if 'kids' in data:
            self._extract_from_kids(data['kids'], normalized)
        
        # 🌟 情况 4: content 结构
        if 'content' in data:
            for idx, item in enumerate(data['content']):
                item_type = item.get('type', 'unknown')
                # 🎯 修正：如果元素是图片，必须读取 image_data
                normalized['artifacts'].append({
                    'type': item_type,
                    'content': item.get('content', ''),
                    'image_data': item.get('image_data') or item.get('image'),  # 补回这行
                    'image_path': item.get('image_path'),  # 补回这行
                    'page_num': item.get('page', 0),
                    'bbox': item.get('bbox'),
                    'metadata': item.get('metadata', {})
                })
        
        # 🌟 提取元数据
        if 'metadata' in data:
            normalized['metadata'].update(data['metadata'])
        
        # 🌟 OpenDataLoader 特殊字段
        if 'number of pages' in data:
            normalized['metadata']['total_pages'] = data['number of pages']
        
        return normalized
    
    def _extract_from_kids(self, kids: List[Dict], normalized: Dict):
        """
        🎯 从 kids 结构提取内容（修正版）
        
        OpenDataLoader 的实际结构：
        - kids 是扁平列表，包含所有元素
        - 每个元素有 type, page number, content
        - 直接遍历，按类型分类
        
        之前的错误：检查 kid.get('type') == 'page'
        正确的逻辑：直接处理 paragraph, heading, table 等元素
        """
        for kid in kids:
            kid_type = kid.get('type', 'unknown')
            page_num = kid.get('page number', 0)
            content = kid.get('content', '')
            
            # 🌟 根据类型分类
            if kid_type == 'table':
                # 表格元素
                normalized['tables'].append({
                    'page_num': page_num,
                    'content': content,
                    'metadata': kid
                })
                normalized['artifacts'].append({
                    'type': 'table',
                    'content': content,
                    'page_num': page_num,
                    'metadata': kid
                })
            
            elif kid_type in ['image', 'image_screenshot', 'screenshot', 'figure']:
                # 图片元素（支持多种类型名称）
                # 🌟 尝试从多个字段提取图片数据
                image_data = kid.get('image_data') or kid.get('image') or kid.get('content')
                
                # 检查是否有外部图片文件路径
                image_path = kid.get('image_path') or kid.get('file_path') or kid.get('path')
                
                normalized['images'].append({
                    'page_num': page_num,
                    'content': content,
                    'image_data': image_data,
                    'image_path': image_path,
                    'metadata': kid
                })
                normalized['artifacts'].append({
                    'type': 'image',
                    'content': content,
                    'image_data': image_data,
                    'image_path': image_path,
                    'page_num': page_num,
                    'metadata': kid
                })
            
            elif kid_type in ['paragraph', 'heading', 'text']:
                # 文字元素（合并为 text_chunk）
                normalized['artifacts'].append({
                    'type': 'text_chunk',
                    'content': content,
                    'page_num': page_num,
                    'metadata': kid
                })
            
            elif kid_type == 'list':
                # 列表元素
                normalized['artifacts'].append({
                    'type': 'list',
                    'content': content,
                    'page_num': page_num,
                    'metadata': kid
                })
            
            else:
                # 其他元素（保留原类型）
                normalized['artifacts'].append({
                    'type': kid_type,
                    'content': content,
                    'page_num': page_num,
                    'metadata': kid
                })
            
            # 如果 kids 下还有 kids，继续递归
            if 'kids' in kid:
                self._extract_from_kids(kid['kids'], normalized)
    
    async def parse_async(
        self,
        pdf_path: str,
        output_dir: str = None,
        pages: Union[List[int], str] = None,
        enable_hybrid: bool = None
    ) -> PDFParseResult:
        """
        异步解析 PDF（将阻塞操作放到背景线程）
        
        Args:
            pdf_path: PDF 文件路径
            output_dir: 输出目录
            pages: 要解析的页码
            enable_hybrid: 是否启用 Hybrid
            
        Returns:
            PDFParseResult: 统一的解析结果
        """
        logger.info(f"📄 异步解析 PDF: {pdf_path}")
        
        # 使用 asyncio.to_thread 将阻塞操作放到背景
        result = await asyncio.to_thread(
            self.parse,
            pdf_path,
            output_dir,
            pages,
            enable_hybrid
        )
        
        return result
    
    def to_artifacts_list(self, result: PDFParseResult) -> List[Dict[str, Any]]:
        """
        🎯 将 PDFParseResult 转换为 Artifacts 列表格式
        
        用于 Ingestion Parser 层（兼容现有的 _convert_to_artifacts）
        
        Args:
            result: PDFParseResult
            
        Returns:
            List[Dict]: Artifacts 列表
        """
        return result.artifacts
    
    def to_parsed_pdf(self, result: PDFParseResult) -> 'ParsedPDF':
        """
        🎯 将 PDFParseResult 转换为 ParsedPDF 格式
        
        用于 Agent Tools 层（兼容现有的 OpenDataLoaderPDF.parse 返回值）
        
        Args:
            result: PDFParseResult
            
        Returns:
            ParsedPDF: 兼容旧格式的对象
        """
        from dataclasses import dataclass
        
        # 导入旧格式的 dataclass（如果存在）
        try:
            from nanobot.agent.tools.pdf_parser import ParsedPDF, ExtractedElement, BoundingBox
        except ImportError:
            # 如果不存在，定义兼容的 dataclass
            @dataclass
            class BoundingBox:
                x: float
                y: float
                width: float
                height: float
                page: int
            
            @dataclass
            class ExtractedElement:
                element_type: str
                content: str
                bbox: BoundingBox
                level: Optional[int] = None
                metadata: Optional[Dict[str, Any]] = None
            
            @dataclass
            class ParsedPDF:
                file_path: str
                total_pages: int
                markdown: str
                elements: List[ExtractedElement]
                tables: List[Dict[str, Any]]
                images: List[Dict[str, Any]]
                metadata: Dict[str, Any]
        
        # 转换 artifacts 为 ExtractedElement 列表
        elements = []
        for artifact in result.artifacts:
            bbox_data = artifact.get('bbox', {})
            bbox = BoundingBox(
                x=bbox_data.get('x', 0),
                y=bbox_data.get('y', 0),
                width=bbox_data.get('width', 0),
                height=bbox_data.get('height', 0),
                page=artifact.get('page_num', 0)
            )
            
            element = ExtractedElement(
                element_type=artifact.get('type', 'unknown'),
                content=artifact.get('content', ''),
                bbox=bbox,
                metadata=artifact.get('metadata', {})
            )
            elements.append(element)
        
        return ParsedPDF(
            file_path=result.file_path,
            total_pages=result.total_pages,
            markdown=result.markdown,
            elements=elements,
            tables=result.tables,
            images=result.images,
            metadata=result.metadata
        )


# ===========================================
# 工厂函数与便捷函数
# ===========================================

def create_pdf_core(enable_hybrid: bool = False) -> OpenDataLoaderCore:
    """
    创建 OpenDataLoaderCore 实例
    
    Args:
        enable_hybrid: 是否启用 Hybrid
        
    Returns:
        OpenDataLoaderCore
    """
    return OpenDataLoaderCore(enable_hybrid=enable_hybrid)


def parse_pdf(
    pdf_path: str,
    enable_hybrid: bool = False,
    pages: Union[List[int], str] = None
) -> PDFParseResult:
    """
    便捷函数：快速解析 PDF
    
    Args:
        pdf_path: PDF 文件路径
        enable_hybrid: 是否启用 Hybrid
        pages: 要解析的页码
        
    Returns:
        PDFParseResult
    """
    core = create_pdf_core(enable_hybrid=enable_hybrid)
    return core.parse(pdf_path, pages=pages)


async def parse_pdf_async(
    pdf_path: str,
    enable_hybrid: bool = False,
    pages: Union[List[int], str] = None
) -> PDFParseResult:
    """
    便捷函数：异步解析 PDF
    
    Args:
        pdf_path: PDF 文件路径
        enable_hybrid: 是否启用 Hybrid
        pages: 要解析的页码
        
    Returns:
        PDFParseResult
    """
    core = create_pdf_core(enable_hybrid=enable_hybrid)
    return await core.parse_async(pdf_path, pages=pages)


# ===========================================
# 测试
# ===========================================

if __name__ == "__main__":
    import sys
    
    print("🧪 测试 OpenDataLoaderCore...")
    
    # 测试环境变量
    print("\n1. 测试 Hybrid URL 配置:")
    print(f"   HYBRID_URL (环境变量): {os.environ.get('HYBRID_URL', '未设置')}")
    print(f"   自动检测 URL: {get_hybrid_url()}")
    print(f"   CUDA 启用: {get_cuda_enabled()}")
    
    # 测试核心类
    print("\n2. 测试 OpenDataLoaderCore 初始化:")
    try:
        core = OpenDataLoaderCore(enable_hybrid=False)
        print(f"   ✅ 初始化成功")
        print(f"   Hybrid URL: {core.hybrid_url}")
    except Exception as e:
        print(f"   ❌ 初始化失败: {e}")
    
    # 测试 JSON 标准化
    print("\n3. 测试 JSON 标准化:")
    
    test_json_1 = {
        "pages": [
            {"page_num": 1, "tables": [{"data": [["A", "B"]]}]},
            {"page_num": 2, "images": [{"image_data": "base64..."}]}
        ]
    }
    
    test_json_2 = {
        "tables": [{"page": 1, "data": [["A", "B"]]}],
        "images": [{"page": 2, "image_data": "base64..."}],
        "elements": [{"type": "heading", "content": "Title"}]
    }
    
    normalized_1 = core._normalize_json(test_json_1)
    normalized_2 = core._normalize_json(test_json_2)
    
    print(f"   输入 1 (pages 结构): {len(normalized_1['artifacts'])} 个 artifacts")
    print(f"   输入 2 (分类结构): {len(normalized_2['artifacts'])} 个 artifacts")
    
    print("\n✅ 测试完成")