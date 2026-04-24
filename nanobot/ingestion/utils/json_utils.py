"""
JSON Utils - LLM 响应 JSON 解析公共函数

消除重复代码，提供统一的 JSON 解析接口。

使用方式：
```python
from nanobot.ingestion.utils.json_utils import parse_llm_json_response

# 基本使用
result = parse_llm_json_response(llm_response)

# 自定义包装 key
result = parse_llm_json_response(llm_response, wrap_keys=['items', 'records'])
```
"""

import json
import re
from typing import List, Dict, Any, Optional
from loguru import logger


def parse_llm_json_response(
    response: str,
    wrap_keys: Optional[List[str]] = None
) -> List[Dict]:
    """
    解析 LLM 返回的 JSON 响应
    
    支持：
    - 从代码块 ```json ... ``` 中提取 JSON
    - 自动解包常见的包装结构（如 {"segments": [...]}）
    - 处理纯 JSON 数组响应
    - 处理单一对象（自动包装成列表）
    
    Args:
        response: LLM 原始响应文本
        wrap_keys: 常见的包装 key 列表，默认 ['segments', 'shareholders', 'data', 'result']
        
    Returns:
        List[Dict]: 解析后的数据列表
        
    Example:
        >>> parse_llm_json_response('```json\\n{"segments": [{"name": "A"}]}\\n```')
        [{'name': 'A'}]
        
        >>> parse_llm_json_response('```json\\n[{"name": "A"}, {"name": "B"}]\\n```')
        [{'name': 'A'}, {'name': 'B'}]
    """
    if wrap_keys is None:
        wrap_keys = ['segments', 'shareholders', 'data', 'result', 'metrics', 'personnel', 'shareholders_data']
    
    try:
        # Step 1: 从代码块中提取 JSON
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # 没有代码块，尝试直接解析整个响应
            json_str = response.strip()
        
        # Step 2: 解析 JSON
        data = json.loads(json_str)
        
        # Step 3: 自动解包常见包装结构
        if isinstance(data, dict):
            for key in wrap_keys:
                if key in data:
                    extracted = data[key]
                    # 确保返回列表
                    if isinstance(extracted, list):
                        return extracted
                    elif isinstance(extracted, dict):
                        return [extracted]
                    elif extracted is None:
                        return []
            
            # 如果没有匹配到任何 wrap_keys，但本身是 dict，返回包装后的列表
            return [data]
        
        if isinstance(data, list):
            return data
        
        # 其他情况返回空列表
        return []
        
    except json.JSONDecodeError as e:
        logger.warning(f"   ⚠️ JSON 解析失败: {e}")
        # 尝试更宽松的解析方式
        return _fallback_json_parse(response, wrap_keys)


def _fallback_json_parse(response: str, wrap_keys: List[str]) -> List[Dict]:
    """
    宽松的 JSON 解析 fallback
    
    处理 LLM 返回的不完整或格式略微错误的 JSON
    """
    try:
        # 尝试找到 JSON 对象的开始和结束
        start = response.find('{')
        end = response.rfind('}')
        
        if start != -1 and end != -1 and start < end:
            json_str = response[start:end+1]
            data = json.loads(json_str)
            
            if isinstance(data, dict):
                for key in wrap_keys:
                    if key in data:
                        extracted = data[key]
                        if isinstance(extracted, list):
                            return extracted
                        elif isinstance(extracted, dict):
                            return [extracted]
                return [data]
            
            if isinstance(data, list):
                return data
        
        return []
        
    except Exception as e:
        logger.warning(f"   ⚠️ Fallback JSON 解析也失败: {e}")
        return []


def extract_json_from_response(response: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 响应中提取单个 JSON 对象（不是数组）
    
    适用于预期返回单一对象的场景
    
    Args:
        response: LLM 原始响应
        
    Returns:
        Optional[Dict]: 解析后的 JSON 对象，解析失败返回 None
    """
    result = parse_llm_json_response(response)
    if result and len(result) > 0:
        return result[0]
    return None


def build_json_response(
    data: Any,
    wrap_key: Optional[str] = None,
    indent: Optional[int] = 2
) -> str:
    """
    将数据构建为 JSON 响应字符串（用于测试或模拟 LLM 响应）
    
    Args:
        data: 要包装的数据
        wrap_key: 可选的包装 key
        indent: JSON 缩进
        
    Returns:
        str: JSON 格式的字符串
        
    Example:
        >>> build_json_response([{"name": "A"}], wrap_key="segments")
        '```json\\n{"segments": [{"name": "A"}]}\\n```'
    """
    if wrap_key:
        wrapped = {wrap_key: data}
    else:
        wrapped = data
    
    json_str = json.dumps(wrapped, ensure_ascii=False, indent=indent)
    return f"```json\n{json_str}\n```"
