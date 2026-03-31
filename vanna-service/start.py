"""
Vanna Service Startup Script

Features:
1. Initialize Vanna AI with ChromaDB + PostgreSQL
2. Auto-train on Database Schema
3. Provide REST API for training and queries
4. Support continuous learning (邊做邊學)
"""

import os
import time
import json
from pathlib import Path
from loguru import logger
import sys
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

# FastAPI imports
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# Database
import psycopg2
from psycopg2.extras import RealDictCursor

# Vanna
try:
    from vanna.chromadb import ChromaDB_VectorStore
    from vanna.openai import OpenAI_Chat
    
    class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
        def __init__(self, config=None):
            ChromaDB_VectorStore.__init__(self, config=config)
            OpenAI_Chat.__init__(self, config=config)
    
    VANNA_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ Vanna imports failed: {e}. Running in mock mode.")
    VANNA_AVAILABLE = False
    MyVanna = None

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# Global Vanna instance
vn: Optional[MyVanna] = None
db_url: str = ""
chroma_path: str = "/app/data/chromadb"

# Ensure data directory exists
Path(chroma_path).mkdir(parents=True, exist_ok=True)


class TrainRequest(BaseModel):
    """Training request model"""
    train_type: str = "schema"  # schema | ddl | sql
    doc_id: Optional[str] = None  # Optional: specific document ID to train on


class AskRequest(BaseModel):
    """Query request model"""
    question: str
    include_sql: bool = True
    include_summary: bool = True


class AskResponse(BaseModel):
    """Query response model"""
    question: str
    sql: Optional[str] = None
    answer: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    training_status: str = "ready"


def get_db_connection():
    """Get PostgreSQL connection"""
    return psycopg2.connect(
        os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports"
        ),
        connect_timeout=10
    )


def initialize_vanna() -> bool:
    """Initialize Vanna AI with ChromaDB and OpenAI"""
    global vn
    
    if not VANNA_AVAILABLE:
        logger.warning("⚠️ Vanna not available, running in mock mode")
        return False
    
    try:
        # Get configuration from environment
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.error("❌ OPENAI_API_KEY not set. Vanna requires OpenAI API key.")
            return False
        
        config = {
            'api_key': openai_api_key,
            'model': os.getenv("VANNA_MODEL", "gpt-4o-mini"),
            'path': chroma_path
        }
        
        vn = MyVanna(config=config)
        logger.info(f"✅ Vanna initialized with ChromaDB (path: {chroma_path})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Vanna initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def connect_vanna_to_postgres():
    """Connect Vanna to PostgreSQL database"""
    global vn, db_url
    
    if vn is None:
        logger.warning("⚠️ Vanna not initialized, skipping database connection")
        return False
    
    try:
        conn = get_db_connection()
        logger.info("✅ Vanna connected to PostgreSQL")
        
        # Get database connection details from URL
        # Format: postgresql://user:password@host:port/dbname
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        
        vn.connect_to_postgres(
            host=parsed.hostname,
            dbname=parsed.path.lstrip('/'),
            user=parsed.username,
            password=parsed.password,
            port=parsed.port or 5432
        )
        
        logger.info("✅ Vanna PostgreSQL connection established")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to connect Vanna to PostgreSQL: {e}")
        return False


def train_vanna_on_schema():
    """讓 Vanna 讀取 PostgreSQL 的結構並進行自我訓練"""
    global vn
    
    if vn is None:
        logger.warning("⚠️ Vanna not initialized, cannot train")
        return False
    
    try:
        logger.info("🧠 正在讓 Vanna 學習 Database Schema...")
        
        # Get all tables from information_schema
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT table_name, table_schema 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        logger.info(f"📊 找到 {len(tables)} 張資料表")
        
        trained_count = 0
        for table in tables:
            table_name = table['table_name']
            
            # Get DDL for each table using pg_get_tabledef
            try:
                cursor.execute(f"SELECT pg_get_tabledef('{table_name}') as ddl")
                ddl_result = cursor.fetchone()
                
                if ddl_result and ddl_result['ddl']:
                    ddl = str(ddl_result['ddl'])
                    vn.train(ddl=ddl)
                    trained_count += 1
                    logger.info(f"   ✅ Trained: {table_name}")
                else:
                    # Fallback: Get table structure from information_schema
                    cursor.execute("""
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_name = %s
                        ORDER BY ordinal_position
                    """, (table_name,))
                    
                    columns = cursor.fetchall()
                    col_defs = [f"{c['column_name']} {c['data_type']}" for c in columns]
                    ddl = f"CREATE TABLE {table_name} (\n  " + ",\n  ".join(col_defs) + "\n)"
                    vn.train(ddl=ddl)
                    trained_count += 1
                    logger.info(f"   ✅ Trained (fallback): {table_name}")
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Failed to train {table_name}: {e}")
                continue
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Vanna 訓練完成！共訓練 {trained_count} 張資料表")
        return True
        
    except Exception as e:
        logger.error(f"❌ 訓練失敗：{e}")
        import traceback
        traceback.print_exc()
        return False


def train_vanna_on_document(doc_id: str) -> bool:
    """針對特定文件進行訓練 (例如新解析的 PDF)"""
    global vn
    
    if vn is None:
        logger.warning("⚠️ Vanna not initialized, cannot train")
        return False
    
    try:
        logger.info(f"🧠 正在針對文件 {doc_id} 進行訓練...")
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. 獲取文件的表格
        cursor.execute("""
            SELECT file_path, metadata
            FROM raw_artifacts
            WHERE doc_id = %s AND file_type = 'table_json'
            LIMIT 10
        """, (doc_id,))
        
        tables = cursor.fetchall()
        
        for table in tables:
            try:
                # 讀取表格 JSON
                table_path = Path("/app/data/raw") / table['file_path']
                if table_path.exists():
                    with open(table_path, 'r', encoding='utf-8') as f:
                        table_data = json.load(f)
                    
                    # 將表格結構訓練給 Vanna
                    table_name = f"extracted_table_{table_path.stem}"
                    ddl = f"CREATE TABLE {table_name} (extracted_data JSONB)"
                    vn.train(ddl=ddl)
                    
                    # 訓練一個範例查詢
                    vn.train(
                        question=f"從 {table_name} 中提取資料",
                        sql=f"SELECT * FROM {table_name}"
                    )
                    
                    logger.info(f"   ✅ Trained table: {table_path.name}")
            except Exception as e:
                logger.warning(f"   ⚠️ Failed to train table: {e}")
                continue
        
        # 2. 獲取文件的 chunks
        cursor.execute("""
            SELECT COUNT(*) as chunk_count
            FROM document_chunks
            WHERE doc_id = %s
        """, (doc_id,))
        
        result = cursor.fetchone()
        if result:
            logger.info(f"   📄 文件包含 {result['chunk_count']} 個 chunks")
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ 文件 {doc_id} 訓練完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 文件訓練失敗：{e}")
        import traceback
        traceback.print_exc()
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager"""
    # Startup
    logger.info("="*60)
    logger.info("Vanna Service Starting...")
    logger.info("="*60)
    
    global db_url
    
    # Wait for database
    max_retries = 30
    retry_delay = 2
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports"
    )
    
    for i in range(max_retries):
        try:
            logger.info(f"Attempting database connection (Attempt {i+1}/{max_retries})...")
            conn = get_db_connection()
            conn.close()
            logger.info("✅ Database connection successful")
            break
        except Exception as e:
            logger.warning(f"Database not ready: {e}")
            if i < max_retries - 1:
                logger.info(f"Waiting {retry_delay} seconds before retry...")
                time.sleep(retry_delay)
            else:
                logger.error("❌ Cannot connect to database, exiting")
                sys.exit(1)
    
    # Initialize Vanna
    if initialize_vanna():
        connect_vanna_to_postgres()
        train_vanna_on_schema()
        logger.info("✅ Vanna Service ready")
    else:
        logger.warning("⚠️ Vanna initialization failed, running in mock mode")
    
    yield
    
    # Shutdown
    logger.info("Vanna Service shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Vanna AI Service",
    description="Text-to-SQL with RAG training for financial queries",
    version="1.0.0",
    lifespan=lifespan
)


# --- API Endpoints ---

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "vanna_available": VANNA_AVAILABLE and vn is not None,
        "chroma_path": chroma_path
    }


@app.get("/status")
async def get_status():
    """Get Vanna service status"""
    return {
        "vanna_initialized": vn is not None,
        "training_status": "ready" if vn else "not_initialized",
        "chroma_path": chroma_path
    }


@app.post("/api/train")
async def trigger_training(
    request: TrainRequest,
    background_tasks: BackgroundTasks
):
    """
    提供給 PDF Ingestion Worker 呼叫。
    當有新文件解析完畢，打這支 API，Vanna 就會在背景學習。
    
    Args:
        train_type: "schema" (全庫結構) | "ddl" (特定 DDL) | "sql" (SQL 範例)
        doc_id: Optional - 特定文件 ID
    """
    if vn is None:
        raise HTTPException(status_code=503, detail="Vanna not initialized")
    
    logger.info(f"📥 收到訓練請求：type={request.train_type}, doc_id={request.doc_id}")
    
    try:
        if request.doc_id:
            # 針對特定文件訓練
            background_tasks.add_task(train_vanna_on_document, request.doc_id)
            return {
                "status": "training_started",
                "message": f"Vanna is learning document {request.doc_id} in background."
            }
        else:
            # 全庫結構訓練
            background_tasks.add_task(train_vanna_on_schema)
            return {
                "status": "training_started",
                "message": "Vanna is learning the database schema in background."
            }
    
    except Exception as e:
        logger.error(f"❌ 訓練請求失敗：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    提供給 WebUI 呼叫，用自然語言生出 SQL 並回答
    
    Args:
        question: 自然語言問題
        include_sql: 是否返回 SQL
        include_summary: 是否返回摘要
    """
    if vn is None:
        # Mock response for demo
        return AskResponse(
            question=request.question,
            sql="SELECT * FROM documents LIMIT 10;",
            answer="[Mock] Vanna is not initialized. This is a demo response.",
            data=[{"demo": "data"}],
            training_status="not_initialized"
        )
    
    try:
        logger.info(f"🤔 收到問題：{request.question}")
        
        # Generate SQL
        sql = vn.generate_sql(request.question) if request.include_sql else None
        
        if sql:
            logger.info(f"📝 生成的 SQL: {sql}")
            
            # Run SQL
            df = vn.run_sql(sql) if request.include_sql else None
            
            # Generate answer
            answer = None
            if request.include_summary and df is not None:
                answer = vn.generate_summary(request.question, df)
            
            # Convert DataFrame to list of dicts
            data = None
            if df is not None:
                data = df.to_dict('records')
            
            return AskResponse(
                question=request.question,
                sql=sql,
                answer=answer,
                data=data,
                training_status="ready"
            )
        else:
            return AskResponse(
                question=request.question,
                sql=None,
                answer="無法生成 SQL，請嘗試重新表述問題",
                training_status="ready"
            )
    
    except Exception as e:
        logger.error(f"❌ 問題回答失敗：{e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/train/ddl")
async def train_with_ddl(ddl: str):
    """直接提供 DDL 進行訓練"""
    if vn is None:
        raise HTTPException(status_code=503, detail="Vanna not initialized")
    
    try:
        vn.train(ddl=ddl)
        logger.info(f"✅ DDL 訓練成功")
        return {"status": "success", "message": "DDL trained successfully"}
    except Exception as e:
        logger.error(f"❌ DDL 訓練失敗：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/train/sql")
async def train_with_sql(question: str, sql: str):
    """提供問題 + SQL 範例進行訓練"""
    if vn is None:
        raise HTTPException(status_code=503, detail="Vanna not initialized")
    
    try:
        vn.train(question=question, sql=sql)
        logger.info(f"✅ SQL 範例訓練成功：{question}")
        return {"status": "success", "message": "SQL example trained successfully"}
    except Exception as e:
        logger.error(f"❌ SQL 訓練失敗：{e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    logger.info("🚀 啟動 Vanna API 服務...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("VANNA_PORT", "8082")),
        log_level="info"
    )
