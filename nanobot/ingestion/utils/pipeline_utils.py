"""
Pipeline Utils - 辅助工具函数

职责：
- 文件 Hash 计算
- 表格 JSON → Markdown 转换
- 页面 Artifacts 合并
- 关键词搜索

这些函数从 pipeline.py 移出，遵循单一职责原则
"""

import hashlib
import re
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from loguru import logger


def compute_file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """
    计算文件 Hash
    
    Args:
        file_path: 文件路径
        algorithm: Hash 算法
        
    Returns:
        str: Hash 字串
    """
    hasher = hashlib.new(algorithm)
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    
    return hasher.hexdigest()


def find_keyword_pages(
    artifacts: List[Dict[str, Any]],
    keywords: List[str]
) -> List[int]:
    """
    在 artifacts 中搜索关键词
    
    Args:
        artifacts: Artifacts 列表
        keywords: 关键词列表
        
    Returns:
        List[int]: 找到的页面列表
    """
    candidate_pages = set()
    
    for artifact in artifacts:
        if artifact is None:
            continue
            
        content = artifact.get("content", "") or ""
        content_lower = content.lower()
        
        for keyword in keywords:
            if keyword.lower() in content_lower:
                candidate_pages.add(artifact.get("page", 0))
                break
    
    return sorted(list(candidate_pages))


def find_revenue_breakdown_pages(
    artifacts: List[Dict[str, Any]],
    keywords: List[str] = None
) -> List[int]:
    """
    在 artifacts 中搜索关键词，找到 Revenue Breakdown 页面
    
    Args:
        artifacts: Artifacts 列表
        keywords: 关键词列表
        
    Returns:
        List[int]: 找到的页面列表
    """
    keywords = keywords or [
        "revenue breakdown", "revenue by", "geographical", 
        "segment", "business segment", "product mix",
        "region", "市場分部", "收入分部", "地區"
    ]
    
    candidate_pages = set()
    
    for artifact in artifacts:
        if artifact is None:
            continue
            
        content = artifact.get("content", "") or artifact.get("markdown", "") or ""
        content_clean = content.lower().replace("\n", " ").replace(" ", "")
        
        for keyword in keywords:
            keyword_clean = keyword.lower().replace(" ", "")
            if keyword_clean in content_clean:
                candidate_pages.add(artifact.get("page", 0))
                break
    
    # 检查表格中是否有百分比
    for artifact in artifacts:
        if artifact is None:
            continue
            
        if artifact.get("type") == "table":
            table_content = artifact.get("content", {})
            if isinstance(table_content, dict):
                table_str = str(table_content).lower()
                if "%" in table_str or "percentage" in table_str:
                    candidate_pages.add(artifact.get("page", 0))
    
    return sorted(list(candidate_pages))


def json_table_to_markdown(table_json: Dict[str, Any]) -> Optional[str]:
    """
    将 JSON 表格转换为 Markdown
    
    Args:
        table_json: 表格 JSON
        
    Returns:
        str: Markdown 表格
    """
    if not table_json:
        return None
    
    rows = table_json.get("rows", []) or table_json.get("data", [])
    headers = table_json.get("headers", [])
    
    if not rows:
        return None
    
    if headers:
        header_line = "| " + " | ".join(headers) + " |"
        separator = "| " + " | ".join(["---"] * len(headers)) + " |"
    else:
        first_row = rows[0] if rows else []
        if isinstance(first_row, dict):
            headers = list(first_row.keys())
        elif isinstance(first_row, list):
            headers = [f"Col{i+1}" for i in range(len(first_row))]
        else:
            return None
        
        header_line = "| " + " | ".join(headers) + " |"
        separator = "| " + " | ".join(["---"] * len(headers)) + " |"
    
    body_lines = []
    for row in rows:
        if isinstance(row, dict):
            cells = [str(row.get(h, "")) for h in headers]
        elif isinstance(row, list):
            cells = [str(cell) for cell in row]
        else:
            continue
        
        body_lines.append("| " + " | ".join(cells) + " |")
    
    return header_line + "\n" + separator + "\n" + "\n".join(body_lines)


def merge_page_artifacts(page_artifacts: List[Dict[str, Any]]) -> str:
    """
    合并页面 artifacts
    
    Args:
        page_artifacts: 页面级别的 artifacts
        
    Returns:
        str: 合并后的文本
    """
    merged_text = ""
    
    for artifact in page_artifacts:
        if artifact is None:
            continue
            
        content = artifact.get("content", "") or artifact.get("markdown", "") or ""
        
        if content:
            merged_text += content + "\n\n"
    
    return merged_text.strip()


def extract_year_from_filename(filename: str) -> Optional[int]:
    """
    从文件名提取年份
    
    Args:
        filename: 文件名
        
    Returns:
        Optional[int]: 年份
    """
    year_match = re.search(r'(20[0-9]{2})', filename)
    if year_match:
        return int(year_match.group(1))
    return None