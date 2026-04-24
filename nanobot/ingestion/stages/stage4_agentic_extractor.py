"""
Stage 4: Agentic 提取与动态写入 (v4.0 - 真正的 Tool Calling)

职责：
- 🌟 真正的 Agentic Workflow（Tool Calling Loop）
- LLM 自己决定调用哪个 Tool
- 行业分配规则执行（规则 A/B）
- Continuous Learning Loop（搜索包底库 → 注册关键词 → 回填）

🌟 v4.0 架构：
1. 从 db_ingestion_tools.py 导入 12 个 Tools
2. 构建 Tools Registry + Schema
3. 调用 AgenticExecutor.run()
4. LLM 自己决定：
   - search_document_pages 找遗漏数据
   - register_new_keyword 注册新关键词
   - backfill_from_fallback 回填数据

🌟 Single Source of Truth: 
这是系统中唯一的提取入口，不再有旧版 Stage 4 或 Toggle 机制
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger

from nanobot.core.llm_core import llm_core
from nanobot.ingestion.agentic_executor import AgenticExecutor, build_tools_registry_from_classes


class Stage4AgenticExtractor:
    """Stage 4: Agentic 提取与动态写入 (v4.0 - Tool Calling)
    
    🌟 唯一的提取入口 - 不再有 Toggle，不再有重复逻辑
    
    v4.10 重构：
    - _build_system_prompt() - 构建系统提示
    - _build_user_message_with_context() - 使用结构化上下文构建用户消息
    - _build_user_message_fallback() - 使用候选页面构建用户消息
    """
    
    # 🌟 常量定义
    DEFAULT_EXTRACTION_TYPES = ["revenue_breakdown", "key_personnel", "financial_metrics"]
    
    @staticmethod
    def _build_tools_registry(db_client: Any = None) -> Dict[str, Any]:
        """
        构建 Tools Registry
        
        🌟 导入所有 db_ingestion_tools 并构建 Registry
        
        v4.0: 19 个完整 Tools（包括新增的 3 个）
        
        Returns:
            Dict[str, Callable]: Tool 名称 → execute 函数
        """
        from nanobot.agent.tools.db_ingestion_tools import (
            GetDBSchemaTool,
            # ❌ SmartInsertDocumentTool 已移除 - 文档在上传时已创建，不应重复创建
            UpdateDocumentStatusTool,
            UpdateDynamicAttributesTool,
            CreateReviewRecordTool,
            RegisterNewKeywordTool,
            GetKeywordStatsTool,
            InsertKeyPersonnelTool,
            InsertFinancialMetricsTool,
            InsertShareholdingTool,
            InsertRevenueBreakdownTool,  # 🆕 致命遗漏修复
            InsertEntityRelationTool,    # 🆕 知识图谱修复
            InsertMarketDataTool,        # 🆕 市场数据修复
            ExtractShareholdersFromTextTool,  # 🆕 v4.11: 專門提取股東
            InsertMentionedCompanyTool,  # 🆕 v4.12: 提及公司
            SearchDocumentPagesTool,     # 🌟 Continuous Learning
            BackfillFromFallbackTool,    # 🌟 Continuous Learning
        )
        # ❌ 移除 InsertArtifactRelationTool - Agent 无法看到 UUID，改用 entity_resolver.py 的 Regex 处理
        
        # 🌟 构建 Tools Registry
        # ❌ SmartInsertDocumentTool 已移除 - 文档在上传时已创建
        tool_classes = [
            GetDBSchemaTool,
            # SmartInsertDocumentTool,  # 文档已存在，无需创建
            UpdateDocumentStatusTool,
            UpdateDynamicAttributesTool,
            CreateReviewRecordTool,
            RegisterNewKeywordTool,
            GetKeywordStatsTool,
            InsertKeyPersonnelTool,
            InsertFinancialMetricsTool,
            InsertShareholdingTool,
            InsertRevenueBreakdownTool,  # 🆕
            InsertEntityRelationTool,    # 🆕
            InsertMarketDataTool,        # 🆕
            ExtractShareholdersFromTextTool,  # 🆕 v4.11
            InsertMentionedCompanyTool,  # 🆕 v4.12
            SearchDocumentPagesTool,     # 🌟 Continuous Learning
            BackfillFromFallbackTool,    # 🌟 Continuous Learning
        ]
        
        return build_tools_registry_from_classes(tool_classes)
    
    @classmethod
    def _build_system_prompt(
        cls,
        company_id: int,
        document_id: int,
        is_index_report: bool,
        index_theme: str,
        confirmed_doc_industry: str
    ) -> str:
        """
        🌟 v4.10: 构建 System Prompt
        
        Args:
            company_id: 公司 ID
            document_id: 文档 ID
            is_index_report: 是否为指数报告
            index_theme: 指数主题
            confirmed_doc_industry: 报告定义的行业
            
        Returns:
            str: 系统提示文本
        """
        if is_index_report:
            report_context = f"""
这是一份【指数/行业报告】(主题: {index_theme or 'Unknown'}, 行业: {confirmed_doc_industry or 'Unknown'})。
里面包含多间公司的数据，请不要预设单一母公司。
行业分配规则：规则 A - 所有成分股都应指派行业 '{confirmed_doc_industry or 'Unknown'}'
"""
        else:
            report_context = f"""
这是一份【单一公司年报】，母公司 ID 为 {company_id or '待提取'}。
行业分配规则：规则 B - 使用 AI 提取各公司行业
"""
        
        system_prompt = f"""
你是一个高级 PostgreSQL 数据库写入 Agent。
任务目标：分析 PDF 内容，智能提取并写入对应的数据表。

{report_context}

📌 可用的 Tools（你可以自由调用）：
1. get_db_schema - 查看数据库结构（🌟 第一步必须调用！）
2. insert_financial_metrics - 写入财务指标（利润、资产）
3. insert_key_personnel - 写入关键人员（董事、高管）
4. insert_shareholding - 写入股东结构（持股比例）
5. insert_revenue_breakdown - 写入收入分解 🌟 新增！（按地区/业务划分）
6. insert_entity_relation - 写入实体关系 🌟 新增！（知识图谱）
7. insert_market_data - 写入市场数据 🌟 新增！（PE、市值、股价）
8. insert_mentioned_company - 写入提及的其他公司 🆕 v4.12！（子公司、对手、合作伙伴）
9. register_new_keyword - 注册新关键词（发现特殊标题时使用）
10. search_document_pages - 搜索包底库找遗漏数据（🌟 关键！）
11. backfill_from_fallback - 回填数据到结构化表
12. update_dynamic_attributes - 更新 JSONB 动态属性（🌟 新字段用这个！）
13. update_document_status - 更新文档状态
14. create_review_record - 创建审核记录（不确定时使用）
15. insert_artifact_relation - 写入跨模态图文关联 🌟 新增！（图表与文字解释）

🌟 执行流程（必须严格遵守）：

⚠️ 重要：文档记录已在上传时创建，document_id={document_id} 已存在，无需创建新文档！

Step 1: 摸清底细 (Schema Compare)
- 第一步必须调用 get_db_schema 了解数据库结构
- 查看有哪些表、有哪些 JSONB 字段

Step 2: 分析 PDF 内容
- 阅读 PDF 内容，识别数据类型
- 对比 Schema，决定写入哪些表
- ⚠️ 【重要】如果看到表格包含多年數據（如 2023、2022、2021），必須提取所有年份的數據！
  → 例如：見到「2023 | 2022」兩列，要調用兩次 insert_financial_metrics，分別 year=2023 和 year=2022
  → 見到「Revenue 40,851 (2023) vs 44,141 (2022)」，要同時寫入兩個年度

Step 3: 动态写入 🌟 关键！（选择正确的 Tool）

========================================
🌟 【动态写入指引 (Tool Usage Guide)】
========================================

⚠️ 多公司数据处理规则 (非常重要！Method A)：

如果数据属于当前 PDF 的「母公司」：
   → 请传入 company_id 参数

如果你发现数据属于「子公司」、「联营公司」、「合资企业」或「竞争对手」：
   → 【不要】填写 company_id
   → 将该公司的名称填入 `company_name` 参数！
   → 系统会自动为 `company_name` 寻找或建立正确的数据库 ID
   
例如：如果母公司是「长和」，但你发现了「腾讯」的利润数据：
   ❌ 错误：company_id=1 (长和的 ID)，但数据是腾讯的
   ✅ 正确：company_name="腾讯"，系统会自动查找或创建腾讯的 ID

⚠️ 选择正确的 Tool 是关键！不同数据用不同 Tool：
1️⃣ 财务指标（利润、资产、负债）
   → 使用 insert_financial_metrics
   → 例如：净利润 123亿、总资产 500亿

2️⃣ 收入分解（按地区/业务/产品划分）🆕
   → 使用 insert_revenue_breakdown
   → 例如：「香港 25%、欧洲 30%、北美 45%」
   → ⚠️ 千万不要用 financial_metrics！

3️⃣ 关键人员（董事、高管）
   → 使用 insert_key_personnel
   → 例如：CEO 张三、独立董事 李四

4️⃣ 股东持股比例
   → 使用 insert_shareholding
   → 例如：第一大股东持股 15.2%

5️⃣ 市场数据（PE ratio、市值、股价）🆕
   → 使用 insert_market_data
   → 例如：市盈率 15倍、市值 500亿

6️⃣ 实体关系（人物-公司关系）🆕
   → 使用 insert_entity_relation
   → 例如：「张三是腾讯CEO」、「A公司收购B公司」

7️⃣ 提及的其他公司（子公司、竞争对手、合作伙伴）🆕 v4.12
   → 使用 insert_mentioned_company
   → 例子：「本集团下辖子公司 ABC Limited」、「我们的竞争对手 XYZ Corp」
   → relation_type 可选: subsidiary, competitor, partner, investor, customer, mentioned

8️⃣ 自定义字段（Schema 没有的）🆕
   → 使用 update_dynamic_attributes
   → 例如：环保评分、ESG 指标、特殊披露
   → 存入 JSONB，无需 ALTER TABLE

9️⃣ 发现图表与文字解释的关联 🆕
   → 使用 insert_artifact_relation
   → 必须提供图表的 artifact_id (source) 和文字段落的 artifact_id (target)
   → 例如：「第 50 页的文字在解释第 5 页的图表」

========================================

- 见到财务数字（利润、资产、负债） → insert_financial_metrics
- 见到高管/董事名单 → insert_key_personnel
- 见到股东持股比例 → insert_shareholding
- 见到按地区/业务划分的收入 → insert_revenue_breakdown 🌟 新增！
- 见到市场数据（PE ratio、市值、股价） → insert_market_data 🌟 新增！
- 见到人物-公司关系（张三是腾讯CEO） → insert_entity_relation
- 发现图表与文字解释的关联 ➔ 使用 insert_artifact_relation 🌟 新增！
- 见到新名词/新标题（如「按地区划分之收益」）→
  ① register_new_keyword 注册
  ② update_dynamic_attributes 写入 JSONB

Step 4: Continuous Learning Loop
- 如果结构化表找不到数据 → search_document_pages 搜索包底库
- 找到后 → backfill_from_fallback 回填

Step 5: 完成
- update_document_status 标记完成

⚠️ 重要：
- 不要返回大 JSON，而是**逐一调用 Tools**
- 发现新字段时，先注册关键词，再写入 JSONB
- 不确定时，创建审核记录
- 选择正确的 Tool！（revenue_breakdown ≠ financial_metrics）
- 🌟 使用 company_name 而不是猜测 ID！（Method A）

开始执行！
"""
        return system_prompt
    
    @classmethod
    def _build_user_message_with_context(
        cls,
        artifacts: List[Dict[str, Any]],
        company_id: int,
        year: int,
        document_id: int,
        context_result: Dict[str, Any]
    ) -> str:
        """
        🌟 v4.10: 使用结构化上下文构建用户消息
        
        Args:
            artifacts: Artifacts 列表
            company_id: 公司 ID
            year: 年份
            document_id: 文档 ID
            context_result: Stage 3.5 结构化上下文
            
        Returns:
            str: 用户消息文本
        """
        from nanobot.ingestion.stages.stage3_5_context_builder import Stage3_5_ContextBuilder
        from nanobot.ingestion.utils.content_builder import build_tables_content, build_texts_content
        
        # 格式化上下文
        context_text = Stage3_5_ContextBuilder.format_context_for_llm(context_result)
        
        # 提取按類型分組的內容
        content_by_type = context_result.get("content_by_type", {})
        
        # 構建結構化提示
        user_message = f"""
請分析以下 PDF 內容，提取數據並寫入數據庫：

{context_text}

## 📄 詳細內容（按數據類型分組）

"""
        
        # 添加每個類型的表格信息
        for data_type, type_data in content_by_type.items():
            tables = type_data.get("tables", [])
            texts = type_data.get("texts", [])
            
            if tables:
                user_message += f"\n### {data_type.upper()} 表格\n\n"
                # 🌟 放寬到 8 個表格，每個表格 3000 字符
                for i, tbl in enumerate(tables[:8]):
                    user_message += f"**Table {i+1} @ Page {tbl['page_num']} - Section: {tbl.get('section_title', 'N/A')}**\n\n"
                    user_message += tbl.get("md", "")[:3000]
                    user_message += "\n\n"
            
            # 🌟 新增：針對 key_personnel 和 shareholding 強制注入文字段落
            if data_type in ["key_personnel", "shareholding"]:
                if texts:
                    user_message += f"\n### {data_type.upper()} 相關文字段落 🆕\n\n"
                    user_message += "⚠️ 以下係純文字內容，可能包含董事名單、股東信息等。請仔細閱讀並提取！\n\n"
                    for i, txt in enumerate(texts[:5]):
                        user_message += f"**Text {i+1} @ Page {txt.get('page_num', 'N/A')}**\n"
                        user_message += txt.get("content", "")[:2000]
                        user_message += "\n\n"
        
        user_message += f"""
公司 ID: {company_id}
主要年份: {year}
文檔 ID: {document_id}

⚠️ **【關鍵】提取所有年份的數據！**
- 這個 PDF 的【主要年份】是 {year}
- 但請提取文檔中【所有年份】的數據！(2023, 2022, 2021, 2020, 2019...)
- 如果見到「Revenue 40,851 (2023) vs 44,141 (2022)」，要分别insert 2023 和 2022 的數據
- 如果見到「Five-year summary 2019-2023」，要全部提取 2019, 2020, 2021, 2022, 2023 的數據
- 絕對不要只insert {year}一年！有幾年就insert 幾年！

🌟 **重要執行規則 (嚴格遵守)：**

1. **雙軌提取策略 (Table + Text)**：
   - 數據可能在【表格】中，也可能在【純文字段落】中。
   - 如果在表格中找到：直接調用 `insert_*` 系列 Tool。
   - 如果在表格中找不到 Key Personnel 或 Shareholder：你【必須】調用 `ExtractShareholdersFromTextTool` 或閱讀純文字內容進行提取！絕對不能直接放棄！

2. **必須完成的強制清單 (Checklist)**：
   在你宣佈任務完成之前，請檢查是否已經嘗試提取以下 7 類數據。如果某項沒有找到，請明確創建 Review Record 說明原因：
   [ ] 財務指標 (insert_financial_metrics)
   [ ] 收入分解 (insert_revenue_breakdown)
   [ ] 關鍵人員 (insert_key_personnel) - 💡 提示：常出現在「董事及高級管理層」文字段落中
   [ ] 股東結構 (insert_shareholding 或 ExtractShareholdersFromTextTool)
   [ ] 市場數據 (insert_market_data)
   [ ] 提及的其他公司 (insert_mentioned_company) - 💡 **主動狩獵模式**：子公司和聯營公司通常在文件較後方（可能在第 100+ 頁的「附註」中）。如果你在目前的文本中找不到，【必須】呼叫 `search_document_pages` 工具，搜尋關鍵字如 "subsidiary", "joint venture", "associate", "附屬公司", "聯營公司", "子公司"，然後再提取！
   [ ] **重大事件 (insert_entity_relation)** - 💡 **必須提取！** 請特別注意以下關鍵字：
       - 收購/併購 (acquisition/merger)：例如「本公司已完成收購 ABC」
       - 派息 (dividend)：例如「宣派末期股息每股 5 元」
       - 分拆/重組 (spin-off/restructuring)：例如「本公司將分拆 XYZ 業務」
       - 合營/聯營 (joint venture/associate)：例如「與 ABC 合營 XYZ」
       - 法律訴訟 (litigation)：例如「本公司涉及與 XYZ 的訴訟」
       - 監管/調查 (regulatory/investigation)：例如「遭監管機構罰款」
       - 減值/撇銷 (impairment/write-off)：例如「就 XYZ 資產減值」
       - 回購/集資 (buyback/capital raising)：例如「股份回購計劃」

3. **不要重複搜索**，請善用上面已經提供的上下文內容。

## 📝 文本段落 - 用於提取實體關係 (Entity Relations) 及關鍵人員

以下係純文本內容，請從中提取【公司併購】、【人事任命】、【股東關係】、【董事名單】等：

{context_result.get("text_content", "")[:5000]}

⚠️ 如果你只搜索而不插入數據，任務將失敗！

請開始執行！
"""
        return user_message
    
    @classmethod
    def _build_user_message_fallback(
        cls,
        artifacts: List[Dict[str, Any]],
        company_id: int,
        year: int,
        document_id: int,
        stage3_result: Dict[str, Any] = None
    ) -> str:
        """
        🌟 v4.10: 使用候选页面构建用户消息（Fallback 模式）
        
        Args:
            artifacts: Artifacts 列表
            company_id: 公司 ID
            year: 年份
            document_id: 文档 ID
            stage3_result: Stage 3 路由结果
            
        Returns:
            str: 用户消息文本
        """
        from nanobot.ingestion.utils.content_builder import build_candidate_pages_content, format_routing_hint
        
        candidate_pages = {}
        
        if stage3_result:
            # 从 Stage 3 结果中提取候选页面
            for data_type, pages in stage3_result.items():
                if isinstance(pages, list) and pages:
                    candidate_pages[data_type] = pages
                    logger.info(f"   📍 Stage 3 路由结果: {data_type} -> {len(pages)} 个候选页面")
        
        # 构建内容
        if candidate_pages:
            logger.info(f"   🎯 使用 Stage 3 候选页面构建内容...")
            
            content_text, routing_hint = build_candidate_pages_content(
                artifacts, 
                candidate_pages,
                max_pages=50,
                max_chars_per_page=5000
            )
            
            user_message = f"""
请分析以下 PDF 内容，提取数据并写入数据库：

📌 Stage 3 路由提示（重点页面）：
{routing_hint}

PDF 内容（候选页面）：
{content_text}

公司 ID: {company_id}
主要年份: {year}
文档 ID: {document_id}

⚠️ **【關鍵】提取所有年份的數據！**
- 這個 PDF 的【主要年份】是 {year}
- 但請提取文檔中【所有年份】的數據！(2023, 2022, 2021, 2020, 2019...)
- 如果見到「Revenue 40,851 (2023) vs 44,141 (2022)」，要分别insert 2023 和 2022 的數據
- 如果見到「Five-year summary 2019-2023」，要全部提取 2019, 2020, 2021, 2022, 2023 的數據
- 絕對不要只insert {year}一年！有幾年就insert 幾年！

🌟 重要提示：
1. 上面的内容是根据 Stage 3 路由结果筛选的候选页面
2. 请重点关注这些页面中的表格数据
3. 使用正确的 Tool 写入数据：
   - revenue_breakdown（收入分解）→ insert_revenue_breakdown
   - financial_metrics（财务指标）→ insert_financial_metrics
   - key_personnel（关键人员）→ insert_key_personnel
   - shareholding（股东结构）→ insert_shareholding
   - market_data（市场数据）→ insert_market_data

⚠️ 必须调用所有相关 Tool！不要遗漏任何数据类型！

请开始执行！
"""
        else:
            # Fallback 到前 20 页
            logger.info(f"   ⚠️ 没有 Stage 3 路由结果，使用前 20 页...")
            
            from nanobot.ingestion.utils.content_builder import build_content_by_pages
            content_text = build_content_by_pages(
                artifacts,
                start_page=1,
                end_page=20,
                max_chars=50000
            )
            
            user_message = f"""
请分析以下 PDF 内容，提取数据并写入数据库：

PDF 内容：
{content_text}

公司 ID: {company_id}
年份: {year}
文档 ID: {document_id}

请开始执行！
"""
        
        return user_message
    
    @staticmethod
    async def run_agentic_write(
        artifacts: List[Dict[str, Any]],
        company_id: int,
        year: int,
        doc_id: str,
        document_id: int,
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None,
        db_client: Any = None,
        extraction_types: List[str] = None,
        progress_callback: Any = None,
        stage3_result: Dict[str, Any] = None,  # 🌟 v4.8: Stage 3 路由结果
        context_result: Dict[str, Any] = None  # 🌟 v4.10: Stage 3.5 結構化上下文
    ) -> Dict[str, Any]:
        """
        🌟 Agentic 多表写入（v4.10 - 使用結構化上下文）
        
        根据文档类型使用不同的写入策略：
        - 指数报告（规则 A）：所有成分股指派同一行业
        - 年报（规则 B）：AI 提取各公司行业
        
        🌟 v4.10 新特性：
        - 使用 Stage 3.5 的結構化上下文（章節樹、表格上下文）
        - Agent 不再需要同時做「理解文檔」和「提取數據」
        - 表格帶有所屬章節、附近文本等上下文信息
        
        Args:
            artifacts: Artifacts 列表
            company_id: 公司 ID
            year: 年份
            doc_id: 文档 ID
            document_id: 文档内部 ID
            is_index_report: 是否为指数报告
            index_theme: 指数主题
            confirmed_doc_industry: 报告定义的行业
            db_client: DB 客户端
            extraction_types: 提取类型
            progress_callback: 进度回调
            stage3_result: Stage 3 路由结果（包含候选页面）
            context_result: Stage 3.5 結構化上下文（章節樹、表格上下文）
            
        Returns:
            Dict: 写入结果
        """
        extraction_types = extraction_types or ["revenue_breakdown", "key_personnel", "financial_metrics"]
        
        logger.info(f"🎯 Stage 4: Agentic 写入（v4.0 Tool Calling）...")
        
        # 🌟 构建 Tools Registry
        tools_registry = Stage4AgenticExtractor._build_tools_registry(db_client)
        
        # 🌟 v4.10: 使用拆分的辅助方法构建 Prompt
        system_prompt = Stage4AgenticExtractor._build_system_prompt(
            company_id=company_id,
            document_id=document_id,
            is_index_report=is_index_report,
            index_theme=index_theme,
            confirmed_doc_industry=confirmed_doc_industry
        )
        
        if context_result:
            logger.info(f"   🏗️ 使用 Stage 3.5 結構化上下文...")
            user_message = cls._build_user_message_with_context(
                artifacts=artifacts,
                company_id=company_id,
                year=year,
                document_id=document_id,
                context_result=context_result
            )
        else:
            logger.info(f"   ⚠️ 没有 Stage 3.5 上下文，使用候选页面...")
            user_message = cls._build_user_message_fallback(
                artifacts=artifacts,
                company_id=company_id,
                year=year,
                document_id=document_id,
                stage3_result=stage3_result
            )
        
        # 🌟 创建 AgenticExecutor
        executor = AgenticExecutor(
            tools_registry=tools_registry,
            max_iterations=40,  # 🌟 v4.11: 增加到 40 以支持更多 Tool 调用
            model=llm_core.default_model
        )
        
        # 🌟 执行 Agentic Workflow
        if progress_callback:
            progress_callback(85.0, "Stage 5: Agentic Tool Calling")
        
        result = await executor.run(
            system_prompt=system_prompt,
            user_message=user_message,
            context={
                "company_id": company_id,
                "year": year,
                "document_id": document_id,
                "is_index_report": is_index_report,
                "confirmed_doc_industry": confirmed_doc_industry,
                "db_client": db_client,  # 🌟 v4.3: 修復 - 必須傳入 db_client
            },
            on_tool_call=lambda name, args: logger.info(f"   📞 Tool Call: {name}")
        )
        
        logger.info(f"✅ Stage 5 完成: iterations={result['iterations']}, tool_calls={len(result['tool_calls'])}")
        
        # 🌟 解析结果
        return {
            "status": "success",
            "content": result["content"],
            "tool_calls": result["tool_calls"],
            "iterations": result["iterations"],
            "is_index_report": is_index_report,
            "industry_rule": "A" if is_index_report else "B"
        }
    
    @staticmethod
    async def run_simple_extraction(
        artifacts: List[Dict[str, Any]],
        company_id: int,
        year: int,
        document_id: int,
        db_client: Any = None,
        extraction_type: str = "revenue_breakdown"
    ) -> Dict[str, Any]:
        """
        🌟 简单提取模式（不使用 Tool Calling，直接写入）
        
        用于简单的单一提取任务
        
        Args:
            artifacts: Artifacts 列表
            company_id: 公司 ID
            year: 年份
            document_id: 文档 ID
            db_client: DB 客户端
            extraction_type: 提取类型
            
        Returns:
            Dict: 提取结果
        """
        logger.info(f"🎯 Stage 5 (Simple): {extraction_type} 提取...")
        
        # 🌟 构建提取 Prompt
        extraction_prompts = {
            "revenue_breakdown": """
提取收入分解数据，返回 JSON 格式：
```json
{
  "segments": [
    {"segment_name": "Europe", "segment_type": "geography", "percentage": 25.0, "amount": 1234567}
  ]
}
```
""",
            "key_personnel": """
提取关键人员数据，返回 JSON 格式：
```json
{
  "personnel": [
    {"name_en": "John Doe", "position": "CEO", "board_role": "Executive Director"}
  ]
}
```
""",
            "financial_metrics": """
提取财务指标，返回 JSON 格式：
```json
{
  "metrics": [
    {"metric_name": "Revenue", "value": 1234567, "unit": "HKD"}
  ]
}
```
"""
        }
        
        prompt = extraction_prompts.get(extraction_type, "提取所有财务数据")
        
        # 🌟 合并内容
        content_text = "\n\n".join([
            a.get("content", "") or ""
            for a in artifacts[:10]
        ])
        
        # 🌟 调用 LLM
        messages = [
            {"role": "user", "content": prompt + "\n\nPDF 内容:\n" + content_text[:5000]}
        ]
        
        response = await llm_core.chat(messages=messages)
        
        # 🌟 解析并写入
        extracted_data = {}
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                extracted_data = json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"   ⚠️ JSON 解析失败: {e}")
        
        # 🌟 写入数据库
        inserted_count = 0
        
        if db_client and extracted_data:
            try:
                if extraction_type == "revenue_breakdown":
                    for seg in extracted_data.get("segments", []):
                        await db_client.insert_revenue_breakdown(
                            company_id=company_id,
                            year=year,
                            segment_name=seg.get("segment_name"),
                            segment_type=seg.get("segment_type"),
                            revenue_percentage=seg.get("percentage"),
                            revenue_amount=seg.get("amount"),
                            source_document_id=document_id
                        )
                        inserted_count += 1
                        
                elif extraction_type == "key_personnel":
                    for person in extracted_data.get("personnel", []):
                        await db_client.insert_key_personnel(
                            company_id=company_id,
                            year=year,
                            name_en=person.get("name_en"),
                            position_title_en=person.get("position"),
                            board_role=person.get("board_role"),
                            source_document_id=document_id
                        )
                        inserted_count += 1
                        
                elif extraction_type == "financial_metrics":
                    for metric in extracted_data.get("metrics", []):
                        await db_client.insert_financial_metric(
                            company_id=company_id,
                            year=year,
                            metric_name=metric.get("metric_name"),
                            value=metric.get("value"),
                            unit=metric.get("unit", "HKD"),
                            source_document_id=document_id
                        )
                        inserted_count += 1
                        
            except Exception as e:
                logger.warning(f"   ⚠️ 写入失败: {e}")
        
        logger.info(f"✅ Stage 5 (Simple) 完成: inserted={inserted_count}")
        
        return {
            "status": "success",
            "extraction_type": extraction_type,
            "inserted_count": inserted_count,
            "extracted_data": extracted_data
        }
    
    @staticmethod
    async def trigger_vanna_training(
        doc_id: str,
        db_client: Any = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        🌟 触发 Vanna 训练
        
        Args:
            doc_id: 文档 ID
            db_client: DB 客户端
            max_retries: 最大重试次数
            
        Returns:
            Dict: 训练结果
        """
        try:
            vanna_url = os.environ.get("VANNA_URL", "http://vanna-service:8000")
            
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                for attempt in range(max_retries):
                    try:
                        response = await client.post(
                            f"{vanna_url}/train",
                            json={"doc_id": doc_id}
                        )
                        
                        if response.status_code == 200:
                            logger.info(f"   ✅ Vanna 训练触发成功: {doc_id}")
                            return {"status": "success", "doc_id": doc_id}
                        else:
                            logger.warning(f"   ⚠️ Vanna 训练触发失败 (attempt {attempt + 1}): {response.status_code}")
                            await asyncio.sleep(2)
                    except Exception as e:
                        logger.warning(f"   ⚠️ Vanna 训练触发失败 (attempt {attempt + 1}): {e}")
                        await asyncio.sleep(2)
            
            return {"status": "failed", "doc_id": doc_id, "error": "max_retries_exceeded"}
            
        except Exception as e:
            logger.warning(f"   ⚠️ Vanna 训练触发失败: {e}")
            return {"status": "failed", "doc_id": doc_id, "error": str(e)}