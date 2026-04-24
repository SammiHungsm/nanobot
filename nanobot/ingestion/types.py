"""
Type Definitions - 類型定義與別名 (v4.16)

目的：統一全系統的類型命名，避免混淆

命名規範：
- doc_id: str - 業務標識符（如 "2023_annual_report_00001"）
  - 用於：文件名、文件路徑、外部 API
- document_id: int - 數據庫主鍵
  - 用於：SQL 表的外鍵、關聯查詢
- company_id: int - 公司主鍵
- page_num: int - 頁碼（從 1 開始）
- artifact_id: str - artifact 唯一標識（UUID）

使用方式：
    from nanobot.ingestion.types import (
        DocId,          # TypeAlias = str
        DocumentId,     # TypeAlias = int
        CompanyId,      # TypeAlias = int
        PageNum,        # TypeAlias = int
        ArtifactId,     # TypeAlias = str
    )
    
    def process_document(doc_id: DocId, document_id: DocumentId):
        # ...
"""

from typing import TypeAlias

# ============================================================
# 基礎類型別名
# ============================================================

DocId: TypeAlias = str
"""業務標識符 - 用於文件名、URL、業務邏輯"""

DocumentId: TypeAlias = int
"""數據庫主鍵 - 用於 SQL 外鍵、關聯"""

CompanyId: TypeAlias = int
"""公司主鍵 - 用於 SQL 外鍵"""

PageNum: TypeAlias = int
"""頁碼 - 從 1 開始"""

ArtifactId: TypeAlias = str
"""Artifact 唯一標識 - UUID 字符串"""

JobId: TypeAlias = str
"""LlamaParse Job ID"""

TraceId: TypeAlias = str
"""追蹤 ID - 用於 Tracing"""

# ============================================================
# 枚舉定義
# ============================================================

class ReportType:
    """報告類型"""
    ANNUAL_REPORT = "annual_report"
    INDEX_REPORT = "index_report"
    QUARTERLY_REPORT = "quarterly_report"
    INTERIM_REPORT = "interim_report"
    ESG_REPORT = "esg_report"


class ProcessingStatus:
    """處理狀態"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEW = "review"


class ExtractionType:
    """提取類型"""
    REVENUE_BREAKDOWN = "revenue_breakdown"
    FINANCIAL_METRICS = "financial_metrics"
    KEY_PERSONNEL = "key_personnel"
    SHAREHOLDING = "shareholding"
    MARKET_DATA = "market_data"
    ENTITY_RELATION = "entity_relation"
    MENTIONED_COMPANY = "mentioned_company"


class ConfidenceLevel:
    """置信度等級"""
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


# ============================================================
# 數據類型定義
# ============================================================

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class ParsedDocument:
    """解析後的文檔"""
    doc_id: DocId
    job_id: JobId
    total_pages: int
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_output_dir: Optional[str] = None


@dataclass
class CompanyInfo:
    """公司信息"""
    company_id: Optional[CompanyId] = None
    stock_code: Optional[str] = None
    name_en: Optional[str] = None
    name_zh: Optional[str] = None
    industry: Optional[str] = None
    sector: Optional[str] = None


@dataclass
class ExtractionResult:
    """提取結果"""
    success: bool
    document_id: DocumentId
    extracted_count: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageMetrics:
    """Stage 指標"""
    stage_name: str
    duration_ms: float
    status: str
    artifacts_processed: int = 0
    errors: int = 0
    warnings: int = 0
