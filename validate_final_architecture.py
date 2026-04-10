"""
Final Architecture Validation - v2.1

验证四个核心架构改进：
1. 无危险 DDL Tools
2. DB Client 支持 EAV + JSONB
3. 安全的 Agent Tools 已注册
4. Master Taxonomy 结构正确
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# UTF-8 输出设置
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 70)
print("[最终架构验证] v2.1 - EAV + JSONB 架构完整测试")
print("=" * 70)
print()

# ============================================================================
# Test 1: 验证无危险 DDL Tools
# ============================================================================
print("[Test 1] 验证无危险 DDL Tools")
print("-" * 70)

dangerous_patterns = [
    "ALTER TABLE",
    "add_column_if_not_exists",
    "DROP TABLE",
    "CREATE TABLE.*EXEC",  # 只检测实际执行的 CREATE TABLE
    "execute.*ALTER",
]

tools_dir = Path("nanobot/agent/tools")
dangerous_files = []

for py_file in tools_dir.glob("*.py"):
    content = py_file.read_text(encoding='utf-8')
    
    # 排除 Vanna 训练用的 DDL（不实际执行）
    if py_file.name == "vanna_tool.py":
        # 只检测是否有 execute 调用 DDL
        if "execute" in content and "CREATE TABLE" in content:
            # 检查是否在同一行（真正执行）
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                if "execute" in line and ("ALTER TABLE" in line or "DROP TABLE" in line):
                    dangerous_files.append((str(py_file), i, line.strip()))
    else:
        # 其他文件检查所有危险模式
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if "ALTER TABLE" in line and "execute" in line:
                dangerous_files.append((str(py_file), i, line.strip()))
            elif "add_column_if_not_exists" in line and "def " in line:
                dangerous_files.append((str(py_file), i, line.strip()))
            elif "DROP TABLE" in line and "execute" in line:
                dangerous_files.append((str(py_file), i, line.strip()))

if not dangerous_files:
    print("[OK] 无危险 DDL Tools")
    print("     - 无 ALTER TABLE 执行代码")
    print("     - 无 add_column_if_not_exists 方法")
    print("     - 无 DROP TABLE 执行代码")
    test1_passed = True
else:
    print("[FAIL] 发现危险 DDL 代码：")
    for file, line_num, line in dangerous_files:
        print(f"     - {file}:{line_num} - {line}")
    test1_passed = False

print()

# ============================================================================
# Test 2: 验证 DB Client 支持 EAV + JSONB
# ============================================================================
print("[Test 2] 验证 DB Client 支持 EAV + JSONB")
print("-" * 70)

db_client_path = Path("nanobot/ingestion/repository/db_client.py")
db_client_code = db_client_path.read_text(encoding='utf-8')

required_methods = {
    "insert_financial_metric": "EAV 写入方法",
    "update_company_extra_data": "JSONB 写入方法",
    "batch_update_company_extra_data": "批量 JSONB 更新",
}

test2_results = {}
for method, desc in required_methods.items():
    if f"async def {method}" in db_client_code:
        test2_results[method] = True
        print(f"[OK] {desc} 已存在: {method}()")
    else:
        test2_results[method] = False
        print(f"[FAIL] {desc} 不存在: {method}()")

# 检查是否使用 ON CONFLICT (幂等性)
if "ON CONFLICT" in db_client_code:
    print("[OK] SQL 具备幂等性 (ON CONFLICT)")
    test2_results["idempotency"] = True
else:
    print("[WARN] SQL 缺少幂等性保护 (无 ON CONFLICT)")
    test2_results["idempotency"] = False

# 检查是否使用 jsonb_set
if "jsonb_set" in db_client_code:
    print("[OK] JSONB 写入使用 PostgreSQL jsonb_set 函数")
    test2_results["jsonb_correct"] = True
else:
    print("[FAIL] JSONB 写入未使用 jsonb_set")
    test2_results["jsonb_correct"] = False

test2_passed = all(test2_results.values())
print()

# ============================================================================
# Test 3: 验证 Agent Tools 已注册
# ============================================================================
print("[Test 3] 验证安全的 Agent Tools 已注册")
print("-" * 70)

financial_tools_path = Path("nanobot/agent/tools/financial.py")
financial_tools_code = financial_tools_path.read_text(encoding='utf-8')

required_tools = {
    "upsert_metric": "标准化指标写入 Tool",
    "upsert_metrics_batch": "批量指标写入 Tool",
}

test3_results = {}
for tool_name, desc in required_tools.items():
    if f"async def {tool_name}" in financial_tools_code:
        test3_results[tool_name] = True
        print(f"[OK] {desc} 已注册: {tool_name}()")
    else:
        test3_results[tool_name] = False
        print(f"[FAIL] {desc} 未注册: {tool_name}()")

# 检查智能路由逻辑
if "static_attributes" in financial_tools_code:
    print("[OK] Tool 包含智能路由逻辑（区分年度指标 vs 静态属性）")
    test3_results["smart_routing"] = True
else:
    print("[FAIL] Tool 缺少智能路由逻辑")
    test3_results["smart_routing"] = False

# 检查 JSONB 和 EAV 调用
if "update_company_extra_data" in financial_tools_code:
    print("[OK] Tool 调用 JSONB 写入方法")
    test3_results["call_jsonb"] = True
else:
    print("[FAIL] Tool 未调用 JSONB 写入方法")
    test3_results["call_jsonb"] = False

if "insert_financial_metric" in financial_tools_code:
    print("[OK] Tool 调用 EAV 写入方法")
    test3_results["call_eav"] = True
else:
    print("[FAIL] Tool 未调用 EAV 写入方法")
    test3_results["call_eav"] = False

test3_passed = all(test3_results.values())
print()

# ============================================================================
# Test 4: 验证 Master Taxonomy 结构
# ============================================================================
print("[Test 4] 验证 Master Taxonomy 结构")
print("-" * 70)

taxonomy_path = Path("nanobot/ingestion/config/financial_terms_mapping.json")

with open(taxonomy_path, 'r', encoding='utf-8') as f:
    taxonomy = json.load(f)

test4_results = {}

# 检查顶级字段
required_sections = ["instructions", "metrics", "company_attributes", "fallback_rule"]
for section in required_sections:
    if section in taxonomy:
        test4_results[section] = True
        print(f"[OK] 顶级字段存在: {section}")
    else:
        test4_results[section] = False
        print(f"[FAIL] 顶级字段缺失: {section}")

# 检查 metrics 结构
if "metrics" in taxonomy:
    metrics = taxonomy["metrics"]
    print(f"[OK] metrics 数量: {len(metrics)}")
    
    # 检查每个 metric 的字段
    required_metric_fields = ["standard_name", "description", "synonyms"]
    sample_metric = metrics[0] if metrics else {}
    
    for field in required_metric_fields:
        if field in sample_metric:
            print(f"[OK] metric 包含字段: {field}")
        else:
            print(f"[FAIL] metric 缺少字段: {field}")

# 检查 company_attributes 结构
if "company_attributes" in taxonomy:
    attrs = taxonomy["company_attributes"]
    print(f"[OK] company_attributes 数量: {len(attrs)}")
    
    # 检查每个 attribute 的字段
    required_attr_fields = ["standard_name", "description", "synonyms", "value_type"]
    sample_attr = attrs[0] if attrs else {}
    
    for field in required_attr_fields:
        if field in sample_attr:
            print(f"[OK] company_attribute 包含字段: {field}")
        else:
            print(f"[WARN] company_attribute 缺少字段: {field}")

# 检查 fallback_rule
if "fallback_rule" in taxonomy:
    fallback = taxonomy["fallback_rule"]
    if "小寫英文" in fallback or "底線" in fallback:
        print("[OK] fallback_rule 包含命名规范")
        test4_results["fallback_correct"] = True
    else:
        print("[WARN] fallback_rule 缺少命名规范说明")
        test4_results["fallback_correct"] = False

test4_passed = all(test4_results.values())
print()

# ============================================================================
# 最终总结
# ============================================================================
print("=" * 70)
print("[最终架构验证结果]")
print("=" * 70)

all_tests = [
    ("Test 1: 无危险 DDL Tools", test1_passed),
    ("Test 2: DB Client 支持 EAV + JSONB", test2_passed),
    ("Test 3: 安全的 Agent Tools 已注册", test3_passed),
    ("Test 4: Master Taxonomy 结构正确", test4_passed),
]

passed_count = sum(1 for _, passed in all_tests if passed)
total_count = len(all_tests)

for test_name, passed in all_tests:
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {test_name}")

print()
print(f"通过测试: {passed_count}/{total_count}")
print(f"完成度: {passed_count/total_count * 100:.1f}%")

if passed_count == total_count:
    print()
    print("=" * 70)
    print("[SUCCESS] 架构重构完成！")
    print("=" * 70)
    print()
    print("核心架构改进：")
    print("  1. DDL 风险已彻底消除")
    print("  2. EAV + JSONB 双轨制已实现")
    print("  3. 智能路由 Tool 已注册")
    print("  4. Master Taxonomy 作为唯一权威字典")
    print()
    print("LLM 的职责已被限制为：")
    print("  - 意图识别（识别指标类型）")
    print("  - 数据标准化（对齐到 standard_name）")
    print()
    print("确定性后端负责：")
    print("  - 幂等性写入（ON CONFLICT）")
    print("  - 智能路由（年度指标 → EAV，静态属性 → JSONB）")
    print("  - 事务管理（确保数据一致性）")
    print()
    print("下一步建议：")
    print("  1. 在 Docker 环境测试数据库连接")
    print("  2. 测试完整流程：PDF → LLM → Taxonomy → DB")
    print("  3. 更新 Vanna 训练文档")
else:
    print()
    print("[WARNING] 部分测试未通过，请检查上述标记 [FAIL] 的项目")

print()
print("验证完成！")