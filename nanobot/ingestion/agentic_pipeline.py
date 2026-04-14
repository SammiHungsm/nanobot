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
    ├── extract_information() - 使用 AI Agent 提取
    └── process_document() - 兼容接口（用于 pipeline.py）
```

瘦身效果：
- 原本的 AgenticIngestionOrchestrator 有 ~400 行
- 现在的 AgenticPipeline 只需 ~50 行
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
        🎯 实现基类的抽象方法
        
        从 Artifacts 中提取结构化数据
        
        Args:
            artifacts: OpenDataLoader 解析出的 Artifacts
            metadata: PDF 元数据
            **kwargs: 其他参数
            
        Returns:
            Dict: 提取的结构化数据
        """
        logger.info("🤖 AgenticPipeline.extract_information 开始提取...")
        
        try:
            # 🌟 使用 llm_core.chat() 提取
            # 构建 Prompt
            prompt = self._build_agent_prompt(artifacts, metadata, **kwargs)
            
            response = await llm_core.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=3000
            )
            
            # 解析 JSON
            extracted_data = self._parse_agent_response(response)
            
            logger.info(f"✅ extract_information 完成: {len(extracted_data)} 个数据项")
            return extracted_data
            
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
        
        旧的 AgenticIngestionOrchestrator 有这个方法，新的 AgenticPipeline 需要兼容
        
        Args:
            document_content: 文档内容（通常是 Prompt）
            filename: 文件名
            user_hints: 用户提示
            
        Returns:
            Dict: 处理结果
        """
        logger.info("🤖 AgenticPipeline.process_document 开始处理...")
        
        try:
            # 🌟 使用 llm_core.chat() 发送 Prompt
            response = await llm_core.chat(
                messages=[{"role": "user", "content": document_content}],
                temperature=0.1,  # 降低温度，提高准确性
                max_tokens=3000
            )
            
            # 🌟 记录原始响应（用于调试）
            logger.debug(f"   🔍 LLM raw response ({len(response)} chars): {response[:500]}...")
            
            # 🌟 如果响应太短，可能是错误
            if len(response) < 50:
                logger.warning(f"   ⚠️ LLM 响应太短 ({len(response)} chars)，可能是空响应或错误")
                return {"success": False, "raw_response": response, "error": "response too short"}
            
            # 🌟 使用增强版 JSON 解析（非贪婪 + 括号平衡）
            result = self._parse_agent_response(response)
            
            if "parse_error" not in result and "raw_response" not in result:
                logger.info(f"✅ process_document 完成: {len(result)} 个数据项")
                return {"success": True, "data": result, "raw_response": response}
            else:
                logger.warning("⚠️ 无法解析 JSON，返回原始响应")
                return {"success": False, "raw_response": response, "error": result.get("parse_error", "parse failed")}
            
        except Exception as e:
            logger.error(f"❌ process_document 失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _build_agent_prompt(
        self,
        artifacts: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        **kwargs
    ) -> str:
        """构建 Agent Prompt"""
        # 提取前几页的文字内容
        first_pages_text = "\n\n".join([
            a.get("content", "")
            for a in artifacts[:5]
            if a.get("type") == "text_chunk"
        ])
        
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
        
        # 2. 嘗試提取第一個完整的 JSON 物件 (使用非貪婪模式，配合 balance braces)
        # 匹配從 { 到 }，確保括號平衡
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
                        # 重置，尋找下一個可能的 JSON
                        start_idx = None
                        continue
        
        # 3. 最後嘗試：貪婪模式但只取第一個 JSON (fallback)
        json_match = re.search(r'\{[\s\S]*?\}', response)  # 非貪婪
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