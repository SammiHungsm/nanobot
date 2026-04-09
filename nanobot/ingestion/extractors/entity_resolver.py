"""
Entity Resolver - 財務名詞標準化

核心功能：
1. 統一不同公司的會計名詞到標準名稱 (Canonical Name)
2. 支援中英文對照
3. 確保 Vanna 查詢的一致性

PoC 核心精神："Garbage in, garbage out"
只有標準化的數據輸入，才能保證 Text-to-SQL 的準確性
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger
from functools import lru_cache


class EntityResolver:
    """
    實體對齊器
    
    將不同公司的會計名詞強制統一為標準名稱
    """
    
    def __init__(self, mapping_path: Optional[str] = None):
        """
        初始化
        
        Args:
            mapping_path: 財務名詞對照表路徑
        """
        if mapping_path is None:
            mapping_path = Path(__file__).parent / "config" / "financial_terms_mapping.json"
        
        self.mapping_path = Path(mapping_path)
        self.mapping: Dict[str, Any] = {}
        self._alias_to_canonical: Dict[str, Tuple[str, str]] = {}  # alias -> (canonical_en, canonical_zh)
        self._load_mapping()
    
    def _load_mapping(self):
        """載入對照表"""
        try:
            with open(self.mapping_path, 'r', encoding='utf-8') as f:
                self.mapping = json.load(f)
            
            # 構建快速查找表
            for term_key, term_data in self.mapping.get("canonical_terms", {}).items():
                canonical_en = term_data["canonical_en"]
                canonical_zh = term_data["canonical_zh"]
                
                # 英文別名
                for alias in term_data.get("aliases_en", []):
                    self._alias_to_canonical[alias.lower()] = (canonical_en, canonical_zh)
                
                # 中文別名
                for alias in term_data.get("aliases_zh", []):
                    self._alias_to_canonical[alias] = (canonical_en, canonical_zh)
                
                # 標準名稱本身
                self._alias_to_canonical[canonical_en.lower()] = (canonical_en, canonical_zh)
                self._alias_to_canonical[canonical_zh] = (canonical_en, canonical_zh)
            
            # 地區對照
            for region_key, region_data in self.mapping.get("revenue_regions", {}).items():
                canonical_en = region_data["canonical_en"]
                canonical_zh = region_data["canonical_zh"]
                
                for alias in region_data.get("aliases", []):
                    self._alias_to_canonical[alias.lower()] = (canonical_en, canonical_zh)
                
                self._alias_to_canonical[canonical_en.lower()] = (canonical_en, canonical_zh)
                self._alias_to_canonical[canonical_zh] = (canonical_en, canonical_zh)
            
            logger.info(f"✅ EntityResolver 載入 {len(self._alias_to_canonical)} 個名詞對照")
            
        except Exception as e:
            logger.error(f"❌ 載入名詞對照表失敗: {e}")
            self.mapping = {}
    
    @lru_cache(maxsize=1000)
    def resolve_metric_name(self, raw_name: str) -> Tuple[str, str]:
        """
        解析財務指標名稱，返回標準化名稱
        
        Args:
            raw_name: 原始名稱（可能是英文或中文）
            
        Returns:
            Tuple[str, str]: (canonical_en, canonical_zh)
        """
        if not raw_name:
            return raw_name, raw_name
        
        # 直接查找
        result = self._alias_to_canonical.get(raw_name.lower())
        if result:
            return result
        
        result = self._alias_to_canonical.get(raw_name)
        if result:
            return result
        
        # 模糊匹配（處理大小寫、空格差異）
        normalized = raw_name.lower().strip()
        for alias, canonical in self._alias_to_canonical.items():
            if normalized == alias.lower().strip():
                return canonical
        
        # 未找到對照，返回原始名稱（但記錄警告）
        logger.warning(f"⚠️ 未找到名詞對照: '{raw_name}'，使用原始名稱")
        return raw_name, raw_name
    
    def resolve_region_name(self, raw_name: str) -> Tuple[str, str]:
        """
        解析地區名稱（Revenue Breakdown 用）
        
        Args:
            raw_name: 原始地區名稱
            
        Returns:
            Tuple[str, str]: (canonical_en, canonical_zh)
        """
        return self.resolve_metric_name(raw_name)
    
    def get_all_canonical_terms(self) -> List[Dict[str, str]]:
        """
        獲取所有標準名稱列表（用於 Vanna 訓練）
        
        Returns:
            List[Dict]: 標準名稱列表
        """
        terms = []
        for term_key, term_data in self.mapping.get("canonical_terms", {}).items():
            terms.append({
                "canonical_en": term_data["canonical_en"],
                "canonical_zh": term_data["canonical_zh"],
                "category": term_data.get("category", "unknown"),
                "aliases_en": term_data.get("aliases_en", []),
                "aliases_zh": term_data.get("aliases_zh", [])
            })
        return terms
    
    def generate_vanna_training_data(self) -> str:
        """
        生成 Vanna 訓練文檔（包含所有標準名稱）
        
        Returns:
            str: 訓練文檔
        """
        lines = [
            "# 財務指標標準名稱對照表",
            "",
            "以下是所有財務指標的標準名稱。查詢時請使用這些標準名稱：",
            "",
            "## 損益表 (Income Statement)",
            ""
        ]
        
        for term_data in self.get_all_canonical_terms():
            if term_data["category"] == "income_statement":
                lines.append(f"- **{term_data['canonical_en']}** ({term_data['canonical_zh']})")
                if term_data["aliases_en"]:
                    lines.append(f"  - English aliases: {', '.join(term_data['aliases_en'][:3])}")
                if term_data["aliases_zh"]:
                    lines.append(f"  - 中文別名: {', '.join(term_data['aliases_zh'][:3])}")
        
        lines.extend([
            "",
            "## 資產負債表 (Balance Sheet)",
            ""
        ])
        
        for term_data in self.get_all_canonical_terms():
            if term_data["category"] == "balance_sheet":
                lines.append(f"- **{term_data['canonical_en']}** ({term_data['canonical_zh']})")
        
        lines.extend([
            "",
            "## 現金流量表 (Cash Flow)",
            ""
        ])
        
        for term_data in self.get_all_canonical_terms():
            if term_data["category"] == "cash_flow":
                lines.append(f"- **{term_data['canonical_en']}** ({term_data['canonical_zh']})")
        
        lines.extend([
            "",
            "## 每股數據 (Per Share)",
            ""
        ])
        
        for term_data in self.get_all_canonical_terms():
            if term_data["category"] == "per_share":
                lines.append(f"- **{term_data['canonical_en']}** ({term_data['canonical_zh']})")
        
        return "\n".join(lines)


# 全局實體對齊器
_entity_resolver: Optional[EntityResolver] = None


def get_entity_resolver() -> EntityResolver:
    """獲取全局實體對齊器"""
    global _entity_resolver
    if _entity_resolver is None:
        _entity_resolver = EntityResolver()
    return _entity_resolver


def resolve_metric_name(raw_name: str) -> Tuple[str, str]:
    """便捷函數：解析財務指標名稱"""
    return get_entity_resolver().resolve_metric_name(raw_name)


def resolve_region_name(raw_name: str) -> Tuple[str, str]:
    """便捷函數：解析地區名稱"""
    return get_entity_resolver().resolve_region_name(raw_name)


# 測試
if __name__ == "__main__":
    resolver = EntityResolver()
    
    # 測試財務指標
    test_cases = [
        "Revenue",
        "營業額",
        "R&D Expenses",
        "研發費用",
        "Net Profit",
        "淨利潤",
        "Total Assets",
        "總資產"
    ]
    
    print("\n📊 財務指標對照測試：")
    for name in test_cases:
        canonical_en, canonical_zh = resolver.resolve_metric_name(name)
        print(f"  '{name}' → {canonical_en} / {canonical_zh}")
    
    # 測試地區
    test_regions = [
        "Hong Kong",
        "香港",
        "Mainland China",
        "中國",
        "Europe",
        "歐洲"
    ]
    
    print("\n🌍 地區對照測試：")
    for name in test_regions:
        canonical_en, canonical_zh = resolver.resolve_region_name(name)
        print(f"  '{name}' → {canonical_en} / {canonical_zh}")