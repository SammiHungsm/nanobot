# Docker Compose 清理指南

## ✅ 保留的文件

### 1. `nanobot/docker-compose.yml` - **主服务（正在使用）**
包含 4 个服务：
- postgres-financial (PostgreSQL 16)
- vanna-service (Text-to-SQL)
- nanobot-gateway (主 AI 服务)
- nanobot-webui (FastAPI 前端)

**这是唯一正在使用的核心配置。**

---

## ❌ 建议删除的文件

### 1. `sfc_poc/docker-compose.yml` - **旧架构**
**原因**：
- 使用 OpenDataLoader MCP Server（已被 OpenDataLoader 替代）
- 架构已过时
- 与 `nanobot/docker-compose.yml` 冲突

**删除命令**：
```bash
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\docker-compose.yml"
```

---

### 2. `vanna/docker-compose.yml` - **Vanna 独立测试**
**原因**：
- Vanna 已集成到 `nanobot/docker-compose.yml`
- 这是早期独立测试版本
- Langflow 未在项目中使用

**删除命令**：
```powershell
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\vanna\docker-compose.yml" -Force
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\vanna\vanna_backend" -Recurse -Force
```

---

## ⚠️ 可选删除的文件

### 3. `nanobot/docker-compose.gpu.yml` - **GPU 版本**
**保留条件**：如果你有 NVIDIA GPU 且需要 GPU 加速

**删除条件**：如果你只用 CPU（大多数情况）

**删除命令**：
```powershell
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\docker-compose.gpu.yml"
```

---

### 4. `LightRAG/docker-compose.yml` - **LightRAG 服务**
**保留条件**：如果你使用 LightRAG 进行 RAG 测试

**删除条件**：如果只专注于 PDF 处理和 Text-to-SQL

**删除命令**：
```powershell
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG\docker-compose.yml"
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG\docker-compose-full.yml"
```

---

## 🚀 清理脚本

### 方案 A：只保留核心（推荐）

```powershell
# 删除旧的根目录 docker-compose
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\docker-compose.yml" -Force

# 删除 Vanna 旧项目
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\vanna" -Recurse -Force

# 删除 GPU 配置（如果不用 GPU）
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\docker-compose.gpu.yml" -Force

# 删除 LightRAG（如果不用）
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG" -Recurse -Force

Write-Host "[OK] 清理完成，只保留 nanobot/docker-compose.yml"
```

### 方案 B：保守清理（保留 GPU 和 LightRAG）

```powershell
# 只删除明显不需要的
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\docker-compose.yml" -Force
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\vanna" -Recurse -Force

Write-Host "[OK] 清理完成，保留 GPU 和 LightRAG 配置"
```

---

## 📁 清理后的项目结构

```
sfc_poc/
├── nanobot/
│   ├── docker-compose.yml       ✅ 唯一的 docker-compose
│   ├── Dockerfile               ✅ Gateway
│   ├── vanna-service/
│   │   └── Dockerfile          ✅ Vanna
│   └── webui/
│       └── Dockerfile          ✅ WebUI
├── LightRAG/                    (可选保留)
└── vanna/                       ❌ 已删除
```

---

## 🎯 建议操作

### 步骤 1：停止所有容器
```powershell
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
docker compose down -v
```

### 步骤 2：执行清理（方案 A 推荐）
```powershell
# 一键清理
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\docker-compose.yml" -Force
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\vanna" -Recurse -Force
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\docker-compose.gpu.yml" -Force

# 如果不使用 LightRAG
Remove-Item "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG" -Recurse -Force
```

### 步骤 3：重新启动
```powershell
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
docker compose up --build
```

---

## 💾 节省空间

删除后的空间节省：
- `vanna/` 目录：~10 MB
- `LightRAG/` 目录：~50 MB（如果删除）
- 混淆的配置文件：减少心智负担

---

## 📊 总结

**保留**：
- ✅ `nanobot/docker-compose.yml`（唯一核心）

**删除**：
- ❌ `sfc_poc/docker-compose.yml`（旧架构）
- ❌ `vanna/docker-compose.yml`（已集成）
- ⚠️ `nanobot/docker-compose.gpu.yml`（可选）
- ⚠️ `LightRAG/`（可选）

**结果**：从 5 个 docker-compose 减少到 1 个，清晰明了！