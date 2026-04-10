# v3.0 架构改进总结 - 移除冗余 + 动态地区处理

## 📊 验证结果

```
[PASS] Test 1: 移除冗余的双重定义
[PASS] Test 2: 移除硬编码的地区
[PASS] Test 3: EntityResolver 适配
[PASS] Test 4: 动态地区处理

通过测试: 4/4
完成度: 100.0%
```

---

## 🎯 核心架构改进

### 改进 1：移除冗余的双重定义

**旧架构问题（v2.1）**：
```json
{
  "financial_metrics_taxonomy": [...],  // ← 定义 standard_name
  "canonical_terms": {...}              // ← 也定义 standard_name
}

→ LLM 困惑："我要看哪一个？"
```

**新架构（v3.0）**：
```json
{
  "core_metrics": [...],  // ← 唯一定义
  "company_attributes": [...]
}

→ LLM 清晰：单一数据源
```

---

### 改进 2：地区和业务分类不再硬编码

**旧架构问题（v2.1）**：
```json
{
  "revenue_regions": {
    "hong_kong": {...},
    "mainland_china": {...},
    "europe": {...}
  }
}
```

**致命伤**：
- A公司划分：大湾区、长三角、京津冀
- B公司划分：APAC、EMEA、Americas
- C公司划分：一带一路、非一带一路

→ AI 强行归类 = 数据失真

**新架构（v3.0）**：
```json
{
  "fallback_rule": {
    "rules": [
      "2. 【地區與業務劃分】：財報中的『地區收入 (Region)』或『業務分類 (Segment)』為公司特有資訊。絕對不要強行歸類！",
      "   - 請直接將財報上的原文翻譯為小寫英文底線格式。",
      "   - 例如：財報寫『大灣區』→ 請輸出 'greater_bay_area'"
    ]
  }
}
```

---

## 🔄 架构设计原则

### 应该硬编码的部分（基于 IFRS/GAAP）

| 类别 | 说明 | 示例 |
|-----|------|------|
| **核心会计名词** | 全球通用的财务概念 | `revenue`, `net_income`, `total_assets` |
| **标准化指标** | Vanna 跨公司查询的基础 | `operating_cash_flow`, `earnings_per_share` |
| **人员/治理属性** | 相对固定的公司信息 | `chief_executive`, `auditor` |

**原因**：
- 财务报表基于国际会计准则（IFRS/GAAP）
- 这些概念在全球是通用的
- 如果不钉死，数据库会变成垃圾场

---

### 不应该硬编码的部分（公司特有信息）

| 类别 | 说明 | 处理方式 |
|-----|------|---------|
| **地区划分** | 每家公司的地区分类不同 | 动态生成，原汁原味保留 |
| **业务板块** | 每家公司的业务结构不同 | 动态生成，原汁原味保留 |
| **客户/产品** | 公司特有的业务信息 | 写入 JSONB，灵活存储 |

**原因**：
- A公司：大湾区、长三角、京津冀
- B公司：APAC、EMEA、Americas
- 强行归类 = 丢失信息

---

## 📝 v3.0 JSON 结构

```json
{
  "version": "3.0.0",
  
  "instruction": "【強制規則】提取數據時，請優先將財報上的名詞映射到 'core_metrics' 的 standard_name...",
  
  "core_metrics": [
    {
      "standard_name": "revenue",
      "canonical_zh": "營業收入",
      "category": "income_statement",
      "synonyms": ["Turnover", "Sales", "營業額", ...]
    }
  ],
  
  "company_attributes": [
    {
      "standard_name": "chief_executive",
      "canonical_zh": "最高行政人員",
      "category": "personnel",
      "value_type": "string",
      "synonyms": ["CEO", "Chief Executive Officer", ...]
    }
  ],
  
  "fallback_rule": {
    "description": "處理字典外指標與動態分類的規則",
    "rules": [
      "1. 【未知指標命名】：使用全小寫英文與底線...",
      "2. 【地區與業務劃分】：公司特有資訊，絕對不要強行歸類！",
      "3. 【數據類型判斷】：..."
    ]
  }
}
```

---

## 🚀 实际应用示例

### 示例 1：A公司的地区收入提取

**财报原文**：
```
地區收入分佈：
- 大灣區：HK$ 1,000M (30%)
- 長三角：HK$ 1,500M (45%)
- 京津冀：HK$ 800M (25%)
```

**v3.0 处理结果**：
```json
{
  "greater_bay_area": {"amount": 1000, "percentage": 30},
  "yangtze_river_delta": {"amount": 1500, "percentage": 45},
  "jing_jin_ji": {"amount": 800, "percentage": 25}
}
```

**存储方式**：
```sql
INSERT INTO revenue_breakdown (company_id, year, category, percentage, amount)
VALUES 
  (1, 2023, 'greater_bay_area', 30.0, 1000),
  (1, 2023, 'yangtze_river_delta', 45.0, 1500),
  (1, 2023, 'jing_jin_ji', 25.0, 800);
```

---

### 示例 2：B公司的地区收入提取

**财报原文**：
```
Revenue by Geography:
- APAC: US$ 500M (50%)
- EMEA: US$ 300M (30%)
- Americas: US$ 200M (20%)
```

**v3.0 处理结果**：
```json
{
  "apac": {"amount": 500, "percentage": 50},
  "emea": {"amount": 300, "percentage": 30},
  "americas": {"amount": 200, "percentage": 20}
}
```

**关键优势**：
- ✅ 保留原始分类逻辑
- ✅ 不强制归到预定义类别
- ✅ 每家公司的数据独立存储

---

## 🎨 架构对比

| 维度 | v2.1 架构 | v3.0 架构 |
|------|----------|----------|
| **数据源数量** | 2 个（taxonomy + canonical） | 1 个（core_metrics） |
| **LLM 困惑度** | 高（要看两个地方） | 低（单一数据源） |
| **地区处理** | 硬编码 7 个地区 | 动态生成 |
| **业务分类** | 未明确定义 | 动态生成 |
| **Fallback 规则** | 简单说明 | 详细规则 |
| **适应性** | 低（地区固定） | 高（支持任意分类） |
| **数据完整性** | 有损失风险 | 完整保留 |

---

## 🔧 EntityResolver 改进

### v3.0 关键改动

```python
def resolve_region_name(self, raw_name: str) -> Tuple[str, str]:
    """
    解析地區名稱（v3.0 重要改變）
    
    - 不再自動歸類到預定義的地區
    - 直接返回原文的小寫英文底線格式
    """
    # 不再使用硬編碼的地區對照
    # 直接使用 Fallback 規則
    fallback_name = self._apply_fallback_rule(raw_name)
    return fallback_name, raw_name
```

**改进效果**：
- ✅ 支持任意地区划分
- ✅ 不损失任何信息
- ✅ 适应不同公司的业务模型

---

## 📊 数据流程

```
PDF 财报
    ↓
LLM 提取（使用 Taxonomy Prompt）
    ↓
标准化判断
    ├─ 核心指标（在 core_metrics 中）→ 使用 standard_name
    │   例如："Turnover" → "revenue"
    │
    └─ 未知指标/地区分类 → 使用 Fallback 规则
        例如："大灣區" → "greater_bay_area"
    ↓
数据存储
    ├─ 数值型指标 → financial_metrics (EAV)
    ├─ 静态属性 → companies.extra_data (JSONB)
    └─ 地区收入 → revenue_breakdown (动态 category)
```

---

## 🎯 适用场景

### 场景 1：港股传统企业
```
地区划分：香港、中国内地、海外
→ 输出：hong_kong, mainland_china, overseas
```

### 场景 2：跨国科技企业
```
地区划分：APAC、EMEA、Americas
→ 输出：apac, emea, americas
```

### 场景 3：内地房企
```
地区划分：大湾区、长三角、京津冀、成渝
→ 输出：greater_bay_area, yangtze_river_delta, jing_jin_ji, chengdu_chongqing
```

### 场景 4：新能源企业
```
业务板块：光伏、风电、储能、氢能
→ 输出：photovoltaic, wind_power, energy_storage, hydrogen_energy
```

---

## 💡 关键学习

### 1. MDM（主数据管理）的重要性
- 核心财务名词是企业的"共同语言"
- 必须建立权威字典，避免歧义

### 2. Hardcode vs Dynamic 的平衡
- **应该 Hardcode**：通用概念（基于国际标准）
- **不应该 Hardcode**：公司特有信息（地区、业务）

### 3. 单一数据源原则
- 避免冗余定义
- LLM 指令遵循能力会下降

### 4. Fallback 规则的重要性
- 明确告诉 AI 如何处理未知情况
- 避免数据丢失

---

## 📁 已修改的文件

1. [financial_terms_mapping.json](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/ingestion/config/financial_terms_mapping.json)
   - v3.0 结构
   - 移除冗余
   - 添加详细 Fallback 规则

2. [entity_resolver.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/ingestion/extractors/entity_resolver.py)
   - 适配 core_metrics
   - 不再自动归类地区
   - 实现 Fallback 规则

3. [validate_v3_architecture.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/validate_v3_architecture.py)
   - v3.0 架构验证脚本

---

## 🚀 下一步

1. **测试实际 PDF 提取流程**
   - 使用 v3.0 Taxonomy Prompt
   - 验证动态地区处理

2. **验证数据库写入**
   - 测试不同公司的地区分类
   - 确保数据完整性

3. **更新 Vanna 训练文档**
   - 添加动态地区说明
   - 更新查询示例

---

## 📝 总结

v3.0 架构通过以下改进，完美解决了 v2.1 的架构问题：

1. **移除冗余**：只保留 `core_metrics`，LLM 不再困惑
2. **动态地区**：支持任意地区划分，不损失信息
3. **清晰规则**：Fallback 规则明确，AI 知道如何处理未知情况
4. **平衡设计**：核心指标硬编码，公司特有信息动态处理

这是企业级数据中台的正确设计！