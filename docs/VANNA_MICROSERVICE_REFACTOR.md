# Vanna 微服務架構文檔

## 📋 概述

Vanna AI Text-to-SQL 微服務，基於 [Vanna.ai](https://vanna.ai/) 框架，結合 ChromaDB 向量存儲和 Alibaba Cloud LLM。

**注意：** 本專案是 `nanobot` 的兄弟項目，位於 `SFC_AI/sfc_poc/vanna/`

## 📁 實際檔案結構

```
SFC_AI/sfc_poc/vanna/
├── README.md
├── docker-compose.yml
└── vanna_backend/
    ├── app_alicloud_mysql.py    # Flask API 服務器 (~391行)
    ├── training_data.py         # 訓練數據（DDL/SQL/Docs）(~461行)
    ├── utility.py               # 工具函數 (~153行)
    ├── vanna_config.py          # Vanna 配置 (~18行)
    ├── test_chart.py
    ├── requirements.txt
    └── chroma_db/               # ChromaDB 向量存儲
```

## 🔧 技術棧

| 組件 | 技術 |
|------|------|
| Text-to-SQL | Vanna 0.7.9 |
| 向量數據庫 | ChromaDB |
| LLM | Alibaba Cloud (Qwen-plus) |
| 資料庫 | MySQL |
| API 框架 | Flask |

## 🌟 API Endpoints

### 現有的 API Endpoints (`app_alicloud_mysql.py`)

| Endpoint | 方法 | 說明 |
|----------|------|------|
| `/api/get_training_data` | GET | 獲取訓練數據 |
| `/api/delete_training_data` | DELETE | 刪除訓練數據 |
| `/api/train_with_ddl` | POST | 使用 DDL 訓練 |
| `/api/train_with_queries` | POST | 使用 Question-SQL 對訓練 |
| `/api/pre_train` | POST | 預訓練（DDL + SQL 對） |
| `/api/generate_sql` | POST | 生成 SQL 查詢 |
| `/api/health` | GET | 健康檢查 |

## ⚠️ DDL 同步問題

**重要：** `training_data.py` 中的 DDL 與 `nanobot/storage/init_complete.sql` 不一致

| 問題 | 說明 |
|------|------|
| 欄位不存在 | `index_theme`, `parent_company`, `is_index_report` |
| 向量維度錯誤 | `VECTOR(1536)` 應為 `VECTOR(384)` |
| 表結構過時 | `document_companies` 使用 `company_name` 而非 `company_id` FK |

**參見：** [CODE_REVIEW_2026-04-25.md](CODE_REVIEW_2026-04-25.md)

## 🚀 部署

```bash
cd SFC_AI/sfc_poc/vanna/vanna_backend

# 安裝依賴
pip install -r requirements.txt

# 運行服務
flask --app app_alicloud_mysql.py run --port 5000
```

## 📊 服務狀態

| 端口 | 服務 |
|------|------|
| 5000 | Vanna Flask API (本地) |
| 8082 | Vanna Service (Docker) |

## ✅ 總結

當前 Vanna Service 實現：
- ✅ ChromaDB 向量存儲
- ✅ Alibaba Cloud LLM 集成
- ✅ MySQL 資料庫連接
- ✅ 預訓練 + 查詢生成
- ❌ **DDL 需要與 nanobot 同步**
