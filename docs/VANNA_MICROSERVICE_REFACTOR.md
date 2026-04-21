# Vanna 微服务架构重构

## 📋 概述

将 Vanna AI 从单体架构重构为真正的微服务架构，实现 Gateway 与 Vanna 的解耦。

## 🌟 功能迁移对照表

| 原本 vanna_tool.py | 现在 vanna-service/start.py |
|-------------------|----------------------------|
| `VannaSQL.discover_dynamic_keys()` | `GET /api/discover_dynamic_keys` |
| `VannaSQL.build_enhanced_prompt()` | 内置在 `POST /api/ask_with_dynamic_schema` |
| `VannaSQL.generate_sql_with_dynamic_schema()` | `POST /api/ask_with_dynamic_schema` |
| `VannaSQL.query_with_dynamic_schema()` | `POST /api/ask_with_dynamic_schema` |
| `VannaSQL.train_schema()` | `POST /api/train` |
| `VannaSQL.generate_sql()` | `POST /api/ask` |
| `VannaSQL.execute()` | 内置在 `/api/ask` 和 `/api/ask_with_dynamic_schema` |

## 🆕 新增 API Endpoints

### 1. `GET /api/discover_dynamic_keys`

发现 JSONB 字段中的所有动态 Keys：

```bash
curl http://localhost:8082/api/discover_dynamic_keys
```

返回：
```json
{
  "discovered_keys": ["index_quarter", "index_theme", "is_audited"],
  "total_keys": 3,
  "sample_values": {
    "index_quarter": "Q3",
    "index_theme": "Biotech"
  },
  "key_frequency": {
    "index_quarter": 50,
    "index_theme": 45
  },
  "discovered_industries": ["Biotech", "Healthcare", "Fintech"],
  "status": "success"
}
```

### 2. `POST /api/ask_with_dynamic_schema`

带 Just-in-Time Schema Injection 的查询：

```bash
curl -X POST http://localhost:8082/api/ask_with_dynamic_schema \
  -H "Content-Type: application/json" \
  -d '{"question": "Find all Q3 Biotech companies"}'
```

## 🚀 部署步骤

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot

# 重建所有镜像
docker-compose build

# 启动服务
docker-compose up -d

# 验证 Vanna Service
curl http://localhost:8082/health
curl http://localhost:8082/api/discover_dynamic_keys
```

## 📊 效果对比

| 指标 | 重构前 | 重构后 |
|------|--------|--------|
| Gateway 镜像大小 | ~2.5 GB | ~1.8 GB |
| WebUI 镜像大小 | ~2.3 GB | ~1.6 GB |
| 依赖冲突风险 | 高 (vanna + torch) | 低 (纯 HTTP) |
| 资源利用率 | 低 (Vanna 容器空闲) | 高 (各司其职) |

## ✅ 总结

所有原本的功能都已迁移到 vanna-service，包括：
- ✅ 动态 Schema 发现 (`discover_dynamic_keys`)
- ✅ Just-in-Time Schema Injection (`ask_with_dynamic_schema`)
- ✅ Text-to-SQL 生成 (`ask`)
- ✅ Vanna 训练 (`train`)
- ✅ Embedding 生成 (`embed`)
