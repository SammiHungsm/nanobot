"""
Validators Module - Python 硬驗證防線

負責所有數據驗證邏輯，確保 LLM 提取的數據符合業務規則。
"""

from typing import Dict, Any, Tuple, List
from loguru import logger


def validate_revenue_percentage(
    extracted_data: Dict[str, Any],
    min_sum: float = 99.0,
    max_sum: float = 101.0
) -> Tuple[bool, float]:
    """
    驗證 Revenue Breakdown 的百分比總和是否接近 100%
    
    Args:
        extracted_data: 提取的數據 Dict
        min_sum: 最小允許總和 (默認 99.0)
        max_sum: 最大允許總和 (默認 101.0)
        
    Returns:
        Tuple[bool, float]: (是否通過驗證, 總百分比)
    """
    try:
        total_percentage = sum(
            item.get("percentage", 0) 
            for item in extracted_data.values()
            if isinstance(item, dict)
        )
        
        logger.info(f"📊 Revenue Breakdown 總百分比: {total_percentage}%")
        logger.info(f"   提取的分類: {list(extracted_data.keys())}")
        
        # 容許捨入誤差
        is_valid = min_sum <= total_percentage <= max_sum
        
        if is_valid:
            logger.info(f"✅ 验证通过！总和 {total_percentage}% 在 [{min_sum}, {max_sum}] 范围内")
        else:
            logger.warning(f"⚠️ 验证失败！总百分比 {total_percentage}% 不在 [{min_sum}, {max_sum}] 范围内")
            logger.warning(f"   可能遗漏了某些地区分类")
        
        return is_valid, total_percentage
        
    except Exception as e:
        logger.error(f"❌ 验证计算失败: {e}")
        return False, 0.0


def validate_financial_amount(
    amount: float,
    min_value: float = 0,
    max_value: float = float('inf')
) -> bool:
    """
    驗證財務金額是否在合理範圍內
    
    Args:
        amount: 金額
        min_value: 最小值
        max_value: 最大值
        
    Returns:
        bool: 是否通過驗證
    """
    try:
        if not isinstance(amount, (int, float)):
            logger.warning(f"⚠️ 金額類型錯誤: {type(amount)}")
            return False
        
        if amount < min_value or amount > max_value:
            logger.warning(f"⚠️ 金額 {amount} 超出合理範圍 [{min_value}, {max_value}]")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 金額驗證失敗: {e}")
        return False


def validate_json_structure(
    data: Dict[str, Any],
    required_fields: List[str]
) -> Tuple[bool, List[str]]:
    """
    驗證 JSON 結構是否包含必要字段
    
    Args:
        data: 數據 Dict
        required_fields: 必要字段列表
        
    Returns:
        Tuple[bool, List[str]]: (是否通過, 缺少的字段列表)
    """
    missing_fields = []
    
    for field in required_fields:
        if field not in data:
            missing_fields.append(field)
    
    if missing_fields:
        logger.warning(f"⚠️ JSON 缺少必要字段: {missing_fields}")
        return False, missing_fields
    
    return True, []


def validate_revenue_breakdown_schema(
    extracted_data: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    驗證 Revenue Breakdown 數據結構
    
    每個分類應該包含:
    - percentage: 數字
    - amount: 數字 (可選)
    
    Args:
        extracted_data: 提取的數據
        
    Returns:
        Tuple[bool, str]: (是否通過, 錯誤信息)
    """
    if not extracted_data:
        return False, "數據為空"
    
    if not isinstance(extracted_data, dict):
        return False, f"數據類型錯誤: 期望 dict，實際 {type(extracted_data)}"
    
    for category, data in extracted_data.items():
        if not isinstance(data, dict):
            return False, f"分類 '{category}' 的數據類型錯誤: 期望 dict，實際 {type(data)}"
        
        if "percentage" not in data:
            return False, f"分類 '{category}' 缺少 'percentage' 字段"
        
        if not isinstance(data.get("percentage"), (int, float)):
            return False, f"分類 '{category}' 的 'percentage' 不是數字"
    
    return True, ""


class ValidationResult:
    """驗證結果封裝類"""
    
    def __init__(self, is_valid: bool, message: str = "", data: Dict = None):
        self.is_valid = is_valid
        self.message = message
        self.data = data or {}
    
    def __bool__(self):
        return self.is_valid
    
    def __repr__(self):
        status = "✅" if self.is_valid else "❌"
        return f"ValidationResult({status}, {self.message})"


def validate_all(
    extracted_data: Dict[str, Any],
    validation_type: str = "revenue_breakdown"
) -> ValidationResult:
    """
    綜合驗證入口
    
    Args:
        extracted_data: 提取的數據
        validation_type: 驗證類型
        
    Returns:
        ValidationResult: 驗證結果
    """
    if validation_type == "revenue_breakdown":
        # 1. 驗證結構
        is_valid_schema, schema_error = validate_revenue_breakdown_schema(extracted_data)
        if not is_valid_schema:
            return ValidationResult(False, schema_error)
        
        # 2. 驗證百分比總和
        is_valid_sum, total_pct = validate_revenue_percentage(extracted_data)
        if not is_valid_sum:
            return ValidationResult(
                False, 
                f"百分比總和 {total_pct}% 不等於 100%",
                {"total_percentage": total_pct}
            )
        
        return ValidationResult(True, "驗證通過", {"total_percentage": total_pct})
    
    else:
        return ValidationResult(True, "無需驗證")