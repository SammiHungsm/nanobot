"""
OpenDataLoader Parser - 純 Parser 層

職責：
- 將 PDF 解析為 Artifacts（文字、表格、圖片）
- 不涉及資料庫操作
- 不涉及 LLM 提取

這是 Parser 層，只負責「看」。
"""

import os
import json
import asyncio
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger


class OpenDataLoaderParser:
    """
    OpenDataLoader 解析器
    
    純 Parser：輸入 PDF，輸出 Artifacts。
    不碰資料庫，不碰 LLM。
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
        logger.info(f"📖 OpenDataLoader 正在解析: {pdf_path}")
        
        # 同步解析（OpenDataLoader 是同步的）
        result_json = self._run_opendataloader(pdf_path, doc_id)
        
        # 轉換為標準 Artifacts 格式
        artifacts = self._convert_to_artifacts(result_json)
        
        logger.info(f"✅ 解析完成：{len(artifacts)} 個 artifacts")
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
        logger.info(f"📖 OpenDataLoader 正在異步解析: {pdf_path}")
        
        # 使用 to_thread 將阻塞操作放到背景
        result_json = await asyncio.to_thread(self._run_opendataloader, pdf_path, doc_id)
        
        # 轉換為標準格式
        artifacts = self._convert_to_artifacts(result_json)
        
        logger.info(f"✅ 解析完成：{len(artifacts)} 個 artifacts")
        return artifacts
    
    def _run_opendataloader(self, pdf_path: str, doc_id: str = None) -> Dict[str, Any]:
        """
        執行 OpenDataLoader 解析
        
        Args:
            pdf_path: PDF 文件路徑
            doc_id: 文檔 ID
            
        Returns:
            Dict: OpenDataLoader 原始輸出
        """
        import traceback
        
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / f"{doc_id or 'output'}.json"
            
            try:
                from opendataloader_pdf import convert
                
                # 嘗試使用關鍵字參數
                try:
                    convert(pdf_path, output_path=str(out_path), output_format="json", pages="all")
                except TypeError:
                    # Fallback: 位置參數
                    convert(pdf_path, str(out_path))
                
                if out_path.exists():
                    if out_path.is_dir():
                        json_files = list(out_path.glob("*.json"))
                        if json_files:
                            with open(json_files[0], 'r', encoding='utf-8') as f:
                                return json.load(f)
                        else:
                            logger.error(f"❌ 目錄中找不到 JSON 文件")
                            return {}
                    else:
                        with open(out_path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                else:
                    logger.error("❌ 轉換完成，但找不到輸出文件")
                    return {}
                    
            except Exception as e:
                logger.error(f"❌ OpenDataLoader 解析失敗: {e}")
                traceback.print_exc()
                return {}
    
    def _convert_to_artifacts(self, result_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        將 OpenDataLoader 輸出轉換為標準 Artifacts 格式
        
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
            if "kids" in result_json:
                content_blocks = result_json["kids"]
            elif "content" in result_json:
                content_blocks = result_json["content"]
            elif "pages" in result_json:
                content_blocks = result_json["pages"]
            elif "elements" in result_json:
                content_blocks = result_json["elements"]
            else:
                content_blocks = []
        else:
            content_blocks = []
        
        if not content_blocks:
            logger.warning("⚠️ OpenDataLoader 返回空內容")
            return artifacts
        
        for i, block in enumerate(content_blocks):
            if not isinstance(block, dict):
                continue
            
            block_type = block.get("type", "unknown")
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
                artifacts.append({
                    "type": "image",
                    "page_num": page_num,
                    "metadata": {
                        "source": "opendataloader",
                        "image_source": block.get("source"),
                        "bounding_box": block.get("bounding box"),
                        "id": block.get("id")
                    }
                })
            
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
    
    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        """獲取 PDF 頁數"""
        try:
            import fitz
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except:
            return 0
    
    @staticmethod
    def find_pages_with_keywords(artifacts: List[Dict[str, Any]], keywords: List[str]) -> List[int]:
        """
        在 Artifacts 中搜尋包含關鍵字的頁面
        
        Args:
            artifacts: Artifacts 列表
            keywords: 關鍵字列表
            
        Returns:
            List[int]: 頁碼列表
        """
        candidate_pages = set()
        
        for artifact in artifacts:
            artifact_type = artifact.get("type")
            page_num = artifact.get("page_num")
            
            if artifact_type == "text_chunk":
                content = str(artifact.get("content", "")).lower()
                for keyword in keywords:
                    if keyword.lower() in content:
                        candidate_pages.add(page_num)
                        break
            
            elif artifact_type == "table":
                table_json = artifact.get("content_json", {})
                content = json.dumps(table_json, ensure_ascii=False).lower()
                for keyword in keywords:
                    if keyword.lower() in content:
                        candidate_pages.add(page_num)
                        break
        
        return sorted(list(candidate_pages))