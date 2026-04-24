"""
RAG Context Utils - RAG-Anything 风格的精准上下文提取

提供统一的上下文提取接口，支持：
- 最近标题 (closest_heading)
- 前文 (previous_text)
- 图说/表说 (caption)
- 后文 (next_text)

使用方式：
```python
from nanobot.ingestion.utils.rag_context import extract_precise_context

# 从 artifacts 列表中提取 target_idx 位置的精准上下文
context = extract_precise_context(artifacts, target_idx=5)

# 自定义搜索范围
context = extract_precise_context(
    artifacts, 
    target_idx=5,
    max_look_back=15,
    max_look_forward=10
)
```
"""

from typing import Dict, List, Any, Optional, Tuple
from loguru import logger


def extract_precise_context(
    artifacts: List[Dict[str, Any]],
    target_idx: int,
    max_look_back: int = 10,
    max_look_forward: int = 5
) -> Dict[str, str]:
    """
    RAG-Anything 风格的精准上下文提取
    
    模拟 RAG-Anything 的精準上下文提取：
    尋找最接近的標題 (Title)、前文 (Intro) 與後文 (Explanation)
    
    Args:
        artifacts: 所有 artifact 列表
        target_idx: 目标 artifact 的索引
        max_look_back: 向前查找的最大 artifact 数（默认 10）
        max_look_forward: 向后查找的最大 artifact 数（默认 5）
        
    Returns:
        Dict[str, str]: {
            "closest_heading": str,   # 最近的可识别标题
            "previous_text": str,     # 前文（最靠近的段落）
            "caption": str,           # 图说/表说（如 "Figure 1:"）
            "next_text": str          # 后文（图表后的第一段解释）
        }
        
    Example:
        >>> artifacts = [
        ...     {"type": "text", "content": "# Revenue Analysis"},
        ...     {"type": "text", "content": "This chart shows..."},
        ...     {"type": "image", "content": "chart.png"},
        ...     {"type": "text", "content": "As shown above..."}
        ... ]
        >>> extract_precise_context(artifacts, target_idx=2)
        {
            "closest_heading": "# Revenue Analysis",
            "previous_text": "This chart shows...",
            "caption": "",
            "next_text": "As shown above..."
        }
    """
    context = {
        "closest_heading": "無明確標題",
        "previous_text": "",
        "caption": "",
        "next_text": ""
    }
    
    # 1. 往前找 (尋找標題和前文)
    for i in range(max(0, target_idx - max_look_back), target_idx):
        if i >= len(artifacts):
            continue
            
        artifact = artifacts[i]
        if artifact is None:
            continue
            
        # 只处理 text 类型
        if artifact.get("type") != "text":
            continue
            
        content = str(artifact.get("content", "")).strip()
        if not content:
            continue
            
        # 判斷是否為標題 (Markdown 標題如 #, ##, 或全大寫短句)
        if _is_heading(content):
            if context["closest_heading"] == "無明確標題":
                context["closest_heading"] = content
                
        # 判斷是否為圖說 (如 Figure 1:, Table 2:)
        elif _is_caption(content):
            if not context["caption"]:
                context["caption"] = content
                
        # 一般前文 (只取最靠近的段落)
        elif not context["previous_text"] and len(content) > 20:
            context["previous_text"] = content
            
        # 如果標題和前文都找到了，就停止往前找
        if context["closest_heading"] != "無明確標題" and context["previous_text"]:
            break
    
    # 2. 往後找 (尋找圖表後的解釋分析)
    for i in range(target_idx + 1, min(target_idx + 1 + max_look_forward, len(artifacts))):
        artifact = artifacts[i]
        if artifact is None:
            continue
            
        if artifact.get("type") != "text":
            continue
            
        content = str(artifact.get("content", "")).strip()
        if content and len(content) > 20:
            context["next_text"] = content
            break  # 找到第一段有意義的後文就停止
            
    return context


def _is_heading(content: str) -> bool:
    """
    判断内容是否为标题
    
    规则：
    - Markdown 标题（以 # 开头）
    - 全大写且长度小于 50 字符
    """
    # Markdown 标题
    if content.startswith("#"):
        return True
        
    # 全大写短句（可能是标题）
    if len(content) < 50 and content.isupper():
        return True
        
    return False


def _is_caption(content: str) -> bool:
    """
    判断内容是否为图说/表说
    
    规则：
    - 包含 "Figure", "Fig.", "Table", "圖" 等关键词
    - 且在开头部分（前 15 个字符）
    """
    content_lower = content.lower()
    
    # 检查开头部分
    prefix = content_lower[:20] if len(content_lower) >= 20 else content_lower
    
    # Figure/Table 关键词检测
    if "figure" in prefix or "fig." in prefix or "table" in prefix or "圖" in prefix:
        return True
        
    return False


def extract_page_context(
    artifacts: List[Dict[str, Any]],
    page_num: int,
    max_look_back: int = 5
) -> Dict[str, str]:
    """
    提取特定页面的上下文（简化版）
    
    用于需要知道某一页的上下文信息，但不关心具体 artifact 索引的场景。
    例如：判断某页是否是标题页、该页附近的内容主题等。
    
    Args:
        artifacts: 所有 artifact 列表
        page_num: 目标页码（从 1 开始）
        max_look_back: 向前查找的最大 artifact 数
        
    Returns:
        Dict[str, str]: 同 extract_precise_context
    """
    # 找到该页的第一个 artifact 索引
    target_idx = None
    for i, artifact in enumerate(artifacts):
        if artifact and artifact.get("page", artifact.get("page_num")) == page_num:
            target_idx = i
            break
    
    if target_idx is None:
        return {
            "closest_heading": "無明確標題",
            "previous_text": "",
            "caption": "",
            "next_text": ""
        }
    
    return extract_precise_context(artifacts, target_idx, max_look_back)


def get_surrounding_texts(
    artifacts: List[Dict[str, Any]],
    target_idx: int,
    before: int = 2,
    after: int = 2
) -> Dict[str, List[str]]:
    """
    获取目标 artifact 周围的多段文本
    
    适用于需要更多上下文信息的场景，例如：
    - 理解某个表格的完整上下文
    - 提取某段文字的前后邻近内容
    
    Args:
        artifacts: 所有 artifact 列表
        target_idx: 目标 artifact 的索引
        before: 向前取的 artifact 数量
        after: 向后取的 artifact 数量
        
    Returns:
        Dict[str, List[str]]: {
            "before": [...],  # 前面的文本列表
            "target": "...",  # 目标文本
            "after": [...]    # 后面的文本列表
        }
    """
    result = {"before": [], "target": "", "after": []}
    
    # 获取目标文本
    if 0 <= target_idx < len(artifacts):
        artifact = artifacts[target_idx]
        if artifact:
            result["target"] = str(artifact.get("content", "")).strip()
    
    # 获取前面的文本
    start_idx = max(0, target_idx - before)
    for i in range(start_idx, target_idx):
        artifact = artifacts[i]
        if artifact and artifact.get("type") == "text":
            content = str(artifact.get("content", "")).strip()
            if content:
                result["before"].append(content)
    
    # 获取后面的文本
    end_idx = min(len(artifacts), target_idx + after + 1)
    for i in range(target_idx + 1, end_idx):
        artifact = artifacts[i]
        if artifact and artifact.get("type") == "text":
            content = str(artifact.get("content", "")).strip()
            if content:
                result["after"].append(content)
    
    return result


def merge_context_with_prompt(
    context: Dict[str, str],
    prompt_template: str = None
) -> str:
    """
    将上下文信息合并到 prompt 模板中
    
    Args:
        context: extract_precise_context 返回的上下文字典
        prompt_template: 可选的 prompt 模板，如果为 None 则使用默认模板
        
    Returns:
        str: 包含上下文信息的 prompt 字符串
    """
    if prompt_template is None:
        prompt_template = """根據以下結構化上下文回答問題：

【所屬章節標題】
{closest_heading}

【圖表前的引言】
{previous_text}

【圖表標籤/圖說】
{caption}

【圖表後的分析】
{next_text}
"""
    
    return prompt_template.format(**context)
