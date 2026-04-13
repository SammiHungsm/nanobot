"""
OpenDataLoader Parser - 純 Parser 層

職責：
- 將 PDF 解析為 Artifacts（文字、表格、圖片）
- 不涉及資料庫操作
- 不涉及 LLM 提取

這是 Parser 層，只負責「看」。

參考：https://github.com/opendataloader-project/opendataloader-pdf
"""

import os
import json
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger


class OpenDataLoaderParser:
    """
    OpenDataLoader 解析器
    
    純 Parser：輸入 PDF，輸出 Artifacts。
    不碰資料庫，不碰 LLM。
    
    根據官方文檔：
    - Python API: opendataloader_pdf.convert()
    - 參數：input_path, output_dir, format, image_output, image_format
    - 支持批量處理：input_path 可以是 list
    """
    
    def __init__(self):
        """初始化"""
        pass
    
    def parse(self, pdf_path: str, doc_id: str = None) -> List[Dict[str, Any]]:
        """
        解析 PDF 文件
        
        Args:
            pdf_path: PDF 文件路徑
            doc_id: 文檔 ID（可選，用於調試）
            
        Returns:
            List[Dict]: Artifacts 列表
        """
        logger.info(f"📖 OpenDataLoader 正在解析：{pdf_path}")
        
        # 同步解析（OpenDataLoader 是同步的）
        result_json = self._run_opendataloader(pdf_path, doc_id)
        
        # 轉換為標準 Artifacts 格式
        artifacts = self._convert_to_artifacts(result_json)
        
        logger.info(f"✅ 解析完成：{len(artifacts)} 個 artifacts")
        return artifacts
    
    def parse_pages(self, pdf_path: str, pages: List[int], doc_id: str = None) -> List[Dict[str, Any]]:
        """
        🌟 只解析 PDF 的特定页面（用于快速提取封面信息）
        
        Args:
            pdf_path: PDF 文件路径
            pages: 要解析的页码列表（如 [1, 2]）
            doc_id: 文档 ID
            
        Returns:
            List[Dict]: Artifacts 列表
        """
        logger.info(f"📖 OpenDataLoader 快速解析 Page {pages}：{pdf_path}")
        
        result_json = self._run_opendataloader(pdf_path, doc_id, pages=pages)
        artifacts = self._convert_to_artifacts(result_json)
        
        logger.info(f"✅ Page {pages} 解析完成：{len(artifacts)} 個 artifacts")
        return artifacts
    
    async def parse_async(self, pdf_path: str, doc_id: str = None) -> List[Dict[str, Any]]:
        """
        異步解析 PDF（將阻塞操作放到背景線程）
        
        Args:
            pdf_path: PDF 文件路徑
            doc_id: 文檔 ID
            
        Returns:
            List[Dict]: Artifacts 列表
        """
        logger.info(f"📖 OpenDataLoader 正在異步解析：{pdf_path}")
        
        # 使用 to_thread 將阻塞操作放到背景
        result_json = await asyncio.to_thread(self._run_opendataloader, pdf_path, doc_id)
        
        # 轉換為標準格式
        artifacts = self._convert_to_artifacts(result_json)
        
        logger.info(f"✅ 解析完成：{len(artifacts)} 個 artifacts")
        return artifacts
    
    def _run_opendataloader(self, pdf_path: str, doc_id: str = None, pages: List[int] = None) -> Dict[str, Any]:
        """
        執行 OpenDataLoader 解析
        
        🔧 根據官方 GitHub 文檔修復 API 調用：
        https://github.com/opendataloader-project/opendataloader-pdf
        
        Python API:
        ```python
        opendataloader_pdf.convert(
            input_path=["file1.pdf", "folder/"],  # 可以是 list 或 str
            output_dir="output/",
            format="markdown,json",  # 逗号分隔
            image_output="embedded",  # 或 "external"
            image_format="png",
            pages=[1, 2, 3]  # 🌟 只处理特定页面
        )
        ```
        
        Args:
            pdf_path: PDF 文件路徑
            doc_id: 文檔 ID
            pages: 要解析的页码列表（如 [1, 2]），None 表示所有页面
            
        Returns:
            Dict: OpenDataLoader 原始輸出
        """
        import traceback
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            try:
                from opendataloader_pdf import convert
                
                logger.debug(f"🔧 調用 OpenDataLoader convert() API")
                logger.debug(f"   input_path: {pdf_path}")
                logger.debug(f"   output_dir: {temp_dir}")
                logger.debug(f"   format: json")
                logger.info("🔥 警告：正在使用純 CPU 執行 OpenDataLoader Hybrid 視覺模式，請耐心等待...")
                
                # 🌟 如果只处理特定页面，不启用 Hybrid（快速模式）
                if pages:
                    # 🌟 将 list 转换为逗号分隔的字符串
                    pages_str = ",".join(str(p) for p in pages)
                    logger.info(f"📄 快速模式：只处理 Page {pages_str}（不启用 Hybrid）")
                    convert(
                        input_path=pdf_path,
                        output_dir=temp_dir,
                        format="json",
                        image_output="embedded",
                        image_format="png",
                        pages=pages_str  # 🌟 字符串格式："1,2"
                    )
                else:
                    # 完整解析：启用 Hybrid
                    convert(
                        input_path=pdf_path,          # 可以是 str 或 list
                        output_dir=temp_dir,          # 目錄路徑
                        format="json",                # 輸出格式
                        image_output="embedded",      # Base64 data URIs
                        image_format="png",           # 圖片格式
                        
                        # 🌟 啟動 Hybrid AI 視覺模式（用 Docling 進行版面與表格分析）
                        hybrid="docling-fast",        # 使用 docling 模型
                        hybrid_mode="auto",           # 🌟 "auto" (dynamic triage) 或 "full" (all pages)
                        hybrid_url="http://localhost:5002",  # 🌟 指向本地 Hybrid 服务器
                        hybrid_timeout="600000",      # 🌟 600 秒 = 10 分钟（CPU 模式需要更长 timeout）
                        hybrid_fallback=True          # 🌟 如果 Hybrid 失败，fallback 到 Java
                    )
                
                # 查找輸出的 JSON 文件
                # OpenDataLoader 會以 PDF 文件名命名輸出文件
                pdf_name = Path(pdf_path).stem
                expected_output = temp_path / f"{pdf_name}.json"
                
                # 如果找不到，嘗試其他可能的文件名
                if not expected_output.exists():
                    json_files = list(temp_path.glob("*.json"))
                    if json_files:
                        expected_output = json_files[0]
                        logger.debug(f"📄 找到 JSON 文件：{expected_output.name}")
                    else:
                        logger.error("❌ 找不到任何 JSON 輸出文件")
                        return {}
                
                # 讀取 JSON
                if expected_output.exists():
                    with open(expected_output, 'r', encoding='utf-8') as f:
                        result = json.load(f)
                    logger.debug(f"✅ 成功讀取 JSON: {expected_output.name}")
                    return result
                else:
                    logger.error("❌ 轉換完成，但找不到輸出文件")
                    return {}
                    
            except ImportError as ie:
                logger.error(f"❌ opendataloader_pdf 未安裝：{ie}")
                logger.error("💡 請運行：pip install opendataloader-pdf")
                traceback.print_exc()
                return {}
            except Exception as e:
                logger.error(f"❌ OpenDataLoader 解析失敗：{e}")
                traceback.print_exc()
                return {}
    
    def _convert_to_artifacts(self, result_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        將 OpenDataLoader 輸出轉換為標準 Artifacts 格式
        
        OpenDataLoader 輸出結構（根據 schema.json）：
        ```json
        {
            "kids": [
                {
                    "type": "table|image|paragraph|heading|list",
                    "page number": 1,
                    "bounding box": {...},
                    "content": "...",
                    "data": "base64..."  // for images (embedded mode)
                }
            ]
        }
        ```
        
        Args:
            result_json: OpenDataLoader 原始輸出
            
        Returns:
            List[Dict]: 標準 Artifacts 列表
        """
        artifacts = []
        
        # 處理不同的輸出格式
        if isinstance(result_json, list):
            content_blocks = result_json
        elif isinstance(result_json, dict):
            # 優先級：kids > pages > content > elements
            if "kids" in result_json:
                content_blocks = result_json["kids"]
            elif "pages" in result_json:
                content_blocks = result_json["pages"]
            elif "content" in result_json:
                content_blocks = result_json["content"]
            elif "elements" in result_json:
                content_blocks = result_json["elements"]
            else:
                content_blocks = []
        else:
            content_blocks = []
        
        if not content_blocks:
            logger.warning("⚠️ OpenDataLoader 返回空內容")
            return artifacts
        
        logger.debug(f"📊 處理 {len(content_blocks)} 個內容塊")
        
        for i, block in enumerate(content_blocks):
            if not isinstance(block, dict):
                continue
            
            block_type = block.get("type", "unknown")
            # 支持不同的 page number 字段名
            page_num = block.get("page number", block.get("page", block.get("page_num", 1)))
            
            if block_type == "table":
                artifacts.append({
                    "type": "table",
                    "page_num": page_num,
                    "content_json": block,
                    "metadata": {
                        "source": "opendataloader",
                        "original_index": i,
                        "bounding_box": block.get("bounding box"),
                        "id": block.get("id")
                    }
                })
            
            elif block_type == "image":
                # 🔧 根據 schema.json 提取圖片數據
                # embedded mode: "data" 字段包含 Base64 data URI
                # external mode: "source" 字段包含文件路徑
                image_data = None
                image_format = block.get("format", "png")
                bounding_box = block.get("bounding box")
                
                # 優先檢查 "data" 字段（embedded 模式的 Base64）
                if "data" in block and block["data"]:
                    image_data = block["data"]  # Base64 data URI
                    logger.debug(f"✅ 找到嵌入圖片數據 (embedded mode)")
                
                # Fallback: 檢查 "source" 是否是 data URI
                elif "source" in block:
                    image_source = block["source"]
                    if isinstance(image_source, str) and image_source.startswith("data:image"):
                        image_data = image_source
                        logger.debug(f"✅ 找到 source 中的 data URI")
                
                artifact = {
                    "type": "image",
                    "page_num": page_num,
                    "metadata": {
                        "source": "opendataloader",
                        "image_source": block.get("source"),
                        "bounding_box": bounding_box,
                        "id": block.get("id"),
                        "image_format": image_format,
                        "has_image_data": image_data is not None,
                        "extraction_mode": "embedded" if image_data else "pending"
                    }
                }
                
                if image_data:
                    artifact["image_data"] = image_data
                    artifact["image_format"] = image_format
                
                artifacts.append(artifact)
            
            elif block_type in ["paragraph", "heading", "header", "footer"]:
                text_content = block.get("content", "")
                if text_content:
                    artifacts.append({
                        "type": "text_chunk",
                        "page_num": page_num,
                        "content": text_content,
                        "metadata": {
                            "source": "opendataloader",
                            "original_index": i,
                            "block_type": block_type,
                            "level": block.get("level") or block.get("heading level"),
                            "font": block.get("font"),
                            "font_size": block.get("font size")
                        }
                    })
            
            elif block_type == "list":
                list_items = block.get("list items", [])
                list_text_parts = []
                for item in list_items:
                    if isinstance(item, dict):
                        item_text = item.get("content", item.get("text", ""))
                        if item_text:
                            list_text_parts.append(item_text)
                
                if list_text_parts:
                    artifacts.append({
                        "type": "text_chunk",
                        "page_num": page_num,
                        "content": " | ".join(list_text_parts),
                        "metadata": {
                            "source": "opendataloader",
                            "original_index": i,
                            "block_type": "list",
                            "number_of_items": block.get("number of list items", len(list_items))
                        }
                    })
            
            else:
                # 其他類型，嘗試提取內容
                text_content = block.get("content", block.get("text", ""))
                if text_content:
                    artifacts.append({
                        "type": "text_chunk",
                        "page_num": page_num,
                        "content": str(text_content),
                        "metadata": {
                            "source": "opendataloader",
                            "original_index": i,
                            "block_type": block_type
                        }
                    })
        
        return artifacts
