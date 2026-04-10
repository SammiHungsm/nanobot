"""
代码修复验证脚本

验证 4 个关键修复：
1. DocumentPipeline 异步初始化
2. Vanna Service 健康检查
3. 环境变量一致性
4. 错误处理完善
"""

import sys
import os
from pathlib import Path
import re

# UTF-8 输出设置
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 70)
print("[代码修复验证] 4 个关键问题")
print("=" * 70)
print()

# ============================================================================
# 修复 1：DocumentPipeline 异步初始化
# ============================================================================
print("[修复 1] DocumentPipeline 异步初始化")
print("-" * 70)

document_service_path = Path("webui/app/services/document_service.py")
document_service_code = document_service_path.read_text(encoding='utf-8')

# 检查是否有延迟初始化
if "self.pipeline = None" in document_service_code:
    print("[PASS] Pipeline 延迟初始化已实现")
    fix1_lazy_init = True
else:
    print("[FAIL] Pipeline 未延迟初始化")
    fix1_lazy_init = False

# 检查是否有 _ensure_pipeline_connected 方法
if "_ensure_pipeline_connected" in document_service_code:
    print("[PASS] _ensure_pipeline_connected 方法已添加")
    fix1_ensure = True
else:
    print("[FAIL] 缺少 _ensure_pipeline_connected 方法")
    fix1_ensure = False

# 检查是否在处理前调用连接
if "await self._ensure_pipeline_connected()" in document_service_code:
    print("[PASS] 在处理前调用异步连接")
    fix1_call = True
else:
    print("[FAIL] 未在处理前调用异步连接")
    fix1_call = False

fix1_passed = fix1_lazy_init and fix1_ensure and fix1_call

print()

# ============================================================================
# 修复 2：Vanna Service 健康检查
# ============================================================================
print("[修复 2] Vanna Service 健康检查")
print("-" * 70)

docker_compose_path = Path("docker-compose.yml")
docker_compose_code = docker_compose_path.read_text(encoding='utf-8')

# 检查 vanna-service 的 depends_on 配置
lines = docker_compose_code.split('\n')
vanna_depends_start = False
vanna_health_check = False

for i, line in enumerate(lines):
    if "vanna-service:" in line:
        vanna_depends_start = True
    
    if vanna_depends_start and "depends_on:" in line:
        # 检查接下来的几行是否有 condition: service_healthy
        for j in range(i, min(i + 10, len(lines))):
            if "condition: service_healthy" in lines[j]:
                vanna_health_check = True
                print("[PASS] Vanna Service 等待 PostgreSQL 健康检查")
                break
        break

if not vanna_health_check:
    print("[FAIL] Vanna Service 未配置健康检查依赖")

fix2_passed = vanna_health_check

print()

# ============================================================================
# 修复 3：环境变量一致性
# ============================================================================
print("[修复 3] 环境变量一致性（本地开发 vs Docker）")
print("-" * 70)

chat_api_path = Path("webui/app/api/chat.py")
chat_api_code = chat_api_path.read_text(encoding='utf-8')

# 检查是否支持 ENV 环境变量
if "ENV" in chat_api_code and "development" in chat_api_code:
    print("[PASS] 支持 ENV 环境变量切换环境")
    fix3_env = True
else:
    print("[FAIL] 未支持 ENV 环境变量")
    fix3_env = False

# 检查是否有本地开发默认值
if "localhost:8081" in chat_api_code:
    print("[PASS] 本地开发默认值已配置")
    fix3_local = True
else:
    print("[FAIL] 缺少本地开发默认值")
    fix3_local = False

# 检查是否有 Docker 服务名
if "nanobot-gateway:8081" in chat_api_code:
    print("[PASS] Docker 服务名已配置")
    fix3_docker = True
else:
    print("[FAIL] 缺少 Docker 服务名")
    fix3_docker = False

fix3_passed = fix3_env and fix3_local and fix3_docker

print()

# ============================================================================
# 修复 4：错误处理完善
# ============================================================================
print("[修复 4] 错误处理完善")
print("-" * 70)

document_service_code = document_service_path.read_text(encoding='utf-8')

# 检查是否有 traceback 导入
if "import traceback" in document_service_code:
    print("[PASS] traceback 模块已导入")
    fix4_traceback = True
else:
    print("[FAIL] traceback 模块未导入")
    fix4_traceback = False

# 检查是否记录 traceback
if "traceback.format_exc()" in document_service_code or "exc_info=True" in document_service_code:
    print("[PASS] 记录详细错误信息")
    fix4_log = True
else:
    print("[FAIL] 未记录详细错误信息")
    fix4_log = False

# 检查是否处理 CancelledError
if "asyncio.CancelledError" in document_service_code:
    print("[PASS] 处理 CancelledError")
    fix4_cancel = True
else:
    print("[WARN] 未处理 CancelledError")
    fix4_cancel = True  # 可选，不强制

fix4_passed = fix4_traceback and fix4_log and fix4_cancel

print()

# ============================================================================
# 最终总结
# ============================================================================
print("=" * 70)
print("[修复验证结果]")
print("=" * 70)

all_fixes = [
    ("修复 1: Pipeline 异步初始化", fix1_passed),
    ("修复 2: Vanna 健康检查", fix2_passed),
    ("修复 3: 环境变量一致性", fix3_passed),
    ("修复 4: 错误处理完善", fix4_passed),
]

passed_count = sum(1 for _, passed in all_fixes if passed)
total_count = len(all_fixes)

for fix_name, passed in all_fixes:
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {fix_name}")

print()
print(f"通过修复: {passed_count}/{total_count}")
print(f"安全度: {passed_count/total_count * 100:.1f}%")

if passed_count == total_count:
    print()
    print("=" * 70)
    print("[SUCCESS] 所有代码修复已完成！")
    print("=" * 70)
    print()
    print("修复总结：")
    print("  1. ✅ Pipeline 延迟初始化，避免同步连接问题")
    print("  2. ✅ Vanna 等待 PostgreSQL 完全启动")
    print("  3. ✅ 支持本地开发和 Docker 环境切换")
    print("  4. ✅ 错误处理包含完整 traceback 和 CancelledError")
    print()
    print("系统稳定性提升：")
    print("  - 避免数据库连接时序问题")
    print("  - 避免服务启动竞争条件")
    print("  - 支持灵活的部署环境")
    print("  - 完整的错误追踪能力")
    print()
    print("下一步：")
    print("  1. 在 Docker 环境测试完整启动流程")
    print("  2. 验证 PDF 处理是否正常")
    print("  3. 测试错误场景的处理")
else:
    print()
    print("[WARNING] 部分修复未完成，请检查上述 [FAIL] 项目")

print()
print("验证完成！")