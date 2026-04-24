# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Pipeline v4.8.4] - 2026-04-22

### Fixed
- **Stage 0**: 修復圖片匹配問題，精確匹配 Page 1 圖片（避免匹配 Page 10, 11, 19 等）
  - 問題：`img_p1_*.jpg` 會錯誤匹配 `img_p10_1.jpg`, `img_p19_1.jpg` 等
  - 解決：使用正則表達式精確過濾

---

## [Pipeline v4.7] - 2026-04-20

### Changed
- **Stage 0**: 移除 PyMuPDF 依賴，完全基於 LlamaParse artifacts
  - 原因：PyMuPDF 與其他依賴衝突，且 LlamaParse 已提供足夠資訊
  - 效果：減少依賴，降低容器大小

### Improved
- **Stage 0**: 改進圖片處理邏輯，支援從 `parse_result.images` 和 `raw_output_dir` 讀取圖片

---

## [Pipeline v4.6] - 2026-04-18

### Changed
- **Pipeline Flow**: Stage 1 (LlamaParse) 先行，然後 Stage 0 (Vision) 分析 Page 1
  - 原因：LlamaParse 解析後有完整 Markdown + 圖片，Vision 提取更準確
  - 效果：提高公司信息提取準確度

---

## [Pipeline v4.3] - 2026-04-15

### Added
- **Stage 0.5**: 新增 `original_filename` 參數，保存原始上傳文件名
- **Documents 表**: 新增 `dynamic_attributes` JSONB 欄位

---

## [Pipeline v4.0] - 2026-04-10

### Changed
- **Pipeline 重構**: 簡化為極簡協調器模式 (~250 行)
- **Stage 4**: 統一提取入口點，使用 Tool Calling 架構

### Removed
- 移除 Toggle 機制，Pipeline 直線化

---

## [Schema v2.3] - 2026-04-15

### Added
- **artifact_relations 表**: 解決跨頁圖文關聯問題
- **documents.dynamic_attributes**: JSONB 動態屬性
- **companies.extra_data**: JSONB 彈性擴展欄位
- **shareholding_structure.trust_name, trustee_name**: 信託資訊欄位
- **document_pages.ocr_confidence, embedding_vector**: OCR 置信度和向量嵌入

### Changed
- **market_data 表欄位名稱變更**:
  - `trade_date` → `data_date`
  - `closing_price` → `close_price`
  - `opening_price` `open_price`
  - `trading_volume` → `volume`
- **revenue_breakdown 表欄位名稱變更**:
  - `category` → `segment_name`
  - `category_type` → `segment_type`
  - `amount` → `revenue_amount`
- **key_personnel 表欄位名稱變更**:
  - `person_name` → `name_en`
  - `person_name_zh` → `name_zh`
  - `committee` → `committee_membership` (JSONB)

### Removed
- **document_pages.company_id**: 移除，必須 JOIN documents 篩選
- **raw_artifacts.company_id**: 移除，必須 JOIN documents

---

## [Vanna Service v2.3.0] - 2026-04-15

### Added
- **Dynamic Schema Injection**: Just-in-Time Schema 注入
- **`/api/discover_dynamic_keys`**: 發現 JSONB 動態 Keys
- **`/api/ask_with_dynamic_schema`**: 帶動態 Schema 的查詢
- **`/api/embed`**: Embedding 生成 API

### Changed
- 微服務架構重構，與 Gateway 解耦

---

## [Schema v2.0] - 2026-03-01

### Added
- **行業雙軌制**: Rule A (權威來源) + Rule B (AI 預測)
- **完美溯源機制**: `raw_artifacts` 表
- **知識圖譜支援**: `entity_relations` 表

---

## [Pipeline v3.0] - 2026-02-15

### Added
- **Stage 4.5**: 知識圖譜提取器
- **Stage 8**: 歸檔器

---

## [Pipeline v2.0] - 2026-01-15

### Added
- **Stage 3.5**: 結構化上下文構建器
- **Stage 5**: Vanna 訓練

---

## [Pipeline v1.0] - 2025-12-01

### Added
- 初始版本
- 基礎 PDF 解析流程
- LlamaParse 集成
- 財務數據提取
