"""
Agentic Ingestion Pipeline

實現智能文件攝入流程：
- Agent 分析前 1-2 頁提取 Metadata
- 規則 A/B 行業分配
- JSONB 動態屬性寫入

Two-Phase Pipeline:
- Phase 1: Agent 分析 → Metadata → DB Insert
- Phase 2: OpenDataLoader → 表格提取 → Chunks
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger

from nanobot.agent.runner import AgentRunner
from nanobot.agent.tools.register_all import register_all_tools


class AgenticIngestionPipeline:
    """
    Agentic Dynamic Ingestion Pipeline
    
    使用 Agent 智能處理文件攝入：
    1. 分析前 1-2 頁
    2. 判斷報告類型
    3. 提取 Metadata
    4. 執行規則 A/B
    5. 寫入資料庫
    """
    
    # Agent System Prompt - 定義智能攝入邏輯
    SYSTEM_PROMPT = """
你是 Nanobot 專業金融資料提取代理。我會提供給你一份金融文件的前 1-2 頁內容。
你的任務是提取核心 Metadata，並準備寫入資料庫。

請嚴格遵守以下邏輯判斷：

## 1. 報告類型識別

判斷這是一般公司的財報 (Annual Report)，還是市場/指數報告 (例如 Hang Seng Indexing Report)。

**指數報告特徵:**
- 名稱包含 "Index", "Indexing", "指數"
- 前言說明是行業指數報告（如 "Hang Seng Biotech Index"）
- 包含多間成分股/公司列表
- 沒有單一母公司

**年報特徵:**
- 有明確的母公司名稱
- 單一公司的財務報告
- 可能包含子公司但以母公司為主體

## 2. 母公司 (Parent Company) 提取

- 如果是一般財報，提取母公司名稱
- 如果是**指數報告**，請將 `parent_company` 設為 null

## 3. 行業 (Industry) 提取與傳遞原則 - 核心邏輯

**規則 A (明確定義):**
- 如果報告前 1-2 頁**明確定義了一個單一的行業主題**（如 "Biotech Index" 代表全都是 Biotech）
- 將提取出的 Industry 記為 `confirmed_industry`
- **所有子公司/成分股都必須強制指派這個 Industry**
- **絕對不要**再為它們各自產生多重 AI Industry 預測
- `industry_source` = 'confirmed'

**規則 B (無明確單一主題):**
- 如果是綜合指數報告（如 Hang Seng Composite Index）
- 或一般年報，沒有定義單一 Industry
- 需要為每一間公司各自提取可能的 `ai_extracted_industries`（可以是 List）
- `industry_source` = 'ai_extracted'

## 4. 動態屬性 (Dynamic Attributes)

如果你發現重要但不在實體 Schema 的資訊，請放入 JSONB 格式的 `dynamic_data` 中：
- `index_quarter` - 報告季度（如 "Q3"）
- `report_version` - 版本號
- `publication_date` - 發布日期
- `is_audited` - 是否經審計
- 其他任何有用的 metadata

## 5. 輸出格式

完成分析後，請以 JSON 格式輸出，並呼叫 `smart_insert_document` Tool:

```json
{
    "filename": "hsi_biotech_q3_2024.pdf",
    "report_type": "index_report",
    "parent_company": null,
    "index_theme": "Hang Seng Biotech Index",
    "confirmed_doc_industry": "Biotech",
    "industry_assignment_rule": "A",
    "dynamic_data": {
        "index_quarter": "Q3",
        "report_version": "2024-v1"
    },
    "sub_companies": [
        {"name": "Sino Biopharmaceutical", "stock_code": "1177.HK"},
        {"name": "BeiGene", "stock_code": "06160.HK"}
    ]
}
```

注意：
- `industry_assignment_rule` 必須明確標示 "A" 或 "B"
- `sub_companies` 列出所有提到的公司及其股票代碼
- 如果是規則 B，每個公司還需要 `ai_industries` 欄位

開始分析吧！
"""
    
    def __init__(self):
        """初始化 Pipeline"""
        self.agent = AgentRunner()
        self._setup_tools()
    
    def _setup_tools(self):
        """註冊所需 Tools"""
        register_all_tools(self.agent.tool_registry)
        logger.info("✅ AgenticIngestionPipeline Tools 已註冊")
    
    async def analyze_document(
        self,
        pdf_path: str,
        filename: str,
        first_pages_text: str
    ) -> Dict[str, Any]:
        """
        Phase 1: Agent 分析前 1-2 頁
        
        Args:
            pdf_path: PDF 檔案路徑
            filename: 檔案名稱
            first_pages_text: 前 1-2 頁的文字內容
            
        Returns:
            分析結果 dict，包含 report_type, companies, industries 等
        """
        logger.info(f"🔍 Phase 1: Agent 分析 {filename}")
        
        # 構建給 Agent 的 Prompt
        prompt = f"""
文件名稱: {filename}
文件路徑: {pdf_path}

前 1-2 頁內容:
---
{first_pages_text}
---

請根據以上內容，按照 System Prompt 的邏輯進行分析，並呼叫 smart_insert_document Tool。
"""
        
        # 呼叫 Agent
        result = await self.agent.run(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            skill="ingestion"
        )
        
        logger.info(f"✅ Agent 分析完成: {json.dumps(result, ensure_ascii=False)[:200]}...")
        
        return result
    
    async def ingest_with_agent(
        self,
        pdf_path: str,
        filename: str,
        first_pages_text: str,
        user_override: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        完整的 Agent Ingestion 流程
        
        Args:
            pdf_path: PDF 檔案路徑
            filename: 檔案名稱
            first_pages_text: 前 1-2 頁的文字內容
            user_override: 用戶指定的覆蓋值（如 report_type, confirmed_industry）
            
        Returns:
            資料庫寫入結果
        """
        logger.info(f"📄 開始 Agent Ingestion: {filename}")
        
        # 1. Agent 分析
        analysis_result = await self.analyze_document(
            pdf_path=pdf_path,
            filename=filename,
            first_pages_text=first_pages_text
        )
        
        # 2. 如果有用戶覆蓋，應用覆蓋值
        if user_override:
            logger.info(f"👤 應用用戶覆蓋: {user_override}")
            for key, value in user_override.items():
                if value is not None:
                    analysis_result[key] = value
            
            # 特殊處理：如果用戶指定了 confirmed_industry，強制使用規則 A
            if user_override.get("confirmed_doc_industry"):
                analysis_result["industry_assignment_rule"] = "A"
        
        # 3. 直接呼叫 smart_insert_document Tool
        from nanobot.agent.tools.db_ingestion_tools import SmartInsertDocumentTool
        
        insert_tool = SmartInsertDocumentTool()
        insert_result = await insert_tool.execute(
            filename=analysis_result.get("filename", filename),
            report_type=analysis_result.get("report_type", "annual_report"),
            parent_company=analysis_result.get("parent_company"),
            index_theme=analysis_result.get("index_theme"),
            confirmed_doc_industry=analysis_result.get("confirmed_doc_industry"),
            dynamic_data=analysis_result.get("dynamic_data", {}),
            sub_companies=analysis_result.get("sub_companies", [])
        )
        
        logger.info(f"✅ Ingestion 完成: {insert_result}")
        
        return json.loads(insert_result)


class TwoPhasePipeline:
    """
    Two-Phase Ingestion Pipeline
    
    Phase 1: Agent 分析 → Metadata → DB Insert (Zone 1)
    Phase 2: OpenDataLoader → 表格提取 → Chunks (Zone 2)
    """
    
    def __init__(self):
        """初始化 Two-Phase Pipeline"""
        self.agentic_pipeline = AgenticIngestionPipeline()
        logger.info("✅ TwoPhasePipeline 已初始化")
    
    async def run(
        self,
        pdf_path: str,
        filename: str,
        user_params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        執行完整的 Two-Phase Pipeline
        
        Args:
            pdf_path: PDF 檔案路徑
            filename: 檔案名稱
            user_params: 用戶提供的參數（如 doc_type, index_theme, confirmed_industry）
            
        Returns:
            完整的處理結果
        """
        logger.info(f"🚀 Two-Phase Pipeline 開始: {filename}")
        
        # ===== Phase 1: Agent Analysis =====
        logger.info("📍 Phase 1: Agent Analysis (Metadata Extraction)")
        
        # 提取前 1-2 頁
        first_pages_text = self._extract_first_pages(pdf_path, max_pages=2)
        
        if not first_pages_text:
            logger.warning("⚠️ 無法提取前頁內容，跳過 Agent 分析")
            first_pages_text = f"[Filename: {filename}]"
        
        # 構建用戶覆蓋參數
        user_override = {}
        if user_params:
            user_override = {
                "report_type": user_params.get("doc_type"),
                "index_theme": user_params.get("index_theme"),
                "confirmed_doc_industry": user_params.get("confirmed_industry"),
                "parent_company": user_params.get("parent_company")
            }
        
        # Agent 分析並寫入
        phase1_result = await self.agentic_pipeline.ingest_with_agent(
            pdf_path=pdf_path,
            filename=filename,
            first_pages_text=first_pages_text,
            user_override=user_override
        )
        
        if not phase1_result.get("success"):
            logger.error(f"❌ Phase 1 失敗: {phase1_result}")
            return phase1_result
        
        doc_id = phase1_result.get("document_id")
        logger.info(f"✅ Phase 1 完成，Document ID: {doc_id}")
        
        # ===== Phase 2: Deep Extraction =====
        logger.info("📍 Phase 2: Deep Extraction (OpenDataLoader)")
        
        try:
            phase2_result = await self._run_opendataloader(
                pdf_path=pdf_path,
                doc_id=doc_id,
                filename=filename
            )
            
            logger.info(f"✅ Phase 2 完成: {phase2_result}")
            
        except Exception as e:
            logger.error(f"❌ Phase 2 失敗: {e}")
            phase2_result = {"success": False, "error": str(e)}
        
        # ===== 整合結果 =====
        final_result = {
            "success": True,
            "document_id": doc_id,
            "filename": filename,
            "phase1": phase1_result,
            "phase2": phase2_result,
            "rule_applied": phase1_result.get("rule_applied"),
            "companies_inserted": phase1_result.get("companies_inserted"),
            "message": f"Successfully processed {filename} with Rule {phase1_result.get('rule_applied', 'N/A')}"
        }
        
        logger.info(f"🎉 Two-Phase Pipeline 完成: {json.dumps(final_result, ensure_ascii=False)[:300]}...")
        
        return final_result
    
    def _extract_first_pages(self, pdf_path: str, max_pages: int = 2) -> str:
        """
        提取 PDF 前 N 頁的文字
        
        Args:
            pdf_path: PDF 檔案路徑
            max_pages: 最大頁數
            
        Returns:
            提取的文字內容
        """
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(pdf_path)
            text_parts = []
            
            for page_num in range(min(max_pages, len(doc))):
                page = doc[page_num]
                text = page.get_text()
                text_parts.append(f"=== Page {page_num + 1} ===\n{text}")
            
            doc.close()
            
            return "\n\n".join(text_parts)
            
        except ImportError:
            logger.warning("⚠️ PyMuPDF 未安裝，嘗試使用其他方法")
            return self._extract_with_pdfplumber(pdf_path, max_pages)
            
        except Exception as e:
            logger.error(f"❌ 提取 PDF 失敗: {e}")
            return ""
    
    def _extract_with_pdfplumber(self, pdf_path: str, max_pages: int = 2) -> str:
        """使用 pdfplumber 提取"""
        try:
            import pdfplumber
            
            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page_num in range(min(max_pages, len(pdf.pages))):
                    page = pdf.pages[page_num]
                    text = page.extract_text() or ""
                    text_parts.append(f"=== Page {page_num + 1} ===\n{text}")
            
            return "\n\n".join(text_parts)
            
        except ImportError:
            logger.warning("⚠️ pdfplumber 也未安裝")
            return ""
            
        except Exception as e:
            logger.error(f"❌ pdfplumber 提取失敗: {e}")
            return ""
    
    async def _run_opendataloader(
        self,
        pdf_path: str,
        doc_id: int,
        filename: str
    ) -> Dict[str, Any]:
        """
        Phase 2: 使用 OpenDataLoader 進行深度提取
        
        Args:
            pdf_path: PDF 檔案路徑
            doc_id: Document ID
            filename: 檔案名稱
            
        Returns:
            提取結果
        """
        logger.info(f"📊 OpenDataLoader 處理: {filename}")
        
        # TODO: 實際呼叫 OpenDataLoader
        # 目前返回模擬結果
        
        return {
            "success": True,
            "tables_extracted": 0,
            "chunks_created": 0,
            "message": "OpenDataLoader processing placeholder"
        }


# ============================================================
# 工廠函數
# ============================================================

def create_ingestion_pipeline() -> TwoPhasePipeline:
    """創建 Two-Phase Pipeline"""
    return TwoPhasePipeline()


async def process_pdf_upload(
    pdf_path: str,
    filename: str,
    user_params: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    處理 PDF 上傳的便捷函數
    
    Args:
        pdf_path: PDF 檔案路徑
        filename: 檔案名稱
        user_params: 用戶參數
        
    Returns:
        處理結果
    """
    pipeline = create_ingestion_pipeline()
    return await pipeline.run(
        pdf_path=pdf_path,
        filename=filename,
        user_params=user_params
    )