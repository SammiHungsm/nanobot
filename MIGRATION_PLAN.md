# Pipeline.py 迁移计划

## 目标
将 pipeline.py (1821 行) 重构为 Orchestrator 模式，逐步替换为 Stage handler 调用

## 当前结构分析

### 核心方法 (需要迁移)
| 方法 | 行数 | 对应 Stage | 功能 |
|------|------|------------|------|
| `process_pdf_full` | 1264-1476 | Orchestrator | 主流程入口 |
| `_extract_and_create_company` | 972-1235 | Stage 0 | 封面预处理 + 公司提取 |
| `_save_opendataloader_artifacts` | 1477-1748 | Stage 2 | 图片保存 + Vision 分析 |
| `smart_extract` | 395-716 | Stage 3 + 4 | 关键字扫描 + 深度提取 |

### 辅助方法 (保留在 Pipeline)
| 方法 | 功能 | 保留原因 |
|------|------|----------|
| `_compute_file_hash` | 计算 Hash | 通用工具 |
| `_create_document` | 创建文档记录 | DB 操作 |
| `save_all_pages_to_fallback_table` | 保存到兜底表 | DB 操作 |
| `_trigger_vanna_training` | 触发训练 | 流程控制 |
| `_get_document_year` | 获取年份 | 查询辅助 |

## 迁移步骤

### Phase 1: 完善 Stage Handlers (确保功能完整)
1. **Stage0Preprocessor** - 完善 `_extract_and_create_company` 所有逻辑
2. **Stage2Enrichment** - 完善 `_save_opendataloader_artifacts` 所有逻辑
3. **Stage3Router** - 完善 `smart_extract` 的关键字扫描逻辑
4. **Stage4Extractor** - 完善 `smart_extract` 的深度提取逻辑

### Phase 2: 更新 pipeline.py 调用 Stage Handlers
1. 修改 `process_pdf_full` 调用 Stage handlers
2. 保留辅助方法在 Pipeline
3. 确保向后兼容

### Phase 3: 清理
1. 移除已迁移的私有方法
2. 简化 pipeline.py 到 ~300 行

## 功能完整性检查清单

### Stage 0 功能
- [ ] 快速解析 Page 1-2
- [ ] Vision API 提取 stock_code
- [ ] Vision API 提取 year
- [ ] Vision API 提取 name_en, name_zh
- [ ] Fallback: 从文件名提取
- [ ] 创建 company 记录

### Stage 1 功能
- [ ] OpenDataLoader Hybrid 解析
- [ ] 分批处理 (避免崩溃)
- [ ] 输出 artifacts (tables, images, text)

### Stage 2 功能
- [ ] 保存图片 PNG 文件
- [ ] Vision 分析图片内容
- [ ] 生成 Enriched Markdown
- [ ] 写入 entity_relations
- [ ] 写入 artifact_relations

### Stage 3 功能
- [ ] 关键字扫描
- [ ] 候选页面路由
- [ ] 支持多种类型 (revenue, personnel, metrics)

### Stage 4 功能
- [ ] LLM 深度提取
- [ ] Revenue Breakdown 提取
- [ ] Key Personnel 提取
- [ ] Financial Metrics 提取
- [ ] JSON 格式强制
- [ ] 写入结构化数据表

### Pipeline 保留功能
- [ ] Hash 计算
- [ ] 文档记录创建
- [ ] 兜底表写入
- [ ] Vanna 训练触发
- [ ] 进度回调
- [ ] 错误处理