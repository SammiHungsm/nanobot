"""
Value Normalizer - 财务数值标准化模块

核心功能：
1. 将原始数值转换为绝对单位（最小单位，如元）
2. 统一币别转换为港币 (HKD)
3. 解决跨公司比较的「数学灾难」

关键概念：
- "5 Million HKD" → standardized_value = 5000000, standardized_currency = 'HKD'
- "1000 RMB '000" → standardized_value = 1000 * 1000 / exchange_rate, standardized_currency = 'HKD'
"""

import re
from typing import Tuple, Optional
from loguru import logger
from decimal import Decimal, ROUND_HALF_UP


# 汇率表（定期更新）
EXCHANGE_RATES = {
    'HKD': 1.0,       # 基准货币
    'RMB': 1.08,      # 人民币兑港币 (2024 参考)
    'CNY': 1.08,      # 人民币兑港币
    'USD': 7.85,      # 美元兑港币
    'EUR': 8.5,       # 欧元兑港币 (参考)
    'GBP': 10.0,      # 英镑兑港币 (参考)
    'JPY': 0.052,     # 日元兑港币 (参考)
}

# 单位倍数表
UNIT_MULTIPLIERS = {
    # 英文单位
    '': 1,            # 无单位 = 基本单位
    'million': 1_000_000,
    'm': 1_000_000,
    'thousand': 1_000,
    'k': 1_000,
    "'000": 1_000,    # 财报常见格式：'000 表示千元
    "'000s": 1_000,
    'billion': 1_000_000_000,
    'bn': 1_000_000_000,
    'b': 1_000_000_000,
    'hundred': 100,
    
    # 中文单位
    '百萬': 1_000_000,
    '百万': 1_000_000,
    '千': 1_000,
    '萬': 10_000,     # 中文万 = 10,000（不是英文的 million）
    '万': 10_000,
    '億': 100_000_000,  # 中文亿
    '亿': 100_000_000,
    '元': 1,
    
    # 特殊格式
    'hk$': 1,         # HK$ 符号，单位为元
    'rmb': 1,
    'us$': 1,
    '$': 1,
}


class ValueNormalizer:
    """
    数值标准化器
    
    将财报中的各种数值格式统一转换为港币绝对单位
    """
    
    def __init__(self, default_currency: str = 'HKD'):
        """
        初始化
        
        Args:
            default_currency: 默认目标币别（统一转换为港币）
        """
        self.default_currency = default_currency
        self.exchange_rates = EXCHANGE_RATES.copy()
    
    def parse_unit_string(self, unit_str: str) -> Tuple[float, str]:
        """
        解析单位字符串，提取倍数和币别
        
        Args:
            unit_str: 单位字符串（如 "RMB '000", "HKD Million", "USD"）
            
        Returns:
            Tuple[float, str]: (倍数, 原始币别)
            
        Examples:
            parse_unit_string("RMB '000") → (1000, 'RMB')
            parse_unit_string("HKD Million") → (1000000, 'HKD')
            parse_unit_string("USD") → (1, 'USD')
        """
        if not unit_str:
            return 1.0, self.default_currency
        
        unit_str = unit_str.strip().upper()
        multiplier = 1.0
        currency = None
        
        # 识别币别
        currency_patterns = {
            'HKD': r'\b(HKD|HK\$|HONG KONG DOLLAR)\b',
            'RMB': r'\b(RMB|CNY|RENMINBI|¥|人民幣|人民币)\b',
            'USD': r'\b(USD|US\$|U.S. DOLLAR|美元)\b',
            'EUR': r'\b(EUR|€|EURO)\b',
            'GBP': r'\b(GBP|£|POUND)\b',
            'JPY': r'\b(JPY|¥|YEN|日元)\b',
        }
        
        for curr, pattern in currency_patterns.items():
            if re.search(pattern, unit_str, re.IGNORECASE):
                currency = curr
                break
        
        if currency is None:
            currency = self.default_currency
        
        # 识别单位倍数
        for unit_key, mult in UNIT_MULTIPLIERS.items():
            # 特殊处理 "'000" 格式（财报常见）
            if "'000" in unit_str or "'000s" in unit_str:
                multiplier = 1_000
                break
            # 中文万特殊处理
            if unit_key in ['萬', '万'] and unit_key in unit_str:
                multiplier = 10_000
                break
            # 中文亿
            if unit_key in ['億', '亿'] and unit_key in unit_str:
                multiplier = 100_000_000
                break
            # 其他单位
            if unit_key.lower() in unit_str.lower() and unit_key not in ['hk$', 'rmb', 'us$', '$']:
                multiplier = mult
                break
        
        return multiplier, currency
    
    def normalize_value(
        self, 
        raw_value: float, 
        unit_str: str,
        target_currency: Optional[str] = None,
        exchange_rate: Optional[float] = None
    ) -> Tuple[Decimal, str]:
        """
        标准化数值
        
        Args:
            raw_value: 原始数值
            unit_str: 单位字符串
            target_currency: 目标币别（默认港币）
            exchange_rate: 自定义汇率（可选）
            
        Returns:
            Tuple[Decimal, str]: (标准化后的绝对数值, 目标币别)
            
        Examples:
            normalize_value(5, "HKD Million") → (5000000, "HKD")
            normalize_value(1000, "RMB '000") → (1000 * 1000 / 1.08, "HKD")
            normalize_value(100, "USD") → (100 * 7.85, "HKD")
        """
        if target_currency is None:
            target_currency = self.default_currency
        
        # 解析单位
        multiplier, source_currency = self.parse_unit_string(unit_str)
        
        # 计算绝对值
        absolute_value = Decimal(str(raw_value)) * Decimal(str(multiplier))
        
        # 汇率转换
        if source_currency != target_currency:
            rate = exchange_rate or self.exchange_rates.get(source_currency, 1.0)
            if target_currency != 'HKD':
                # 如果目标不是港币，需要先转港币再转目标
                hkd_value = absolute_value * Decimal(str(rate))
                target_rate = self.exchange_rates.get(target_currency, 1.0)
                standardized_value = hkd_value / Decimal(str(target_rate))
            else:
                standardized_value = absolute_value * Decimal(str(rate))
        else:
            standardized_value = absolute_value
        
        # 四舍五入到两位小数
        standardized_value = standardized_value.quantize(
            Decimal('0.01'), 
            rounding=ROUND_HALF_UP
        )
        
        logger.debug(
            f"标准化: {raw_value} {unit_str} → {standardized_value} {target_currency}"
            f" (倍数={multiplier}, 汇率={source_currency}→{target_currency})"
        )
        
        return standardized_value, target_currency
    
    def update_exchange_rate(self, currency: str, rate: float):
        """
        更新汇率
        
        Args:
            currency: 币别
            rate: 兑港币汇率
        """
        self.exchange_rates[currency] = rate
        logger.info(f"更新汇率: {currency} → HKD @ {rate}")


# 全局标准化器
_normalizer: Optional[ValueNormalizer] = None


def get_value_normalizer() -> ValueNormalizer:
    """获取全局标准化器"""
    global _normalizer
    if _normalizer is None:
        _normalizer = ValueNormalizer()
    return _normalizer


def normalize_financial_value(
    raw_value: float,
    unit_str: str,
    target_currency: str = 'HKD'
) -> Tuple[Decimal, str]:
    """
    便捷函数：标准化财务数值
    
    Args:
        raw_value: 原始数值
        unit_str: 单位字符串
        target_currency: 目标币别
        
    Returns:
        Tuple[Decimal, str]: (标准化数值, 币别)
    """
    return get_value_normalizer().normalize_value(raw_value, unit_str, target_currency)


# 测试
if __name__ == "__main__":
    normalizer = ValueNormalizer()
    
    test_cases = [
        (5, "HKD Million"),
        (1000, "RMB '000"),
        (100, "USD"),
        (50, "EUR"),
        (10000, ""),
        (5, "萬"),           # 中文万
        (3, "億"),           # 中文亿
        (500, "'000"),       # 千元格式
        (2.5, "HK$ Million"),
    ]
    
    print("\n📊 数值标准化测试：")
    for value, unit in test_cases:
        standardized, currency = normalizer.normalize_value(value, unit)
        print(f"  {value} '{unit}' → {standardized} {currency}")
    
    print("\n💰 单位解析测试：")
    unit_tests = [
        "RMB '000",
        "HKD Million",
        "USD",
        "CNY Thousand",
        "'000s",
        "HK$ M",
    ]
    
    for unit in unit_tests:
        multiplier, currency = normalizer.parse_unit_string(unit)
        print(f"  '{unit}' → multiplier={multiplier}, currency={currency}")