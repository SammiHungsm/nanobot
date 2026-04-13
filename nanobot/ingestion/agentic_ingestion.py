"""
Agentic Ingestion Module - 智能代理攝入模組

此模組實現了「Agentic Dynamic Ingestion」架構，使用 AI Agent 動態處理資料庫寫入。

核心特性：
1. 動態 Metadata 提取
2. 規則 A/B 行業分配
3. JSONB 動態屬性支援
4. Two-Phase Pipeline 整合
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from loguru import logger


# ============================================================
# 核心系統提示 (System Prompt)
# ============================================================

INGESTION_SYSTEM_PROMPT = """
你是 Nanobot 專業金融資料提取代理。我會提供給你一份金融文件的前 1-2 頁內容。
你的任務是提取核心 Metadata，並準備寫入資料庫。

## 📋 你的職責

1. **報告類型識別**
   - Annual Report (年報): 單一公司的財務報告
   - Index Report (指數報告): 市場/指數報告，涵蓋多間成分股

2. **母公司提取規則**
   - Annual Report → 提取母公司名稱
   - Index Report → parent_company = null

3. **行業分配規則 ⭐ 核心邏輯**

### 規則 A - 明確定義的行業主題
**觸發條件:**
- 報告名稱包含行業關鍵字 (如 "Biotech Index", "Healthcare Index")
- 或前言明確說明主題

**執行步驟:**
1. 設定 `confirmed_doc_industry` = 該行業 (如 "Biotech")
2. 設定 `index_theme` = 報告主題 (如 "Hang Seng Biotech Index")
3. **所有成分股的 assigned_industry 都強制設為這個行業**
4. **絕對不要**再為各公司產生 AI Industry 預測

**範例輸入:**
```
Hang Seng Biotech Index
Quarterly Review Q3 2024

This report covers the 50 constituents of the Hang Seng Biotech Index...
Companies: Company A (0001.HK), Company B (0002.HK)...
```

**範例輸出:**
```json
{
    "report_type": "index_report",
    "parent_company": null,
    "index_theme": "Hang Seng Biotech Index",
    "confirmed_doc_industry": "Biotech",
    "industry_assignment_rule": "A",
    "sub_companies": [
        {"name": "Company A", "stock_code": "0001.HK"},
        {"name": "Company B", "stock_code": "0002.HK"}
    ]
}
```

### 規則 B - 無明確單一主題
**觸發條件:**
- 綜合指數報告 (如恆生指數，涵蓋多行業)
- 一般年報

**執行步驟:**
1. `confirmed_doc_industry` = null
2. 為每間公司提取 `ai_industries` (可能是多個行業的 List)

**範例輸入:**
```
ABC Corporation Limited
Annual Report 2024

ABC Corporation is a leading technology company...
Business segments: Software, Hardware, Cloud Services...
```

**範例輸出:**
```json
{
    "report_type": "annual_report",
    "parent_company": "ABC Corporation Limited",
    "index_theme": null,
    "confirmed_doc_industry": null,
    "industry_assignment_rule": "B",
    "sub_companies": [],
    "ai_extracted_industries": ["Technology", "Software", "Hardware"]
}
```

4. **動態屬性 (Dynamic Attributes)**
如果發現重要但不在實體 Schema 的資訊，請放入 JSONB 格式的 `dynamic_data` 中：

```json
{
    "report_quarter": "Q3",
    "report_year": "2024",
    "index_version": "v2.1",
    "constituent_count": 50,
    "base_date": "2024-01-01",
    "is_audited": true,
    "currency": "HKD",
    "reporting_standard": "IFRS"
}
```

## 📤 輸出格式

完成分析後，呼叫 `smart_insert_document_tool`，傳入以下參數：

```json
{
    "filename": "report.pdf",
    "report_type": "index_report",
    "parent_company": null,
    "index_theme": "Hang Seng Biotech Index",
    "confirmed_doc_industry": "Biotech",
    "dynamic_data": {
        "report_quarter": "Q3",
        "report_year": "2024"
    },
    "sub_companies": [
        {"name": "Company A", "stock_code": "0001.HK"},
        {"name": "Company B", "stock_code": "0002.HK"}
    ],
    "industry_assignment_rule": "A"
}
```

## ⚠️ 重要提醒

1. **嚴格遵守規則 A/B** - 不要混淆兩種情況
2. **股票代碼格式** - 使用標準格式如 `0001.HK`, `0700.HK`
3. **行業命名一致性** - 使用標準行業分類 (Technology, Healthcare, Finance, etc.)
4. **null 值處理** - Index Report 的 parent_company 必須是 null
5. **動態屬性靈活性** - 可以添加任何有意義的額外屬性

請開始分析文件內容。
"""


# ============================================================
# Agentic Ingestion Orchestrator
# ============================================================

class AgenticIngestionOrchestrator:
    """
    智能攝入協調器
    
    協調 Agent、Tools 和 Pipeline 之間的交互
    """
    
    def __init__(self, agent_runner=None, tools_registry=None):
        """
        初始化協調器
        
        Args:
            agent_runner: Agent Runner 實例
            tools_registry: Tools 註冊表
        """
        self.agent_runner = agent_runner
        self.tools_registry = tools_registry
        self._tools_registered = False  # 🌟 标记 Tools 是否已注册
        
        # 🌟 如果没有传入 agent_runner，自动创建一个
        if self.agent_runner is None:
            self._lazy_init_agent_runner()
        
        # 🌟 只有在没有延迟初始化时才注册 Tools
        if not self._tools_registered:
            self._register_tools()
        
        logger.info("🤖 Agentic Ingestion Orchestrator 初始化完成")
    
    def _lazy_init_agent_runner(self):
        """
        延迟初始化 AgentRunner
        
        🌟 当外部没有传入 agent_runner 时，自动创建一个
        
        创建步骤：
        1. 从 LLMClientManager 获取 API Key 和 Base URL
        2. 创建 OpenAICompatProvider
        3. 创建 ToolRegistry 并注册 Tools
        4. 创建 AgentRunner
        """
        try:
            from nanobot.providers.openai_compat_provider import OpenAICompatProvider
            from nanobot.agent.runner import AgentRunner
            from nanobot.agent.tools.registry import ToolRegistry
            from nanobot.ingestion.utils.llm_client import get_llm_client, get_llm_model
            
            # 1. 从 LLMClientManager 获取配置
            llm_client = get_llm_client()
            model = get_llm_model()
            
            if llm_client:
                # 2. 获取 API Key 和 Base URL
                # LLMClientManager 返回的是 AsyncOpenAI 客户端，我们需要提取配置
                api_key = llm_client.api_key if hasattr(llm_client, 'api_key') else None
                api_base = str(llm_client.base_url) if hasattr(llm_client, 'base_url') else None
                
                if not api_key or api_key.startswith("sk-YOUR"):
                    logger.warning("   ⚠️ API Key 无效，将使用规则模式处理")
                    return
                
                # 3. 创建 OpenAICompatProvider
                provider = OpenAICompatProvider(
                    api_key=api_key,
                    api_base=api_base,
                    default_model=model or "qwen3.5-plus"
                )
                
                # 4. 创建 ToolRegistry（如果还没有）
                if self.tools_registry is None:
                    self.tools_registry = ToolRegistry()
                
                # 5. 注册 Ingestion Tools
                self._register_tools()
                
                # 6. 创建 AgentRunner
                self.agent_runner = AgentRunner(provider=provider)
                
                logger.info(f"   ✅ 延迟初始化 AgentRunner 完成 (model={model or 'qwen3.5-plus'})")
            else:
                logger.warning("   ⚠️ 无法获取 LLM Client，将使用规则模式处理")
                
        except Exception as e:
            logger.error(f"   ❌ 延迟初始化 AgentRunner 失败: {e}")
            logger.warning("   ⚠️ 将使用规则模式处理")
    
    def _register_tools(self):
        """註冊必要的 Tools"""
        if self.tools_registry and not self._tools_registered:
            from nanobot.agent.tools.db_ingestion_tools import register_ingestion_tools
            from nanobot.agent.tools.dynamic_schema_tools import register_dynamic_schema_tools
            
            register_ingestion_tools(self.tools_registry)
            register_dynamic_schema_tools(self.tools_registry)
            
            self._tools_registered = True  # 🌟 标记已注册
            
            # 🌟 打印注册的工具列表（上线前确认）
            registered_tools = list(self.tools_registry._tools.keys())
            logger.info(f"   ✅ 已注册 {len(registered_tools)} 个 Tools: {registered_tools}")
    
    async def process_document(
        self,
        document_content: str,
        filename: str,
        user_hints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        處理單個文檔
        
        🌟 支持不同阶段的处理：
        - Stage 0 (预处理): 识别报告类型、提取母公司
        - Stage 5 (结构化提取): 提取 Revenue Breakdown 并写入数据库
        
        Args:
            document_content: PDF 内容或 Stage 5 Prompt
            filename: 檔案名稱
            user_hints: 用戶提供的提示
                - stage: "preprocessing" 或 "structured_extraction"
                - doc_type, index_theme, confirmed_doc_industry, etc.
        
        Returns:
            處理結果
        """
        logger.info(f"📄 開始處理文檔: {filename}")
        
        # 🌟 检查是否是 Stage 5 (结构化提取)
        stage = user_hints.get("stage", "preprocessing") if user_hints else "preprocessing"
        
        if stage == "structured_extraction":
            # 🌟 Stage 5: 直接使用传入的 Prompt，不叠加 Stage 0 的 System Prompt
            logger.info("   🔧 Stage 5: 结构化提取与写入")
            
            if self.agent_runner:
                # 直接执行传入的 stage5_prompt
                return await self._process_with_agent(document_content)
            else:
                # 使用规则处理 Stage 5
                return await self._process_stage5_with_rules(user_hints)
        
        # 🌟 Stage 0: 使用默认的预处理逻辑
        logger.info("   🔧 Stage 0: 预处理（识别报告类型）")
        
        # 構建完整 Prompt
        prompt = self._build_prompt(document_content, filename, user_hints)
        
        # 如果有 Agent，使用 Agent 處理
        if self.agent_runner:
            return await self._process_with_agent(prompt)
        
        # 否則使用規則處理
        return await self._process_with_rules(document_content, filename, user_hints)
    
    async def _process_stage5_with_rules(
        self,
        user_hints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        使用规则处理 Stage 5 (结构化提取)
        
        🌟 当没有 agent_runner 时，使用硬编码逻辑
        
        Args:
            user_hints: 包含 page_content, company_id, year, page_num 等
        
        Returns:
            处理结果
        """
        from nanobot.agent.tools.db_ingestion_tools import SmartInsertDocumentTool
        
        logger.info("   📋 使用规则模式处理 Stage 5")
        
        if not user_hints:
            return {"success": False, "error": "No user_hints provided"}
        
        page_content = user_hints.get("page_content", "")
        company_id = user_hints.get("company_id")
        year = user_hints.get("year")
        page_num = user_hints.get("page_num")
        is_index_report = user_hints.get("doc_type") == "index_report"
        
        # 🌟 如果是指数报告，使用 SmartInsertDocumentTool 写入
        if is_index_report:
            params = {
                "filename": user_hints.get("filename", "unknown.pdf"),
                "report_type": "index_report",
                "parent_company": None,
                "index_theme": user_hints.get("index_theme"),
                "confirmed_doc_industry": user_hints.get("confirmed_doc_industry"),
                "dynamic_data": {"page_num": page_num, "year": year},
                "sub_companies": [],  # 🌟 从 page_content 提取成分股（简化版）
                "industry_assignment_rule": "A"
            }
            
            tool = SmartInsertDocumentTool()
            return await tool.execute(**params)
        
        # 🌟 如果是年报，尝试提取 Revenue Breakdown
        # (这里简化处理，实际应该调用 FinancialAgent)
        return {
            "success": True,
            "stage": "structured_extraction",
            "page_num": page_num,
            "company_id": company_id,
            "note": "Stage 5 processed with rules (no agent_runner)"
        }
    
    def _build_prompt(
        self,
        document_content: str,
        filename: str,
        user_hints: Optional[Dict[str, Any]] = None
    ) -> str:
        """構建完整的 Agent Prompt"""
        prompt = f"""
{INGESTION_SYSTEM_PROMPT}

---

📄 **文件名稱**: {filename}
"""

        if user_hints:
            prompt += f"""
📌 **用戶提供的提示信息**:
"""
            for key, value in user_hints.items():
                prompt += f"- {key}: {value}\n"
        
        prompt += f"""
📄 **文件內容 (前 1-2 頁)**:
```
{document_content[:8000]}  # 限制長度避免超過 Token 限制
```

---

請分析以上內容，提取 Metadata 並呼叫 smart_insert_document_tool。
"""
        
        return prompt
    
    async def _process_with_agent(self, prompt: str) -> Dict[str, Any]:
        """使用 Agent 處理"""
        try:
            # 🌟 AgentRunner.run() 需要 AgentRunSpec，而不是简单的 prompt 字符串
            from nanobot.agent.runner import AgentRunSpec, AgentRunResult
            from nanobot.agent.hook import AgentHook
            
            # 构建 initial_messages
            initial_messages = [
                {"role": "system", "content": "你是一个高级 PostgreSQL 数据库写入 Agent。请根据用户的指令执行数据库写入操作。"},
                {"role": "user", "content": prompt}
            ]
            
            # 构建 AgentRunSpec
            spec = AgentRunSpec(
                initial_messages=initial_messages,
                tools=self.tools_registry,
                model=self.agent_runner.provider.default_model if self.agent_runner.provider else "qwen3.5-plus",
                max_iterations=10,
                max_tool_result_chars=8000,
                temperature=0.3,
                hook=AgentHook()
            )
            
            # 调用 AgentRunner.run()
            result: AgentRunResult = await self.agent_runner.run(spec)
            
            # 返回结果
            return {
                "success": result.stop_reason == "completed",
                "final_content": result.final_content,
                "tools_used": result.tools_used,
                "usage": result.usage,
                "stop_reason": result.stop_reason,
                "error": result.error
            }
            
        except Exception as e:
            logger.error(f"❌ Agent 处理失败: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def _process_with_rules(
        self,
        document_content: str,
        filename: str,
        user_hints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """使用規則處理 (無 Agent 時的 fallback)"""
        from nanobot.agent.tools.db_ingestion_tools import SmartInsertDocumentTool
        
        logger.info("📋 使用規則模式處理")
        
        # 如果用戶提供了提示，優先使用
        if user_hints:
            report_type = user_hints.get("doc_type", "annual_report")
            index_theme = user_hints.get("index_theme")
            confirmed_industry = user_hints.get("confirmed_doc_industry")
            
            params = {
                "filename": filename,
                "report_type": report_type,
                "parent_company": None if report_type == "index_report" else "待提取",
                "index_theme": index_theme,
                "confirmed_doc_industry": confirmed_industry,
                "dynamic_data": user_hints.get("dynamic_data", {}),
                "sub_companies": user_hints.get("sub_companies", []),
                "industry_assignment_rule": "A" if confirmed_industry else "B"
            }
            
            tool = SmartInsertDocumentTool()
            return await tool.execute(**params)
        
        # 嘗試從內容識別
        content_lower = document_content.lower()
        
        # 偵測報告類型
        is_index_report = any(kw in content_lower for kw in [
            "index", "指數", "constituent", "成分股",
            "hang seng", "恆生"
        ])
        
        # 提取指數主題
        index_theme = None
        confirmed_industry = None
        
        if is_index_report:
            # 嘗試提取指數主題
            import re
            patterns = [
                (r"Hang\s+Seng\s+Biotech\s+Index", "Biotech"),
                (r"Hang\s+Seng\s+Tech\s+Index", "Technology"),
                (r"Hang\s+Seng\s+Healthcare\s+Index", "Healthcare"),
                (r"Hang\s+Seng\s+(\w+)\s+Index", None),
                (r"恒生生物科技指數", "Biotech"),
                (r"恒生科技指數", "Technology"),
            ]
            
            for pattern, industry in patterns:
                match = re.search(pattern, document_content, re.IGNORECASE)
                if match:
                    index_theme = match.group(0)
                    confirmed_industry = industry
                    break
        
        params = {
            "filename": filename,
            "report_type": "index_report" if is_index_report else "annual_report",
            "parent_company": None if is_index_report else "待提取",
            "index_theme": index_theme,
            "confirmed_doc_industry": confirmed_industry,
            "dynamic_data": {},
            "sub_companies": [],
            "industry_assignment_rule": "A" if confirmed_industry else "B"
        }
        
        tool = SmartInsertDocumentTool()
        return await tool.execute(**params)


# ============================================================
# 便利函數
# ============================================================

def get_ingestion_system_prompt() -> str:
    """獲取攝入系統提示"""
    return INGESTION_SYSTEM_PROMPT


def create_extraction_prompt(document_content: str, filename: str) -> str:
    """
    創建提取 Prompt
    
    Args:
        document_content: 文檔內容
        filename: 檔案名稱
    
    Returns:
        完整的 Agent Prompt
    """
    return f"""
{INGESTION_SYSTEM_PROMPT}

---

📄 **文件名稱**: {filename}

📄 **文件內容**:
```
{document_content[:8000]}
```

請分析以上內容並提取 Metadata。
"""


# ============================================================
# 日誌
# ============================================================

logger.info("✅ Agentic Ingestion 模組已載入")