"""
Stage 5: Agentic 写入与行业分配 (v4.0 - 真正的 Tool Calling)

职责：
- 🌟 真正的 Agentic Workflow（Tool Calling Loop）
- LLM 自己决定调用哪个 Tool
- 行业分配规则执行（规则 A/B）
- Continuous Learning Loop（搜索包底库 → 注册关键词 → 回填）

🌟 v4.0 架构：
1. 从 db_ingestion_tools.py 导入 16 个 Tools
2. 构建 Tools Registry + Schema
3. 调用 AgenticExecutor.run()
4. LLM 自己决定：
   - search_document_pages 找遗漏数据
   - register_new_keyword 注册新关键词
   - backfill_from_fallback 回填数据
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


class Stage5AgenticWriter:
    """Stage 5: Agentic 写入与行业分配 (v4.0 - 真正的 Tool Calling)"""
    
    @staticmethod
    def _build_tools_registry(db_client: Any = None) -> Dict[str, Any]:
        """
        构建 Tools Registry
        
        🌟 导入所有 db_ingestion_tools 并构建 Registry
        
        Returns:
            Dict[str, Callable]: Tool 名称 → execute 函数
        """
        from nanobot.agent.tools.db_ingestion_tools import (
            GetDBSchemaTool,
            SmartInsertDocumentTool,
            UpdateDocumentStatusTool,
            UpdateDynamicAttributesTool,
            CreateReviewRecordTool,
            RegisterNewKeywordTool,
            GetKeywordStatsTool,
            InsertKeyPersonnelTool,
            InsertFinancialMetricsTool,
            InsertShareholdingTool,
            SearchDocumentPagesTool,
            BackfillFromFallbackTool,
        )
        
        # 🌟 构建 Tools Registry
        tool_classes = [
            GetDBSchemaTool,
            SmartInsertDocumentTool,
            UpdateDocumentStatusTool,
            UpdateDynamicAttributesTool,
            CreateReviewRecordTool,
            RegisterNewKeywordTool,
            GetKeywordStatsTool,
            InsertKeyPersonnelTool,
            InsertFinancialMetricsTool,
            InsertShareholdingTool,
            SearchDocumentPagesTool,  # 🌟 Continuous Learning
            BackfillFromFallbackTool,  # 🌟 Continuous Learning
        ]
        
        return build_tools_registry_from_classes(tool_classes)
    
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
        progress_callback: Any = None
    ) -> Dict[str, Any]:
        """
        🌟 Agentic 多表写入（v4.0 - 真正的 Tool Calling）
        
        根据文档类型使用不同的写入策略：
        - 指数报告（规则 A）：所有成分股指派同一行业
        - 年报（规则 B）：AI 提取各公司行业
        
        🌟 新特性：
        - LLM 自己决定调用哪个 Tool
        - 支持 Continuous Learning Loop
        - 自动搜索包底库找遗漏数据
        
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
            
        Returns:
            Dict: 写入结果
        """
        extraction_types = extraction_types or ["revenue_breakdown", "key_personnel", "financial_metrics"]
        
        logger.info(f"🎯 Stage 5: Agentic 写入（v4.0 Tool Calling）...")
        
        # 🌟 构建 Tools Registry
        tools_registry = Stage5AgenticWriter._build_tools_registry(db_client)
        
        # 🌟 构建 System Prompt
        if is_index_report:
            report_context = f"""
这是一份【指数/行业报告】(主题: {index_theme or 'Unknown'}, 行业: {confirmed_doc_industry or 'Unknown'})。
里面包含多间公司的数据，请不要预设单一母公司。
行业分配规则：规则 A - 所有成分股都应指派行业 '{confirmed_doc_industry or 'Unknown'}'
"""
        else:
            report_context = f"""
这是一份【单一公司年报】，母公司 ID 为 {company_id or '待提取'}。
行业分配规则：规则 B - 使用 AI 提取各公司的行业
"""
        
        system_prompt = f"""
你是一个高级 PostgreSQL 数据库写入 Agent。
任务目标：分析 PDF 内容，智能提取并写入对应的数据表。

{report_context}

📌 可用的 Tools（你可以自由调用）：
1. get_db_schema - 查看数据库结构
2. smart_insert_document - 智能写入文档（支持规则 A/B）
3. insert_financial_metrics - 写入财务指标
4. insert_key_personnel - 写入关键人员
5. insert_shareholding - 写入股东结构
6. register_new_keyword - 注册新关键词（发现特殊标题时使用）
7. search_document_pages - 搜索包底库找遗漏数据（🌟 关键！）
8. backfill_from_fallback - 回填数据到结构化表
9. update_document_status - 更新文档状态
10. create_review_record - 创建审核记录（不确定时使用）

🌟 Continuous Learning Loop：
如果在结构化表找不到数据，请：
① 调用 search_document_pages 搜索包底库
② 发现新标题 → register_new_keyword 注册
③ 找到数据 → backfill_from_fallback 回填

执行步骤：
1. 先调用 get_db_schema 了解数据库结构
2. 分析 PDF 内容，决定写入哪些表
3. 调用对应的 insert_* Tools
4. 如果找不到数据，搜索包底库并回填
5. 完成后调用 update_document_status 标记完成
"""
        
        # 🌟 合并 artifacts 内容作为用户消息
        content_text = "\n\n".join([
            a.get("content", "") or a.get("markdown", "") or ""
            for a in artifacts[:20]  # 限制内容长度
        ])
        
        user_message = f"""
请分析以下 PDF 内容，提取数据并写入数据库：

PDF 内容（前 20 页）：
{content_text[:10000]}

公司 ID: {company_id}
年份: {year}
文档 ID: {document_id}

请开始执行！
"""
        
        # 🌟 创建 AgenticExecutor
        executor = AgenticExecutor(
            tools_registry=tools_registry,
            max_iterations=15,
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
                "confirmed_doc_industry": confirmed_doc_industry
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