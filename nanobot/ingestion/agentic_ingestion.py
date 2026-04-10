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

🌟 支持指數報告特殊處理：
- 規則 A：報告明確定義行業主題 → 所有成分股強制指派該行業
- 規則 B：一般綜合報告 → 各公司各自 AI 提取行業
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
    document_type: Optional[str] = None
    parent_company: Optional[str] = None
    parent_stock_code: Optional[str] = None
    is_index_report: bool = False
    index_theme: Optional[str] = None
    confirmed_doc_industry: Optional[str] = None
    subsidiaries: List[Dict[str, Any]] = field(default_factory=list)
    fiscal_year: Optional[int] = None
    ai_industries: Optional[List[str]] = None
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
    
    # Agent 系統提示詞 (支持指數報告特殊處理)
    INGESTION_SYSTEM_PROMPT = """你是 Nanobot 專業金融資料提取代理。我會提供給你一份金融文件的前 1-2 頁內容。
你的任務是提取核心 Metadata，並準備寫入資料庫。

請嚴格遵守以下邏輯判斷：

## 1. 報告類型識別

判斷這是一般公司的財報 (annual_report)，還是市場/指數報告 (index_report)。

**識別特徵**：
- 年報 (annual_report)：有單一母公司名稱、股票代碼
- 指數報告 (index_report)：如 "Hang Seng Index"、"恒生指數"、"HSI Biotech Index" 等，包含多間成分股

## 2. 母公司 (Parent Company) 提取

- **如果是一般財報**：提取母公司名稱和股票代碼
- **如果是指數報告**：因為它涵蓋多間公司，請將 `parent_company` 設為 null，並將 `is_index_report` 設為 true

## 3. 行業 (Industry) 提取與傳遞原則 🌟 核心邏輯

仔細閱讀前 1-2 頁。判斷這份報告是否**明確定義了一個單一的行業主題**：

### 規則 A：明確定義的行業主題

**條件**：報告標題或前言明確定義了行業主題
- 例如："Hang Seng Biotech Index" → 全部都是 Biotech
- 例如："恒生科技指數" → 全部都是 Technology

**執行**：
1. 將該行業設為 `confirmed_doc_industry`（如 "Biotech"）
2. 設置 `index_theme` 為指數名稱（如 "Hang Seng Biotech Index"）
3. **重要**：報告中列出的**所有成分股**，都必須強制指派這個 Industry
4. **絕對不要**再為各成分股各自產生多重 (Multiple) 的 AI Industry 預測

### 規則 B：無明確單一主題

**條件**：一般綜合報告，沒有定義單一 Industry
- 例如：綜合年報、跨行業集團報告

**執行**：
1. `confirmed_doc_industry` 設為 null
2. 為每一間子公司/成分股各自提取可能的 `ai_industries`（可以是 List）

## 4. 成分股/子公司提取

對於指數報告，提取所有成分股：
- 公司名稱 (中英文)
- 股票代碼
- 關係類型：`index_constituent`（指數報告）或 `subsidiary`（一般年報）

## 5. 動態屬性 (Dynamic Attributes)

如果你發現重要但不在實體 Schema 的資訊：
- 報告發布季度
- 指數編制規則版本
- 審計師
- 特殊事項

請放入 `dynamic_attributes` 中（JSON 格式）。

## 6. 執行寫入

完成分析後，呼叫 `smart_insert_document` 工具寫入數據庫。

---

## 輸出格式

請以 JSON 格式返回分析結果：

```json
{
    "document_type": "index_report",
    "parent_company": null,
    "parent_stock_code": null,
    "is_index_report": true,
    "index_theme": "Hang Seng Biotech Index",
    "confirmed_doc_industry": "Biotech",
    "fiscal_year": 2024,
    "ai_industries": null,
    "subsidiaries": [
        {
            "name": "Sino Biopharmaceutical",
            "stock_code": "01177",
            "relation_type": "index_constituent",
            "ai_industries": null
        }
    ],
    "dynamic_attributes": {
        "index_quarter": "Q3",
        "constituent_count": 50
    },
    "confidence_scores": {
        "document_type": 0.95,
        "confirmed_doc_industry": 0.98
    }
}
```

**注意**：當 `confirmed_doc_industry` 有值時，`subsidiaries` 中的 `ai_industries` 應為 null（規則 A）。
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
{intro_text[:8000]}

請按照系統提示中指定的 JSON 格式返回分析結果。記住：
- 如果是指數報告且有明確行業主題，使用規則 A
- 如果是一般綜合報告，使用規則 B
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
            
            logger.info(f"✅ Analysis complete: "
                       f"type={analysis.document_type}, "
                       f"is_index={analysis.is_index_report}, "
                       f"parent={analysis.parent_company}, "
                       f"subsidiaries={len(analysis.subsidiaries)}, "
                       f"confirmed_industry={analysis.confirmed_doc_industry}")
            
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
                    document_type=data.get('document_type'),
                    parent_company=data.get('parent_company'),
                    parent_stock_code=data.get('parent_stock_code'),
                    is_index_report=data.get('is_index_report', False),
                    index_theme=data.get('index_theme'),
                    confirmed_doc_industry=data.get('confirmed_doc_industry'),
                    subsidiaries=data.get('subsidiaries', []),
                    fiscal_year=data.get('fiscal_year'),
                    ai_industries=data.get('ai_industries'),
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

重要提醒：
- 如果 confirmed_doc_industry 有值，表示使用規則 A（所有成分股強制指派該行業）
- 如果 confirmed_doc_industry 為 null，表示使用規則 B（各公司各自 AI 提取行業）

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
                "analysis": {
                    "document_type": analysis.document_type,
                    "is_index_report": analysis.is_index_report,
                    "index_theme": analysis.index_theme,
                    "confirmed_doc_industry": analysis.confirmed_doc_industry,
                    "parent_company": analysis.parent_company,
                    "subsidiaries_count": len(analysis.subsidiaries),
                    "industry_rule": "A (report_defined)" if analysis.confirmed_doc_industry else "B (ai_extracted)"
                },
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
        print(f"Industry Rule: {result['analysis']['industry_rule']}")
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