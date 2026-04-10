"""
Database Ingestion Tools for Agentic Dynamic Ingestion

這些 Tools 讓 Nanobot Agent 能夠：
1. 查看當前資料庫 Schema
2. 動態寫入數據 (實體欄位 + JSONB)
3. 處理複雜的公司關係

設計理念：
- 核心欄位 → 實體欄位 (快速查詢)
- 動態屬性 → JSONB 欄位 (靈活擴展)
- AI 判斷 → 保留人工覆核機制
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from loguru import logger

from nanobot.agent.tools.base import Tool


class GetDBSchemaTool(Tool):
    """
    [Tool] 讓 Agent 獲取目前資料庫的 Schema
    
    用途：
    - Agent 了解有哪些實體欄位可用
    - 判斷是否需要將新屬性放入 JSONB
    """
    
    @property
    def name(self) -> str:
        return "get_db_schema"
    
    @property
    def description(self) -> str:
        return (
            "Get the current database schema for documents and companies tables. "
            "Use this to understand what entity columns are available before inserting data. "
            "Any attributes not in the schema should be stored in JSONB columns."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "table_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of table names to get schema for. Default: all ingestion tables."
                }
            }
        }
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(self, table_names: Optional[List[str]] = None) -> str:
        """執行 Schema 查詢"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            # 默認查詢這些表
            tables = table_names or ['documents', 'document_companies', 'companies', 'financial_metrics']
            
            schema_info = {}
            
            async with db.connection() as conn:
                for table in tables:
                    # 獲取欄位信息
                    columns = await conn.fetch(
                        """
                        SELECT 
                            column_name,
                            data_type,
                            is_nullable,
                            column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = $1
                        ORDER BY ordinal_position
                        """,
                        table
                    )
                    
                    if columns:
                        schema_info[table] = {
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
            
            # 添加設計說明
            result = {
                "schema": schema_info,
                "design_notes": {
                    "entity_columns": "Use for frequently queried, stable attributes",
                    "jsonb_columns": [
                        "zone1_raw_data - Store raw extraction data",
                        "dynamic_attributes - Store AI-discovered attributes not in schema",
                        "ai_extracted_industries - Store multiple industries extracted by AI"
                    ],
                    "review_mechanism": "confirmed_industry requires human review, ai_extracted_industries is AI suggestion"
                }
            }
            
            logger.info(f"📋 Retrieved schema for tables: {list(schema_info.keys())}")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"❌ Failed to get schema: {e}")
            return f"Error: Failed to get database schema: {str(e)}"
        finally:
            await db.close()


class SmartInsertDocumentTool(Tool):
    """
    [Tool] 智能寫入文檔數據
    
    核心功能：
    1. 寫入實體欄位 (parent_company, confirmed_industry)
    2. 寫入 JSONB 動態屬性
    3. 處理一對多公司關係
    4. 🌟 支持指數報告的強制 Industry 賦值邏輯
    
    Industry 賦值規則：
    - 規則 A：如果報告明確定義了單一行業主題（如 Hang Seng Biotech Index），
              所有子公司/成分股都強制指派這個 Industry，不再各自產生多重 AI Industry 預測
    - 規則 B：如果是一般綜合報告，沒有定義單一 Industry，才需要為每間子公司各自提取可能的 ai_extracted_industries
    """
    
    @property
    def name(self) -> str:
        return "smart_insert_document"
    
    @property
    def description(self) -> str:
        return (
            "Insert document metadata with dynamic attributes support. "
            "Use this tool to write extracted data to the database. "
            "Core attributes go to entity columns, others go to JSONB columns. "
            "Returns the document ID if successful.\n\n"
            "🌟 Special handling for index reports:\n"
            "- If the report has a defined industry theme (e.g., 'Hang Seng Biotech Index'), "
            "all constituents will be assigned that industry (Rule A).\n"
            "- Otherwise, each company gets AI-extracted industries (Rule B)."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "The original filename of the document"
                },
                "file_path": {
                    "type": "string",
                    "description": "The storage path of the file"
                },
                "document_type": {
                    "type": "string",
                    "enum": ["annual_report", "index_report", "quarterly_report", "other"],
                    "description": "Type of document"
                },
                "parent_company": {
                    "type": ["string", "null"],
                    "description": "The parent company name. NULL for index reports (like HSI reports)"
                },
                "parent_stock_code": {
                    "type": ["string", "null"],
                    "description": "The stock code of the parent company"
                },
                # 🌟 新增：指數報告專用欄位
                "index_theme": {
                    "type": ["string", "null"],
                    "description": "Index theme name (e.g., 'Hang Seng Biotech Index'). Only for index reports."
                },
                "is_index_report": {
                    "type": "boolean",
                    "description": "Whether this is an index/market report (no single parent company)"
                },
                # 🌟 核心邏輯：報告定義的行業
                "confirmed_doc_industry": {
                    "type": ["string", "null"],
                    "description": "Industry explicitly defined by the report (e.g., 'Biotech' for Hang Seng Biotech Index). "
                                   "If set, ALL constituents will be assigned this industry (Rule A)."
                },
                "fiscal_year": {
                    "type": "integer",
                    "description": "The fiscal year of the document"
                },
                "ai_industries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of industries extracted by AI (used when confirmed_doc_industry is null)"
                },
                "subsidiaries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "stock_code": {"type": "string"},
                            "relation_type": {"type": "string"},
                            "ai_industries": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "AI-extracted industries for this company (ignored if confirmed_doc_industry is set)"
                            }
                        }
                    },
                    "description": "List of subsidiary or related companies (constituents for index reports)"
                },
                "dynamic_attributes": {
                    "type": "object",
                    "description": "Additional attributes discovered by AI that are not in the schema. Will be stored in JSONB."
                },
                "extraction_metadata": {
                    "type": "object",
                    "description": "Metadata about the extraction process"
                },
                "confidence_scores": {
                    "type": "object",
                    "description": "Confidence scores for extracted values (0.0-1.0)"
                }
            },
            "required": ["filename", "file_path", "document_type"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        filename: str,
        file_path: str,
        document_type: str,
        parent_company: Optional[str] = None,
        parent_stock_code: Optional[str] = None,
        index_theme: Optional[str] = None,
        is_index_report: bool = False,
        confirmed_doc_industry: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        ai_industries: Optional[List[str]] = None,
        subsidiaries: Optional[List[Dict]] = None,
        dynamic_attributes: Optional[Dict] = None,
        extraction_metadata: Optional[Dict] = None,
        confidence_scores: Optional[Dict] = None
    ) -> str:
        """
        執行智能寫入
        
        🌟 核心邏輯：
        - 規則 A：如果 confirmed_doc_industry 有值，所有子公司強制指派這個 Industry
        - 規則 B：如果 confirmed_doc_industry 為空，使用各公司的 ai_industries
        """
        from nanobot.ingestion.repository.db_client import DBClient
        import uuid
        
        db = DBClient()
        await db.connect()
        
        try:
            document_id = str(uuid.uuid4())
            
            async with db.transaction() as conn:
                # 1. 寫入主文檔記錄
                await conn.execute(
                    """
                    INSERT INTO documents (
                        id, filename, file_path,
                        parent_company_name,
                        index_theme,
                        is_index_report,
                        document_type,
                        confirmed_industry,
                        fiscal_year,
                        ai_extracted_industries,
                        dynamic_attributes,
                        extraction_metadata,
                        processing_status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'processing')
                    """,
                    document_id,
                    filename,
                    file_path,
                    parent_company,
                    index_theme,                    # 🌟 指數主題
                    is_index_report,                # 🌟 是否為指數報告
                    document_type,
                    confirmed_doc_industry,         # 🌟 報告定義的行業
                    fiscal_year,
                    json.dumps(ai_industries) if ai_industries else None,
                    json.dumps(dynamic_attributes) if dynamic_attributes else None,
                    json.dumps(extraction_metadata) if extraction_metadata else None
                )
                
                logger.info(f"📄 Inserted document: {filename} (ID: {document_id}, type: {document_type})")
                
                # 2. 處理母公司 (如果有)
                company_id = None
                if parent_company and parent_stock_code:
                    company_id = await self._upsert_company(
                        conn, parent_company, parent_stock_code, ai_industries
                    )
                    
                    # 更新文檔的公司關聯
                    await conn.execute(
                        "UPDATE documents SET parent_company_id = $1 WHERE id = $2",
                        company_id, document_id
                    )
                
                # 3. 寫入關聯公司 (子公司/成分股) - 🌟 實現 Industry 賦值邏輯
                subsidiary_count = 0
                if subsidiaries:
                    for sub in subsidiaries:
                        sub_company_id = await self._upsert_company(
                            conn,
                            sub.get("name"),
                            sub.get("stock_code"),
                            None
                        )
                        
                        # 🌟 核心邏輯：決定 assigned_industry
                        assigned_industry = None
                        ai_suggested_industries = None
                        industry_source = None
                        
                        if confirmed_doc_industry:
                            # 規則 A：報告有明確定義的行業 → 強制覆蓋
                            assigned_industry = confirmed_doc_industry
                            industry_source = 'report_defined'
                            # 忽略 sub.get('ai_industries')，因為報告已經定義死了
                            logger.debug(f"📋 Rule A: Assigned '{assigned_industry}' to {sub.get('name')} (from report definition)")
                        else:
                            # 規則 B：報告沒寫死 → 使用 AI 提取的行業
                            sub_ai_industries = sub.get("ai_industries", [])
                            if sub_ai_industries:
                                if len(sub_ai_industries) == 1:
                                    assigned_industry = sub_ai_industries[0]
                                else:
                                    # 多個行業，存入 JSONB
                                    ai_suggested_industries = json.dumps(sub_ai_industries)
                                    assigned_industry = sub_ai_industries[0]  # 主行業
                                industry_source = 'ai_extracted'
                                logger.debug(f"🤖 Rule B: AI extracted industries for {sub.get('name')}: {sub_ai_industries}")
                        
                        # 插入 document_companies 記錄
                        await conn.execute(
                            """
                            INSERT INTO document_companies (
                                document_id, company_id, company_name, stock_code,
                                assigned_industry, ai_suggested_industries, industry_source,
                                relation_type
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (document_id, company_id, relation_type) DO UPDATE SET
                                assigned_industry = EXCLUDED.assigned_industry,
                                ai_suggested_industries = EXCLUDED.ai_suggested_industries,
                                industry_source = EXCLUDED.industry_source
                            """,
                            document_id,
                            sub_company_id,
                            sub.get("name"),
                            sub.get("stock_code"),
                            assigned_industry,
                            ai_suggested_industries,
                            industry_source,
                            sub.get("relation_type", "index_constituent" if is_index_report else "subsidiary")
                        )
                        subsidiary_count += 1
                    
                    logger.info(f"🏢 Inserted {subsidiary_count} related companies "
                               f"(industry_source: {industry_source or 'N/A'})")
                
                # 4. 創建待覆核記錄 (如果需要)
                if confidence_scores:
                    low_confidence_items = [
                        key for key, score in confidence_scores.items()
                        if score < 0.8
                    ]
                    
                    if low_confidence_items:
                        await conn.execute(
                            """
                            INSERT INTO data_review_queue (
                                document_id, company_id,
                                review_type, ai_suggestions, ai_confidence_score
                            ) VALUES ($1, $2, 'industry_confirmation', $3, $4)
                            """,
                            document_id,
                            company_id,
                            json.dumps({
                                "ai_industries": ai_industries,
                                "confirmed_doc_industry": confirmed_doc_industry,
                                "low_confidence_items": low_confidence_items,
                                "confidence_scores": confidence_scores
                            }),
                            min(confidence_scores.values())
                        )
                        
                        logger.info(f"⚠️ Created review record for low confidence items: {low_confidence_items}")
            
            # 5. 記錄 Agent 日誌
            await self._log_agent_action(
                document_id=document_id,
                action="smart_insert",
                result={
                    "document_type": document_type,
                    "parent_company": parent_company,
                    "index_theme": index_theme,
                    "is_index_report": is_index_report,
                    "confirmed_doc_industry": confirmed_doc_industry,
                    "subsidiaries_count": subsidiary_count if subsidiaries else 0,
                    "industry_assignment_rule": "A (report_defined)" if confirmed_doc_industry else "B (ai_extracted)"
                }
            )
            
            return json.dumps({
                "success": True,
                "document_id": document_id,
                "document_type": document_type,
                "parent_company": parent_company,
                "index_theme": index_theme,
                "confirmed_industry": confirmed_doc_industry,
                "subsidiaries_count": subsidiary_count if subsidiaries else 0,
                "industry_assignment_rule": "A" if confirmed_doc_industry else "B",
                "message": f"Successfully inserted {document_type} '{filename}' with {subsidiary_count if subsidiaries else 0} related companies"
            })
            
        except Exception as e:
            logger.exception(f"❌ Failed to insert document: {e}")
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"Failed to insert document: {str(e)}"
            })
        finally:
            await db.close()
    
    async def _upsert_company(
        self,
        conn,
        name: str,
        stock_code: Optional[str],
        industries: Optional[List[str]]
    ) -> int:
        """Upsert 公司記錄，返回 company_id"""
        # 標準化股票代碼
        normalized_code = stock_code.zfill(5) if stock_code else None
        
        # 檢查是否存在
        if normalized_code:
            existing = await conn.fetchrow(
                "SELECT id FROM companies WHERE stock_code = $1",
                normalized_code
            )
            if existing:
                return existing["id"]
        
        # 創建新公司
        result = await conn.fetchrow(
            """
            INSERT INTO companies (
                stock_code,
                name_en_extracted,
                sector,
                industry,
                ai_extracted_industries
            ) VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            normalized_code,
            name,
            industries[0] if industries else "Unknown",
            industries[0] if industries else "Unknown",
            json.dumps(industries) if industries else None
        )
        
        return result["id"]
    
    async def _log_agent_action(
        self,
        document_id: str,
        action: str,
        result: Dict
    ):
        """記錄 Agent 操作日誌"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO agent_ingestion_logs (
                        document_id, agent_type, action_taken, action_result
                    ) VALUES ($1, 'ingestion', $2, $3)
                    """,
                    document_id,
                    action,
                    json.dumps(result)
                )
        finally:
            await db.close()


class UpdateDynamicAttributesTool(Tool):
    """
    [Tool] 更新 JSONB 動態屬性
    
    用於追加或更新文檔的動態屬性，不影響實體欄位
    """
    
    @property
    def name(self) -> str:
        return "update_dynamic_attributes"
    
    @property
    def description(self) -> str:
        return (
            "Update JSONB dynamic attributes for an existing document. "
            "Use this to add new AI-discovered attributes without altering the schema. "
            "Existing attributes will be merged (not replaced)."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "The document UUID"
                },
                "attributes": {
                    "type": "object",
                    "description": "Key-value pairs to add to dynamic_attributes"
                },
                "merge_mode": {
                    "type": "string",
                    "enum": ["merge", "replace"],
                    "description": "How to handle existing attributes. 'merge' combines, 'replace' overwrites."
                }
            },
            "required": ["document_id", "attributes"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        document_id: str,
        attributes: Dict[str, Any],
        merge_mode: str = "merge"
    ) -> str:
        """執行 JSONB 更新"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                if merge_mode == "merge":
                    # 使用 PostgreSQL 的 JSONB 合併操作符
                    result = await conn.execute(
                        """
                        UPDATE documents
                        SET dynamic_attributes = COALESCE(dynamic_attributes, '{}'::jsonb) || $1
                        WHERE id = $2
                        """,
                        json.dumps(attributes),
                        document_id
                    )
                else:
                    # 替換模式
                    result = await conn.execute(
                        """
                        UPDATE documents
                        SET dynamic_attributes = $1
                        WHERE id = $2
                        """,
                        json.dumps(attributes),
                        document_id
                    )
                
                if result == "UPDATE 0":
                    return json.dumps({
                        "success": False,
                        "error": "Document not found",
                        "document_id": document_id
                    })
                
                logger.info(f"📝 Updated dynamic attributes for document {document_id}")
                
                return json.dumps({
                    "success": True,
                    "document_id": document_id,
                    "updated_keys": list(attributes.keys()),
                    "merge_mode": merge_mode
                })
                
        except Exception as e:
            logger.exception(f"❌ Failed to update attributes: {e}")
            return json.dumps({
                "success": False,
                "error": str(e)
            })
        finally:
            await db.close()


class CreateReviewRecordTool(Tool):
    """
    [Tool] 創建待覆核記錄
    
    當 AI 置信度較低時，創建人工覆核任務
    """
    
    @property
    def name(self) -> str:
        return "create_review_record"
    
    @property
    def description(self) -> str:
        return (
            "Create a record in the data review queue for human verification. "
            "Use this when AI extraction has low confidence or complex cases need human review."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "The document UUID"
                },
                "company_id": {
                    "type": ["integer", "null"],
                    "description": "Optional company ID"
                },
                "review_type": {
                    "type": "string",
                    "enum": ["industry_confirmation", "data_validation", "entity_resolution"],
                    "description": "Type of review needed"
                },
                "ai_suggestions": {
                    "type": "object",
                    "description": "AI's suggested values"
                },
                "confidence_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "AI confidence score (0.0-1.0)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "normal", "low"],
                    "description": "Review priority"
                }
            },
            "required": ["document_id", "review_type", "ai_suggestions"]
        }
    
    @property
    def read_only(self) -> bool:
        return False
    
    async def execute(
        self,
        document_id: str,
        review_type: str,
        ai_suggestions: Dict,
        company_id: Optional[int] = None,
        confidence_score: Optional[float] = None,
        priority: str = "normal"
    ) -> str:
        """創建覆核記錄"""
        from nanobot.ingestion.repository.db_client import DBClient
        import uuid
        
        db = DBClient()
        await db.connect()
        
        try:
            review_id = str(uuid.uuid4())
            
            async with db.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO data_review_queue (
                        id, document_id, company_id,
                        review_type, priority,
                        ai_suggestions, ai_confidence_score
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    review_id,
                    document_id,
                    company_id,
                    review_type,
                    priority,
                    json.dumps(ai_suggestions),
                    confidence_score
                )
            
            logger.info(f"📋 Created review record: {review_id} ({review_type})")
            
            return json.dumps({
                "success": True,
                "review_id": review_id,
                "review_type": review_type,
                "priority": priority
            })
            
        except Exception as e:
            logger.exception(f"❌ Failed to create review: {e}")
            return json.dumps({
                "success": False,
                "error": str(e)
            })
        finally:
            await db.close()


# ============================================================
# Tool 註冊函數
# ============================================================

def register_ingestion_tools(registry) -> None:
    """
    註冊所有 Ingestion Tools 到 ToolRegistry
    
    Usage:
        from nanobot.agent.tools.db_ingestion_tools import register_ingestion_tools
        register_ingestion_tools(agent_loop.tools)
    """
    registry.register(GetDBSchemaTool())
    registry.register(SmartInsertDocumentTool())
    registry.register(UpdateDynamicAttributesTool())
    registry.register(CreateReviewRecordTool())
    
    logger.info("✅ Registered 4 ingestion tools: get_db_schema, smart_insert_document, update_dynamic_attributes, create_review_record")