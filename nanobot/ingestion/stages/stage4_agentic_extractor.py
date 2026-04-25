"""
Stage 4: Agentic 提取与动态写入 (v4.0 - 真正的 Tool Calling)

职责：
- 真正的 Agentic Workflow（Tool Calling Loop）
- LLM 自己决定调用哪个 Tool
- 行业分配规则执行（规则 A/B）
- Continuous Learning Loop（搜索 → 回填）

架构：
1. 从 db_ingestion_tools.py 导入 Tools
2. 构建 Tools Registry + Schema
3. 调用 AgenticExecutor.run()
4. LLM 自己决定：
   - search_document_pages 找遗漏数据
   - backfill_from_fallback 回填数据

Single Source of Truth: 
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
        # Import Apache AGE Tools
        from nanobot.agent.tools.apache_age_tools import (
            InsertGraphNodeTool,
            InsertGraphEdgeTool,
            QueryGraphTool,
            SyncToGraphTool,
        )
        
        from nanobot.agent.tools.db_ingestion_tools import (
            GetDBSchemaTool,
            UpdateDynamicAttributesTool,
            CreateReviewRecordTool,
            InsertKeyPersonnelTool,
            InsertFinancialMetricsTool,
            InsertShareholdingTool,
            InsertRevenueBreakdownTool,
            InsertEntityRelationTool,
            InsertMarketDataTool,
            ExtractShareholdersFromTextTool,
            InsertMentionedCompanyTool,
            SearchDocumentPagesTool,
            BackfillFromFallbackTool,
        )
        # 已移除 RegisterNewKeywordTool, GetKeywordStatsTool - 改為純 Agentic 指令模式
        # 移除 InsertArtifactRelationTool - Agent 无法看到 UUID
        
        # 构建 Tools Registry
        tool_classes = [
            GetDBSchemaTool,
            UpdateDynamicAttributesTool,
            CreateReviewRecordTool,
            InsertKeyPersonnelTool,
            InsertFinancialMetricsTool,
            InsertShareholdingTool,
            InsertRevenueBreakdownTool,
            InsertEntityRelationTool,
            InsertMarketDataTool,
            ExtractShareholdersFromTextTool,
            InsertMentionedCompanyTool,
            SearchDocumentPagesTool,
            BackfillFromFallbackTool,
            # Apache AGE Graph Tools
            InsertGraphNodeTool,
            InsertGraphEdgeTool,
            QueryGraphTool,
            SyncToGraphTool,
        ]
        
        return build_tools_registry_from_classes(tool_classes)
    
    @classmethod
    def _build_system_prompt(
        cls,
        company_id: int,
        document_id: int,
        is_index_report: bool,
        index_theme: str,
        confirmed_doc_industry: str,
        year: int = 2025
    ) -> str:
        """
        🌟 v4.16: 使用 Policy Classes 構建 System Prompt
        
        將龐大的 System Prompt 拆分為獨立的 Policy 類
        
        Args:
            company_id: 公司 ID
            document_id: 文档 ID
            is_index_report: 是否为指数报告
            index_theme: 指数主题
            confirmed_doc_industry: 报告定义的行业
            year: 主要年份
            
        Returns:
            str: 系统提示文本
        """
        # 🌟 v4.16: 使用 Policy Registry
        from nanobot.ingestion.stages.stage4_policies import PolicyRegistry
        
        policies = PolicyRegistry.for_stage4(
            is_index_report=is_index_report,
            index_theme=index_theme,
            confirmed_doc_industry=confirmed_doc_industry,
            parent_company_id=company_id,
            primary_year=year
        )
        
        # 工具列表（Policy 類不包含這個）
        tools_section = f"""
可用的 Tools（你可以自由调用）：
1. get_db_schema - 查看数据库结构（第一步必须调用！）
2. insert_financial_metrics - 写入财务指标（利润、资产）
3. insert_key_personnel - 写入关键人员（董事、高管）
4. insert_shareholding - 写入股东结构（持股比例）
5. insert_revenue_breakdown - 写入收入分解（按地区/业务划分）
6. insert_entity_relation - 写入实体关系（公司对公司的关系）
7. insert_market_data - 写入市场数据（PE、市值、股价）
8. insert_mentioned_company - 写入提及的其他公司
9. register_new_keyword - 注册新关键词
10. search_document_pages - 搜索包底库找遗漏数据
11. backfill_from_fallback - 回填数据到结构化表
12. update_dynamic_attributes - 更新 JSONB 动态属性
13. create_review_record - 创建审核记录

Apache AGE Graph Tools (知识图谱)：
14. insert_graph_node - 在知识图谱中创建节点（Company、Person等）
15. insert_graph_edge - 在知识图谱中创建关系（SUBSIDIARY_OF、INVESTED_IN等）
16. query_graph - 用Cypher查询知识图谱
17. sync_to_graph - 将现有的公司关系和董事数据同步到图谱

重要：文档记录已在上传时创建，document_id={document_id} 已存在，无需创建新文档！
"""
        
        # 🌟 拼接所有 Policy
        policies_section = policies.build()
        
        # 🌟 執行流程（簡化版）
        execution_flow = """
執行流程：

Step 1: 摸清底细
   - 調用 get_db_schema 了解數據庫結構

Step 2: 分析 PDF 内容
   - 識別數據類型
   - 對比 Schema，決定寫入哪些表

Step 3: 動態寫入
   - 根據數據類型選擇正確的 Tool
   - 嚴格遵守本提示中的規則

Step 4: 持續學習
   - 如果找不到數據 → search_document_pages
   - 找到後 → backfill_from_fallback

Step 5: 完成
   - update_document_status 標記完成

重要：
- 不要返回大 JSON，而是**逐一調用 Tools**
- 不確定時，創建審核記錄
"""
        
        return f"""
你是一個高級 PostgreSQL 數據庫寫入 Agent。
任務目標：分析 PDF 內容，智能提取並寫入對應的數據表。

{policies_section}

{tools_section}

{execution_flow}

開始執行！
"""
    
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

重要：提取【所有年份】的數據，絕對不能只提取部分年份！
- 這個 PDF 的主要年份是 {year}，但这只是参考，不要限制自己！
- ❌ 禁止只插入 2023 和 2022 兩年！
- ✅ 必須提取文檔中【每一個】年份的數據！(2019, 2020, 2021, 2022, 2023, 2024... 所有見到的年都要！)
- 如果見到「Revenue 40,851 (2023) vs 44,141 (2022)」→ 要【同時】insert 2023 和 2022 的數據
- 如果見到「Five-year summary 2019-2023」→ 要【全部】提取 2019, 2020, 2021, 2022, 2023
- 如果見到「Ten-year summary 2014-2023」→ 要【全部】提取 2014 到 2023 的每一年！

【關鍵原則】有幾年就 insert 幾年，不要選擇性忽略任何年份！

重要執行規則：

1. **雙軌提取策略 (Table + Text)**：
   - 數據可能在【表格】中，也可能在【純文字段落】中。
   - 如果在表格中找到：直接調用 insert_* 系列 Tool。
   - 如果在表格中找不到 Key Personnel 或 Shareholder：必須調用 ExtractShareholdersFromTextTool 或閱讀純文字內容！

2. **必須完成的強制清單**：
   [ ] 財務指標 (insert_financial_metrics)
   [ ] 收入分解 (insert_revenue_breakdown)
   [ ] 關鍵人員 (insert_key_personnel) - 常出現在「董事及高級管理層」文字段落中
   [ ] 股東結構 (insert_shareholding 或 ExtractShareholdersFromTextTool)
   [ ] 市場數據 (insert_market_data)
   [ ] 提及的其他公司 (insert_mentioned_company) - 主動狩獵模式
   [ ] **重大事件 (insert_entity_relation)** - 必須提取！

3. **公司關係識別關鍵字 patterns**：

   子公司/附屬公司：
   - "本公司的附屬公司"、"附屬公司包括"、"our subsidiaries"
   - "held directly/indirectly"、"owned as to"
   
   收購/併購：
   - "已完成收購"、"acquired"、"merger"、"併購"
   - "收購代價"、"收購事項"
   
   合作夥伴/合營：
   - "與...合營"、"joint venture"、"合營企業"
   - "策略聯盟"、"strategic partnership"
   
   投資/持股：
   - "持有...%權益"、"own stake"、"invested in"
   - "持股量"、"shareholding"

   主席/董事變動：
   - "欣然宣布"、"獲委任為"、"辭任"
   - "appointment"、"resignation"、"新任主席"

4. **寫入知識圖譜 (Apache AGE)**：

   除了 insert_entity_relation，你還可以：
   
   a) 使用 insert_graph_node 創建圖譜節點：
      - insert_graph_node(label="Company", properties={{"name": "公司名稱"}})
      - insert_graph_node(label="Person", properties={{"name": "人名"}})
   
   b) 使用 insert_graph_edge 創建圖譜關係：
      - insert_graph_edge(source_label="Company", source_name="A公司", 
                          target_label="Company", target_name="B公司",
                          relation_type="SUBSIDIARY_OF")
      - insert_graph_edge(source_label="Person", source_name="李先生",
                          target_label="Company", target_name="A公司",
                          relation_type="EXECUTIVE_OF", 
                          properties={{"position": "主席"}})
   
   c) 常見關係類型：
      - SUBSIDIARY_OF（子公司）
      - INVESTED_IN（投資）
      - PARTNERED_WITH（合作）
      - EXECUTIVE_OF（高管任職）
      - DIRECTOR_OF（董事）
      - ACQUIRED_BY（被收購）
      - JOINT_VENTURE_WITH（合營）

5. **文本段落 - 用於提取實體關係**

以下係純文本內容，請從中提取公司併購、人事任命、股東關係、董事名單：

{context_result.get("text_content", "")[:5000]}

如果你只搜索而不插入數據，任務將失敗！

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

⚠️ **【關鍵】提取【所有年份】的數據，絕對不能只提取部分年份！**
- 這個 PDF 的【主要年份】是 {year}，但这只是参考，不要限制自己！
- ❌ 禁止只插入 {year} 和另一年（如 2023 和 2022）！
- ✅ 必須提取文檔中【每一個】年份的數據！(2019, 2020, 2021, 2022, 2023, 2024... 所有見到的年都要！)
- 如果見到「Revenue 40,851 (2023) vs 44,141 (2022)」→ 要【同時】insert 所有涉及的年份
- 如果見到「Five-year summary 2019-2023」→ 要【全部】提取 2019, 2020, 2021, 2022, 2023 的每一年！
- 如果見到「Ten-year summary 2014-2023」→ 要【全部】提取 2014 到 2023 的每一年！
- 絕對不要只insert {year}一年！有幾年就insert 幾年！

【關鍵原則】有幾年就 insert 幾年，不要選擇性忽略任何年份！

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
        artifacts: List[Dict[str, Any]] = None,  # 🌟 v4.12: 改為可選
        company_id: int = None,
        year: int = None,
        doc_id: str = None,
        document_id: int = None,
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None,
        db_client: Any = None,
        extraction_types: List[str] = None,
        progress_callback: Any = None,
        stage3_result: Dict[str, Any] = None,
        context_result: Dict[str, Any] = None,
        use_db_artifacts: bool = False,  # 🌟 v4.12: 從 DB 讀取 artifacts
        artifact_types: List[str] = None,  # 🌟 v4.12: 過濾 artifact 類型
        batch_size: int = 50  # 🌟 v4.12: 分批處理
    ) -> Dict[str, Any]:
        """
        🌟 Agentic 多表写入（v4.12 - 支援 DB 讀取 + 分批處理）
        
        🌟 v4.12 新特性：
        - use_db_artifacts=True: 從 DB 讀取 artifacts（解決記憶體壓力）
        - batch_size: 分批處理（解決 token 上限問題）
        - artifact_types: 過濾特定類型的 artifacts
        
        Args:
            artifacts: Artifacts 列表（如果 use_db_artifacts=True 則可選）
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
            stage3_result: Stage 3 路由结果
            context_result: Stage 3.5 結構化上下文
            use_db_artifacts: 🆕 是否從 DB 讀取 artifacts
            artifact_types: 🆕 過濾 artifact 類型（如 ["vision_analysis", "text_chunk", "table"]）
            batch_size: 🆕 每批處理的 artifact 數量
            
        Returns:
            Dict: 写入结果
        """
        extraction_types = extraction_types or ["revenue_breakdown", "key_personnel", "financial_metrics"]
        
        # 🌟 v4.12: 從 DB 讀取 artifacts（解決記憶體壓力）
        if use_db_artifacts and db_client and document_id:
            logger.info(f"🎯 Stage 4: 從 DB 讀取 artifacts (document_id={document_id})...")
            
            # 默認讀取這些類型
            if artifact_types is None:
                artifact_types = ["vision_analysis", "text_chunk", "table", "image"]
            
            # 統計總數
            total_count = await db_client.count_raw_artifacts_by_document(
                document_id=document_id,
                artifact_types=artifact_types
            )
            
            logger.info(f"   📊 DB 中有 {total_count} 個 artifacts，每批 {batch_size} 個")
            
            # 🌟 v4.12: 如果 artifacts 太多，改為分批處理
            if total_count > batch_size:
                return await Stage4AgenticExtractor._run_batch_extraction(
                    db_client=db_client,
                    document_id=document_id,
                    company_id=company_id,
                    year=year,
                    doc_id=doc_id,
                    is_index_report=is_index_report,
                    index_theme=index_theme,
                    confirmed_doc_industry=confirmed_doc_industry,
                    extraction_types=extraction_types,
                    artifact_types=artifact_types,
                    batch_size=batch_size,
                    total_count=total_count,
                    progress_callback=progress_callback
                )
            
            # 讀取所有 artifacts
            artifacts = await db_client.get_raw_artifacts_by_document(
                document_id=document_id,
                artifact_types=artifact_types,
                limit=1000
            )
            
            logger.info(f"   ✅ 從 DB 讀取了 {len(artifacts)} 個 artifacts")
        
        # 如果 artifacts 還是空的，報錯
        if not artifacts:
            logger.error("❌ 沒有 artifacts 可以處理")
            return {"status": "failed", "error": "No artifacts to process"}
        
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
            user_message = Stage4AgenticExtractor._build_user_message_with_context(
                artifacts=artifacts,
                company_id=company_id,
                year=year,
                document_id=document_id,
                context_result=context_result
            )
        else:
            logger.info(f"   ⚠️ 没有 Stage 3.5 上下文，使用候选页面...")
            user_message = Stage4AgenticExtractor._build_user_message_fallback(
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
    async def _run_batch_extraction(
        db_client: Any,
        document_id: int,
        company_id: int,
        year: int,
        doc_id: str,
        is_index_report: bool,
        index_theme: str,
        confirmed_doc_industry: str,
        extraction_types: List[str],
        artifact_types: List[str],
        batch_size: int,
        total_count: int,
        progress_callback: Any = None
    ) -> Dict[str, Any]:
        """
        🌟 v4.12: 分批處理大量 artifacts（解決 token 上限問題）
        
        當 artifacts 數量 > batch_size 時，分批處理：
        1. 每批讀取 batch_size 個 artifacts
        2. 調用 Agent 提取
        3. 合併結果
        
        Args:
            db_client: DB 客戶端
            document_id: 文檔 ID
            company_id: 公司 ID
            year: 年份
            doc_id: 文檔 ID
            is_index_report: 是否為指數報告
            index_theme: 指數主題
            confirmed_doc_industry: 行業
            extraction_types: 提取類型
            artifact_types: artifact 類型過濾
            batch_size: 每批數量
            total_count: 總數
            progress_callback: 進度回調
            
        Returns:
            Dict: 合併後的結果
        """
        import math
        
        total_batches = math.ceil(total_count / batch_size)
        logger.info(f"   🔄 分批處理: {total_count} artifacts = {total_batches} 批")
        
        all_tool_calls = []
        total_iterations = 0
        
        for batch_idx in range(total_batches):
            offset = batch_idx * batch_size
            
            # 讀取這批 artifacts
            artifacts = await db_client.get_raw_artifacts_by_document(
                document_id=document_id,
                artifact_types=artifact_types,
                limit=batch_size,
                offset=offset
            )
            
            if not artifacts:
                continue
            
            logger.info(f"   📦 Batch {batch_idx + 1}/{total_batches}: {len(artifacts)} artifacts")
            
            if progress_callback:
                progress = 60.0 + (batch_idx / total_batches) * 20.0
                progress_callback(progress, f"Stage 4: Batch {batch_idx + 1}/{total_batches}")
            
            # 🌟 構建這批的 user_message
            # 簡化版：只包含內容，不重複系統提示
            content_text = "\n\n".join([
                f"--- Page {a.get('page', '?')} ({a.get('type', '?')}) ---\n{a.get('content', '')[:2000]}"
                for a in artifacts[:20]  # 每批最多 20 個
            ])
            
            user_message = f"""
請繼續分析以下 PDF 內容（Batch {batch_idx + 1}/{total_batches}）：

{content_text}

公司 ID: {company_id}
主要年份: {year}
文檔 ID: {document_id}

⚠️ 【關鍵】必須提取【所有年份】的數據！
- ❌ 禁止只插入 {year} 和另一年！
- ✅ 必須提取文檔中【每一個】年份！(2019, 2020, 2021, 2022, 2023, 2024... 所有見到的年都要！)
- 有幾年就 insert 幾年，不要選擇性忽略任何年份！

請提取數據並寫入數據庫！
"""
            
            # 構建 tools registry
            tools_registry = Stage4AgenticExtractor._build_tools_registry(db_client)
            system_prompt = Stage4AgenticExtractor._build_system_prompt(
                company_id=company_id,
                document_id=document_id,
                is_index_report=is_index_report,
                index_theme=index_theme,
                confirmed_doc_industry=confirmed_doc_industry
            )
            
            # 執行 Agent
            executor = AgenticExecutor(
                tools_registry=tools_registry,
                max_iterations=20,  # 分批時減少迭代
                model=llm_core.default_model
            )
            
            result = await executor.run(
                system_prompt=system_prompt,
                user_message=user_message,
                context={
                    "company_id": company_id,
                    "year": year,
                    "document_id": document_id,
                    "is_index_report": is_index_report,
                    "confirmed_doc_industry": confirmed_doc_industry,
                    "db_client": db_client,
                },
                on_tool_call=lambda name, args: logger.info(f"      📞 Tool Call: {name}")
            )
            
            all_tool_calls.extend(result.get("tool_calls", []))
            total_iterations += result.get("iterations", 0)
        
        logger.info(f"✅ 分批處理完成: {total_batches} 批, {len(all_tool_calls)} tool_calls")
        
        return {
            "status": "success",
            "content": f"Processed {total_count} artifacts in {total_batches} batches",
            "tool_calls": all_tool_calls,
            "iterations": total_iterations,
            "is_index_report": is_index_report,
            "industry_rule": "A" if is_index_report else "B",
            "batches_processed": total_batches
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
