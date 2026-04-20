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
        notes: Optional[str] = None
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
        merge: bool = True
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
        reasoning: Optional[str] = None
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
            "Use this when you find board members, management team, or committee members."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {"type": "integer", "description": "Company ID"},
                "document_id": {"type": "integer", "description": "Document ID"},
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
            "required": ["company_id", "personnel_list"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, company_id: int, personnel_list: List[Dict], document_id: Optional[int] = None) -> str:
        """写入关键人员"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            inserted_count = 0
            
            async with db.connection() as conn:
                for person in personnel_list:
                    name_en = person.get("name_en")
                    
                    if not name_en:
                        continue  # 🌟 v1.2: 跳过没有 name_en 的记录
                    
                    # committee_membership 需要转为 JSON
                    import json
                    committee_json = json.dumps(person.get("committee_membership", [])) if person.get("committee_membership") else None
                    
                    # 🌟 v1.2: 先检查是否存在，再决定 INSERT 或 UPDATE
                    existing = await conn.fetchval(
                        "SELECT id FROM key_personnel WHERE company_id = $1 AND name_en = $2",
                        company_id,
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
                            company_id,
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
                "company_id": company_id,
                "inserted_count": inserted_count,
                "message": f"✅ 写入 {inserted_count} 位关键人员"
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
            "Use this when you find financial figures like revenue, profit, assets, liabilities."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {"type": "integer", "description": "Company ID"},
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
            "required": ["company_id", "year", "metrics"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, company_id: int, year: int, metrics: List[Dict]) -> str:
        """写入财务指标"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            inserted_count = 0
            
            async with db.connection() as conn:
                for metric in metrics:
                    await conn.execute(
                        """
                        INSERT INTO financial_metrics 
                        (company_id, year, metric_name, value, unit, standardized_value, source_page)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (company_id, year, fiscal_period, metric_name)  -- 🌟 v1.2: 修正约束名（需要 fiscal_period）
                        DO UPDATE SET value = $4, standardized_value = $6
                        """,
                        company_id,
                        year,
                        metric.get("metric_name"),
                        metric.get("value"),
                        metric.get("unit", "HKD"),
                        metric.get("standardized_value"),
                        metric.get("source_page")
                    )
                    inserted_count += 1
            
            return json.dumps({
                "success": True,
                "company_id": company_id,
                "year": year,
                "inserted_count": inserted_count,
                "message": f"✅ 写入 {inserted_count} 个财务指标"
            }, indent=2, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()


class InsertShareholdingTool(Tool):
    """
    [Tool] 写入股东结构数据
    
    Schema v2.3:
    - shareholder_name, share_type
    - shares_held, percentage
    """
    
    @property
    def name(self) -> str:
        return "insert_shareholding"
    
    @property
    def description(self) -> str:
        return (
            "Insert shareholding structure into shareholding_structure table. "
            "Use this when you find shareholder names and ownership percentages."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {"type": "integer", "description": "Company ID"},
                "year": {"type": "integer", "description": "Year"},
                "shareholders": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "shareholder_name": {"type": "string", "description": "Shareholder name"},
                            "share_type": {"type": ["string", "null"], "description": "Share type (e.g., 'ordinary')"},
                            "shares_held": {"type": ["number", "null"], "description": "Number of shares"},
                            "percentage": {"type": "number", "description": "Ownership percentage"}
                        },
                        "required": ["shareholder_name", "percentage"]
                    },
                    "description": "List of shareholders"
                }
            },
            "required": ["company_id", "year", "shareholders"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, company_id: int, year: int, shareholders: List[Dict]) -> str:
        """写入股东结构"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            inserted_count = 0
            
            async with db.connection() as conn:
                for sh in shareholders:
                    await conn.execute(
                        """
                        INSERT INTO shareholding_structure 
                        (company_id, year, shareholder_name, share_type, shares_held, percentage)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        company_id,
                        year,
                        sh.get("shareholder_name"),
                        sh.get("share_type"),
                        sh.get("shares_held"),
                        sh.get("percentage")
                    )
                    inserted_count += 1
            
            return json.dumps({
                "success": True,
                "inserted_count": inserted_count
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
            "⚠️ This is NOT the same as financial_metrics! Use this specifically for revenue breakdown tables."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {"type": "integer", "description": "Company ID"},
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
            "required": ["company_id", "year", "segments"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, company_id: int, year: int, segments: List[Dict], document_id: Optional[int] = None) -> str:
        """写入收入分解"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        # 🌟 v1.2: 强制转换 document_id 为整数（Agent 可能传字符串）
        if document_id is not None:
            try:
                document_id = int(document_id)
            except (ValueError, TypeError):
                document_id = None
        
        db = DBClient()
        await db.connect()
        
        try:
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
                        company_id,
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
                "company_id": company_id,
                "year": year,
                "inserted_count": inserted_count,
                "message": f"✅ 写入 {inserted_count} 个收入分解项到 revenue_breakdown 表"
            }, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"❌ 写入收入分解失败: {e}")
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()


class InsertEntityRelationTool(Tool):
    """
    [Tool] 写入实体关系（知识图谱） 🌟 知识图谱遗漏修复
    
    功能：
    - 写入 entity_relations 表
    - 支持 person/company/event/location 四种实体类型
    - 支持 CEO_of/partner_of/acquired/located_in 等关系
    
    使用场景：
    - Agent 读到「张三是腾讯的CEO」→ 写入实体关系
    - Agent 读到「公司A收购公司B」→ 写入收购关系
    """
    
    @property
    def name(self) -> str:
        return "insert_entity_relation"
    
    @property
    def description(self) -> str:
        return (
            "Insert entity relation (knowledge graph) into entity_relations table. "
            "Use this when you find relationships like 'Person A is CEO of Company B', "
            "'Company A acquired Company B', or 'Person X located in Region Y'. "
            "Supports person/company/event/location entity types."
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
                "source_entity_name": {"type": "string", "description": "Name of the source entity"},
                "relation_type": {
                    "type": "string",
                    "description": "Type of relation (e.g., 'CEO_of', 'partner_of', 'acquired', 'located_in', 'subsidiary_of')"
                },
                "target_entity_type": {
                    "type": "string",
                    "enum": ["person", "company", "event", "location"],
                    "description": "Type of the target entity"
                },
                "target_entity_name": {"type": "string", "description": "Name of the target entity"},
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
        event_year: Optional[int] = None
    ) -> str:
        """写入实体关系"""
        from nanobot.ingestion.repository.db_client import DBClient
        
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
                    source_entity_name,
                    relation_type,
                    target_entity_type,
                    target_entity_name,
                    confidence_score,
                    event_year
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
    [Tool] 写入市场数据 🌟 市场数据遗漏修复
    
    功能：
    - 写入 market_data 表
    - 支持 PE Ratio, Market Cap, 股价等市场指标
    
    Schema v2.3:
    - metric_name (pe_ratio, market_cap, stock_price)
    - value, date
    """
    
    @property
    def name(self) -> str:
        return "insert_market_data"
    
    @property
    def description(self) -> str:
        return (
            "Insert market data (PE ratio, market cap, stock price) into market_data table. "
            "Use this when you find market-related figures on the first page of annual reports. "
            "⚠️ This is different from financial_metrics (which are for revenue/profit/assets)."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_id": {"type": "integer", "description": "Company ID"},
                "document_id": {"type": "integer", "description": "Source document ID"},
                "metrics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "metric_name": {
                                "type": "string",
                                "description": "Metric name (e.g., 'pe_ratio', 'market_cap', 'stock_price')"
                            },
                            "value": {"type": "number", "description": "Value"},
                            "unit": {"type": ["string", "null"], "description": "Unit (e.g., 'HKD', 'billion')"},
                            "date": {"type": ["string", "null"], "description": "Date of the data"}
                        },
                        "required": ["metric_name", "value"]
                    },
                    "description": "List of market data metrics"
                }
            },
            "required": ["company_id", "document_id", "metrics"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(self, company_id: int, document_id: int, metrics: List[Dict]) -> str:
        """写入市场数据"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            inserted_count = 0
            
            async with db.connection() as conn:
                for metric in metrics:
                    await conn.execute(
                        """
                        INSERT INTO market_data 
                        (company_id, document_id, metric_name, value, unit, date)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        company_id,
                        document_id,
                        metric.get("metric_name"),
                        metric.get("value"),
                        metric.get("unit"),
                        metric.get("date")
                    )
                    inserted_count += 1
            
            logger.info(f"✅ 写入 {inserted_count} 个市场数据指标")
            
            return json.dumps({
                "success": True,
                "inserted_count": inserted_count,
                "message": f"✅ 写入 {inserted_count} 个市场数据到 market_data 表"
            }, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"❌ 写入市场数据失败: {e}")
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        finally:
            await db.close()


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
    
    async def execute(self, keyword: str, category: Optional[str] = None) -> str:
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
    
    async def execute(self, document_id: int, keywords: List[str], limit: int = 10) -> str:
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
                      data_type: str, extracted_data: Dict, new_keyword: Optional[str] = None) -> str:
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
                            (company_id, year, shareholder_name, share_type, shares_held, 
                             percentage, source_document_id)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            """,
                            company_id, year, shareholder_name,
                            data.get("share_type"),
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
    registry.register(UpdateDocumentStatusTool())
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
    
    # 🌟 Multimodal RAG Tools (跨模態圖文檢索)
    try:
        from nanobot.agent.tools.multimodal_rag import GetChartContextTool, GetChartContextByTitleTool
        registry.register(GetChartContextTool())
        registry.register(GetChartContextByTitleTool())
    except ImportError:
        logger.warning("⚠️ Multimodal RAG tools not available")
    
    logger.info("✅ Registered 19 ingestion tools (including 3 new Tools: revenue_breakdown, entity_relation, market_data)")


# 1. 定義參數 Schema
class InsertArtifactRelationArgs(BaseModel):
    document_id: int = Field(..., description="文檔的內部整數 ID (document_id)")
    source_artifact_id: str = Field(..., description="源實體 ID (通常是圖表或圖片的 artifact_id)")
    target_artifact_id: str = Field(..., description="目標實體 ID (通常是解釋性文字段落的 artifact_id)")
    relation_type: str = Field("explained_by", description="關係類型，例如 'explained_by' 或 'referenced_in'")
    confidence_score: float = Field(1.0, description="關聯置信度 (0.0 - 1.0)")

# 2. 定義 Tool 類別
class InsertArtifactRelationTool:
    name = "insert_artifact_relation"
    description = "將圖表或圖片與解釋它的文字段落建立跨模態關聯，解決圖文跨頁斷裂問題。"
    args_schema = InsertArtifactRelationArgs

    @staticmethod
    async def execute(args: dict, context: dict) -> str:
        db_client = context.get("db_client")
        if not db_client:
            return "❌ Error: Database client not found in context."
        
        try:
            success = await db_client.insert_artifact_relation(
                document_id=args["document_id"],
                source_artifact_id=args["source_artifact_id"],
                target_artifact_id=args["target_artifact_id"],
                relation_type=args.get("relation_type", "explained_by"),
                confidence_score=args.get("confidence_score", 1.0),
                extraction_method="llm_inferred"
            )
            if success:
                return f"✅ 成功寫入圖文關聯: {args['source_artifact_id']} ➔ {args['target_artifact_id']}"
            else:
                return "❌ 寫入失敗，請檢查資料庫日誌。"
        except Exception as e:
            return f"❌ 寫入時發生錯誤: {str(e)}"