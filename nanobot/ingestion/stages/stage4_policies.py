"""
Stage 4 Policies - 系統提示模塊化拆分 (v4.16)

將龐大的 System Prompt 拆分成獨立的 Policy 類：

1. ReportTypePolicy - 報告類型判斷（指數/年報）
2. IndustryAssignmentPolicy - 行業分配規則 A/B
3. ToolSelectionPolicy - Tool 選擇指引
4. ExtractionChecklistPolicy - 強制提取清單
5. MultiYearExtractionPolicy - 多年數據提取規則
6. EntityRelationPolicy - 實體關係識別規則
7. ContinuousLearningPolicy - 持續學習規則

使用方式：
    from nanobot.ingestion.stages.stage4_policies import (
        ReportTypePolicy,
        IndustryAssignmentPolicy,
        ToolSelectionPolicy
    )
    
    policies = [
        ReportTypePolicy(is_index_report=True, index_theme="Hang Seng Biotech"),
        IndustryAssignmentPolicy(industry="Healthcare"),
        ToolSelectionPolicy(),
        ExtractionChecklistPolicy(),
    ]
    
    system_prompt = "\n\n".join(p.to_prompt() for p in policies)

"""

from typing import Any, Dict, List, Optional


# ============================================================
# Policy 基類
# ============================================================

class Policy:
    """Policy 基類"""
    
    def to_prompt(self) -> str:
        """轉換為 Prompt 字符串"""
        raise NotImplementedError
    
    @property
    def name(self) -> str:
        return self.__class__.__name__.replace("Policy", "")


# ============================================================
# ReportTypePolicy - 報告類型判斷
# ============================================================

class ReportTypePolicy(Policy):
    """
    報告類型策略
    
    根據報告類型提供不同的上下文
    """
    
    def __init__(
        self,
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None,
        parent_company_id: int = None
    ):
        self.is_index_report = is_index_report
        self.index_theme = index_theme
        self.confirmed_doc_industry = confirmed_doc_industry
        self.parent_company_id = parent_company_id
    
    def to_prompt(self) -> str:
        if self.is_index_report:
            return f"""
📋 報告類型：【指數/行業報告】
- 主題: {self.index_theme or 'Unknown'}
- 行業: {self.confirmed_doc_industry or 'Unknown'}
- 注意: 裡面包含多間公司的數據，請不要预设单一母公司
- 行業分配: 規則 A - 所有成分股都應指派行業 '{self.confirmed_doc_industry or 'Unknown'}'
"""
        else:
            return f"""
📋 報告類型：【單一公司年報】
- 母公司 ID: {self.parent_company_id or '待提取'}
- 注意: 只需處理母公司數據
- 行業分配: 規則 B - 使用 AI 提取各公司行業
"""


# ============================================================
# IndustryAssignmentPolicy - 行業分配規則
# ============================================================

class IndustryAssignmentPolicy(Policy):
    """
    行業分配策略
    
    規則 A: 指數報告強制分配同一行業
    規則 B: AI 自動識別各公司行業
    """
    
    # 允許的行業列表
    VALID_INDUSTRIES = [
        "Technology", "Healthcare", "Finance", "Energy", "Consumer Goods",
        "Real Estate", "Telecommunications", "Industrials", "Materials",
        "Utilities", "Retail", "Manufacturing", "Transportation"
    ]
    
    def __init__(self, confirmed_industry: str = None, rule: str = "B"):
        """
        Args:
            confirmed_industry: 確認的行業（規則 A）
            rule: 規則 A 或 B
        """
        self.confirmed_industry = confirmed_industry
        self.rule = rule
    
    def to_prompt(self) -> str:
        if self.rule == "A":
            return f"""
🏭 行業分配規則 A（指數報告）
- 所有公司都必須分配行業: {self.confirmed_industry or 'Unknown'}
- 禁止使用 AI 判斷行業
- 適用於: 指數成分股報告、行業研究報告
"""
        else:
            return f"""
🏭 行業分配規則 B（AI 識別）
- 由 AI 根據公司主營業務自動判斷行業
- 可以使用 AI 提取的行業關鍵詞
- 禁止: 未確認就隨便分配行業
- 允許的行業: {', '.join(self.VALID_INDUSTRIES)}
"""


# ============================================================
# ToolSelectionPolicy - Tool 選擇指引
# ============================================================

class ToolSelectionPolicy(Policy):
    """
    Tool 選擇策略
    
    指導 LLM 如何根據數據類型選擇正確的 Tool
    """
    
    # Tool 選擇映射表
    TOOL_MAP = {
        "financial_metrics": "insert_financial_metrics",
        "revenue_breakdown": "insert_revenue_breakdown",
        "key_personnel": "insert_key_personnel",
        "shareholding": "insert_shareholding",
        "market_data": "insert_market_data",
        "entity_relation": "insert_entity_relation",
        "mentioned_company": "insert_mentioned_company",
        "dynamic_attributes": "update_dynamic_attributes",
        "artifact_relation": "insert_artifact_relation",
    }
    
    def to_prompt(self) -> str:
        lines = [
            "🛠️ Tool 選擇指引",
            "",
            "選擇正確的 Tool 非常關鍵！不同數據用不同 Tool：",
            ""
        ]
        
        examples = [
            ("financial_metrics", "insert_financial_metrics", "利潤、資產、負債、EPS"),
            ("revenue_breakdown", "insert_revenue_breakdown", "按地區/業務/產品劃分的收入"),
            ("key_personnel", "insert_key_personnel", "董事、高管、委員會成員"),
            ("shareholding", "insert_shareholding", "股東持股比例、控股股東"),
            ("market_data", "insert_market_data", "PE ratio、市值、股價"),
            ("entity_relation", "insert_entity_relation", "人物-公司關係、收購併購"),
            ("mentioned_company", "insert_mentioned_company", "子公司、競爭對手、合作夥伴"),
            ("dynamic_attributes", "update_dynamic_attributes", "ESG、自定義字段"),
        ]
        
        for data_type, tool, examples_text in examples:
            lines.append(f"  {data_type} → {tool}")
            lines.append(f"    例: {examples_text}")
            lines.append("")
        
        lines.append("⚠️ 常見錯誤:")
        lines.append("  - 收入分解（百分比）誤用 insert_financial_metrics")
        lines.append("  - 市場數據（PE ratio）誤用 insert_revenue_breakdown")
        lines.append("  - 子公司誤用 insert_key_personnel")
        
        return "\n".join(lines)


# ============================================================
# MultiYearExtractionPolicy - 多年數據提取
# ============================================================

class MultiYearExtractionPolicy(Policy):
    """
    多年數據提取策略
    
    確保提取所有年份的數據，不僅僅是主要年份
    """
    
    def __init__(self, primary_year: int = 2025):
        self.primary_year = primary_year
    
    def to_prompt(self) -> str:
        return f"""
📅 多年數據提取規則（非常重要！）

⚠️ 【關鍵】這個 PDF 的主要年份是 {self.primary_year}
但請提取文檔中【所有年份】的數據！

常見場景：
1. 「2023 | 2022 | 2021」多列數據
   → 必須分別 insert 2023、2022、2021 的數據

2. 「Revenue 40,851 (2023) vs 44,141 (2022)」
   → 要同時寫入 2023 和 2022 的數據

3. 「Five-year summary 2019-2023」
   → 全部提取 2019, 2020, 2021, 2022, 2023

4. 表格中的「同上」或「Same as above」
   → 需要根據上下文推斷實際數值

絕對禁止：
- 只 insert {self.primary_year} 一年！
- 看到多年數據但只提取最後一年
- 跳過任何年份

正確做法：
- 有幾年就 insert 幾年
- 即使是同一家公司，也要按年份分開記錄
"""


# ============================================================
# ExtractionChecklistPolicy - 強制提取清單
# ============================================================

class ExtractionChecklistPolicy(Policy):
    """
    強制提取清單
    
    確保所有必需的數據類型都被嘗試提取
    """
    
    def __init__(self, include_all: bool = True):
        self.include_all = include_all
    
    def to_prompt(self) -> str:
        return """
📋 強制提取清單

在你宣佈任務完成之前，請檢查是否已經嘗試提取以下 7 類數據：

[ ] 財務指標 (insert_financial_metrics)
    - 營收、淨利潤、資產、負債
    - EPS、ROE、負債比率

[ ] 收入分解 (insert_revenue_breakdown)
    - 按地區（香港/中國/歐洲/北美）
    - 按業務（零售/港口/基建）
    - 百分比 + 金額

[ ] 關鍵人員 (insert_key_personnel)
    - 董事名單（Executive/Non-Executive/Independent）
    - 高級管理層
    - 委員會成員

[ ] 股東結構 (insert_shareholding 或 ExtractShareholdersFromTextTool)
    - 控股股東
    - 主要機構投資者
    - 持股比例

[ ] 市場數據 (insert_market_data)
    - PE ratio、市盈率
    - 市值、股價
    - 成交量

[ ] 提及的公司 (insert_mentioned_company)
    - 子公司
    - 聯營公司、合營企業
    - 競爭對手、合作夥伴

[ ] 實體關係 (insert_entity_relation)
    - 收購/併購事件
    - 派息公告
    - 分拆/重組
    - 減值/撇銷
    - 法律訴訟

如果某項沒有找到，請明確創建 Review Record 說明原因！
"""


# ============================================================
# EntityRelationPolicy - 實體關係識別
# ============================================================

class EntityRelationPolicy(Policy):
    """
    實體關係識別策略
    
    識別並提取重要的公司事件和關係
    """
    
    # 關鍵事件關鍵詞
    EVENT_KEYWORDS = {
        "acquisition": ["收購", "併購", "收購事項", "acquisition", "merger"],
        "dividend": ["派息", "股息", "末期息", "dividend", "distribution"],
        "spin_off": ["分拆", "重組", "spin-off", "restructuring", "分拆上市"],
        "joint_venture": ["合營", "聯營", "合資", "joint venture", "associate"],
        "litigation": ["訴訟", "法律行動", "litigation", "lawsuit", "法律訴訟"],
        "regulatory": ["監管", "調查", "罰款", "regulatory", "investigation", "penalty"],
        "impairment": ["減值", "撇銷", "impairment", "write-off", "減值虧損"],
        "buyback": ["回購", "股份回購", "buyback", "repurchase"],
        "capital_raising": ["集資", "配股", "供股", "capital raising", "placing"],
    }
    
    def to_prompt(self) -> str:
        lines = [
            "🔗 實體關係識別規則",
            "",
            "請特別注意以下關鍵字，提取相關事件：",
            ""
        ]
        
        for event_type, keywords in self.EVENT_KEYWORDS.items():
            lines.append(f"  {event_type}:")
            lines.append(f"    中: {', '.join(k for k in keywords if not k.isascii())}")
            lines.append(f"    英: {', '.join(k for k in keywords if k.isascii())}")
            lines.append("")
        
        lines.append("範例：")
        lines.append("  - 「本公司已完成收購 ABC Limited」→ acquisition")
        lines.append("  - 「宣派末期股息每股 5 元」→ dividend")
        lines.append("  - 「本公司遭監管機構罰款」→ regulatory")
        
        return "\n".join(lines)


# ============================================================
# ContinuousLearningPolicy - 持續學習
# ============================================================

class ContinuousLearningPolicy(Policy):
    """
    持續學習策略
    
    指導 LLM 如何處理未知關鍵字和回填數據
    """
    
    def to_prompt(self) -> str:
        return """
🔄 持續學習規則

1️⃣ 發現新關鍵字：
   - 如果看到新的標題關鍵字（如「營運地區收益剖析」）
   - 調用 register_new_keyword 將其加入知識庫
   - 這樣下次處理其他年報時就能自動識別

2️⃣ 找不到結構化數據：
   - 搜索 document_pages 包底庫
   - 找到了？→ 分析標題，註冊關鍵字，回填數據
   - 沒找到？→ 創建 Review Record

3️⃣ 發現數據但無法結構化：
   - 使用 update_dynamic_attributes 寫入 JSONB
   - 無需 ALTER TABLE，直接擴展

4️⃣ 錯誤處理：
   - Tool 調用失敗 → 記錄錯誤，繼續其他任務
   - 不要因為一個 Tool 失敗而放棄整個流程
"""


# ============================================================
# CompanyNameResolutionPolicy - 公司名稱解析
# ============================================================

class CompanyNameResolutionPolicy(Policy):
    """
    公司名稱解析策略 (Method A)
    
    指導 LLM 如何處理母公司vs子公司
    """
    
    def to_prompt(self) -> str:
        return """
🏢 公司名稱解析規則（Method A）

⚠️ 多公司數據處理（非常重要！）

如果數據屬於【母公司】：
   → 請傳入 company_id 參數

如果數據屬於【子公司】【聯營公司】【競爭對手】：
   → 【不要】填寫 company_id
   → 將公司名稱填入 company_name 參數！
   → 系統會自動查找或創建正確的數據庫 ID

範例：
  母公司「長和」利潤數據：
    ❌ 錯誤: company_id=1 (長和ID)，但數據是騰訊的
    ✅ 正確: company_name="騰訊"

  「子公司 ABC Limited 營收」：
    ✅ 正確: company_name="ABC Limited"

  「競爭對手 XYZ Corp」：
    ✅ 正確: company_name="XYZ Corp"
    ✅ 正確: relation_type="competitor"

為什麼要這樣？
  - LLM 不擅長記住數據庫 ID
  - Python 負責查找/創建公司記錄
  - LLM 只需要理解公司名稱
"""


# ============================================================
# Policy Registry
# ============================================================

class PolicyRegistry:
    """
    Policy 註冊表
    
    方便批量構建 System Prompt
    """
    
    def __init__(self):
        self._policies: List[Policy] = []
    
    def add(self, policy: Policy) -> "PolicyRegistry":
        self._policies.append(policy)
        return self
    
    def build(self) -> str:
        """構建完整的 System Prompt"""
        return "\n\n".join(p.to_prompt() for p in self._policies)
    
    @classmethod
    def for_stage4(
        cls,
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None,
        parent_company_id: int = None,
        primary_year: int = 2025
    ) -> "PolicyRegistry":
        """
        為 Stage 4 構建 Policy Registry
        
        Args:
            is_index_report: 是否為指數報告
            index_theme: 指數主題
            confirmed_doc_industry: 確認的行業
            parent_company_id: 母公司 ID
            primary_year: 主要年份
        """
        rule = "A" if is_index_report else "B"
        
        registry = cls()
        registry.add(ReportTypePolicy(
            is_index_report=is_index_report,
            index_theme=index_theme,
            confirmed_doc_industry=confirmed_doc_industry,
            parent_company_id=parent_company_id
        ))
        registry.add(IndustryAssignmentPolicy(
            confirmed_industry=confirmed_doc_industry,
            rule=rule
        ))
        registry.add(ToolSelectionPolicy())
        registry.add(MultiYearExtractionPolicy(primary_year=primary_year))
        registry.add(ExtractionChecklistPolicy())
        registry.add(EntityRelationPolicy())
        registry.add(CompanyNameResolutionPolicy())
        registry.add(ContinuousLearningPolicy())
        
        return registry
