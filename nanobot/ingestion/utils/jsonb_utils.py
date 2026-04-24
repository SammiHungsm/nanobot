"""
JSONB Utilities - 統一的 JSONB 操作輔助函數 (v4.16)

提供：
1. JsonbEncoder - 自定義 JSON Encoder
2. jsonb_set - PostgreSQL jsonb_set 語句生成
3. jsonb_merge - JSONB 合併操作
4. safe_jsonb_value - 安全地將 Python 對象轉換為 JSONB 兼容值

使用方式：
    from nanobot.ingestion.utils.jsonb_utils import JsonbEncoder, safe_jsonb_value, jsonb_merge
    
    # 在 asyncpg 中的使用
    await conn.execute(
        \"UPDATE table SET extra_data = $1::jsonb WHERE id = $2\",
        json.dumps(data, cls=JsonbEncoder),
        table_id
    )
    
    # JSONB 合併
    await conn.execute(
        f\"UPDATE table SET extra_data = extra_data || $1::jsonb WHERE id = $2\",
        json.dumps(partial_data, cls=JsonbEncoder),
        table_id
    )
"""

import json
from datetime import datetime, date, time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from loguru import logger


# ============================================================
# 自定義 JSON Encoder
# ============================================================

class JsonbEncoder(json.JSONEncoder):
    """
    自定義 JSON Encoder，用於處理 PostgreSQL JSONB 不支持的類型
    
    支持的類型：
    - datetime, date, time → ISO 格式字符串
    - Decimal → float
    - UUID → string
    - bytes → base64 string
    - set, frozenset → list
    """
    
    def default(self, obj: Any) -> Any:
        """
        轉換不支持的類型
        
        Args:
            obj: 需要轉換的對象
            
        Returns:
            JSON 兼容的類型
        """
        # datetime 系列
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, time):
            return obj.isoformat()
        
        # Decimal → float（損失精度但 JSONB 支持）
        if isinstance(obj, Decimal):
            return float(obj)
        
        # UUID → string
        if isinstance(obj, UUID):
            return str(obj)
        
        # bytes → base64（如果無法編碼則返回字符串描述）
        if isinstance(obj, bytes):
            try:
                import base64
                return base64.b64encode(obj).decode('ascii')
            except Exception:
                return f"<binary {len(obj)} bytes>"
        
        # set/frozenset → list
        if isinstance(obj, (set, frozenset)):
            return list(obj)
        
        # 未知類型 → 字符串描述
        try:
            return str(obj)
        except Exception:
            return f"<unserializable {type(obj).__name__}>"


# ============================================================
# 便捷函數
# ============================================================

def safe_jsonb_value(value: Any) -> str:
    """
    將 Python 對象安全地轉換為 JSONB 字符串
    
    Args:
        value: Python 對象（dict, list, 或任何 JSON 兼容類型）
        
    Returns:
        JSON 字符串
    """
    if value is None:
        return None
    
    if isinstance(value, str):
        # 如果是字符串，先解析再重新編碼（確保格式一致）
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # 無法解析，直接返回字符串
            return value
    
    return json.dumps(value, cls=JsonbEncoder, ensure_ascii=False)


def safe_jsonb_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    確保字典中的所有值都是 JSONB 兼容的
    
    Args:
        data: 原始字典
        
    Returns:
        處理後的字典
    """
    result = {}
    for key, value in data.items():
        if value is None:
            result[key] = None
        elif isinstance(value, (dict, list, str, int, float, bool)):
            result[key] = value
        else:
            # 使用 JsonbEncoder 處理
            try:
                result[key] = json.loads(json.dumps(value, cls=JsonbEncoder))
            except (json.JSONDecodeError, TypeError):
                result[key] = str(value)
    return result


# ============================================================
# PostgreSQL JSONB 操作輔助函數
# ============================================================

def jsonb_set_statement(
    column: str,
    key_path: Optional[List[str]] = None,
    value: Any = None,
    create_missing: bool = True
) -> str:
    """
    生成 PostgreSQL jsonb_set SQL 語句
    
    Args:
        column: 列名（如 'extra_data'）
        key_path: 鍵路徑（如 ['metadata', 'version']）
        value: 要設置的值（Python 對象）
        create_missing: 是否創建缺失的鍵（True = 'true', False = 'false'）
        
    Returns:
        SQL 表達式字符串（如 'extra_data = jsonb_set(extra_data, '{metadata,version}', '"1.0"', true)'）
    
    Example:
        # 設置 extra_data['metadata']['version'] = '1.0'
        jsonb_set_statement('extra_data', ['metadata', 'version'], '1.0')
        
        # 結果：
        # extra_data = jsonb_set(extra_data, '{metadata,version}', '"1.0"', true)
    """
    # 構建鍵路徑
    if key_path:
        path_str = "{" + ",".join(key_path) + "}"
    else:
        # 根級別
        path_str = "{}"
    
    # 將值轉換為 JSON 字符串
    if value is None:
        value_json = "null"
    elif isinstance(value, str):
        # 字符串需要用雙引號包裹
        value_json = f'"{value}"'
    else:
        value_json = json.dumps(value, cls=JsonbEncoder)
    
    # 創建缺失鍵的參數
    create_str = 'true' if create_missing else 'false'
    
    return f'jsonb_set({column}, \'{path_str}\', \'{value_json}\', {create_str})'


def jsonb_merge_expression(
    column1: str,
    column2: str
) -> str:
    """
    生成 PostgreSQL JSONB 合併表達式（|| 運算符）
    
    Args:
        column1: 第一個列名
        column2: 第二個列名
        
    Returns:
        SQL 表達式字符串
    """
    return f"{column1} || {column2}"


def jsonb_merge_value_expression(
    column: str,
    value: Dict[str, Any],
    coalesce: bool = True
) -> str:
    """
    生成合併 JSONB 值的 SQL 表達式
    
    Args:
        column: 列名
        value: 要合併的字典
        coalesce: 是否使用 COALESCE（如果列為 NULL）
        
    Returns:
        SQL 表達式字符串
        
    Example:
        # extra_data || '{"new_key": "new_value"}'::jsonb
        jsonb_merge_value_expression('extra_data', {'new_key': 'new_value'})
    """
    value_json = safe_jsonb_value(value)
    
    if coalesce:
        return f"COALESCE({column}, '{{}}'::jsonb) || '{value_json}'::jsonb"
    else:
        return f"{column} || '{value_json}'::jsonb"


# ============================================================
# DBClient 的 JSONB 輔助方法 Mixin
# ============================================================

class JsonbHelperMixin:
    """
    JSONB 操作輔助 Mixin
    
    提供統一的 JSONB 操作接口
    
    使用方式：
        class MyDBClient(JsonbHelperMixin, DBClient):
            pass
    """
    
    @staticmethod
    def encode_jsonb(data: Any) -> str:
        """
        將 Python 對象編碼為 JSONB 字符串
        
        Args:
            data: Python 對象
            
        Returns:
            JSON 字符串（用於 $1::jsonb 參數）
        """
        return safe_jsonb_value(data)
    
    @staticmethod
    def encode_jsonb_for_insert(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        為 INSERT 語句準備 JSONB 數據
        
        將 {'key': value} 轉換為 {'key': json.dumps(value)}
        
        Args:
            data: 原始字典
            
        Returns:
            處理後的字典
        """
        result = {}
        for key, value in data.items():
            if value is None:
                result[key] = None
            elif isinstance(value, (dict, list)):
                # 嵌套的 dict/list 需要先序列化
                result[key] = safe_jsonb_value(value)
            else:
                result[key] = value
        return result
    
    @staticmethod
    def jsonb_set_sql(
        column: str,
        key_path: List[str],
        value: Any,
        create_missing: bool = True
    ) -> str:
        """
        生成 jsonb_set SQL
        
        Args:
            column: 列名
            key_path: 鍵路徑
            value: 值
            create_missing: 是否創建缺失鍵
            
        Returns:
            SQL 表達式
        """
        return jsonb_set_statement(column, key_path, value, create_missing)
    
    @staticmethod
    def jsonb_merge_sql(column: str, value: Dict[str, Any]) -> str:
        """
        生成合併 JSONB 的 SQL
        
        Args:
            column: 列名
            value: 要合併的字典
            
        Returns:
            SQL 表達式
        """
        return jsonb_merge_value_expression(column, value)


# ============================================================
# 向後兼容別名
# ============================================================

DateTimeEncoder = JsonbEncoder  # 向後兼容
