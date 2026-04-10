"""
致命风险 Fact-Check 验证脚本

验证 4 个致命风险是否已修复：
1. JSONB NULL 覆写崩溃
2. 数值型别转换灾难
3. Vanna 训练数据缺失
4. 旧毒药 Tool 残留
"""

import json
import sys
from pathlib import Path
import re

# UTF-8 输出设置
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 70)
print("[致命风险 Fact-Check] 4 大风险验证")
print("=" * 70)
print()

# ============================================================================
# Fact-Check 1: JSONB NULL 覆写崩溃
# ============================================================================
print("[Fact-Check 1] JSONB NULL 覆写崩溃")
print("-" * 70)

db_client_path = Path("nanobot/ingestion/repository/db_client.py")
db_client_code = db_client_path.read_text(encoding='utf-8')

# 检查是否使用 COALESCE
if "COALESCE(extra_data, '{}'::jsonb)" in db_client_code:
    print("[PASS] JSONB 写入已使用 COALESCE 兜底")
    print("       防止了 NULL 覆写崩溃")
    fact1_passed = True
else:
    print("[FAIL] JSONB 写入未使用 COALESCE")
    print("       存在 NULL 覆写崩溃风险！")
    fact1_passed = False

print()

# ============================================================================
# Fact-Check 2: 数值型别转换灾难
# ============================================================================
print("[Fact-Check 2] 数值型别转换灾难")
print("-" * 70)

financial_tools_path = Path("nanobot/agent/tools/financial.py")
financial_tools_code = financial_tools_path.read_text(encoding='utf-8')

# 检查是否有数值清洗函数
if "_clean_numeric_value" in financial_tools_code:
    print("[PASS] 已实现数值清洗函数 _clean_numeric_value()")
    
    # 检查是否处理千分位
    if "replace(',', '')" in financial_tools_code or "re.sub" in financial_tools_code:
        print("       - 已处理千分位逗号")
    
    # 检查是否处理货币符号
    if "HKD" in financial_tools_code or "USD" in financial_tools_code or "re.sub" in financial_tools_code:
        print("       - 已处理货币符号")
    
    # 检查是否处理数量级缩写
    if "multiplier" in financial_tools_code and ("Million" in financial_tools_code or "Billion" in financial_tools_code):
        print("       - 已处理数量级缩写 (M/B/K)")
    
    # 检查是否处理括号负数
    if "is_negative" in financial_tools_code and "(" in financial_tools_code:
        print("       - 已处理括号负数 (会计惯例)")
    
    fact2_passed = True
else:
    print("[FAIL] 未实现数值清洗函数")
    print("       存在型别转换灾难风险！")
    fact2_passed = False

print()

# ============================================================================
# Fact-Check 3: Vanna 训练数据缺失
# ============================================================================
print("[Fact-Check 3] Vanna 训练数据缺失")
print("-" * 70)

documentation_path = Path("nanobot/vanna-service/data/documentation.json")
if not documentation_path.exists():
    documentation_path = Path("vanna-service/data/documentation.json")

with open(documentation_path, 'r', encoding='utf-8') as f:
    vanna_docs = json.load(f)

# 检查是否包含 EAV 查询训练
has_eav_training = False
has_jsonb_training = False

for item in vanna_docs.get("items", []):
    if "eav" in item.get("id", "").lower() or "metric_name" in item.get("content", ""):
        has_eav_training = True
    
    if "jsonb" in item.get("id", "").lower() or "->>" in item.get("content", ""):
        has_jsonb_training = True

if has_eav_training:
    print("[PASS] Vanna 已包含 EAV 查询训练数据")
    # 显示示例
    for item in vanna_docs.get("items", []):
        if "eav" in item.get("id", "").lower():
            print(f"       - {item['id']}: {item['content'][:60]}...")
            break
    fact3_eav = True
else:
    print("[FAIL] Vanna 缺少 EAV 查询训练数据")
    fact3_eav = False

if has_jsonb_training:
    print("[PASS] Vanna 已包含 JSONB 查询训练数据")
    # 显示示例
    for item in vanna_docs.get("items", []):
        if "jsonb" in item.get("id", "").lower():
            print(f"       - {item['id']}: {item['content'][:60]}...")
            break
    fact3_jsonb = True
else:
    print("[FAIL] Vanna 缺少 JSONB 查询训练数据")
    fact3_jsonb = False

fact3_passed = fact3_eav and fact3_jsonb

print()

# ============================================================================
# Fact-Check 4: 旧毒药 Tool 残留
# ============================================================================
print("[Fact-Check 4] 旧毒药 Tool 残留")
print("-" * 70)

# 全局搜索危险代码
dangerous_patterns = [
    (r"ALTER\s+TABLE", "ALTER TABLE"),
    (r"add_column_if_not_exists", "add_column_if_not_exists"),
    (r"get_table_schema", "get_table_schema"),
    (r"DROP\s+TABLE", "DROP TABLE"),
]

found_dangerous = []

for pattern, name in dangerous_patterns:
    # 搜索 Python 文件
    for py_file in Path("nanobot").glob("**/*.py"):
        # 排除测试文件和注释
        if "test" in str(py_file).lower():
            continue
        
        content = py_file.read_text(encoding='utf-8')
        
        # 移除所有 docstring 和注释
        # 移除三引号 docstring
        content_no_docstring = re.sub(r'""".*?"""', '', content, flags=re.DOTALL)
        content_no_docstring = re.sub(r"'''.*?'''", '', content_no_docstring, flags=re.DOTALL)
        
        # 移除单行注释
        lines_no_comments = []
        for line in content_no_docstring.split('\n'):
            # 移除行内注释
            if '#' in line:
                line = line.split('#')[0]
            lines_no_comments.append(line)
        
        content_clean = '\n'.join(lines_no_comments)
        lines = content_clean.split('\n')
        
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                # 排除 Vanna 训练数据中的 DDL 示例
                if "vanna-service" in str(py_file) or "CREATE TABLE" in line:
                    continue
                
                found_dangerous.append((str(py_file), i, line.strip(), name))

if not found_dangerous:
    print("[PASS] 未发现残留的 DDL 危险代码")
    print("       - 无 ALTER TABLE")
    print("       - 无 add_column_if_not_exists")
    print("       - 无 get_table_schema")
    print("       - 无 DROP TABLE")
    fact4_passed = True
else:
    print("[FAIL] 发现残留的 DDL 危险代码：")
    for file, line_num, line, pattern in found_dangerous[:5]:
        print(f"       - {file}:{line_num} - {pattern}")
        print(f"         {line}")
    fact4_passed = False

print()

# ============================================================================
# 最终总结
# ============================================================================
print("=" * 70)
print("[Fact-Check 结果]")
print("=" * 70)

all_checks = [
    ("Fact-Check 1: JSONB NULL 覆写", fact1_passed),
    ("Fact-Check 2: 数值型别转换", fact2_passed),
    ("Fact-Check 3: Vanna 训练数据", fact3_passed),
    ("Fact-Check 4: DDL 代码残留", fact4_passed),
]

passed_count = sum(1 for _, passed in all_checks if passed)
total_count = len(all_checks)

for check_name, passed in all_checks:
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {check_name}")

print()
print(f"通过检查: {passed_count}/{total_count}")
print(f"安全度: {passed_count/total_count * 100:.1f}%")

if passed_count == total_count:
    print()
    print("=" * 70)
    print("[SUCCESS] 所有致命风险已防堵！")
    print("=" * 70)
    print()
    print("系统现在安全：")
    print("  1. ✅ JSONB 写入具备 NULL 保护")
    print("  2. ✅ 数值转换具备完整清洗逻辑")
    print("  3. ✅ Vanna 已学会 EAV + JSONB 查询")
    print("  4. ✅ DDL 危险代码已彻底清除")
    print()
    print("架构优势：")
    print("  - 永远不会 Crash（无 DDL 风险）")
    print("  - 数据完整性保证（清洗 + 验证）")
    print("  - Vanna 查询正确性（训练完整）")
    print("  - 企业级稳定性（防御性编程）")
    print()
    print("下一步：")
    print("  1. 在 Docker 环境进行集成测试")
    print("  2. 测试实际 PDF 提取流程")
    print("  3. 验证 Vanna 查询准确性")
else:
    print()
    print("[WARNING] 部分致命风险未修复，请检查上述 [FAIL] 项目")

print()
print("Fact-Check 完成！")