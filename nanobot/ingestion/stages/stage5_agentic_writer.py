"""
Stage 5: Agentic 写入与行业分配 (v3.2)

职责：
- Agentic 多表写入（Revenue + Personnel + Metrics）
- 行业分配规则执行（规则 A/B）
- 触发 Vanna 训练

🌟 v3.2: 使用 LlamaParse raw output

行业分配规则：
- 规则 A（is_index_report=true）：所有成分股都指派 confirmed_doc_industry
- 规则 B（is_index_report=false）：使用 AI 提取各公司的行业
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger

from nanobot.core.llm_core import llm_core


class Stage5AgenticWriter:
    """Stage 5: Agentic 写入与行业分配"""
    
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
        🌟 Agentic 多表写入
        
        根据文档类型使用不同的写入策略：
        - 指数报告（规则 A）：所有成分股指派同一行业
        - 年报（规则 B）：AI 提取各公司行业
        
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
        
        logger.info(f"🎯 Stage 5: Agentic 写入...")
        
        # 🌟 构建专属于 Stage 5 的 Prompt
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
        
        # 🌟 智能多表写入 Prompt
        stage5_prompt = f"""
你是一个高级 PostgreSQL 数据库写入 Agent。
任务目标：分析 PDF 内容，智能提取并写入对应的数据表。

{report_context}

提取类型：{', '.join(extraction_types)}

请返回 JSON 格式的结构化数据：
```json
{
  "revenue_breakdown": [
    {"segment_name": "Europe", "segment_type": "geography", "revenue_percentage": 25.0}
  ],
  "key_personnel": [
    {"name_en": "John Doe", "position_title_en": "CEO", "board_role": "Executive Director"}
  ],
  "financial_metrics": [
    {"metric_name": "Revenue", "value": 1234567, "unit": "HKD"}
  ],
  "companies": [
    {"stock_code": "02359", "name_en": "Company A", "industry": "{confirmed_doc_industry if is_index_report else 'AI提取'}"}
  ]
}
```

只返回 JSON，不要其他文字。
"""
        
        # 🌟 调用 LLM 提取
        if progress_callback:
            progress_callback(85.0, "Stage 5: LLM 提取结构化数据")
        
        # 合并 artifacts 内容
        content_text = "\n\n".join([
            a.get("content", "") or a.get("markdown", "") or ""
            for a in artifacts[:10]  # 限制内容长度
        ])
        
        llm_response = await llm_core.chat(
            prompt=stage5_prompt + "\n\nPDF 内容:\n" + content_text[:5000],
            require_json=True
        )
        
        # 解析 LLM 输出
        extracted_data = {}
        try:
            if isinstance(llm_response, dict):
                extracted_data = llm_response
            elif isinstance(llm_response, str):
                # 尝试解析 JSON
                import re
                json_match = re.search(r'\{[\s\S]*\}', llm_response)
                if json_match:
                    extracted_data = json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"   ⚠️ LLM 输出解析失败: {e}")
        
        # 🌟 写入数据库
        if progress_callback:
            progress_callback(90.0, "Stage 5: 写入数据库")
        
        write_result = {
            "revenue_inserted": 0,
            "personnel_inserted": 0,
            "metrics_inserted": 0,
            "companies_updated": 0
        }
        
        # 写入 Revenue Breakdown
        if "revenue_breakdown" in extracted_data and db_client:
            for item in extracted_data["revenue_breakdown"]:
                try:
                    await db_client.insert_revenue_breakdown(
                        company_id=company_id,
                        year=year,
                        segment_name=item.get("segment_name"),
                        segment_type=item.get("segment_type", "geography"),
                        revenue_percentage=item.get("revenue_percentage"),
                        revenue_amount=item.get("revenue_amount"),
                        currency=item.get("currency", "HKD"),
                        source_document_id=document_id
                    )
                    write_result["revenue_inserted"] += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ Revenue 写入失败: {e}")
        
        # 写入 Key Personnel
        if "key_personnel" in extracted_data and db_client:
            for person in extracted_data["key_personnel"]:
                try:
                    await db_client.insert_key_personnel(
                        company_id=company_id,
                        year=year,
                        name_en=person.get("name_en"),
                        name_zh=person.get("name_zh"),
                        position_title_en=person.get("position_title_en"),
                        role=person.get("role"),
                        board_role=person.get("board_role"),
                        committee_membership=person.get("committee_membership"),
                        biography=person.get("biography"),
                        source_document_id=document_id
                    )
                    write_result["personnel_inserted"] += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ Personnel 写入失败: {e}")
        
        # 写入 Financial Metrics
        if "financial_metrics" in extracted_data and db_client:
            for metric in extracted_data["financial_metrics"]:
                try:
                    await db_client.insert_financial_metric(
                        company_id=company_id,
                        year=year,
                        metric_name=metric.get("metric_name"),
                        value=metric.get("value"),
                        unit=metric.get("unit", "HKD"),
                        source_document_id=document_id
                    )
                    write_result["metrics_inserted"] += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ Metric 写入失败: {e}")
        
        # 🌟 行业分配规则执行
        if "companies" in extracted_data and db_client:
            for company_data in extracted_data["companies"]:
                stock_code = company_data.get("stock_code")
                
                if stock_code:
                    # 🌟 规则 A：指数报告，所有公司指派同一行业
                    if is_index_report and confirmed_doc_industry:
                        industry = confirmed_doc_industry
                    # 🌟 规则 B：年报，AI 提取行业
                    else:
                        industry = company_data.get("industry")
                    
                    try:
                        # 查询或创建公司
                        existing_company = await db_client.get_company_by_stock_code(stock_code)
                        
                        if existing_company:
                            # 更新行业
                            await db_client.update_company_industry(
                                existing_company.get("id"),
                                industry
                            )
                        else:
                            # 创建新公司
                            await db_client.upsert_company(
                                stock_code=stock_code,
                                name_en=company_data.get("name_en"),
                                name_zh=company_data.get("name_zh"),
                                industry=[industry] if industry else None
                            )
                        
                        write_result["companies_updated"] += 1
                        
                    except Exception as e:
                        logger.warning(f"   ⚠️ 公司行业更新失败: {e}")
        
        logger.info(f"✅ Stage 5 完成: {write_result}")
        
        return {
            "status": "success",
            "extracted_data": extracted_data,
            "write_result": write_result,
            "is_index_report": is_index_report,
            "industry_rule": "A" if is_index_report else "B"
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