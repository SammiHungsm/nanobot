"""
Database Ingestion Tools - Smart Insert with Industry Assignment Rules

這些 Tools 用於智能寫入文檔數據，支持：
1. 規則 A：指數報告強制行業分配
2. 規則 B：AI 自動提取各行業
3. JSONB 動態屬性存儲
4. 事務性寫入保證數據一致性
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from loguru import logger

from nanobot.agent.tools.base import Tool
from pydantic import BaseModel, Field


# ============================================================
# Helper: 名称转 ID (Method A 的核心魔法)
# ============================================================

async def _resolve_company_id(
    db_client: Any,
    company_id: Optional[int],
    company_name: Optional[str],
    context: dict = None
) -> tuple[Optional[int], Optional[str]]:
    """
    🌟 名称转 ID 的核心魔法 (Method A - v1.4 修正版)
    
    核心邏輯變更（v1.4）：
    - ❌ 不再創建虛假股票代碼 (SUB_XX, PARENT)
    - ✅ 先查詢公司是否存在
    - ✅ 只有當公司真實存在時才返回其 ID
    
    LLM 只擅长理解文字（公司名称），不擅长记住数据库的 ID。
    这个函数让 Python 负责查 ID，LLM 只需要传公司名称。
    
    Args:
        db_client: 数据库客户端
        company_id: LLM 传入的 company_id（母公司）
        company_name: LLM 传入的公司名称（子公司/竞争对手等）
        context: 执行上下文（包含默认 company_id）
        
    Returns:
        tuple[company_id, error_message]: 返回解析后的 company_id，或错误信息
    """
    actual_company_id = company_id
    error_msg = None
    
    # 如果 LLM 传入了公司名称（不是母公司）
    if company_name and str(company_name).lower() not in ["", "none", "null"]:
        try:
            # 🌟 v1.4: 先查询公司是否存在（不创建虚假记录）
            existing_company = await db_client.search_companies_by_name(company_name)
            
            if existing_company:
                # 公司存在，使用其 ID
                actual_company_id = existing_company.get("id")
                logger.info(f"✅ 查詢公司成功: '{company_name}' -> ID={actual_company_id}")
            else:
                # 🌟 v1.4: 公司不存在，返回错误而不是创建虚假记录
                error_msg = f"公司 '{company_name}' 未找到。请确保该公司已在数据库中註冊。"
                logger.warning(f"⚠️ {error_msg}")
        except Exception as e:
            error_msg = f"查询公司名称 '{company_name}' 失败: {e}"
            logger.warning(f"⚠️ {error_msg}")
    
    # Fallback: 使用上下文中的默认 company_id
    if not actual_company_id and context:
        actual_company_id = context.get("company_id")
    
    return actual_company_id, error_msg

class GetDBSchemaTool(Tool):
    """
    [Tool] 獲取當前資料庫 Schema
    
    功能：
    - 返回所有表的結構
    - 返回 JSONB 欄位的 Keys
    - 用於 Agent 了解資料庫結構
    """
    
    @property
    def name(self) -> str:
        return "get_db_schema"
    
    @property
    def description(self) -> str:
        return (
            "Get the current database schema including tables, columns, and JSONB keys. "
            "Use this before inserting documents to understand the database structure."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_samples": {
                    "type": "boolean",
                    "description": "Include sample data for each table",
                    "default": False
                }
            }
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(self, include_samples: bool = False) -> str:
        """執行 Schema 獲取"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 獲取所有表的結構
                tables_info = {}
                
                # 獲取表列表
                tables = await conn.fetch(
                    """
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                    """
                )
                
                for table in tables:
                    table_name = table["table_name"]
                    
                    # 獲取列信息
                    columns = await conn.fetch(
                        """
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = $1
                        ORDER BY ordinal_position
                        """,
                        table_name
                    )
                    
                    tables_info[table_name] = {
                        "columns": [
                            {
                                "name": col["column_name"],
                                "type": col["data_type"],
                                "nullable": col["is_nullable"] == "YES",
                                "default": col["column_default"]
                            }
                            for col in columns
                        ]
                    }
                    
                    # 如果是 JSONB 列，獲取 Keys
                    jsonb_cols = [col["name"] for col in tables_info[table_name]["columns"] 
                                  if col["type"] == "jsonb"]
                    
                    if jsonb_cols:
                        for col_name in jsonb_cols:
                            try:
                                keys = await conn.fetch(
                                    f"""
                                    SELECT DISTINCT jsonb_object_keys({col_name}) AS key
                                    FROM {table_name}
                                    WHERE {col_name} IS NOT NULL
                                    LIMIT 50
                                    """
                                )
                                tables_info[table_name][f"{col_name}_keys"] = [k["key"] for k in keys]
                            except Exception:
                                pass
                    
                    # 獲取樣本數據
                    if include_samples:
                        try:
                            sample = await conn.fetchrow(
                                f"SELECT * FROM {table_name} LIMIT 1"
                            )
                            if sample:
                                tables_info[table_name]["sample"] = dict(sample)
                        except Exception:
                            pass
                
                result = {
                    "success": True,
                    "tables": tables_info,
                    "query_hint": """
📌 可用的主要表 (Schema v2.3):
- documents: 文檔主表 (owner_company_id, file_size_bytes)
- document_companies: 關聯公司表 (橋樑表)
- document_pages: 兜底表 (Zone 2, 只依賴 document_id) ← 🌟 包底庫！所有 PDF 頁面都在這裡
- financial_metrics: 扁平化財務指標表
- revenue_breakdown: 收入分解表 (segment_name, segment_type)
- key_personnel: 关键人员表 (董事、高管)
- shareholding_structure: 股东结构表
- review_queue: 人工審核隊列 (priority INTEGER 1-10)

🌟 持续学习规则 (Continuous Learning Loop):
如果你发现：
1. 结构化表 (revenue_breakdown, financial_metrics) 中没有用户要的数据
2. 但在 document_pages (包底库) 中找到了答案
请执行以下步骤：
① 分析找到数据的页面标题/关键词
② 调用 register_new_keyword 注册新关键词
③ 把找到的数据回填到结构化表
④ 这样下次处理类似文档时就不会漏接了！
"""
                }
                
                return json.dumps(result, indent=2, ensure_ascii=False, default=str)
                
        except Exception as e:
            logger.error(f"❌ 獲取 Schema 失敗: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            await db.close()


class SmartInsertDocumentTool(Tool):
    """
    [Tool] 智能寫入文檔 (支持規則 A/B)
    
    功能：
    - 自動判斷報告類型
    - 應用行業分配規則 A (強制) 或 B (AI提取)
    - 事務性寫入多個表
    - 支持動態屬性 (JSONB)
    """
    
    @property
    def name(self) -> str:
        return "smart_insert_document"
    
    @property
    def description(self) -> str:
        return (
            "Smart insert a document with industry assignment rules. "
            "Rule A: Force all companies to have the confirmed industry. "
            "Rule B: Use AI suggested industries for each company. "
            "Returns the inserted document_id and company count."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file being processed"
                },
                "report_type": {
                    "type": "string",
                    "enum": ["annual_report", "index_report"],
                    "description": "Type of report"
                },
                "parent_company": {
                    "type": ["string", "null"],
                    "description": "Parent company name (for annual reports)"
                },
                "index_theme": {
                    "type": ["string", "null"],
                    "description": "Index theme (for index reports, e.g., 'Hang Seng Biotech Index')"
                },
                "confirmed_doc_industry": {
                    "type": ["string", "null"],
                    "description": "Confirmed industry from report title (Rule A)"
                },
                "industry_assignment_rule": {
                    "type": "string",
                    "enum": ["A", "B"],
                    "description": "A = force industry to all companies, B = AI extraction per company"
                },
                "dynamic_data": {
                    "type": "object",
                    "description": "Dynamic attributes to store in JSONB column"
                },
                "sub_companies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "stock_code": {"type": ["string", "null"]},
                            "ai_industries": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "AI suggested industries (Rule B)"
                            }
                        }
                    },
                    "description": "List of companies to insert"
                }
            },
            "required": ["filename", "report_type"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        filename: str,
        report_type: str,
        parent_company: Optional[str] = None,
        index_theme: Optional[str] = None,
        confirmed_doc_industry: Optional[str] = None,
        industry_assignment_rule: str = "B",
        dynamic_data: Optional[Dict[str, Any]] = None,
        sub_companies: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        執行智能寫入 (Schema v2.3 完全對齊)
        
        🌟 Schema v2.3 變更：
        - documents.parent_company → 刪除（改用 owner_company_id）
        - documents.index_theme → 刪除（改用 companies.extra_data）
        - documents.confirmed_industry → 刪除（改用 document_companies）
        - documents.dynamic_attributes → 刪除（改用 companies.extra_data）
        - documents.status → processing_status
        
        Args:
            filename: 文件名
            report_type: 報告類型 ('annual_report' 或 'index_report')
            parent_company: 母公司名稱 (年報用)
            index_theme: 指數主題 (指數報告用)
            confirmed_doc_industry: 確認的行業 (規則 A)
            industry_assignment_rule: 行業分配規則 ('A' 或 'B')
            dynamic_data: 動態屬性 (存入 companies.extra_data)
            sub_companies: 子公司/成分股列表
        """
        from nanobot.ingestion.repository.db_client import DBClient
        import uuid
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                async with conn.transaction():
                    # 🌟 1. 處理母公司 (只存基本資訊，不存動態屬性)
                    owner_company_id = None
                    if parent_company:
                        # Upsert 母公司（只存基本資訊）
                        owner_company_id = await conn.fetchval(
                            """
                            INSERT INTO companies (stock_code, name_en) 
                            VALUES ($1, $2)
                            ON CONFLICT (stock_code) DO UPDATE SET name_en = $2
                            RETURNING id
                            """,
                            "PARENT",  # 临时 stock_code
                            parent_company
                        )
                    
                    # 🌟 2. 寫入主 Document (將動態屬性寫入 documents.dynamic_attributes！)
                    # 🌟 修正：無論有沒有母公司，index_theme 和 dynamic_data 都要存到 documents 表
                    doc_id_str = f"agent_{uuid.uuid4().hex[:8]}"
                    
                    # 🌟 組整動態屬性：index_theme + dynamic_data
                    doc_dynamic_attrs = json.dumps({
                        "index_theme": index_theme,
                        "confirmed_doc_industry": confirmed_doc_industry,
                        "industry_assignment_rule": industry_assignment_rule,
                        **(dynamic_data or {})
                    })
                    
                    doc_result = await conn.fetchrow(
                        """
                        INSERT INTO documents (
                            doc_id, filename, report_type, owner_company_id, processing_status, dynamic_attributes
                        ) VALUES ($1, $2, $3, $4, 'pending', $5::jsonb)
                        RETURNING id
                        """,
                        doc_id_str, filename, report_type, owner_company_id, doc_dynamic_attrs
                    )
                    doc_id_int = doc_result["id"]
                    
                    # 🌟 3. 寫入關聯公司 (document_companies 橋樑表)
                    companies_inserted = 0
                    if sub_companies:
                        for comp in sub_companies:
                            company_name = comp.get("name")
                            stock_code = comp.get("stock_code") or f"UNKNOWN_{uuid.uuid4().hex[:4]}"
                            ai_industries = comp.get("ai_industries", [])
                            
                            is_rule_a = (industry_assignment_rule == "A" and confirmed_doc_industry)
                            
                            # Upsert 公司實體 (Schema v2.3)
                            comp_id = await conn.fetchval(
                                """
                                INSERT INTO companies (
                                    stock_code, name_en, confirmed_industry, is_industry_confirmed
                                ) VALUES ($1, $2, $3, $4)
                                ON CONFLICT (stock_code) DO UPDATE SET name_en = $2
                                RETURNING id
                                """,
                                stock_code, company_name,
                                confirmed_doc_industry if is_rule_a else None,
                                is_rule_a
                            )
                            
                            # 建立多對多關聯 (document_companies)
                            await conn.execute(
                                """
                                INSERT INTO document_companies (
                                    document_id, company_id, relation_type,
                                    extracted_industries, extraction_source
                                ) VALUES ($1, $2, 'mentioned', $3::jsonb, $4)
                                """,
                                doc_id_int, comp_id,
                                json.dumps(ai_industries) if not is_rule_a else None,
                                "confirmed" if is_rule_a else "ai_predict"
                            )
                            companies_inserted += 1
                    
                    result = {
                        "success": True,
                        "document_id": doc_id_str,
                        "companies_inserted": companies_inserted,
                        "rule_applied": industry_assignment_rule,
                        "confirmed_industry": confirmed_doc_industry
                    }
                    return json.dumps(result, ensure_ascii=False)
                    
        except Exception as e:
            logger.error(f"❌ Smart insert failed: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            await db.close()


class UpdateDocumentStatusTool(Tool):
    """
    [Tool] 更新文檔處理狀態
    """
    
    @property
    def name(self) -> str:
        return "update_document_status"
    
    @property
    def description(self) -> str:
        return (
            "Update the processing status of a document. "
            "Use this after processing to mark as completed, failed, or for review."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "integer",
                    "description": "ID of the document to update"
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "processing", "completed", "failed", "review"],
                    "description": "New status"
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes about the status change"
                }
            },
            "required": ["document_id", "status"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        document_id: int,
        status: str,
        notes: Optional[str] = None,
        **kwargs  # 🌟 防弹参数：吸收 LLM 幻觉产生的多余参数
    ) -> str:
        """更新文檔狀態 (Schema v2.3: processing_status)"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 🌟 更新主表狀態 (Schema v2.3: processing_status, not status)
                await conn.execute(
                    "UPDATE documents SET processing_status = $1, updated_at = NOW() WHERE id = $2",
                    status,
                    document_id
                )
                
                result = {
                    "success": True,
                    "document_id": document_id,
                    "new_status": status,
                    "notes": notes
                }
                
                return json.dumps(result, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"❌ Status update failed: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            await db.close()


class UpdateDynamicAttributesTool(Tool):
    """
    [Tool] 更新文檔的動態屬性 (JSONB)
    """
    
    @property
    def name(self) -> str:
        return "update_dynamic_attributes"
    
    @property
    def description(self) -> str:
        return (
            "Update the dynamic_attributes JSONB column of a document. "
            "Use this to add or update flexible metadata that doesn't fit in fixed columns."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "integer",
                    "description": "ID of the document"
                },
                "attributes": {
                    "type": "object",
                    "description": "Key-value pairs to set in dynamic_attributes"
                },
                "merge": {
                    "type": "boolean",
                    "description": "If true, merge with existing attributes; if false, replace",
                    "default": True
                }
            },
            "required": ["document_id", "attributes"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        document_id: int,
        attributes: Dict[str, Any],
        merge: bool = True,
        **kwargs  # 🌟 防弹参数：吸收 LLM 幻觉产生的多余参数
    ) -> str:
        """
        更新動態屬性
        
        🌟 Schema v2.3: 动态属性存储在 documents.dynamic_attributes
        - 修正：指数报告的 owner_company_id 为 NULL，不能依赖 companies 表
        - 直接更新 documents.dynamic_attributes，确保所有报告类型都能正常工作
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 🌟 修正：直接更新 documents 表，不依赖 owner_company_id
                # 🌟 修正：指数报告的 owner_company_id 为 NULL，必须直接更新 documents 表
                if merge:
                    # 合併現有屬性 (Schema v2.3)
                    result = await conn.fetchrow(
                        """
                        UPDATE documents 
                        SET dynamic_attributes = COALESCE(dynamic_attributes, '{}'::jsonb) || $1::jsonb,
                            updated_at = NOW()
                        WHERE id = $2
                        RETURNING dynamic_attributes
                        """,
                        json.dumps(attributes),
                        document_id
                    )
                else:
                    # 替換所有屬性 (Schema v2.3)
                    result = await conn.fetchrow(
                        """
                        UPDATE documents 
                        SET dynamic_attributes = $1::jsonb,
                            updated_at = NOW()
                        WHERE id = $2
                        RETURNING dynamic_attributes
                        """,
                        json.dumps(attributes),
                        document_id
                    )
                
                return json.dumps({
                    "success": True,
                    "document_id": document_id,
                    "dynamic_attributes": result["dynamic_attributes"] if result else None
                }, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"❌ Update dynamic attributes failed: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            await db.close()


class CreateReviewRecordTool(Tool):
    """
    [Tool] 創建人工審核記錄
    """
    
    @property
    def name(self) -> str:
        return "create_review_record"
    
    @property
    def description(self) -> str:
        return (
            "Create a human review record for a document. "
            "Use this when AI extraction has low confidence or needs manual verification."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "ID of the document needing review"},
                "review_type": {"type": "string", "enum": ["industry_assignment", "company_extraction", "data_quality", "other"]},
                "priority": {
                    "type": "integer", 
                    "description": "Priority level from 1 (highest) to 10 (lowest)",
                    "default": 5
                },
                "issue_description": {
                    "type": "string",
                    "description": "Description of what needs review (AI suggestion or issue)"
                }
            },
            "required": ["document_id", "review_type"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        document_id: int,
        review_type: str,
        priority: int = 5,
        issue_description: Optional[str] = None
    ) -> str:
        """創建審核記錄"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 🌟 Schema v2.3: 表名 review_queue，欄位 priority(整數), issue_description
                # 🌟 Schema v2.3: 移除 ON CONFLICT，因為可能同一份文件有多個審核事項
                result = await conn.fetchrow(
                    """
                    INSERT INTO review_queue (document_id, review_type, priority, issue_description, status)
                    VALUES ($1, $2, $3, $4, 'pending')
                    RETURNING id, status
                    """,
                    document_id,
                    review_type,
                    priority,
                    issue_description
                )
                
                return json.dumps({
                    "success": True,
                    "review_id": result["id"],
                    "document_id": document_id,
                    "status": result["status"],
                    "priority": priority,
                    "review_type": review_type
                }, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"❌ Create review record failed: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            await db.close()


class RegisterNewKeywordTool(Tool):
    """
    [Tool] 註冊新的搜索關鍵字
    
    功能：
    - Agent 發現新的財報專有名詞時，將其註冊到全局知識庫
    - 防呆機制：禁止太短或太通用的詞
    - 支持分級制度：gold/silver/bronze
    
    使用場景：
    - 在財報中發現「營運地區收益剖析」這種特殊標題
    - Agent 應該呼叫此 Tool 將其加入知識庫
    - 下次處理其他公司年報時，就能自動識別這個詞
    """
    
    @property
    def name(self) -> str:
        return "register_new_keyword"
    
    @property
    def description(self) -> str:
        return (
            "Register a new search keyword to the global knowledge base. "
            "Use this when you discover a unique term that should be recognized in future documents. "
            "Example: If you find '營運地區收益剖析' as a revenue section title, register it so the system "
            "can automatically find similar sections in other annual reports."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["revenue_breakdown", "key_personnel", "esg", "financial_metrics"],
                    "description": "Category of the keyword"
                },
                "keyword": {
                    "type": "string",
                    "description": "New keyword to register (e.g., '營運地區收益剖析', 'Geographical Revenue Split')"
                },
                "confidence": {
                    "type": "string",
                    "enum": ["gold", "silver", "bronze"],
                    "default": "bronze",
                    "description": "Confidence level. Use 'bronze' for AI-discovered keywords (pending review)"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this keyword is useful and should be added"
                }
            },
            "required": ["category", "keyword"]
        }
    
    @property
    def read_only(self) -> bool:
        return False  # 會寫入 JSON
    
    async def execute(
        self,
        category: str,
        keyword: str,
        confidence: str = "bronze",
        reasoning: Optional[str] = None,
        **kwargs  # 🌟 防弹参数：吸收 LLM 幻觉产生的多余参数
    ) -> str:
        """註冊新關鍵字"""
        from nanobot.ingestion.utils.keyword_manager import KeywordManager
        
        km = KeywordManager()
        
        # 调用 KeywordManager 的 add_keyword（已有防呆机制）
        result = km.add_keyword(
            category=category,
            keyword=keyword,
            source="agent",
            confidence=confidence,
            reasoning=reasoning or "Agent discovered during document processing"
        )
        
        if result["success"]:
            logger.info(f"🧠 Agent 發現新關鍵字: '{keyword}' → {category}")
        
        return json.dumps(result, indent=2, ensure_ascii=False)


class GetKeywordStatsTool(Tool):
    """
    [Tool] 獲取關鍵字庫統計信息
    
    功能：
    - 返回各類別的關鍵字數量
    - 返回低效能關鍵字（假陽性）
    - 幫助 Agent 了解知識庫狀況
    """
    
    @property
    def name(self) -> str:
        return "get_keyword_stats"
    
    @property
    def description(self) -> str:
        return (
            "Get statistics about the keyword knowledge base. "
            "Returns total keywords, confidence distribution, and low-performance keywords."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category (optional)",
                    "default": None
                }
            }
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(self, category: Optional[str] = None) -> str:
        """獲取統計信息"""
        from nanobot.ingestion.utils.keyword_manager import KeywordManager
        
        km = KeywordManager()
        stats = km.get_stats(category)
        
        return json.dumps(stats, indent=2, ensure_ascii=False)


class InsertKeyPersonnelTool(Tool):
    """
    [Tool] 写入关键人员数据
    
    功能：
    - 写入 key_personnel 表
    - 支持 board_role, committee_membership 等
    - 🌟 支持通过公司名称写入（Method A）
    
    Schema v2.3:
    - name_en, name_zh, position_title_en
    - role, board_role (Executive/Non-Executive/Independent)
    - committee_membership (JSONB 数组)
    """
    
    @property
    def name(self) -> str:
        return "insert_key_personnel"
    
    @property
    def description(self) -> str:
        return (
            "Insert key personnel (directors, executives) into key_personnel table. "
            "Use this when you find board members, management team, or committee members. "
            "🌟 Supports company_name for subsidiary data (Method A)."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": ["integer", "null"], 
                    "description": "母公司的 ID（如果是母公司数据，请填此项）"
                },
                "company_name": {
                    "type": ["string", "null"], 
                    "description": "🌟 如果数据属于子公司、关联公司或竞争对手，请填写他们的公司名称，系统会自动查找或创建对应的 ID"
                },
                "document_id": {"type": ["integer", "null"], "description": "Document ID"},
                "personnel_list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name_en": {"type": "string", "description": "English name"},
                            "name_zh": {"type": ["string", "null"], "description": "Chinese name"},
                            "position_title_en": {"type": ["string", "null"], "description": "Position title"},
                            "board_role": {
                                "type": "string",
                                "enum": ["Executive", "Non-Executive", "Independent Non-Executive"],
                                "description": "Board role type"
                            },
                            "committee_membership": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Committee memberships (e.g., ['Audit Committee', 'Remuneration Committee'])"
                            },
                            "biography": {"type": ["string", "null"], "description": "Brief biography"}
                        },
                        "required": ["name_en"]
                    },
                    "description": "List of key personnel to insert"
                }
            },
            "required": ["personnel_list"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, personnel_list: List[Dict], company_id: int = None, 
                      company_name: str = None, document_id: Optional[int] = None, 
                      context: dict = None, **kwargs) -> str:
        """写入关键人员
        
        🌟 Method A: 支持 company_name 参数
        🌟 防弹参数：
        - **kwargs 吸收 LLM 幻觉产生的多余参数
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        # 🌟 v4.5: Always prefer context's document_id
        if context is None:
            context = kwargs.get("context", {})
        if context and context.get("document_id"):
            document_id = context["document_id"]
        
        db = DBClient()
        await db.connect()
        
        try:
            # 🌟 Method A: 名称转 ID
            actual_company_id, error = await _resolve_company_id(
                db_client=db,
                company_id=company_id,
                company_name=company_name,
                context=context
            )
            
            if error:
                return json.dumps({"success": False, "error": error}, indent=2)
            
            if not actual_company_id:
                return json.dumps({
                    "success": False, 
                    "error": "必须提供 company_id 或 company_name"
                }, indent=2)
            
            inserted_count = 0
            
            async with db.connection() as conn:
                for person in personnel_list:
                    name_en = person.get("name_en")
                    
                    if not name_en:
                        continue  # 🌟 v1.2: 跳过没有 name_en 的记录
                    
                    # committee_membership 需要转为 JSON
                    committee_json = json.dumps(person.get("committee_membership", [])) if person.get("committee_membership") else None
                    
                    # 🌟 v1.2: 先检查是否存在，再决定 INSERT 或 UPDATE
                    existing = await conn.fetchval(
                        "SELECT id FROM key_personnel WHERE company_id = $1 AND name_en = $2",
                        actual_company_id,  # 🌟 使用转换后的 ID
                        name_en
                    )
                    
                    if existing:
                        await conn.execute(
                            """
                            UPDATE key_personnel SET
                                position_title_en = $1,
                                board_role = $2,
                                committee_membership = $3::jsonb,
                                document_id = $4
                            WHERE id = $5
                            """,
                            person.get("position_title_en"),
                            person.get("board_role"),
                            committee_json,
                            document_id,
                            existing
                        )
                    else:
                        await conn.execute(
                            """
                            INSERT INTO key_personnel 
                            (company_id, document_id, name_en, name_zh, position_title_en, board_role, committee_membership, biography)
                            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
                            """,
                            actual_company_id,  # 🌟 使用转换后的 ID
                            document_id,
                            name_en,
                            person.get("name_zh"),
                            person.get("position_title_en"),
                            person.get("board_role"),
                            committee_json,
                            person.get("biography")
                        )
                    inserted_count += 1
            
            return json.dumps({
                "success": True,
                "company_id": actual_company_id,
                "company_name": company_name,
                "inserted_count": inserted_count,
                "message": f"✅ 写入 {inserted_count} 位关键人员 (公司: {company_name or f'ID={actual_company_id}'})"
            }, indent=2, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()


class InsertFinancialMetricsTool(Tool):
    """
    [Tool] 写入财务指标数据
    
    功能：
    - 写入 financial_metrics 表
    - 支持标准化货币单位
    - 🌟 支持通过公司名称写入（Method A）
    
    Schema v2.3:
    - metric_name (如 revenue, net_income, total_assets)
    - value, unit, standardized_value
    """
    
    @property
    def name(self) -> str:
        return "insert_financial_metrics"
    
    @property
    def description(self) -> str:
        return (
            "Insert financial metrics into financial_metrics table. "
            "Use this when you find financial figures like revenue, profit, assets, liabilities. "
            "🌟 Supports company_name for subsidiary/competitor data (Method A)."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": ["integer", "null"], 
                    "description": "母公司的 ID（如果是母公司数据，请填此项）"
                },
                "company_name": {
                    "type": ["string", "null"], 
                    "description": "🌟 如果数据属于子公司、关联公司或竞争对手，请填写他们的公司名称，系统会自动查找或创建对应的 ID"
                },
                "year": {"type": "integer", "description": "Financial year"},
                "metrics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "metric_name": {"type": "string", "description": "Metric name (e.g., 'revenue', 'net_income')"},
                            "value": {"type": "number", "description": "Raw value"},
                            "unit": {"type": "string", "description": "Unit (e.g., 'HKD', 'RMB')"},
                            "standardized_value": {"type": ["number", "null"], "description": "Value in HKD"},
                            "source_page": {"type": ["integer", "null"], "description": "Source page number"}
                        },
                        "required": ["metric_name", "value"]
                    },
                    "description": "List of financial metrics"
                }
            },
            "required": ["year", "metrics"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, year: int, metrics: List[Dict], company_id: int = None, 
                      company_name: str = None, document_id: int = None,
                      context: dict = None, **kwargs) -> str:
        """写入财务指标
        
        🌟 Method A: 支持 company_name 参数
        - 如果传入 company_name，系统会自动查找或创建公司 ID
        - LLM 不需要记住 ID，只需要传公司名称
        
        🌟 防弹参数：
        - **kwargs 吸收 LLM 幻觉产生的多余参数（如 document_id）
        
        🌟 v4.5: context.document_id fallback
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        # 🌟 v4.5: Always prefer context's document_id
        if context is None:
            context = kwargs.get("context", {})
        if context and context.get("document_id"):
            document_id = context["document_id"]
        
        db = DBClient()
        await db.connect()
        
        try:
            # 🌟 Method A: 名称转 ID
            actual_company_id, error = await _resolve_company_id(
                db_client=db,
                company_id=company_id,
                company_name=company_name,
                context=context
            )
            
            if error:
                return json.dumps({"success": False, "error": error}, indent=2)
            
            if not actual_company_id:
                return json.dumps({
                    "success": False, 
                    "error": "必须提供 company_id 或 company_name"
                }, indent=2)
            
            inserted_count = 0
            updated_count = 0
            
            async with db.connection() as conn:
                for metric in metrics:
                    # 🌟 使用 ON CONFLICT DO UPDATE 避免重複插入
                    result = await conn.execute(
                        """
                        INSERT INTO financial_metrics 
                        (company_id, year, metric_name, value, unit, standardized_value, source_page)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (company_id, year, fiscal_period, metric_name) 
                        DO UPDATE SET 
                            value = EXCLUDED.value,
                            unit = EXCLUDED.unit,
                            standardized_value = EXCLUDED.standardized_value,
                            source_page = EXCLUDED.source_page
                        """,
                        actual_company_id,  # 🌟 使用转换后的 ID
                        year,
                        metric.get("metric_name"),
                        metric.get("value"),
                        metric.get("unit", "HKD"),
                        metric.get("standardized_value"),
                        metric.get("source_page")
                    )
                    # 检查是插入还是更新
                    if "INSERT 0 1" in str(result):
                        inserted_count += 1
                    else:
                        updated_count += 1
            
            return json.dumps({
                "success": True,
                "company_id": actual_company_id,
                "company_name": company_name,
                "year": year,
                "inserted_count": inserted_count,
                "updated_count": updated_count,
                "message": f"✅ 寫入 {inserted_count} 個新指標，更新 {updated_count} 個現有指標 (公司: {company_name or f'ID={actual_company_id}'})"
            }, indent=2, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()


class InsertShareholdingTool(Tool):
    """
    [Tool] 寫入股東結構數據
    
    🌟 支持通过公司名称写入（Method A）
    
    Schema v2.3 實際結構：
    - shareholder_name, shareholder_type (不是 share_type!)
    - shares_held, percentage, is_controlling, is_institutional
    """
    
    @property
    def name(self) -> str:
        return "insert_shareholding"
    
    @property
    def description(self) -> str:
        return (
            "Insert shareholding structure into shareholding_structure table. "
            "Use this when you find shareholder names and ownership percentages. "
            "Optional fields: shareholder_type, is_controlling, is_institutional, trust_name, trustee_name. "
            "🌟 Supports company_name for subsidiary data (Method A). "
            "Note: year and notes columns removed in v4.6."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": ["integer", "null"], 
                    "description": "母公司的 ID（如果是母公司数据，请填此项）"
                },
                "company_name": {
                    "type": ["string", "null"], 
                    "description": "🌟 如果数据属于子公司、关联公司或竞争对手，请填写他们的公司名称，系统会自动查找或创建对应的 ID"
                },
                "shareholders": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "shareholder_name": {"type": "string", "description": "Shareholder name"},
                            "shareholder_type": {"type": ["string", "null"], "description": "Shareholder type (e.g., 'individual', 'corporate', 'institutional')"},
                            "shares_held": {"type": ["number", "null"], "description": "Number of shares"},
                            "percentage": {"type": "number", "description": "Ownership percentage"},
                            "is_controlling": {"type": ["boolean", "null"], "description": "Is controlling shareholder"},
                            "is_institutional": {"type": ["boolean", "null"], "description": "Is institutional investor"},
                            "trust_name": {"type": ["string", "null"], "description": "Trust name if applicable"},
                            "trustee_name": {"type": ["string", "null"], "description": "Trustee name if applicable"}
                        },
                "required": ["shareholder_name", "percentage"]
                    },
                    "description": "List of shareholders"
                }
            },
            "required": ["shareholders"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, shareholders: List[Dict], company_id: int = None,
                      company_name: str = None, document_id: int = None,
                      context: dict = None, **kwargs) -> str:
        """寫入股東結構
        
        🌟 Method A: 支持 company_name 参数
        🌟 v4.6: 移除 year 和 notes（冗餘欄位）
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        # 🌟 v4.5: Always prefer context's document_id
        if context is None:
            context = kwargs.get("context", {})
        if context and context.get("document_id"):
            document_id = context["document_id"]
        
        db = DBClient()
        await db.connect()
        
        try:
            # 🌟 Method A: 名称转 ID
            actual_company_id, error = await _resolve_company_id(
                db_client=db,
                company_id=company_id,
                company_name=company_name,
                context=context
            )
            
            if error:
                return json.dumps({"success": False, "error": error}, indent=2)
            
            if not actual_company_id:
                return json.dumps({
                    "success": False, 
                    "error": "必须提供 company_id 或 company_name"
                }, indent=2)
            
            inserted_count = 0
            
            async with db.connection() as conn:
                for sh in shareholders:
                    await conn.execute(
                        """
                        INSERT INTO shareholding_structure 
                        (company_id, shareholder_name, shareholder_type, shares_held, percentage,
                         is_controlling, is_institutional, trust_name, trustee_name, source_document_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        """,
                        actual_company_id,
                        sh.get("shareholder_name"),
                        sh.get("shareholder_type"),
                        sh.get("shares_held"),
                        sh.get("percentage"),
                        sh.get("is_controlling"),
                        sh.get("is_institutional"),
                        sh.get("trust_name"),
                        sh.get("trustee_name"),
                        document_id
                    )
                    inserted_count += 1
            
            return json.dumps({
                "success": True,
                "company_id": actual_company_id,
                "company_name": company_name,
                "source_document_id": document_id,
                "inserted_count": inserted_count,
                "message": f"✅ 寫入 {inserted_count} 個股東 (公司: {company_name or f'ID={actual_company_id}'})"
            }, indent=2, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()


class InsertRevenueBreakdownTool(Tool):
    """
    [Tool] 写入收入分解数据 🌟 致命遗漏修复
    
    功能：
    - 写入 revenue_breakdown 表
    - 支持 business/geography/product 三种 segment_type
    - Agent 见到「按地区划分收入」时必须用这个 Tool
    - 🌟 支持通过公司名称写入（Method A）
    
    Schema v2.3:
    - segment_name, segment_type (business/geography/product)
    - revenue_amount, revenue_percentage
    """
    
    @property
    def name(self) -> str:
        return "insert_revenue_breakdown"
    
    @property
    def description(self) -> str:
        return (
            "Insert revenue breakdown data into revenue_breakdown table. "
            "Use this when you find revenue split by business segments, geography, or products. "
            "⚠️ This is NOT the same as financial_metrics! Use this specifically for revenue breakdown tables. "
            "🌟 Supports company_name for subsidiary data (Method A)."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": ["integer", "null"], 
                    "description": "母公司的 ID（如果是母公司数据，请填此项）"
                },
                "company_name": {
                    "type": ["string", "null"], 
                    "description": "🌟 如果数据属于子公司、关联公司或竞争对手，请填写他们的公司名称，系统会自动查找或创建对应的 ID"
                },
                "year": {"type": "integer", "description": "Financial year"},
                "document_id": {"type": ["integer", "null"], "description": "Source document ID"},
                "segments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "segment_name": {"type": "string", "description": "Segment name (e.g., 'Europe', 'Hong Kong', 'Consumer Products')"},
                            "segment_type": {
                                "type": "string",
                                "enum": ["business", "geography", "product"],
                                "description": "Type of segmentation"
                            },
                            "revenue_amount": {"type": ["number", "null"], "description": "Revenue amount in original currency"},
                            "revenue_percentage": {"type": ["number", "null"], "description": "Percentage of total revenue"},
                            "currency": {"type": "string", "default": "HKD", "description": "Currency code"}
                        },
                        "required": ["segment_name"]
                    },
                    "description": "List of revenue segments"
                }
            },
            "required": ["year", "segments"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, year: int, segments: List[Dict], company_id: int = None,
                      company_name: str = None, document_id: Optional[int] = None, 
                      context: dict = None, **kwargs) -> str:
        """写入收入分解
        
        🌟 Method A: 支持 company_name 参数
        🌟 防弹参数：**kwargs 吸收 LLM 幻觉产生的多余参数
        🌟 v4.5: context.document_id fallback
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        # 🌟 v4.5: Always prefer context's document_id
        if context is None:
            context = kwargs.get("context", {})
        if context and context.get("document_id"):
            document_id = context["document_id"]
        elif document_id is not None:
            try:
                document_id = int(document_id)
            except (ValueError, TypeError):
                document_id = None
        
        db = DBClient()
        await db.connect()
        
        try:
            # 🌟 Method A: 名称转 ID
            actual_company_id, error = await _resolve_company_id(
                db_client=db,
                company_id=company_id,
                company_name=company_name,
                context=context
            )
            
            if error:
                return json.dumps({"success": False, "error": error}, indent=2)
            
            if not actual_company_id:
                return json.dumps({
                    "success": False, 
                    "error": "必须提供 company_id 或 company_name"
                }, indent=2)
            
            # 🌟 v1.3: 强制转换 actual_company_id 为整数（防止 asyncpg 类型错误）
            try:
                actual_company_id = int(actual_company_id)
            except (ValueError, TypeError):
                return json.dumps({
                    "success": False,
                    "error": f"company_id 必须是整数，收到: {actual_company_id}"
                }, indent=2)
            
            inserted_count = 0
            
            async with db.connection() as conn:
                for seg in segments:
                    await conn.execute(
                        """
                        INSERT INTO revenue_breakdown 
                        (company_id, year, segment_name, segment_type, revenue_amount, 
                         revenue_percentage, currency, source_document_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (company_id, year, segment_name, segment_type)  -- 🌟 v1.2: 修正约束名
                        DO UPDATE SET 
                            revenue_amount = $5,
                            revenue_percentage = $6,
                            source_document_id = $8
                        """,
                        actual_company_id,  # 🌟 v1.3: 已验证为整数类型
                        year,
                        seg.get("segment_name"),
                        seg.get("segment_type", "geography"),
                        seg.get("revenue_amount"),
                        seg.get("revenue_percentage"),
                        seg.get("currency", "HKD"),
                        document_id
                    )
                    inserted_count += 1
            
            logger.info(f"✅ 写入 {inserted_count} 个收入分解项")
            
            return json.dumps({
                "success": True,
                "company_id": actual_company_id,
                "company_name": company_name,
                "year": year,
                "inserted_count": inserted_count,
                "message": f"✅ 写入 {inserted_count} 个收入分解项到 revenue_breakdown 表 (公司: {company_name or f'ID={actual_company_id}'})"
            }, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"❌ 写入收入分解失败: {e}")
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()


from typing import Any, Optional
import json
from loguru import logger
# 假設你的 Tool 基類已經 import，保留你原本的 import

class InsertEntityRelationTool(Tool):
    """
    [Tool] 写入实体关系（知识图谱） 🌟 知识图谱遗漏修复 (严格强约束版)
    """
    
    @property
    def name(self) -> str:
        return "insert_entity_relation"
    
    @property
    def description(self) -> str:
        return (
            "Insert entity relation (knowledge graph) into entity_relations table. "
            "⚠️ STRICT RULE: You MUST use standardized official names for entities. "
            "Do NOT use pronouns like 'The Company', 'The Group', or 'It'. "
            "Resolve them to the actual company name before inserting."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "Source document ID"},
                "source_entity_type": {
                    "type": "string",
                    "enum": ["person", "company", "event", "location"],
                    "description": "Type of the source entity"
                },
                "source_entity_name": {
                    "type": "string", 
                    "description": "Name of the source entity (e.g., 'Tencent Holdings' NOT 'The Group')"
                },
                "relation_type": {
                    "type": "string",
                    # 🌟 第 1 層防護：在 Schema 中嚴格鎖死 Enum，不讓 LLM 亂作夢！
                    "enum": [
                        "executive_of",      # 董事/高管
                        "subsidiary_of",     # 子公司
                        "acquired_by",       # 被收購
                        "partnered_with",    # 合作夥伴
                        "competitor_of",     # 競爭對手
                        "invested_in",       # 投資
                        "supplier_of",       # 供應商
                        "customer_of"        # 客戶
                    ],
                    "description": "Type of relation. YOU MUST STRICTLY CHOOSE FROM THIS LIST ONLY."
                },
                "target_entity_type": {
                    "type": "string",
                    "enum": ["person", "company", "event", "location"],
                    "description": "Type of the target entity"
                },
                "target_entity_name": {
                    "type": "string", 
                    "description": "Name of the target entity"
                },
                "confidence_score": {
                    "type": "number",
                    "default": 0.8,
                    "description": "Confidence of the extraction (0.0-1.0)"
                },
                "event_year": {"type": ["integer", "null"], "description": "Year of the event/relation"}
            },
            "required": ["document_id", "source_entity_type", "source_entity_name", 
                         "relation_type", "target_entity_type", "target_entity_name"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        document_id: int,
        source_entity_type: str,
        source_entity_name: str,
        relation_type: str,
        target_entity_type: str,
        target_entity_name: str,
        confidence_score: float = 0.8,
        event_year: Optional[Any] = None,
        context: dict = None,  # 🌟 v4.5: Context fallback for document_id
        **kwargs  # 🌟 防弹参数：吸收 LLM 幻觉产生的多余参数
    ) -> str:
        """写入实体关系"""
        
        # 🌟 v4.5: Always prefer context's document_id (overrides LLM's hallucinated value)
        if context and context.get("document_id"):
            document_id = context["document_id"]
            logger.info(f"   🔧 Using context document_id={document_id} instead of LLM's value")
        elif document_id == 0:
            logger.warning(f"⚠️ LLM passed document_id=0 and no context fallback available, skipping")
            return json.dumps({"success": False, "error": "document_id is 0 and no context fallback available"}, ensure_ascii=False)
        
        # ==================================================
        # 🌟 第 2 層防護：Python 邏輯層過濾 (防止 LLM 繞過 Schema)
        # ==================================================
        allowed_relations = {
            "executive_of", "subsidiary_of", "acquired_by", 
            "partnered_with", "competitor_of", "invested_in", 
            "supplier_of", "customer_of"
        }
        
        if relation_type not in allowed_relations:
            logger.warning(f"⚠️ LLM 試圖寫入非法的關係類型: {relation_type}，已拒絕。")
            return json.dumps({
                "success": False,
                "error": f"STRICT RULE VIOLATION: '{relation_type}' is not allowed. You MUST choose from {list(allowed_relations)}."
            }, ensure_ascii=False)
            
        # 擋下沒有意義的代名詞實體
        bad_words = ["the group", "the company", "it", "本公司", "本集團"]
        if source_entity_name.lower() in bad_words or target_entity_name.lower() in bad_words:
            logger.warning(f"⚠️ LLM 試圖寫入代名詞實體: {source_entity_name} -> {target_entity_name}，已拒絕。")
            return json.dumps({
                "success": False,
                "error": "STRICT RULE VIOLATION: You cannot use pronouns ('The Company', '本集團') as entity names. Please resolve to the actual proper noun."
            }, ensure_ascii=False)
        # ==================================================
        
        from nanobot.ingestion.repository.db_client import DBClient
        
        actual_event_year = None
        if event_year is not None:
            try:
                actual_event_year = int(event_year)
            except (ValueError, TypeError):
                logger.warning(f"⚠️ 無法將 event_year '{event_year}' 轉換為整數，將設為 NULL")
                actual_event_year = None

        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO entity_relations 
                    (document_id, source_entity_type, source_entity_name, 
                     relation_type, target_entity_type, target_entity_name,
                     extraction_confidence, event_year)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    document_id,
                    source_entity_type,
                    source_entity_name.strip(),
                    relation_type,
                    target_entity_type,
                    target_entity_name.strip(),
                    confidence_score,
                    actual_event_year
                )
            
            logger.info(f"✅ 写入实体关系: {source_entity_name} → {relation_type} → {target_entity_name}")
            
            return json.dumps({
                "success": True,
                "relation": f"{source_entity_name} → {relation_type} → {target_entity_name}",
                "confidence": confidence_score,
                "message": f"✅ 知识图谱关系已写入"
            }, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"❌ 写入实体关系失败: {e}")
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()

class InsertMarketDataTool(Tool):
    """
    [Tool] 寫入市場數據
    
    功能：
    - 寫入 market_data 表
    - 支援 PE Ratio, Market Cap, 股價等市場指標
    - 🌟 支持通过公司名称写入（Method A）
    
    Schema v2.3 實際結構：
    - company_id, data_date (必填)
    - pe_ratio, market_cap, close_price, volume 等
    """
    
    @property
    def name(self) -> str:
        return "insert_market_data"
    
    @property
    def description(self) -> str:
        return (
            "Insert market data (PE ratio, market cap, stock price) into market_data table. "
            "Use this when you find market-related figures on the first page of annual reports. "
            "⚠️ This is different from financial_metrics (which are for revenue/profit/assets). "
            "Required: company_id OR company_name, data_date. Optional: pe_ratio, market_cap, close_price, volume, etc. "
            "🌟 Supports company_name for subsidiary data (Method A)."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": ["integer", "null"], 
                    "description": "母公司的 ID（如果是母公司数据，请填此项）"
                },
                "company_name": {
                    "type": ["string", "null"], 
                    "description": "🌟 如果数据属于子公司、关联公司或竞争对手，请填写他们的公司名称，系统会自动查找或创建对应的 ID"
                },
                "data_date": {"type": "string", "description": "Data date (YYYY-MM-DD format, e.g., '2023-12-31')"},
                "period_type": {"type": ["string", "null"], "description": "Period type (e.g., 'daily', 'yearly')"},
                "pe_ratio": {"type": ["number", "null"], "description": "Price-to-Earnings ratio"},
                "pb_ratio": {"type": ["number", "null"], "description": "Price-to-Book ratio"},
                "market_cap": {"type": ["number", "null"], "description": "Market capitalization"},
                "close_price": {"type": ["number", "null"], "description": "Closing stock price"},
                "open_price": {"type": ["number", "null"], "description": "Opening stock price"},
                "high_price": {"type": ["number", "null"], "description": "High stock price"},
                "low_price": {"type": ["number", "null"], "description": "Low stock price"},
                "volume": {"type": ["integer", "null"], "description": "Trading volume"},
                "turnover": {"type": ["number", "null"], "description": "Turnover"},
                "dividend_yield": {"type": ["number", "null"], "description": "Dividend yield (%)"},
                "source": {"type": ["string", "null"], "description": "Data source"}
            },
            "required": ["data_date"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, data_date: str, company_id: int = None, company_name: str = None, 
                      document_id: int = None, context: dict = None, **kwargs) -> str:
        """寫入市場數據
        
        🌟 Method A: 支持 company_name 参数
        🌟 防彈參數：**kwargs 吸收 LLM 幻覺產生的多餘參數
        🌟 v4.5: context.document_id fallback
        """
        from nanobot.ingestion.repository.db_client import DBClient
        from datetime import datetime, date as date_type
        
        # 🌟 v4.5: Always prefer context's document_id
        if context is None:
            context = kwargs.get("context", {})
        if context and context.get("document_id"):
            document_id = context["document_id"]
        
        db = DBClient()
        await db.connect()
        
        try:
            # 🌟 Method A: 名称转 ID
            actual_company_id, error = await _resolve_company_id(
                db_client=db,
                company_id=company_id,
                company_name=company_name,
                context=context
            )
            
            if error:
                return json.dumps({"success": False, "error": error}, indent=2)
            
            if not actual_company_id:
                return json.dumps({
                    "success": False, 
                    "error": "必须提供 company_id 或 company_name"
                }, indent=2)
            
            # 🌟 將字串日期轉換為 date 物件
            if isinstance(data_date, str):
                data_date_obj = datetime.strptime(data_date, "%Y-%m-%d").date()
            elif isinstance(data_date, date_type):
                data_date_obj = data_date
            else:
                data_date_obj = date_type.today()  # Fallback
            
            async with db.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO market_data 
                    (company_id, data_date, period_type, pe_ratio, pb_ratio, market_cap,
                     close_price, open_price, high_price, low_price, volume, turnover,
                     dividend_yield, source)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    actual_company_id,  # 🌟 使用转换后的 ID
                    data_date_obj,  # 🌟 使用 date 物件
                    kwargs.get("period_type"),
                    kwargs.get("pe_ratio"),
                    kwargs.get("pb_ratio"),
                    kwargs.get("market_cap"),
                    kwargs.get("close_price"),
                    kwargs.get("open_price"),
                    kwargs.get("high_price"),
                    kwargs.get("low_price"),
                    kwargs.get("volume"),
                    kwargs.get("turnover"),
                    kwargs.get("dividend_yield"),
                    kwargs.get("source")
                )
            
            logger.info(f"✅ 寫入市場數據: company_id={actual_company_id}, date={data_date}")
            
            return json.dumps({
                "success": True,
                "company_id": actual_company_id,
                "company_name": company_name,
                "data_date": data_date,
                "message": f"✅ 成功寫入市場數據 (公司: {company_name or f'ID={actual_company_id}'})"
            }, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"❌ 寫入市場數據失敗: {e}")
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()


class ExtractShareholdersFromTextTool(Tool):
    """
    [Tool] 從文本中提取股東結構
    
    🌟 專門用於處理年報中非結構化的股東信息
    
    使用場景：
    - 董事報告中嘅持股信息
    - 關聯方交易描述
    - "Substantial Shareholders" 章節
    """
    
    @property
    def name(self) -> str:
        return "extract_shareholders_from_text"
    
    @property
    def description(self) -> str:
        return (
            "Extract shareholder information from unstructured text in annual reports. "
            "Use this when shareholding_structure table is empty after normal extraction. "
            "Returns structured shareholder data ready for insert_shareholding."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text_content": {
                    "type": "string",
                    "description": "Text content containing shareholder information"
                },
                "company_id": {"type": "integer", "description": "Company ID"},
                "year": {"type": "integer", "description": "Year"},
                "document_id": {"type": "integer", "description": "Document ID"}
            },
            "required": ["text_content", "company_id", "year"]
        }
    
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return self.parameters
    
    async def execute(
        self,
        text_content: str,
        company_id: int,
        year: int,
        document_id: int = None,
        **kwargs
    ) -> str:
        """從文本中提取股東信息"""
        from nanobot.core.llm_core import llm_core
        
        extraction_prompt = f"""
請從以下年報文本中提取股東結構數據：

{text_content[:10000]}

提取要求：
1. 識別所有提及的股東（個人、公司、機構）
2. 提取持股數量和比例
3. 標注股東類型：
   - Executive Director（執行董事）
   - Non-Executive Director（非執行董事）
   - Independent Non-Executive Director（獨立非執行董事）
   - Substantial Shareholder（主要股東，>5%）
   - Institutional Investor（機構投資者）

輸出 JSON 格式：
{{
  "shareholders": [
    {{
      "shareholder_name": "姓名",
      "shareholder_type": "類型",
      "shares_held": 持股數量,
      "percentage": 持股比例,
      "is_controlling": true/false,
      "is_institutional": true/false,
      "notes": "備註"
    }}
  ]
}}

⚠️ 只返回 JSON，不要其他內容。
"""
        
        try:
            response = await llm_core.chat(extraction_prompt, model="z-ai/glm4.7")
            
            # 解析 LLM 響應
            import json
            import re
            
            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                shareholders = result.get("shareholders", [])
                
                if shareholders:
                    # 自動調用 insert_shareholding
                    from nanobot.ingestion.repository.db_client import DBClient
                    
                    db = DBClient()
                    await db.connect()
                    
                    inserted = 0
                    async with db.connection() as conn:
                        for sh in shareholders:
                            try:
                                await conn.execute(
                                    """
                                    INSERT INTO shareholding_structure 
                                    (company_id, document_id, year, shareholder_name, shareholder_type,
                                     shares_held, percentage, is_controlling, is_institutional, notes)
                                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                                    """,
                                    company_id,
                                    document_id,
                                    year,
                                    sh.get("shareholder_name"),
                                    sh.get("shareholder_type"),
                                    sh.get("shares_held"),
                                    sh.get("percentage"),
                                    sh.get("is_controlling"),
                                    sh.get("is_institutional"),
                                    sh.get("notes")
                                )
                                inserted += 1
                            except Exception as e:
                                logger.warning(f"插入股東失敗: {e}")
                    
                    await db.close()
                    
                    return json.dumps({
                        "success": True,
                        "extracted_count": len(shareholders),
                        "inserted_count": inserted,
                        "shareholders": shareholders[:5]  # 只返回前 5 個
                    }, indent=2, ensure_ascii=False)
            
            return json.dumps({"success": False, "error": "無法解析股東信息"}, indent=2)
            
        except Exception as e:
            logger.error(f"❌ 提取股東失敗: {e}")
            return json.dumps({"success": False, "error": str(e)}, indent=2)


class CleanupLowPerformanceKeywordsTool(Tool):
    """
    [Tool] 清理低效能關鍵字（反向學習）
    
    功能：
    - 自動檢測命中率低於 20% 的關鍵字
    - Bronze 等級 → 直接移除
    - Silver 等級 → 降級為 Bronze
    - Gold 等級 → 保持（需人工審核）
    
    使用場景：
    - 定期清理知識庫，防止「關鍵字爆炸」
    - 優化掃描效能
    """
    
    @property
    def name(self) -> str:
        return "cleanup_low_performance_keywords"
    
    @property
    def description(self) -> str:
        return (
            "Clean up low-performance keywords from the knowledge base. "
            "Removes keywords with hit_rate < 20% (after min 5 uses). "
            "Bronze keywords are removed, Silver are downgraded to Bronze, Gold are kept."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "min_usage": {
                    "type": "integer",
                    "description": "Minimum usage count before cleanup",
                    "default": 5
                },
                "min_hit_rate": {
                    "type": "number",
                    "description": "Minimum hit rate threshold (0.0-1.0)",
                    "default": 0.2
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Only report, don't actually remove",
                    "default": False
                }
            }
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        min_usage: int = 5,
        min_hit_rate: float = 0.2,
        dry_run: bool = False
    ) -> str:
        """執行清理"""
        from nanobot.ingestion.utils.keyword_manager import KeywordManager
        
        km = KeywordManager()
        
        if dry_run:
            # 只返回統計，不執行清理
            stats = km.get_stats()
            low_perf = stats.get("low_performance", [])
            return json.dumps({
                "dry_run": True,
                "would_remove": len(low_perf),
                "low_performance_keywords": low_perf,
                "message": f"⚠️ Dry run: {len(low_perf)} keywords would be cleaned"
            }, indent=2, ensure_ascii=False)
        
        result = km.auto_cleanup_low_performance(min_usage, min_hit_rate)
        
        logger.info(f"🧹 反向學習: 移除 {result['removed_count']} 個，降級 {result['downgraded_count']} 個低效能關鍵字")
        
        return json.dumps(result, indent=2, ensure_ascii=False)


class GetKeywordContextTool(Tool):
    """
    [Tool] 獲取關鍵字的上下文信息
    
    功能：
    - 返回典型頁碼範圍
    - 返回共同出現的特徵
    - 返回行業命中統計
    """
    
    @property
    def name(self) -> str:
        return "get_keyword_context"
    
    @property
    def description(self) -> str:
        return (
            "Get context information for a keyword: typical page range, "
            "co-occurrence features, and industry-specific statistics."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Keyword to analyze"
                },
                "category": {
                    "type": "string",
                    "description": "Category filter (optional)",
                    "default": None
                }
            },
            "required": ["keyword"]
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(self, keyword: str, category: Optional[str] = None, **kwargs) -> str:
        """獲取上下文"""
        from nanobot.ingestion.utils.keyword_manager import KeywordManager
        
        km = KeywordManager()
        context = km.get_keyword_context(keyword, category)
        
        return json.dumps(context, indent=2, ensure_ascii=False)


class SearchDocumentPagesTool(Tool):
    """
    [Tool] 搜索包底库 (document_pages) 找遗漏数据
    
    🌟 核心功能：Continuous Learning Loop 的关键
    
    使用场景：
    1. 结构化表 (revenue_breakdown) 没有用户要的数据
    2. 在包底库中搜索关键词
    3. 找到后 → 注册新关键词 → 回填数据
    
    这是打破"鸡生蛋"问题的核心机制！
    """
    
    @property
    def name(self) -> str:
        return "search_document_pages"
    
    @property
    def description(self) -> str:
        return (
            "Search the fallback table (document_pages) for keywords. "
            "Use this when structured tables (revenue_breakdown, financial_metrics) don't have the data. "
            "If you find the data here, please: "
            "1) Register the page title as a new keyword, "
            "2) Backfill the data to structured tables. "
            "This is the Continuous Learning Loop!"
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "Document ID to search"},
                "keywords": {"type": "array", "items": {"type": "string"}, "description": "Keywords to search"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["document_id", "keywords"]
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(self, document_id: int, keywords: List[str], limit: int = 10, **kwargs) -> str:
        """搜索包底库"""
        from nanobot.ingestion.repository.db_client import DBClient
        db = DBClient()
        await db.connect()
        try:
            async with db.connection() as conn:
                conditions = [f"markdown_content ILIKE '%{kw}%'" for kw in keywords]
                where_clause = " AND ".join(conditions) if len(conditions) > 1 else conditions[0]
                results = await conn.fetch(
                    f"SELECT page_num, markdown_content FROM document_pages WHERE document_id = $1 AND {where_clause} LIMIT $2",
                    document_id, limit
                )
                if not results:
                    return json.dumps({"success": True, "found": False, "message": "包底库中也没有找到"}, indent=2)
                pages = [{"page_num": r["page_num"], "preview": r["markdown_content"][:300]} for r in results]
                return json.dumps({"success": True, "found": True, "pages_found": pages, 
                    "hint": "找到后请注册新关键词并回填数据"}, indent=2, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()


class SearchChartByDescriptionTool(Tool):
    """
    🌟 v4.0: 用自然語言描述搵圖表（語意搵圖）
    
    功能：
    - 讓 Agent 可以用「描述」而非「圖號」來搵圖
    - 支持關鍵字搜尋 + AI Summary 搜尋
    - 頁數範圍過濾
    
    使用場景：
    - 用戶問：「加拿大銷售趨勢如何？」
    - Agent 調用：search_chart_by_description(document_id=123, chart_description="加拿大銷售")
    - 系統自動搵到相關圖表的 artifact_id
    - 然後調用 AnalyzeChartWithVisionTool 獲取精確數據
    
    預期改善：圖表提取正確率從 70% ↑ 88%
    """
    
    @property
    def name(self) -> str:
        return "search_chart_by_description"
    
    @property
    def description(self) -> str:
        return (
            "用自然語言描述搵圖表（例如『加拿大銷售趨勢圖』），系統會靠 AI Summary 同關鍵字搵出 artifact_id。"
            "\n\n使用場景："
            "\n- 用戶問：「加拿大收入佔比多少？」"
            "\n- Agent 不知道圖號，但可以搜索關鍵字「加拿大」"
            "\n- 調用此工具後得到 artifact_id"
            "\n- 然後調用 analyze_chart_with_vision 讀取精確數據"
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "integer", 
                    "description": "文檔 ID"
                },
                "chart_description": {
                    "type": "string",
                    "description": "圖表描述（例如：『加拿大及美國嘅營收比較圖』）"
                },
                "page_range": {
                    "type": "string",
                    "description": "頁數範圍（例如：『20-30』），可選"
                }
            },
            "required": ["document_id", "chart_description"]
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(
        self, 
        document_id: int, 
        chart_description: str, 
        page_range: str = None,
        **kwargs
    ) -> str:
        """執行圖表搜索"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 🌟 用 ILIKE 搜尋 AI Summary 和關鍵字
                # 支援 content（原始內容）和 content_json->>'ai_summary'
                query = """
                SELECT 
                    artifact_id, 
                    page_num, 
                    content,
                    artifact_type
                FROM raw_artifacts
                WHERE document_id = $1 
                AND artifact_type IN ('image', 'chart', 'table', 'vision_analysis')
                AND (
                    content::text ILIKE $2
                    OR content->>'ai_summary' ILIKE $2
                    OR content->>'analysis'->>'markdown_representation' ILIKE $2
                )
                """
                
                # 處理頁數範圍
                params = [document_id, f"%{chart_description}%"]
                
                if page_range:
                    try:
                        # 解析 "20-30" 為兩個數字
                        start_page, end_page = map(int, page_range.split('-'))
                        query += " AND page_num BETWEEN $3 AND $4"
                        params.extend([start_page, end_page])
                    except Exception as e:
                        logger.warning(f"⚠️ 無法解析頁數範圍 '{page_range}': {e}")
                
                query += " ORDER BY page_num ASC LIMIT 5"
                
                results = await conn.fetch(query, *params)
                
                if not results:
                    return json.dumps({
                        "success": False,
                        "message": f"未找到匹配『{chart_description}』的圖表",
                        "suggestion": "請嘗試其他關鍵字，例如：revenue, Canada, 營收, 圖表"
                    }, ensure_ascii=False)
                
                # 格式化結果
                matches = []
                for r in results:
                    content = r["content"]
                    
                    # 提取 AI Summary
                    ai_summary = ""
                    if isinstance(content, dict):
                        ai_summary = content.get("ai_summary", "")
                        if not ai_summary:
                            # 嘗試從 analysis 中獲取
                            analysis = content.get("analysis", {})
                            if isinstance(analysis, dict):
                                ai_summary = analysis.get("markdown_representation", "")
                    elif isinstance(content, str):
                        ai_summary = content[:200] if len(content) > 200 else content
                    
                    matches.append({
                        "artifact_id": r["artifact_id"],
                        "page_num": r["page_num"],
                        "artifact_type": r["artifact_type"],
                        "preview": ai_summary[:100] + "..." if len(ai_summary) > 100 else ai_summary
                    })
                
                return json.dumps({
                    "success": True,
                    "query": chart_description,
                    "matches": matches,
                    "hint": f"找到 {len(matches)} 個匹配的圖表。請使用 analyze_chart_with_vision(artifact_id) 來讀取精確數據。"
                }, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"❌ 圖表搜索失敗: {e}")
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
        finally:
            await db.close()


class BackfillFromFallbackTool(Tool):
    """
    [Tool] 从包底库回填数据到结构化表
    
    🌟 Continuous Learning Loop 的最后一步
    """
    
    @property
    def name(self) -> str:
        return "backfill_from_fallback"
    
    @property
    def description(self) -> str:
        return "Backfill data from document_pages to structured tables after finding it."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "year": {"type": "integer"},
                "document_id": {"type": "integer"},
                "page_num": {"type": "integer"},
                "data_type": {
                    "type": "string",
                    "enum": ["revenue_breakdown", "financial_metrics", "key_personnel", "shareholding", "market_data"],
                    "description": "Type of data to backfill"
                },
                "extracted_data": {"type": "object"},
                "new_keyword": {"type": ["string", "null"]}
            },
            "required": ["company_id", "year", "document_id", "page_num", "data_type", "extracted_data"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, company_id: int, year: int, document_id: int, page_num: int, 
                      data_type: str, extracted_data: Dict, new_keyword: Optional[str] = None,
                      **kwargs  # 🌟 防弹参数：吸收 LLM 幻觉产生的多余参数
    ) -> str:
        """回填数据"""
        from nanobot.ingestion.repository.db_client import DBClient
        from nanobot.ingestion.utils.keyword_manager import KeywordManager
        
        db = DBClient()
        await db.connect()
        try:
            count = 0
            async with db.connection() as conn:
                if data_type == "revenue_breakdown":
                    for seg, data in extracted_data.items():
                        await conn.execute(
                            """
                            INSERT INTO revenue_breakdown 
                            (company_id, year, segment_name, segment_type, revenue_amount, 
                             revenue_percentage, currency, source_document_id, source_page)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                            ON CONFLICT (company_id, year, segment_name) 
                            DO UPDATE SET 
                                revenue_amount = $5,
                                revenue_percentage = $6,
                                source_document_id = $8
                            """,
                            company_id, year, seg,
                            data.get("segment_type", "geography"),
                            data.get("amount"),
                            data.get("percentage"),
                            data.get("currency", "HKD"),
                            document_id, page_num
                        )
                        count += 1
                
                # 👇 新增：处理 financial_metrics 的回填
                elif data_type == "financial_metrics":
                    for metric_name, data in extracted_data.items():
                        await conn.execute(
                            """
                            INSERT INTO financial_metrics 
                            (company_id, year, metric_name, value, unit, standardized_value, 
                             source_document_id, source_page)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (company_id, year, metric_name) 
                            DO UPDATE SET 
                                value = $4,
                                standardized_value = $6,
                                source_document_id = $7,
                                source_page = $8
                            """,
                            company_id, year, metric_name,
                            data.get("value"),
                            data.get("unit", "HKD"),
                            data.get("standardized_value"),
                            document_id, page_num
                        )
                        count += 1
                
                # 👇 新增：处理 key_personnel 的回填
                elif data_type == "key_personnel":
                    for person_name, data in extracted_data.items():
                        await conn.execute(
                            """
                            INSERT INTO key_personnel 
                            (company_id, year, name_en, position_title_en, board_role, 
                             source_document_id)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            ON CONFLICT (company_id, year, name_en) 
                            DO UPDATE SET 
                                position_title_en = $4,
                                board_role = $5,
                                source_document_id = $6
                            """,
                            company_id, year, person_name,
                            data.get("position"),
                            data.get("board_role"),
                            document_id
                        )
                        count += 1
                
                # 👇 新增：处理 shareholding 的回填
                elif data_type == "shareholding":
                    for shareholder_name, data in extracted_data.items():
                        await conn.execute(
                            """
                            INSERT INTO shareholding_structure 
                            (company_id, year, shareholder_name, shareholder_type, shares_held, 
                             percentage, source_document_id)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            """,
                            company_id, year, shareholder_name,
                            data.get("shareholder_type"),  # 🌟 修正：shareholder_type
                            data.get("shares_held"),
                            data.get("percentage"),
                            document_id
                        )
                        count += 1
            
            if new_keyword:
                km = KeywordManager()
                km.add_keyword("revenue_breakdown", new_keyword, "continuous_learning", "silver",
                              reasoning=f"Agent discovered in page {page_num} during backfill")
            
            return json.dumps({
                "success": True,
                "data_type": data_type,
                "inserted_count": count,
                "keyword_registered": new_keyword is not None,
                "new_keyword": new_keyword,
                "source_page": page_num,
                "message": f"✅ 从包底库回填 {count} 条 {data_type} 数据"
            }, indent=2, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()


# ============================================================
# Tool 註冊函數
# ============================================================

def register_ingestion_tools(registry) -> None:
    """
    註冊所有攝入相關 Tools (v4.0 - 16 個完整 Tools)
    
    🌟 v4.0 补齐所有缺失的 Tools：
    - InsertRevenueBreakdownTool 🆕 致命遗漏修复
    - InsertEntityRelationTool 🆕 知识图谱修复
    - InsertMarketDataTool 🆕 市场数据修复
    
    Usage:
        from nanobot.agent.tools.db_ingestion_tools import register_ingestion_tools
        register_ingestion_tools(agent_loop.tools)
    """
    # 🌟 核心 Tools
    registry.register(GetDBSchemaTool())
    registry.register(SmartInsertDocumentTool())
    # ❌ UpdateDocumentStatusTool 已移除 - Status 由 pipeline 在所有 stages 完成后统一设置
    # registry.register(UpdateDocumentStatusTool())
    registry.register(UpdateDynamicAttributesTool())
    registry.register(CreateReviewRecordTool())
    
    # 🌟 知识库管理 Tools
    registry.register(RegisterNewKeywordTool())
    registry.register(GetKeywordStatsTool())
    registry.register(CleanupLowPerformanceKeywordsTool())
    registry.register(GetKeywordContextTool())
    
    # 🌟 数据写入 Tools (完整版)
    registry.register(InsertKeyPersonnelTool())
    registry.register(InsertFinancialMetricsTool())
    registry.register(InsertShareholdingTool())
    registry.register(InsertRevenueBreakdownTool())  # 🆕 致命遗漏修复
    registry.register(InsertEntityRelationTool())    # 🆕 知识图谱修复
    registry.register(InsertMarketDataTool())        # 🆕 市场数据修复
    
    # 🌟 Continuous Learning Loop Tools
    registry.register(SearchDocumentPagesTool())
    registry.register(BackfillFromFallbackTool())
    
    # 🌟 v4.0: Multimodal RAG Tools - 語意搵圖
    registry.register(SearchChartByDescriptionTool())
    
    # 🌟 Multimodal RAG Tools (跨模態圖文檢索)
    try:
        from nanobot.agent.tools.multimodal_rag import GetChartContextTool, GetChartContextByTitleTool
        registry.register(GetChartContextTool())
        registry.register(GetChartContextByTitleTool())
    except ImportError:
        logger.warning("⚠️ Multimodal RAG tools not available")
    
    # 🌟 v4.12: Additional Tools
    registry.register(InsertArtifactRelationTool())  # 🆕 圖文關聯
    registry.register(InsertMentionedCompanyTool())  # 🆕 提及公司
    registry.register(ExtractShareholdersFromTextTool())  # 🆕 從文本提取股東
    
    logger.info("✅ Registered 22 ingestion tools (v4.12: +artifact_relation, +mentioned_company, +extract_shareholders)")




# ============================================================
# Additional Tools (v4.12) - Correct Format
# ============================================================

class InsertArtifactRelationTool(Tool):
    """
    [Tool] 寫入跨模態圖文關聯
    """
    @property
    def name(self) -> str:
        return "insert_artifact_relation"
    
    @property
    def description(self) -> str:
        return "將圖表或圖片與解釋它的文字段落建立跨模態關聯，解決圖文跨頁斷裂問題。"
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "文檔 ID"},
                "source_artifact_id": {"type": "string", "description": "源實體 ID (圖表/圖片的 artifact_id)"},
                "target_artifact_id": {"type": "string", "description": "目標實體 ID (解釋文字的 artifact_id)"},
                "relation_type": {"type": "string", "default": "explained_by"},
                "confidence_score": {"type": "number", "default": 1.0}
            },
            "required": ["document_id", "source_artifact_id", "target_artifact_id"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, document_id: int, source_artifact_id: str, target_artifact_id: str, 
                     relation_type: str = "explained_by", confidence_score: float = 1.0, **kwargs) -> str:
        context = kwargs.get("context", {})
        db_client = context.get("db_client")
        if not db_client:
            return "Error: Database client not found in context."
        
        try:
            success = await db_client.insert_artifact_relation(
                document_id=document_id,
                source_artifact_id=source_artifact_id,
                target_artifact_id=target_artifact_id,
                relation_type=relation_type,
                confidence_score=confidence_score,
                extraction_method="agentic_inferred"
            )
            if success:
                return f"Success: Artifact relation created: {source_artifact_id} -> {target_artifact_id}"
            else:
                return "Error: Failed to create artifact relation"
        except Exception as e:
            return f"Error: {str(e)}"


class InsertMentionedCompanyTool(Tool):
    """
    [Tool] 提取並寫入文件中提及的其他公司 (v4.12)
    """
    @property
    def name(self) -> str:
        return "insert_mentioned_company"
    
    @property
    def description(self) -> str:
        return "當在文件中發現提及其他公司（如子公司、聯營公司、競爭對手）時調用。將其寫入數據庫並與當前文檔建立關聯。"
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name_en": {"type": "string", "description": "公司英文名稱"},
                "name_zh": {"type": "string", "description": "公司中文名稱"},
                "stock_code": {"type": "string", "description": "股票代碼 (如有，例如 0700.HK)"},
                "relation_type": {
                    "type": "string", 
                    "enum": ["subsidiary", "competitor", "partner", "investor", "customer", "mentioned"],
                    "description": "與主公司的關係分類"
                }
            },
            "required": ["relation_type"]
        }
    
    @property
    def read_only(self) -> bool:
        return False

    async def execute(self, name_en: str = None, name_zh: str = None, stock_code: str = None, 
                     relation_type: str = "mentioned", context: dict = None) -> str:
        """
        🌟 v4.5: 顯式添加 context 參數，讓 agentic_executor 能夠檢測並傳入
        """
        context = context or {}
        document_id = context.get("document_id")
        
        if not name_en and not name_zh:
            return json.dumps({"success": False, "error": "Must provide name_en or name_zh"}, ensure_ascii=False)
        
        # 🌟 v4.5: 自己創建 DBClient 實例，不依賴 context
        from nanobot.ingestion.repository.db_client import DBClient
        db_client = DBClient()
        await db_client.connect()
        
        if not document_id:
            # 嘗試從最近處理的 document 獲取 document_id
            try:
                async with db_client.connection() as conn:
                    row = await conn.fetchrow(
                        "SELECT id FROM documents ORDER BY created_at DESC LIMIT 1"
                    )
                    if row:
                        document_id = row["id"]
            except Exception as e:
                logger.warning(f"⚠️ Could not fetch latest document_id: {e}")
        
        import uuid
        if not stock_code:
            stock_code = f"MENTIONED_{uuid.uuid4().hex[:6]}"
        
        try:
            # 1. UPSERT company
            company_id = await db_client.upsert_company(
                stock_code=stock_code,
                name_en=name_en,
                name_zh=name_zh,
                name_source="agentic_extractor"
            )
            
            if not company_id:
                return json.dumps({
                    "success": False, 
                    "error": f"Failed to create company {name_en or name_zh}"
                }, ensure_ascii=False)
            
            # 2. Create document-company relation
            success = await db_client.add_mentioned_company(
                document_id=document_id,
                company_id=company_id,
                relation_type=relation_type,
                extraction_source="agentic_extractor"
            )
            
            if success:
                return json.dumps({
                    "success": True,
                    "company_id": company_id,
                    "company_name": name_en or name_zh,
                    "relation_type": relation_type,
                    "message": f"✅ Mentioned company created: {name_en or name_zh} (ID: {company_id})"
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False, 
                    "error": "Failed to create document-company relation"
                }, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"InsertMentionedCompanyTool error: {e}")
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
        finally:
            # 🌟 v4.5: 確保關閉數據庫連接
            await db_client.close()
