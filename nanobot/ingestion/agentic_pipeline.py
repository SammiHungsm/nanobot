"""
Agentic Pipeline - 使用 AI Agent 的 Pipeline

🎯 继承 BaseIngestionPipeline，只关注 Agent 提取逻辑

架构：
```
BaseIngestionPipeline (基類)
    ├── run() - 主流程
    ├── parse_document() - PDF 解析
    ├── save_to_db() - DB 储存
    └── extract_information() - 抽象方法
        ↓
AgenticPipeline (子類)
    └── extract_information() - 使用 AI Agent 提取
```

瘦身效果：
- 原本的 AgenticIngestionOrchestrator 有 ~400 行
- 现在的 AgenticPipeline 只需 ~30 行
- Parser/DB 代码全部删除（由基类处理）
"""

from typing import Dict, Any, List
from loguru import logger

from nanobot.ingestion.base_pipeline import BaseIngestionPipeline
from nanobot.core.llm_core import llm_core


class AgenticPipeline(BaseIngestionPipeline):
    """
    🎯 Agentic Pipeline - 使用 AI Agent 进行智能提取
    
    🌟 只关注它特别的地方（Agent 提取逻辑）
    - PDF 解析由基类处理
    - DB 储存由基类处理
    - 进度追踪由基类处理
    
    Example:
        pipeline = AgenticPipeline(db_url="postgresql://...")
        await pipeline.connect()
        result = await pipeline.run("report.pdf")
        await pipeline.close()
    """
    
    async def extract_information(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        🎯 覆写提取逻辑：使用 AI Agent 进行复杂分析
        
        Args:
            artifacts: OpenDataLoader 解析出的 Artifacts
            metadata: PDF 元数据
            **kwargs: 其他参数（如 is_index_report, confirmed_industry）
            
        Returns:
            Dict: 提取的结构化数据
            
        提取内容：
        - 报告类型（年报/指数报告）
        - 公司信息（名称、行业）
        - 财务数据（营收、利润）
        - Key Personnel（高管信息）
        """
        logger.info("🤖 Agent 正在分析 Artifacts...")
        
        # 🌟 构建 Prompt
        prompt = self._build_agent_prompt(artifacts, metadata, **kwargs)
        
        # 🌟 调用 LLM（使用统一的 llm_core）
        response = await llm_core.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # 低温度，确保准确性
            max_tokens=2000
        )
        
        # 🌟 解析 JSON（LLM 应返回 JSON 格式）
        extracted_data = self._parse_agent_response(response)
        
        logger.info(f"✅ Agent 分析完成：{len(extracted_data)} 个数据项")
        
        return extracted_data
    
    def _build_agent_prompt(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        **kwargs
    ) -> str:
        """
        构建 Agent Prompt
        
        Args:
            artifacts: Artifacts 列表
            metadata: PDF 元数据
            **kwargs: 其他参数
            
        Returns:
            str: 完整的 Prompt
        """
        # 🌟 提取前几页的文字内容（用于分析）
        first_pages_text = "\n\n".join([
            a.get("content", "")
            for a in artifacts[:5]  # 只用前 5 个 artifacts
            if a.get("type") == "text_chunk"
        ])
        
        # 🌟 用户提供的参数（如 is_index_report）
        is_index_report = kwargs.get("is_index_report", False)
        confirmed_industry = kwargs.get("confirmed_industry")
        
        prompt = f"""
你是 Nanobot 金融数据提取 Agent。请分析以下 PDF 内容，提取结构化数据。

【报告信息】
- 文件名：{metadata.get('filename', 'Unknown')}
- 总页数：{metadata.get('total_pages', 0)}
- 类型：{'指数报告' if is_index_report else '年报'}
- 行业（用户指定）：{confirmed_industry or '未知'}

【前几页内容】
{first_pages_text[:3000]}

【提取要求】
请提取以下信息，并以 JSON 格式返回：

1. 报告类型：
   - "annual_report" (年报)
   - "index_report" (指数报告)

2. 公司信息：
   - 母公司名称（年报）
   - 成分股列表（指数报告）

3. 行业信息：
   - 如果是指数报告且用户指定了行业，所有成分股都应指派这个行业
   - 如果是年报，提取公司的 AI 行业预测

4. 财务数据（如有）：
   - 营收 breakdown
   - 利润数据

【返回格式】
```json
{
    "report_type": "annual_report" 或 "index_report",
    "parent_company": {...} 或 null,
    "companies": [...],
    "financial_data": {...}
}
```

请开始分析。
"""
        
        return prompt
    
    def _parse_agent_response(self, response: str) -> Dict[str, Any]:
        """
        解析 Agent 的 JSON 回复
        
        Args:
            response: LLM 的回复
            
        Returns:
            Dict: 解析后的数据
        """
        import json
        import re
        
        # 🌟 提取 JSON 部分（可能有 Markdown 包装）
        json_match = re.search(r'\{[\s\S]*\}', response)
        
        if json_match:
            json_str = json_match.group(0)
            try:
                data = json.loads(json_str)
                return data
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ JSON 解析失败: {e}")
                return {"raw_response": response, "parse_error": str(e)}
        
        else:
            logger.warning("⚠️ 未找到 JSON 格式")
            return {"raw_response": response}


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