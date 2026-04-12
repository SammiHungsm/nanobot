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
📌 可用的主要表:
- documents: 文檔主表 (含 JSONB 動態屬性)
- document_companies: 關聯公司表
- document_chunks: 文檔切片
- document_tables: 提取的表格
- document_processing_history: 處理歷史
- data_review_queue: 人工審核隊列
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
                    # 🌟 1. 處理母公司 (將動態屬性放入 companies.extra_data)
                    owner_company_id = None
                    if parent_company:
                        # Upsert 母公司，extra_data 存儲 index_theme 等動態信息
                        owner_company_id = await conn.fetchval(
                            """
                            INSERT INTO companies (stock_code, name_en, extra_data) 
                            VALUES ($1, $2, $3::jsonb)
                            ON CONFLICT (stock_code) DO UPDATE SET 
                                extra_data = COALESCE(companies.extra_data, '{}'::jsonb) || $3::jsonb
                            RETURNING id
                            """,
                            "PARENT",  # 临时 stock_code
                            parent_company,
                            json.dumps({"index_theme": index_theme, **(dynamic_data or {})})
                        )
                    
                    # 🌟 2. 寫入主 Document (適配 v2.3 欄位)
                    doc_id_str = f"agent_{uuid.uuid4().hex[:8]}"
                    doc_result = await conn.fetchrow(
                        """
                        INSERT INTO documents (
                            doc_id, filename, report_type, owner_company_id, processing_status
                        ) VALUES ($1, $2, $3, $4, 'pending')
                        RETURNING id
                        """,
                        doc_id_str, filename, report_type, owner_company_id
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
        
        🌟 Schema v2.3: 动态属性存储在 companies.extra_data
        - documents.dynamic_attributes 已删除
        - 通过 documents.owner_company_id 找到对应的 companies 记录
        - 更新 companies.extra_data
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 🌟 通过 documents.owner_company_id 找到对应的 company
                if merge:
                    # 合併現有屬性 (Schema v2.3)
                    result = await conn.fetchrow(
                        """
                        UPDATE companies 
                        SET extra_data = COALESCE(extra_data, '{}'::jsonb) || $1::jsonb,
                            updated_at = NOW()
                        WHERE id = (SELECT owner_company_id FROM documents WHERE id = $2)
                        RETURNING extra_data
                        """,
                        json.dumps(attributes),
                        document_id
                    )
                else:
                    # 替換所有屬性 (Schema v2.3)
                    result = await conn.fetchrow(
                        """
                        UPDATE companies 
                        SET extra_data = $1::jsonb,
                            updated_at = NOW()
                        WHERE id = (SELECT owner_company_id FROM documents WHERE id = $2)
                        RETURNING extra_data
                        """,
                        json.dumps(attributes),
                        document_id
                    )
                
                return json.dumps({
                    "success": True,
                    "document_id": document_id,
                    "extra_data": result["extra_data"] if result else None
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
                "document_id": {
                    "type": "integer",
                    "description": "ID of the document needing review"
                },
                "review_type": {
                    "type": "string",
                    "enum": ["industry_assignment", "company_extraction", "data_quality", "other"],
                    "description": "Type of review needed"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "Priority level",
                    "default": "medium"
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about what needs review"
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
        priority: str = "medium",
        notes: Optional[str] = None
    ) -> str:
        """創建審核記錄"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                result = await conn.fetchrow(
                    """
                    INSERT INTO data_review_queue (document_id, review_type, priority, notes)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (document_id) DO UPDATE SET
                        review_type = EXCLUDED.review_type,
                        priority = EXCLUDED.priority,
                        notes = EXCLUDED.notes,
                        status = 'pending'
                    RETURNING id, status
                    """,
                    document_id,
                    review_type,
                    priority,
                    notes
                )
                
                return json.dumps({
                    "success": True,
                    "review_id": result["id"],
                    "document_id": document_id,
                    "status": result["status"]
                }, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"❌ Create review record failed: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            await db.close()


# ============================================================
# Tool 註冊函數
# ============================================================

def register_ingestion_tools(registry) -> None:
    """
    註冊所有攝入相關 Tools
    
    Usage:
        from nanobot.agent.tools.db_ingestion_tools import register_ingestion_tools
        register_ingestion_tools(agent_loop.tools)
    """
    registry.register(GetDBSchemaTool())
    registry.register(SmartInsertDocumentTool())
    registry.register(UpdateDocumentStatusTool())
    registry.register(UpdateDynamicAttributesTool())
    registry.register(CreateReviewRecordTool())
    
    logger.info("✅ Registered 5 ingestion tools: get_db_schema, smart_insert_document, update_document_status, update_dynamic_attributes, create_review_record")