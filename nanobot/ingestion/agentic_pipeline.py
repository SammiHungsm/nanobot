"""
Agentic Pipeline - 使用 AI Agent 的 Pipeline (v3.3)

🎯 继承 BaseIngestionPipeline，使用 AgentRunner + Tools Calling

🌟 v3.3: 使用 AgentRunner 实现真正的 Tools Calling
- Agent 可以自己查 DB Schema (get_db_schema)
- Agent 可以自己写入数据 (smart_insert_document)
- Agent 可以自己更新 JSONB (update_dynamic_attributes)
- Agent 可以自己注册关键词 (register_new_keyword)

架构：
```
BaseIngestionPipeline (基類)
 ├── run() - 主流程
 ├── parse_document() - PDF 解析
 ├── save_to_db() - DB 储存
 └── extract_information() - 抽象方法
 ↓
AgenticPipeline (子類)
 ├── extract_information() - 使用 AgentRunner + Tools
 ├── process_document() - 兼容接口（用于 pipeline.py）
 └── _get_tools_registry() - 构建 Tools Registry
```
"""

from typing import Dict, Any, List
from loguru import logger
from pathlib import Path
import os

from nanobot.ingestion.base_pipeline import BaseIngestionPipeline
from nanobot.agent.runner import AgentRunner, AgentRunSpec, AgentRunResult
from nanobot.agent.tools.registry import ToolRegistry
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
    BackfillFromFallbackTool
)
from nanobot.agent.tools.dynamic_schema_tools import (
    GetDynamicKeysTool,
    GetJSONBSchemaTool,
    PrepareVannaPromptTool
)
from nanobot.core.llm_core import llm_core
from nanobot.providers.base import LLMProvider


class AgenticPipeline(BaseIngestionPipeline):
    """
    🎯 Agentic Pipeline - 使用 AI Agent 进行智能提取
    
    🌟 关键改进：使用 AgentRunner + Tools Calling
    - Agent 可以自己查 DB Schema (get_db_schema)
    - Agent 可以自己写入数据 (smart_insert_document)
    - Agent 可以自己更新 JSONB (update_dynamic_attributes)
    - Agent 可以自己注册关键词 (register_new_keyword)
    
    Example:
        pipeline = AgenticPipeline(db_url="postgresql://...")
        await pipeline.connect()
        result = await pipeline.run("report.pdf")
        await pipeline.close()
    """
    
    def __init__(self, db_url: str = None, data_dir: str = None):
        """初始化"""
        super().__init__(db_url=db_url, data_dir=data_dir)
        
        # 🌟 AgentRunner 实例
        self.runner = None
        self.model = "qwen3-235b"  # 默认模型
    
    def _get_tools_registry(self) -> ToolRegistry:
        """
        🌟 构建 Tools Registry（Agent 可以调用的工具）
        
        包含所有 Agentic 写入相关的 Tools
        """
        registry = ToolRegistry()
        
        # 🌟 Schema 查询 Tools
        registry.register(GetDBSchemaTool())
        registry.register(GetDynamicKeysTool())
        registry.register(GetJSONBSchemaTool())
        
        # 🌟 智能写入 Tools
        registry.register(SmartInsertDocumentTool())
        registry.register(UpdateDocumentStatusTool())
        registry.register(UpdateDynamicAttributesTool())
        
        # 🌟 结构化数据写入 Tools
        registry.register(InsertKeyPersonnelTool())
        registry.register(InsertFinancialMetricsTool())
        registry.register(InsertShareholdingTool())
        
        # 🌟 关键词管理 Tools
        registry.register(RegisterNewKeywordTool())
        registry.register(GetKeywordStatsTool())
        
        # 🌟 审核队列 Tools
        registry.register(CreateReviewRecordTool())
        
        # 🌟 Vanna 相关 Tools
        registry.register(PrepareVannaPromptTool())
        
        logger.info(f"✅ Tools Registry 已构建: {len(registry.tools)} 个工具")
        
        return registry
    
    async def _ensure_runner(self):
        """确保 AgentRunner 已初始化"""
        if self.runner is None:
            # 使用 llm_core 的 _get_provider() 获取 provider 实例
            provider = llm_core._get_provider(self.model)
            if provider is None:
                # Fallback: 创建新的 provider
                from nanobot.providers import OpenAICompatProvider
                provider = OpenAICompatProvider(
                    api_key=llm_core.config.get_api_key(self.model) if llm_core.config else os.getenv("OPENAI_API_KEY"),
                    base_url=llm_core.config.get_base_url(self.model) if llm_core.config else None
                )
                logger.warning("⚠️ 使用 Fallback Provider")
            
            self.runner = AgentRunner(provider=provider)
            logger.info(f"✅ AgentRunner 已初始化 (model={self.model})")
    
    async def extract_information(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        🎯 实现基类的抽象方法
        
        使用 AgentRunner + Tools Calling 从 Artifacts 中提取结构化数据
        
        Args:
            artifacts: LlamaParse 解析出的 Artifacts
            metadata: PDF 元数据
            **kwargs: 其他参数（is_index_report, index_theme, confirmed_doc_industry）
            
        Returns:
            Dict: 提取的结构化数据
        """
        logger.info("🤖 AgenticPipeline.extract_information 开始提取...")
        
        await self._ensure_runner()
        
        # 🌟 构建 System Prompt
        system_prompt = self._build_system_prompt(**kwargs)
        
        # 🌟 构建 User Prompt（包含 Artifacts 内容）
        user_prompt = self._build_user_prompt(artifacts, metadata, **kwargs)
        
        # 🌟 构建 Messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # 🌟 构建 Tools Registry
        tools_registry = self._get_tools_registry()
        
        # 🌟 构建 AgentRunSpec
        spec = AgentRunSpec(
            initial_messages=messages,
            tools=tools_registry,
            model=self.model,
            max_iterations=10,
            max_tool_result_chars=10000,
            temperature=0.1,
            max_tokens=3000
        )
        
        try:
            # 🌟 运行 AgentRunner
            result: AgentRunResult = await self.runner.run(spec)
            
            if result.error:
                logger.error(f"❌ AgentRunner 失败: {result.error}")
                return {"success": False, "error": result.error}
            
            # 🌟 解析最终结果
            final_content = result.final_content or ""
            extracted_data = self._parse_agent_response(final_content)
            
            # 🌟 记录使用的 Tools
            logger.info(f"✅ Agent 使用了 {len(result.tools_used)} 个 Tools: {result.tools_used}")
            
            return {
                "success": True,
                "data": extracted_data,
                "tools_used": result.tools_used,
                "usage": result.usage,
                "raw_response": final_content
            }
            
        except Exception as e:
            logger.error(f"❌ extract_information 失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_document(
        self,
        document_content: str,
        filename: str,
        user_hints: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        🎯 兼容接口：用于 pipeline.py 的 smart_extract
        
        使用 AgentRunner + Tools Calling
        
        Args:
            document_content: 文档内容（通常是 Stage 5 Prompt）
            filename: 文件名
            user_hints: 用户提示（stage, doc_type, index_theme, confirmed_doc_industry, page_num, year, company_id）
            
        Returns:
            Dict: 处理结果
        """
        logger.info("🤖 AgenticPipeline.process_document 开始处理...")
        
        await self._ensure_runner()
        
        user_hints = user_hints or {}
        
        # 🌟 构建 System Prompt（告诉 Agent 它可以调用哪些 Tools）
        system_prompt = """
你是一个专业的 PostgreSQL 数据库写入 Agent。
你可以使用以下 Tools 来完成任务：

📌 查询 Schema：
- get_db_schema: 查看当前数据库表结构
- get_dynamic_keys: 发现 JSONB 动态属性的所有 Keys
- get_jsonb_schema: 查看特定 JSONB 列的结构

📌 智能写入：
- smart_insert_document: 智能写入文档（支持规则 A/B）
- update_dynamic_attributes: 更新文档的动态属性（JSONB）
- update_document_status: 更新文档状态

📌 结构化数据写入：
- insert_key_personnel: 写入关键人员（董事、高管）
- insert_financial_metrics: 写入财务指标
- insert_shareholding: 写入股东结构

📌 关键词管理：
- register_new_keyword: 注册新的搜索关键词（持续学习）
- get_keyword_stats: 查看关键词统计

📌 审核队列：
- create_review_record: 创建人工审核记录

📌 Vanna 相关：
- prepare_vanna_prompt: 为 Vanna SQL 生成准备 Prompt

【工作流程】
1. 先调用 get_db_schema 了解数据库结构
2. 根据文档内容，判断页面类型
3. 提取对应的结构化数据
4. 使用对应的 Tool 写入数据库
5. 如果发现新的关键词，调用 register_new_keyword
6. 如果遇到不确定的数据，调用 create_review_record

请根据用户提供的文档内容，智能完成提取和写入任务。
"""
        
        # 🌟 构建 Messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": document_content}
        ]
        
        # 🌟 构建 Tools Registry
        tools_registry = self._get_tools_registry()
        
        # 🌟 构建 AgentRunSpec
        spec = AgentRunSpec(
            initial_messages=messages,
            tools=tools_registry,
            model=self.model,
            max_iterations=10,
            max_tool_result_chars=10000,
            temperature=0.1,
            max_tokens=3000
        )
        
        try:
            # 🌟 运行 AgentRunner
            result: AgentRunResult = await self.runner.run(spec)
            
            if result.error:
                logger.error(f"❌ process_document 失败: {result.error}")
                return {"success": False, "error": result.error, "raw_response": result.final_content}
            
            # 🌟 解析最终结果
            final_content = result.final_content or ""
            
            # 🌟 记录使用的 Tools
            logger.info(f"✅ Agent 使用了 {len(result.tools_used)} 个 Tools: {result.tools_used}")
            logger.info(f"   📊 Token 使用: prompt={result.usage.get('prompt_tokens', 0)}, completion={result.usage.get('completion_tokens', 0)}")
            
            return {
                "success": True,
                "tools_used": result.tools_used,
                "usage": result.usage,
                "raw_response": final_content,
                "stop_reason": result.stop_reason
            }
            
        except Exception as e:
            logger.error(f"❌ process_document 失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def ingest_with_agent(
        self,
        pdf_path: str,
        filename: str,
        task_id: str = None
    ) -> Dict[str, Any]:
        """
        🌟 Stage 0/5: 使用 Agent 进行智能入库
        
        分析 PDF 前 1-2 页，提取实体信息并动态写入数据库
        
        Args:
            pdf_path: PDF 文件路径
            filename: 原始文件名
            task_id: 任务 ID (可选)
            
        Returns:
            Dict: {"success": bool, "document_id": str, "analysis": {...}, "needs_review": bool}
        """
        logger.info(f"🤖 ingest_with_agent: {filename}")
        
        await self._ensure_runner()
        
        try:
            # 🌟 Step 1: 使用 PDFParser 解析 PDF
            parse_result = await self.parser.parse_async(pdf_path)
            
            artifacts = parse_result.artifacts
            total_pages = parse_result.total_pages
            
            # 🌟 Step 2: 只分析前 1-2 页（封面）
            cover_artifacts = [a for a in artifacts if a.get("page") in [1, 2]]
            
            # 🌟 Step 3: 构建分析 Prompt
            cover_content = self._merge_artifacts(cover_artifacts)
            
            analysis_prompt = f"""
分析以下 PDF 封面内容，提取关键信息：

【文件名】{filename}
【总页数】{total_pages}
【封面内容】
{cover_content[:2000]}

【提取要求】
1. 判断报告类型（annual_report 或 index_report）
2. 提取公司信息（母公司名称或成分股列表）
3. 提取年份
4. 如果是指数报告，提取指数主题和行业

请使用 get_db_schema 查看数据库结构，然后使用 smart_insert_document 写入。
"""
            
            # 🌟 Step 4: 使用 AgentRunner 处理
            result = await self.process_document(
                document_content=analysis_prompt,
                filename=filename,
                user_hints={"task_id": task_id}
            )
            
            # 🌟 Step 5: 检查是否需要人工复核
            needs_review = False
            analysis = result.get("data", {})
            confidence_scores = analysis.get("confidence_scores", {})
            
            if confidence_scores:
                needs_review = any(score < 0.8 for score in confidence_scores.values())
            
            if needs_review:
                logger.warning("⚠️ 低置信度，需要人工复核")
                # 调用 create_review_record
            
            return {
                "success": result.get("success", False),
                "document_id": analysis.get("document_id"),
                "analysis": analysis,
                "needs_review": needs_review,
                "tools_used": result.get("tools_used", [])
            }
            
        except Exception as e:
            logger.error(f"❌ ingest_with_agent 失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _merge_artifacts(self, artifacts: List[Dict[str, Any]]) -> str:
        """合并多个 Artifacts 为文本"""
        text_parts = []
        
        for artifact in artifacts:
            content = artifact.get("content") or artifact.get("markdown") or ""
            if content:
                text_parts.append(content)
        
        return "\n\n".join(text_parts)
    
    def _build_system_prompt(self, **kwargs) -> str:
        """构建 System Prompt"""
        is_index_report = kwargs.get("is_index_report", False)
        confirmed_industry = kwargs.get("confirmed_industry")
        
        prompt = """
你是一个专业的金融数据提取 Agent。
你可以使用 Tools 来完成任务：

📌 查询 Schema：
- get_db_schema: 查看数据库表结构
- get_dynamic_keys: 发现 JSONB 动态属性

📌 智能写入：
- smart_insert_document: 智能写入文档（支持规则 A/B）
- update_dynamic_attributes: 更新 JSONB 动态属性

📌 关键词管理：
- register_new_keyword: 注册新的搜索关键词

【工作流程】
1. 先调用 get_db_schema 了解数据库结构
2. 分析文档内容，提取结构化数据
3. 使用 smart_insert_document 写入
4. 如果发现新关键词，调用 register_new_keyword
"""
        
        if is_index_report and confirmed_industry:
            prompt += f"""
【重要规则】
这是一份指数报告，行业为 '{confirmed_industry}'。
所有成分股都必须被指派这个行业（规则 A）。
"""
        
        return prompt
    
    def _build_user_prompt(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        **kwargs
    ) -> str:
        """构建 User Prompt"""
        # 提取前几页的文字内容
        first_pages_text = "\n\n".join([
            a.get("content", "") or a.get("markdown", "")
            for a in artifacts[:5]
            if a.get("type") in ["text_chunk", "text"]
        ])
        
        prompt = f"""
【文档信息】
- 文件名：{metadata.get('filename', 'Unknown')}
- 总页数：{metadata.get('total_pages', 0)}

【前几页内容】
{first_pages_text[:3000]}

请提取结构化数据并写入数据库。
"""
        
        return prompt
    
    def _parse_agent_response(self, response: str) -> Dict[str, Any]:
        """
        解析 Agent 的 JSON 回复，增强容错能力
        
        修复：使用非贪婪模式提取 JSON，防止 LLM 多余文字干扰
        """
        import json
        import re
        
        # 1. 優先嘗試提取 Markdown 區塊 ```json ... ``` (使用非貪婪模式 *?)
        md_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if md_match:
            json_str = md_match.group(1).strip()
            try:
                data = json.loads(json_str)
                logger.info(f"✅ Markdown JSON 解析成功")
                return data
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ Markdown JSON 解析失败，嘗試其他方法: {e}")
        
        # 2. 嘗試提取第一個完整的 JSON 物件 (使用括號平衡)
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
                    json_str = response[start_idx:i+1]
                    try:
                        data = json.loads(json_str)
                        logger.info(f"✅ Balanced brace JSON 解析成功 (位置 {start_idx}-{i})")
                        return data
                    except json.JSONDecodeError as e:
                        logger.warning(f"⚠️ JSON 解析失败 (位置 {start_idx}-{i}): {e}")
                        start_idx = None
                        continue
        
        # 3. 最後嘗試：貪婪模式但只取第一個 JSON (fallback)
        json_match = re.search(r'\{[\s\S]*?\}', response)
        if json_match:
            json_str = json_match.group(0)
            try:
                data = json.loads(json_str)
                logger.info(f"✅ Fallback JSON 解析成功")
                return data
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ JSON 解析失败: {e}")
        
        # 4. 完全失敗，返回原始響應
        logger.warning("⚠️ 未找到有效 JSON 格式")
        return {"raw_response": response, "parse_error": "no valid JSON found"}


# ===========================================
# 工厂函数（兼容旧代码）
# ===========================================

def create_agentic_pipeline(db_url: str = None, data_dir: str = None) -> AgenticPipeline:
    """
    创建 AgenticPipeline 实例
    
    Args:
        db_url: PostgreSQL 连接字符串
        data_dir: 数据存储目录
        
    Returns:
        AgenticPipeline
    """
    return AgenticPipeline(db_url=db_url, data_dir=data_dir)