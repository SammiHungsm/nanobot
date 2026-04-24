"""
RAG Context Utils - RAG-Anything 风格的精准上下文提取

提供统一的上下文提取接口，支持：
- 最近标题 (closest_heading)
- 前文 (previous_text)
- 图说/表说 (caption)
- 后文 (next_text)

🌟 v4.11 修复：
① extend_to_page_start — 自动扩展到同一页开头，不怕财报标题在第 1 页
② 扫描 text/heading/title 类型 — 不再只扫描 text
③ 收集所有 caption — 同一页有 Figure 1, Figure 2 都能抓到
④ 收集所有 next_text — 图表后多段解說都能保留
⑤ 参数化 — 所有范围参数都可配置

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
    max_look_forward=10,
    extend_to_page_start=False  # 关闭页面级扩展
)
```
"""

from typing import Dict, List, Any, Optional, Tuple
from loguru import logger


def extract_precise_context(
    artifacts: List[Dict[str, Any]],
    target_idx: int,
    max_look_back: int = 10,
    max_look_forward: int = 5,
    extend_to_page_start: bool = True
) -> Dict[str, str]:
    """
    RAG-Anything 风格的精准上下文提取
    
    🌟 v4.11 修复（按准确度排序）：
    ① max_look_back 扩展到同一页开头（默认 True）— 财报标题可能在第 1 页
    ③ 收集所有 caption（不只第一个）— 同一页有多个 Figure 1, Figure 2
    ④ 收集所有 next_text（不只一段）— 图表后可能有多段解说
    ② 同时扫描 text/heading/title 类型
    ⑤ 参数化 — max_look_back/forward 可传参控制
    
    Args:
        artifacts: 所有 artifact 列表
        target_idx: 目标 artifact 的索引
        max_look_back: 向前查找的最大 artifact 数（默认 10，extend_to_page_start=True 时忽略）
        max_look_forward: 向后查找的最大 artifact 数（默认 5）
        extend_to_page_start: 是否扩展到同一页开头（默认 True，覆盖 max_look_back）
        
    Returns:
        Dict[str, str]: {
            "closest_heading": str,      # 最近的可识别标题
            "all_headings": List[str],   # 🆕 v4.11 所有找到的标题（由近到远）
            "previous_text": str,        # 前文（最靠近的段落）
            "caption": str,             # 🆕 所有图说/表说（用 | 分隔）
            "all_captions": List[str],   # 🆕 v4.11 所有 caption 列表
            "next_text": str,            # 🆕 所有后文（用 \n---\n 分隔）
            "all_next_texts": List[str]  # 🆕 v4.11 所有后文列表
        }
    """
    context = {
        "closest_heading": "無明確標題",
        "all_headings": [],
        "previous_text": "",
        "caption": "",
        "all_captions": [],
        "next_text": "",
        "all_next_texts": []
    }
    
    target_artifact = artifacts[target_idx] if 0 <= target_idx < len(artifacts) else None
    target_page = target_artifact.get("page", 0) if target_artifact else 0
    
    # 🌟 ① 计算往后找的起始位置
    if extend_to_page_start and target_page > 0:
        look_back_start = 0
        for i in range(target_idx - 1, -1, -1):
            a = artifacts[i]
            if a is None:
                continue
            a_page = a.get("page", 0)
            if a_page != target_page:
                break
            look_back_start = i
    else:
        look_back_start = max(0, target_idx - max_look_back)
    
    # 1. 往前找 (寻找标题和前文)
    for i in range(look_back_start, target_idx):
        if i >= len(artifacts):
            continue
            
        artifact = artifacts[i]
        if artifact is None:
            continue
        
        # 🌟 ② 支持 text / heading / title 类型
        art_type = artifact.get("type", "")
        if art_type not in ("text", "heading", "title"):
            continue
            
        content = str(artifact.get("content", "")).strip()
        if not content:
            continue
        
        # 判断是否为标题
        if _is_heading(content, art_type):
            context["all_headings"].append(content)
            context["closest_heading"] = content  # 最近的一个覆盖
            
        # 🌟 ③ 收集所有 caption（不只第一个）
        elif _is_caption(content):
            context["all_captions"].append(content)
            
        # 一般前文 (只取最靠近的段落)
        elif not context["previous_text"] and len(content) > 20:
            context["previous_text"] = content
    
    # 🌟 ③ caption 合并为字符串
    if context["all_captions"]:
        context["caption"] = " | ".join(context["all_captions"])
    
    # 2. 往后找 (寻找图表后的所有解释分析)
    for i in range(target_idx + 1, min(target_idx + 1 + max_look_forward, len(artifacts))):
        artifact = artifacts[i]
        if artifact is None:
            continue
        
        art_type = artifact.get("type", "")
        if art_type not in ("text", "heading", "title"):
            continue
            
        content = str(artifact.get("content", "")).strip()
        if content and len(content) > 20:
            context["all_next_texts"].append(content)
            if not context["next_text"]:
                context["next_text"] = content
    
    # 🌟 ④ next_text 合并为多段落字符串
    if len(context["all_next_texts"]) > 1:
        context["next_text"] = "\n---\n".join(context["all_next_texts"])
    
    return context


def _is_heading(content: str, art_type: str = None) -> bool:
    """
    判断内容是否为标题
    
    规则：
    - 如果传入 art_type="heading" 或 "title"，直接认为是标题
    - Markdown 标题（以 # 开头）
    - 全大写且长度小于 50 字符
    """
    # 🌟 ② 如果 artifact 本身类型是 heading/title，直接通过
    if art_type in ("heading", "title"):
        return True
    
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
    - 且在开头部分（前 20 个字符）
    """
    content_lower = content.lower()
    prefix = content_lower[:20] if len(content_lower) >= 20 else content_lower
    
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
    
    Args:
        artifacts: 所有 artifact 列表
        page_num: 目标页码（从 1 开始）
        max_look_back: 向前查找的最大 artifact 数
        
    Returns:
        Dict[str, str]: 同 extract_precise_context
    """
    target_idx = None
    for i, artifact in enumerate(artifacts):
        if artifact and artifact.get("page", artifact.get("page_num")) == page_num:
            target_idx = i
            break
    
    if target_idx is None:
        return {
            "closest_heading": "無明確標題",
            "all_headings": [],
            "previous_text": "",
            "caption": "",
            "all_captions": [],
            "next_text": "",
            "all_next_texts": []
        }
    
    return extract_precise_context(artifacts, target_idx, max_look_back=max_look_back)


def get_surrounding_texts(
    artifacts: List[Dict[str, Any]],
    target_idx: int,
    before: int = 2,
    after: int = 2
) -> Dict[str, List[str]]:
    """
    获取目标 artifact 周围的多段文本
    
    Args:
        artifacts: 所有 artifact 列表
        target_idx: 目标 artifact 的索引
        before: 向前取的 artifact 数量
        after: 向后取的 artifact 数量
        
    Returns:
        Dict[str, List[str]]: {
            "before": [...],
            "target": "...",
            "after": [...]
        }
    """
    result = {"before": [], "target": "", "after": []}
    
    if 0 <= target_idx < len(artifacts):
        artifact = artifacts[target_idx]
        if artifact:
            result["target"] = str(artifact.get("content", "")).strip()
    
    start_idx = max(0, target_idx - before)
    for i in range(start_idx, target_idx):
        artifact = artifacts[i]
        if artifact and artifact.get("type") == "text":
            content = str(artifact.get("content", "")).strip()
            if content:
                result["before"].append(content)
    
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
    """
    if prompt_template is None:
        prompt_template = """根據以下結構化上下文回答問題：

【所屬章節標題】
{closest_heading}

【所有標題層級】
{all_headings}

【圖表前的引言】
{previous_text}

【圖表標籤/圖說】
{caption}

【圖表後的分析】
{next_text}
"""
    
    return prompt_template.format(**context)
