# 服务器启动流程总结

## 📊 快速启动指南

### 方式 1：Docker Compose（推荐）

```bash
# 进入项目目录
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 方式 2：本地开发

```bash
# 1. 启动 PostgreSQL（必须）
docker-compose up -d postgres-financial

# 2. 设置环境变量
export ENV=development
export DATABASE_URL=postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports

# 3. 启动 Vanna Service
cd vanna-service
python start.py

# 4. 启动 Gateway（另一个终端）
cd ..
python -m nanobot gateway --config config/config.json

# 5. 启动 WebUI（另一个终端）
cd webui
python -m app.main
```

---

## 🔄 服务启动顺序

```
1. PostgreSQL (postgres-financial)
   └─ 健康检查通过：pg_isready

2. Vanna Service (vanna-service)
   ├─ 等待 PostgreSQL 健康检查 ✅
   ├─ 连接数据库
   ├─ 加载训练数据
   └─ 启动 FastAPI (port 8000)

3. Nanobot Gateway (nanobot-gateway)
   ├─ 等待 PostgreSQL 健康检查 ✅
   ├─ 加载配置
   ├─ 注册 Tools
   └─ 启动 HTTP 服务 (port 8081)

4. WebUI (nanobot-webui)
   ├─ 等待 PostgreSQL 健康检查 ✅
   ├─ 初始化目录
   ├─ 延迟初始化 DocumentPipeline
   └─ 启动 FastAPI (port 3000)
```

---

## 🧪 健康检查

```bash
# PostgreSQL
curl http://localhost:5433 || echo "PostgreSQL 未启动"

# Vanna Service
curl http://localhost:8000/health

# Gateway
curl http://localhost:8081/health

# WebUI
curl http://localhost:3000/health
```

---

## 🐛 常见问题

### 问题 1：服务启动失败

**症状**：`docker-compose ps` 显示服务状态为 `Exit (1)`

**排查**：
```bash
# 查看详细日志
docker-compose logs [service-name] --tail 100

# 检查依赖服务
docker-compose exec postgres-financial pg_isready -U postgres
```

---

### 问题 2：PDF 处理卡住

**症状**：上传后状态一直显示 "processing"

**排查**：
```bash
# 检查队列状态
docker exec -it nanobot-webui python -c "
from app.api import document_service
import asyncio
print(asyncio.run(document_service.get_queue_status()))
"

# 检查 Pipeline 连接
docker exec -it nanobot-webui python -c "
from app.services.document_service import DocumentService
import asyncio
ds = DocumentService('/app/uploads', '/app/outputs')
asyncio.run(ds._ensure_pipeline_connected())
print('Pipeline 连接成功')
"
```

---

### 问题 3：Vanna 查询失败

**症状**：返回 SQL 错误或空结果

**排查**：
```bash
# 检查 Vanna 训练状态
curl http://localhost:8000/status

# 重新训练
curl -X POST http://localhost:8000/train \
  -H "Content-Type: application/json" \
  -d '{"train_type": "schema"}'
```

---

## 📝 修复记录

| 修复项 | 问题 | 解决方案 | 状态 |
|-------|------|---------|------|
| Pipeline 初始化 | 同步初始化异步对象 | 延迟初始化 + `_ensure_pipeline_connected()` | ✅ 已修复 |
| Vanna 依赖 | 未等待 PostgreSQL 就绪 | 添加 `condition: service_healthy` | ✅ 已修复 |
| 环境变量 | 硬编码 Docker 服务名 | 支持 ENV 环境变量切换 | ✅ 已修复 |
| 错误处理 | 缺少 traceback 和 CancelledError | 添加完整错误追踪 | ✅ 已修复 |

---

## 📚 相关文档

- [完整服务器 Workflow](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docs/SERVER_WORKFLOW.md)
- [架构总结 v3.0](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/ARCHITECTURE_V3_SUMMARY.md)
- [代码修复验证](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/verify_code_fixes.py)

---

## 🎯 下一步

1. **测试完整流程**：上传 PDF → 处理 → 查询
2. **性能测试**：并发 PDF 处理
3. **错误场景测试**：模拟各种失败情况
4. **日志监控**：配置 ELK 或其他日志系统