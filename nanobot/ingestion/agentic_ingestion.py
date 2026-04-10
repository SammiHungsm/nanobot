"""
Agentic Ingestion Module - 智能代理動態寫入

這個模塊實現了「Agentic Dynamic Ingestion」架構：
1. 首頁掃描與實體識別 (First 1-2 Pages Scan)
2. Schema 動態反射與評估
3. 動態資料寫入

設計理念：
- AI 只做「Schema 決策」與「Metadata 提取」
- 大量數據寫入仍由 Python 批次處理
- 保留人工覆核機制確保數據準確度
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


@dataclass
class DocumentAnalysis:
    """文檔分析結果"""
    parent_company: Optional[Dict[str, Any]] = None
    subsidiaries: List[Dict[str, Any]] = field(default_factory=list)
    industries: List[str] = field(default_factory=list)
    document_type: Optional[str] = None
    fiscal_year: Optional[int] = None
    is_index_report: bool = False
    dynamic_attributes: Dict[str, Any] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)


class AgenticIngestionPipeline:
    """
    智能代理動態寫入管道
    
    流程：
    1. 解析 PDF 前 1-2 頁
    2. 呼叫 Agent 分析實體信息
    3. 動態寫入數據庫
    4. 創建待覆核記錄
    """
    
    # Agent 系統提示詞
    INGESTION_SYSTEM_PROMPT = """你是 Nanobot 數據庫寫入代理，專門負責分析金融文件並提取關鍵實體信息。

你的任務是從文件的前幾頁內容中提取：

1. **母公司信息** (Parent Company)
   - 公司名稱 (中英文)
   - 股票代碼
   - 注意：如果是「恒指報告」或「指數報告」，可能沒有單一母公司，請設為 null

2. **相關公司** (Subsidiaries / Index Constituents)
   - 一份文檔可能包含多間公司
   - 提取公司名稱、股票代碼
   - 標註關係類型：subsidiary, index_constituent, associate

3. **行業信息** (Industries)
   - 可能有多個行業
   - AI 提取的行業放入 ai_industries 列表

4. **文檔類型** (Document Type)
   - annual_report, quarterly_report, index_report, etc.

5. **財政年度** (Fiscal Year)
   - 從文檔中識別年份

6. **動態屬性** (Dynamic Attributes)
   - 如果你發現了值得記錮但不在 Schema 實體欄位中的屬性
   - 例如：報告季度、審計師、特殊事項等
   - 這些會被存入 JSONB 欄位

**重要決策原則**：
- 如果是恒指/指數報告，parent_company = null，但會有多個 constituents
- 如果無法確定某個值，將其放入 dynamic_attributes 而非實體欄位
- 對於置信度較低的提取，在 confidence_scores 中標註

**輸出格式**：
請以 JSON 格式返回分析結果，格式如下：
```json
{
    "parent_company": {
        "name_en": "...",
        "name_zh": "...",
        "stock_code": "..."
    },
    "subsidiaries": [
        {"name": "...", "stock_code": "...", "relation_type": "subsidiary"}
    ],
    "industries": ["Finance", "Technology"],
    "document_type": "annual_report",
    "fiscal_year": 2024,
    "is_index_report": false,
    "dynamic_attributes": {
        "auditor": "...",
        "reporting_currency": "HKD"
    },
    "confidence_scores": {
        "parent_company": 0.95,
        "industries": 0.85
    }
}
```
"""

    def __init__(self, agent_loop: AgentLoop = None):
        """
        初始化
        
        Args:
            agent_loop: AgentLoop 實例 (如果為 None，會創建新的)
        """
        self.agent_loop = agent_loop
        self._tools_registered = False
    
    def _ensure_tools_registered(self):
        """確保 Ingestion Tools 已註冊"""
        if self._tools_registered:
            return
        
        if self.agent_loop:
            from nanobot.agent.tools.db_ingestion_tools import register_ingestion_tools
            register_ingestion_tools(self.agent_loop.tools)
            self._tools_registered = True
    
    async def analyze_document(
        self,
        pdf_path: str,
        pages_to_scan: int = 2
    ) -> DocumentAnalysis:
        """
        分析文檔前幾頁，提取實體信息
        
        Args:
            pdf_path: PDF 文件路徑
            pages_to_scan: 掃描頁數 (默認前 2 頁)
        
        Returns:
            DocumentAnalysis: 分析結果
        """
        self._ensure_tools_registered()
        
        logger.info(f"🔍 Analyzing document: {pdf_path} (first {pages_to_scan} pages)")
        
        # 1. 提取前幾頁文本
        intro_text = await self._extract_first_pages(pdf_path, pages_to_scan)
        
        if not intro_text:
            logger.warning(f"⚠️ No text extracted from {pdf_path}")
            return DocumentAnalysis()
        
        # 2. 調用 Agent 分析
        prompt = f"""請分析以下金融文件的前 {pages_to_scan} 頁內容，提取關鍵實體信息。

文件路徑: {pdf_path}

=== 文件內容 ===
{intro_text[:8000]}  # 限制長度避免超過 token 限制

請按照系統提示中指定的 JSON 格式返回分析結果。
"""
        
        try:
            # 調用 Agent
            response = await self.agent_loop.process_direct(
                content=prompt,
                session_key="ingestion:analysis"
            )
            
            # 解析結果
            content = response.content if response else ""
            analysis = self._parse_analysis_result(content)
            
            logger.info(f"✅ Analysis complete: parent_company={analysis.parent_company}, "
                       f"subsidiaries={len(analysis.subsidiaries)}, "
                       f"industries={analysis.industries}")
            
            return analysis
            
        except Exception as e:
            logger.exception(f"❌ Failed to analyze document: {e}")
            return DocumentAnalysis()
    
    async def _extract_first_pages(
        self,
        pdf_path: str,
        pages: int
    ) -> str:
        """
        提取 PDF 前幾頁文本
        
        Args:
            pdf_path: PDF 文件路徑
            pages: 頁數
        
        Returns:
            str: 提取的文本內容
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF not installed. Install with: pip install pymupdf")
            return ""
        
        text_parts = []
        
        try:
            with fitz.open(pdf_path) as doc:
                for page_num in range(min(pages, len(doc))):
                    page = doc[page_num]
                    page_text = page.get_text()
                    text_parts.append(f"=== Page {page_num + 1} ===\n{page_text}")
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.exception(f"Failed to extract text from PDF: {e}")
            return ""
    
    def _parse_analysis_result(self, content: str) -> DocumentAnalysis:
        """
        解析 Agent 返回的分析結果
        
        Args:
            content: Agent 返回的文本
        
        Returns:
            DocumentAnalysis: 結構化的分析結果
        """
        # 嘗試從內容中提取 JSON
        try:
            # 找到 JSON 塊
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
                
                return DocumentAnalysis(
                    parent_company=data.get('parent_company'),
                    subsidiaries=data.get('subsidiaries', []),
                    industries=data.get('industries', []),
                    document_type=data.get('document_type'),
                    fiscal_year=data.get('fiscal_year'),
                    is_index_report=data.get('is_index_report', False),
                    dynamic_attributes=data.get('dynamic_attributes', {}),
                    confidence_scores=data.get('confidence_scores', {})
                )
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from agent response: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error parsing analysis result: {e}")
        
        return DocumentAnalysis()
    
    async def ingest_with_agent(
        self,
        pdf_path: str,
        filename: str,
        task_id: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        使用 Agent 執行完整的智能寫入流程
        
        Args:
            pdf_path: PDF 文件路徑
            filename: 原始文件名
            task_id: 任務 ID (可選)
            **kwargs: 其他參數 (company_id, year 等)
        
        Returns:
            Dict: 包含 document_id 和處理結果
        """
        self._ensure_tools_registered()
        
        start_time = time.time()
        
        logger.info(f"🚀 Starting agentic ingestion for: {filename}")
        
        # 1. 分析文檔
        analysis = await self.analyze_document(pdf_path)
        
        # 2. 調用智能寫入 Tool
        insert_prompt = f"""請使用 smart_insert_document 工具將以下分析結果寫入數據庫：

文件名: {filename}
文件路徑: {pdf_path}

分析結果:
{json.dumps(analysis.__dict__, indent=2, ensure_ascii=False, default=str)}

請執行寫入操作並返回結果。
"""
        
        try:
            response = await self.agent_loop.process_direct(
                content=insert_prompt,
                session_key="ingestion:insert"
            )
            
            # 解析結果
            content = response.content if response else ""
            
            # 嘗試提取 document_id
            document_id = None
            try:
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    result = json.loads(content[json_start:json_end])
                    document_id = result.get('document_id')
            except:
                pass
            
            elapsed = time.time() - start_time
            
            logger.info(f"✅ Agentic ingestion completed in {elapsed:.2f}s")
            
            return {
                "success": True,
                "document_id": document_id,
                "analysis": analysis.__dict__,
                "elapsed_seconds": elapsed,
                "task_id": task_id
            }
            
        except Exception as e:
            logger.exception(f"❌ Agentic ingestion failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_id": task_id
            }
    
    async def update_progress(self, task_id: str, progress: int, status: str = None):
        """更新任務進度"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                if status:
                    await conn.execute(
                        """
                        UPDATE document_tasks 
                        SET progress = $2, status = $3, updated_at = NOW()
                        WHERE task_id = $1
                        """,
                        task_id, progress, status
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE document_tasks 
                        SET progress = $2, updated_at = NOW()
                        WHERE task_id = $1
                        """,
                        task_id, progress
                    )
        finally:
            await db.close()


# ============================================================
# 便捷函數
# ============================================================

async def run_agentic_ingestion(
    pdf_path: str,
    filename: str,
    agent_loop: AgentLoop = None,
    task_id: str = None
) -> Dict[str, Any]:
    """
    執行智能代理動態寫入
    
    這是主要的入口函數，用於在 Pipeline 中調用
    
    Args:
        pdf_path: PDF 文件路徑
        filename: 原始文件名
        agent_loop: AgentLoop 實例 (可選，會自動創建)
        task_id: 任務 ID (可選)
    
    Returns:
        Dict: 包含 document_id 和處理結果
    
    Usage:
        from nanobot.ingestion.agentic_ingestion import run_agentic_ingestion
        
        result = await run_agentic_ingestion(
            pdf_path="/path/to/report.pdf",
            filename="Annual Report 2024.pdf"
        )
        
        print(f"Document ID: {result['document_id']}")
    """
    if agent_loop is None:
        # 創建默認 AgentLoop
        from nanobot.agent.loop import AgentLoop
        from nanobot.bus.queue import MessageBus
        from nanobot.config.loader import load_config, resolve_config_env_vars
        
        config = resolve_config_env_vars(load_config())
        bus = MessageBus()
        
        # 創建 provider (簡化版)
        from nanobot.providers.openai_compat_provider import OpenAICompatProvider
        provider = OpenAICompatProvider(
            api_key=config.get_provider(config.agents.defaults.model).api_key,
            default_model=config.agents.defaults.model
        )
        
        agent_loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=config.workspace_path,
            model=config.agents.defaults.model
        )
    
    pipeline = AgenticIngestionPipeline(agent_loop=agent_loop)
    return await pipeline.ingest_with_agent(
        pdf_path=pdf_path,
        filename=filename,
        task_id=task_id
    )