"""
Stage 4: Agentic 深度结构化提取

职责：
- 对候选页面调用 Financial Agent (LLM)
- 提取结构化数据 (Revenue Breakdown, Key Personnel, Financial Metrics)
- 返回 JSON 结果
- 写入数据库
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from loguru import logger

from nanobot.core.llm_core import llm_core


class Stage4Extractor:
    """Stage 4: Agentic 深度结构化提取"""
    
    @staticmethod
    async def extract_structured_data(
        artifacts: List[Dict[str, Any]],
        target_pages: List[int],
        company_id: int,
        year: int,
        doc_id: str,
        document_id: int,
        extraction_types: List[str] = None,
        llm_model: str = None,
        db_client: Any = None,
        progress_callback: Callable = None,
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None,
        merge_page_artifacts_fn: callable = None
    ) -> Dict[str, Any]:
        """
        对目标页面进行深度提取
        
        Args:
            artifacts: artifact 列表
            target_pages: 目标页面列表
            company_id: 公司 ID
            year: 年份
            doc_id: 文档 ID (字符串)
            document_id: 文档内部 ID (整数)
            extraction_types: 提取类型列表
            llm_model: LLM 模型
            db_client: DB 客户端
            progress_callback: 进度回调
            is_index_report: 是否为指数报告
            index_theme: 指数主题
            confirmed_doc_industry: 确认的行业
            merge_page_artifacts_fn: 合并页面 artifacts 的函数
            
        Returns:
            Dict: {"revenue_breakdown": [...], "key_personnel": [...], "stats": {...}}
        """
        logger.info(f"🤖 Stage 4: 开始 Agentic 深度提取...")
        logger.info(f"   👉 目标页面: {len(target_pages)} 页")
        
        extraction_types = extraction_types or ["revenue_breakdown", "key_personnel", "financial_metrics"]
        results = {et: [] for et in extraction_types}
        stats = {"pages_processed": 0, "total_extracted": 0, "errors": []}
        
        if not year:
            year = datetime.now().year
        
        for i, page_num in enumerate(sorted(target_pages)):
            if progress_callback:
                progress = 40.0 + (i + 1) / max(len(target_pages), 1) * 40.0
                progress_callback(progress, f"提取 Page {page_num}...")
            
            # 从 artifacts 中提取该页面的所有内容
            # 🌟 v3.2: LlamaParse 使用 'page' 字段，不是 'page_num'
            page_artifacts = [a for a in artifacts if a.get("page") == page_num]
            
            if not page_artifacts:
                logger.warning(f"   ⚠️ Page {page_num} 在 artifacts 中找不到，跳过")
                stats["errors"].append(f"Page {page_num} not found")
                continue
            
            # 合并该页面的所有文本和表格
            if merge_page_artifacts_fn:
                page_content = merge_page_artifacts_fn(page_artifacts)
            else:
                page_content = Stage4Extractor._merge_page_artifacts(page_artifacts)
            
            if not page_content or len(page_content.strip()) < 50:
                logger.warning(f"   ⚠️ Page {page_num} 内容过短，跳过")
                stats["errors"].append(f"Page {page_num} too short")
                continue
            
            logger.info(f"   📊 提取 Page {page_num} ({len(page_content)} chars)...")
            
            # 构建 Agentic Prompt
            prompt = Stage4Extractor._build_extraction_prompt(
                page_num, page_content, company_id, year, doc_id,
                is_index_report, index_theme, confirmed_doc_industry
            )
            
            # 调用 LLM
            try:
                response = await llm_core.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=3000
                )
                
                # 解析结果
                result = Stage4Extractor._parse_llm_response(response)
                
                if result:
                    page_type = result.get("page_type", "unknown")
                    data = result.get("data", {})
                    
                    if page_type in extraction_types and data:
                        # 保存提取结果
                        items = data.get("items", [])
                        if items:
                            results[page_type].append({
                                "page_num": page_num,
                                "items": items,
                                "confidence": result.get("confidence", 0.8)
                            })
                            
                            # 🌟 写入数据库
                            if db_client:
                                await Stage4Extractor._save_to_db(
                                    page_type, items, company_id, year, 
                                    document_id, page_num, db_client
                                )
                            
                            logger.info(f"   ✅ Page {page_num} 提取 {page_type}: {len(items)} 条")
                            stats["total_extracted"] += len(items)
                
                stats["pages_processed"] += 1
            
            except Exception as e:
                logger.warning(f"   ⚠️ Page {page_num} 提取失败: {e}")
                stats["errors"].append(f"Page {page_num}: {str(e)}")
        
        # 总结
        stats["total_extracted"] = sum(len(r) for r in results.values())
        logger.info(f"   ✅ Stage 4 完成: {stats['pages_processed']} 页, {stats['total_extracted']} 条记录")
        
        return {"results": results, "stats": stats}
    
    @staticmethod
    def _build_extraction_prompt(
        page_num: int,
        page_content: str,
        company_id: int,
        year: int,
        doc_id: str,
        is_index_report: bool,
        index_theme: str,
        confirmed_doc_industry: str
    ) -> str:
        """构建提取 Prompt（避免 f-string 嵌套）"""
        
        # 安全处理 page_content 中的 {} 字符
        page_content_safe = page_content[:6000].replace('{', '[').replace('}', ']')
        
        # 构建 report_context
        if is_index_report:
            report_context_str = f"指数报告 (主题: {index_theme or 'Unknown'}, 行业: {confirmed_doc_industry or 'Unknown'})"
        else:
            report_context_str = f"单一公司年报 (公司 ID: {company_id or '待提取'})"
        
        prompt = """
你是一个高级 PostgreSQL 数据库写入 Agent。
任务目标：分析 PDF 第 """ + str(page_num) + """ 页的内容类型，智能提取并写入对应的数据表。

【背景资讯】
- 文档 ID: """ + str(doc_id) + """
- 年份: """ + str(year) + """
- 报告类型: """ + report_context_str + """

【页面类型识别】

| 类型 | 关键词 |
|------|--------|
| revenue_breakdown | revenue, segment, geographical, 地区 |
| key_personnel | director, management, 高管, 董事 |
| financial_metrics | profit, assets, liabilities |
| other | 不符合以上 |

【待处理文本】
""" + page_content_safe + """

【返回格式】
返回严格 JSON（单行，无换行）：
{"page_type": "...", "data": {"items": [...]}, "confidence": 0.9}

Revenue Breakdown 示例：
{"page_type": "revenue_breakdown", "data": {"items": [{"segment_name": "Europe", "segment_type": "geography", "percentage": 25.0}]}, "confidence": 0.85}

Key Personnel 示例：
{"page_type": "key_personnel", "data": {"items": [{"name_en": "John", "position_title_en": "CEO"}]}, "confidence": 0.8}

只返回 JSON，不要其他文字。
"""
        return prompt
    
    @staticmethod
    def _parse_llm_response(response: str) -> Optional[Dict]:
        """解析 LLM 响应"""
        
        md_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if md_match:
            try:
                return json.loads(md_match.group(1).strip())
            except json.JSONDecodeError:
                pass
        
        # 括号平衡提取
        brace_count = 0
        start_idx = None
        for i, char in enumerate(response):
            if char == '{':
                if start_idx is None:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx is not None:
                    try:
                        return json.loads(response[start_idx:i+1])
                    except json.JSONDecodeError:
                        start_idx = None
        
        return None
    
    @staticmethod
    async def _save_to_db(
        page_type: str,
        items: List[Dict],
        company_id: int,
        year: int,
        document_id: int,
        page_num: int,
        db_client: Any
    ):
        """保存提取结果到数据库"""
        
        try:
            if page_type == "revenue_breakdown":
                for item in items:
                    await db_client.insert_revenue_breakdown(
                        company_id=company_id,
                        year=year,
                        document_id=document_id,
                        page_num=page_num,
                        segment_name=item.get("segment_name"),
                        segment_type=item.get("segment_type", "unknown"),
                        revenue_percentage=item.get("percentage"),
                        revenue_amount=item.get("amount"),
                        currency=item.get("currency", "HKD"),
                        notes=item.get("notes")
                    )
            
            elif page_type == "key_personnel":
                for item in items:
                    await db_client.insert_key_personnel(
                        company_id=company_id,
                        document_id=document_id,
                        name_en=item.get("name_en"),
                        name_zh=item.get("name_zh"),
                        position_title_en=item.get("position_title_en"),
                        board_role=item.get("board_role"),
                        committee_membership=json.dumps(item.get("committee_membership", [])),
                        biography=item.get("biography"),
                        page_num=page_num
                    )
            
            elif page_type == "financial_metrics":
                for item in items:
                    await db_client.insert_financial_metric(
                        company_id=company_id,
                        year=year,
                        document_id=document_id,
                        metric_name=item.get("metric_name"),
                        value=item.get("value"),
                        unit=item.get("unit", "HKD"),
                        standardized_value=item.get("standardized_value"),
                        notes=item.get("notes"),
                        page_num=page_num
                    )
            
        except Exception as e:
            logger.warning(f"   ⚠️ DB 写入失败: {e}")
    
    @staticmethod
    def _merge_page_artifacts(page_artifacts: List[Dict]) -> str:
        """合并页面 artifacts 为文本"""
        merged = ""
        for artifact in page_artifacts:
            content = artifact.get("content", "") or artifact.get("markdown", "") or artifact.get("text", "")
            if artifact.get("type") == "table":
                table_json = artifact.get("content_json", {})
                content = json.dumps(table_json, ensure_ascii=False)
            merged += content + "\n\n"
        return merged.strip()