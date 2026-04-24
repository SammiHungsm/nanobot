"""
Tracing & Monitoring - Pipeline 追蹤與監控 (v4.16)

提供：
1. PipelineTracer - Pipeline 級別的追蹤
2. StageTracer - Stage 級別的追蹤
3. MetricsCollector - 指標收集器
4. 統一日誌格式

使用方式：
    from nanobot.ingestion.utils.tracing import PipelineTracer, MetricsCollector
    
    tracer = PipelineTracer("2023_annual_report_00001")
    
    async with tracer.span("stage4_agentic"):
        result = await stage4.run(...)
    
    metrics = MetricsCollector.get_current()
    logger.info(metrics.summary())
"""

import time
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from contextlib import asynccontextmanager, contextmanager
from loguru import logger
from dataclasses import dataclass, field, asdict
from enum import Enum


# ============================================================
# Enums
# ============================================================

class SpanStatus(Enum):
    """Span 狀態"""
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


# ============================================================
# Dataclasses
# ============================================================

@dataclass
class Span:
    """追蹤 Span"""
    name: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    parent_id: Optional[str] = None
    start_time: float = field(default_factory=time.perf_counter)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: SpanStatus = SpanStatus.OK
    error_message: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    children: List["Span"] = field(default_factory=list)
    
    def end(self, status: SpanStatus = SpanStatus.OK, error: Optional[str] = None):
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status
        if error:
            self.error_message = error


@dataclass
class MetricPoint:
    """指標數據點"""
    name: str
    value: float
    unit: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: Dict[str, str] = field(default_factory=dict)


# ============================================================
# PipelineTracer
# ============================================================

class PipelineTracer:
    """
    Pipeline 追蹤器
    
    功能：
    - 記錄 Pipeline 級別的執行追蹤
    - 支持嵌套 Span（Stage 之間的包含關係）
    - 自動計算 Duration 和 Status
    - 生成追蹤報告
    
    使用方式：
        tracer = PipelineTracer("2023_annual_report_00001")
        
        async with tracer.span("stage4"):
            await stage4.run(...)
        
        report = tracer.generate_report()
    """
    
    def __init__(self, doc_id: str, trace_id: Optional[str] = None):
        """
        初始化
        
        Args:
            doc_id: 文檔 ID
            trace_id: 追蹤 ID（如果為 None，自動生成）
        """
        self.trace_id = trace_id or f"trace_{uuid.uuid4().hex[:12]}"
        self.doc_id = doc_id
        self.start_time = time.perf_counter()
        self.end_time: Optional[float] = None
        self.spans: List[Span] = []
        self._span_stack: List[Span] = []  # 用於嵌套 Span
        self._current_span: Optional[Span] = None
    
    @property
    def duration_ms(self) -> float:
        """總執行時間（毫秒）"""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return (time.perf_counter() - self.start_time) * 1000
    
    @contextmanager
    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        創建 Span（同步版本）
        
        Args:
            name: Span 名稱（如 "stage4_agentic"）
            attributes: 額外屬性
        """
        span = Span(
            name=name,
            parent_id=self._current_span.span_id if self._current_span else None,
            attributes=attributes or {}
        )
        
        self._span_stack.append(span)
        self._current_span = span
        self.spans.append(span)
        
        try:
            yield span
        except Exception as e:
            span.end(SpanStatus.ERROR, str(e))
            raise
        finally:
            span.end()
            self._span_stack.pop()
            self._current_span = self._span_stack[-1] if self._span_stack else None
    
    @asynccontextmanager
    async def async_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        創建 Span（異步版本）
        
        Args:
            name: Span 名稱
            attributes: 額外屬性
        """
        span = Span(
            name=name,
            parent_id=self._current_span.span_id if self._current_span else None,
            attributes=attributes or {}
        )
        
        self._span_stack.append(span)
        self._current_span = span
        self.spans.append(span)
        
        try:
            yield span
        except Exception as e:
            span.end(SpanStatus.ERROR, str(e))
            raise
        finally:
            span.end()
            self._span_stack.pop()
            self._current_span = self._span_stack[-1] if self._span_stack else None
    
    def record_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        記錄事件
        
        Args:
            name: 事件名稱
            attributes: 事件屬性
        """
        if self._current_span:
            event = {
                "name": name,
                "timestamp": datetime.now().isoformat(),
                "attributes": attributes or {}
            }
            self._current_span.attributes.setdefault("_events", []).append(event)
    
    def generate_report(self) -> Dict[str, Any]:
        """
        生成追蹤報告
        
        Returns:
            dict: 追蹤報告
        """
        self.end_time = time.perf_counter()
        
        # 按名稱分組統計
        span_stats: Dict[str, Dict[str, Any]] = {}
        for span in self.spans:
            if span.name not in span_stats:
                span_stats[span.name] = {
                    "count": 0,
                    "total_duration_ms": 0,
                    "min_duration_ms": float("inf"),
                    "max_duration_ms": 0,
                    "errors": 0
                }
            
            stats = span_stats[span.name]
            stats["count"] += 1
            stats["total_duration_ms"] += span.duration_ms or 0
            stats["min_duration_ms"] = min(stats["min_duration_ms"], span.duration_ms or 0)
            stats["max_duration_ms"] = max(stats["max_duration_ms"], span.duration_ms or 0)
            if span.status == SpanStatus.ERROR:
                stats["errors"] += 1
        
        # 計算平均值
        for name, stats in span_stats.items():
            if stats["count"] > 0:
                stats["avg_duration_ms"] = stats["total_duration_ms"] / stats["count"]
        
        return {
            "trace_id": self.trace_id,
            "doc_id": self.doc_id,
            "pipeline_duration_ms": self.duration_ms,
            "total_spans": len(self.spans),
            "span_stats": span_stats,
            "errors": sum(1 for s in self.spans if s.status == SpanStatus.ERROR),
            "spans": [
                {
                    "name": s.name,
                    "span_id": s.span_id,
                    "parent_id": s.parent_id,
                    "duration_ms": s.duration_ms,
                    "status": s.status.value,
                    "error_message": s.error_message,
                    "attributes": {k: v for k, v in s.attributes.items() if not k.startswith("_")}
                }
                for s in self.spans
            ]
        }


# ============================================================
# MetricsCollector
# ============================================================

class MetricsCollector:
    """
    指標收集器
    
    功能：
    - 收集 Pipeline 執行指標
    - LLM 調用次數和 Token 消耗
    - Tool 調用次數和成功率
    - Stage 執行時間
    - 自動計算 QPS、延遲百分位
    
    使用方式：
        collector = MetricsCollector()
        
        # 記錄 LLM 調用
        collector.record_llm_call(model="gpt-4", tokens=1000, latency_ms=200)
        
        # 記錄 Tool 調用
        collector.record_tool_call(tool_name="insert_financial_metrics", success=True)
        
        # 獲取報告
        report = collector.generate_report()
    """
    
    # 類級別的全局收集器
    _instances: Dict[str, "MetricsCollector"] = {}
    _current: Optional["MetricsCollector"] = None
    
    def __init__(self, name: str = "default"):
        """
        初始化
        
        Args:
            name: 收集器名稱
        """
        self.name = name
        self.start_time = time.perf_counter()
        self.end_time: Optional[float] = None
        
        # LLM 指標
        self.llm_calls: List[Dict[str, Any]] = []
        self.total_tokens = 0
        self.total_llm_latency_ms = 0.0
        
        # Tool 指標
        self.tool_calls: List[Dict[str, Any]] = []
        self.tool_success = 0
        self.tool_failure = 0
        
        # Stage 指標
        self.stage_durations: Dict[str, float] = {}
        
        # 自定義指標
        self.custom_metrics: List[MetricPoint] = []
    
    @classmethod
    def get_current(cls) -> "MetricsCollector":
        """獲取當前收集器"""
        if cls._current is None:
            cls._current = cls()
        return cls._current
    
    @classmethod
    def set_current(cls, collector: "MetricsCollector"):
        """設置當前收集器"""
        cls._current = collector
        cls._instances[collector.name] = collector
    
    @classmethod
    def get_instance(cls, name: str) -> Optional["MetricsCollector"]:
        """獲取指定名稱的收集器"""
        return cls._instances.get(name)
    
    def record_llm_call(
        self,
        model: str,
        tokens: int,
        latency_ms: float,
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        記錄 LLM 調用
        
        Args:
            model: 模型名稱
            tokens: 消耗的 Token 數
            latency_ms: 延遲（毫秒）
            success: 是否成功
            error: 錯誤信息
        """
        self.llm_calls.append({
            "model": model,
            "tokens": tokens,
            "latency_ms": latency_ms,
            "success": success,
            "error": error,
            "timestamp": datetime.now().isoformat()
        })
        self.total_tokens += tokens
        self.total_llm_latency_ms += latency_ms
    
    def record_tool_call(
        self,
        tool_name: str,
        success: bool,
        latency_ms: float = 0,
        error: Optional[str] = None,
        company_id: Optional[int] = None
    ):
        """
        記錄 Tool 調用
        
        Args:
            tool_name: Tool 名稱
            success: 是否成功
            latency_ms: 延遲（毫秒）
            error: 錯誤信息
            company_id: 公司 ID
        """
        self.tool_calls.append({
            "tool_name": tool_name,
            "success": success,
            "latency_ms": latency_ms,
            "error": error,
            "company_id": company_id,
            "timestamp": datetime.now().isoformat()
        })
        
        if success:
            self.tool_success += 1
        else:
            self.tool_failure += 1
    
    def record_stage_duration(self, stage_name: str, duration_ms: float):
        """
        記錄 Stage 執行時間
        
        Args:
            stage_name: Stage 名稱
            duration_ms: 執行時間（毫秒）
        """
        if stage_name not in self.stage_durations:
            self.stage_durations[stage_name] = 0
        self.stage_durations[stage_name] += duration_ms
    
    def record_metric(self, name: str, value: float, unit: str = "", tags: Optional[Dict] = None):
        """
        記錄自定義指標
        
        Args:
            name: 指標名稱
            value: 指標值
            unit: 單位
            tags: 標籤
        """
        self.custom_metrics.append(MetricPoint(
            name=name,
            value=value,
            unit=unit,
            tags=tags or {}
        ))
    
    def generate_report(self) -> Dict[str, Any]:
        """
        生成指標報告
        
        Returns:
            dict: 指標報告
        """
        self.end_time = time.perf_counter()
        total_duration_ms = (self.end_time - self.start_time) * 1000
        
        # LLM 統計
        llm_report = {}
        if self.llm_calls:
            latencies = [c["latency_ms"] for c in self.llm_calls]
            llm_report = {
                "total_calls": len(self.llm_calls),
                "total_tokens": self.total_tokens,
                "avg_latency_ms": sum(latencies) / len(latencies),
                "p50_latency_ms": self._percentile(latencies, 0.5),
                "p95_latency_ms": self._percentile(latencies, 0.95),
                "p99_latency_ms": self._percentile(latencies, 0.99),
                "success_rate": sum(1 for c in self.llm_calls if c["success"]) / len(self.llm_calls)
            }
        
        # Tool 統計
        tool_report = {}
        if self.tool_calls:
            tool_names = set(c["tool_name"] for c in self.tool_calls)
            tool_stats = {}
            for name in tool_names:
                calls = [c for c in self.tool_calls if c["tool_name"] == name]
                successes = sum(1 for c in calls if c["success"])
                tool_stats[name] = {
                    "total": len(calls),
                    "success": successes,
                    "failure": len(calls) - successes,
                    "success_rate": successes / len(calls) if calls else 0
                }
            
            tool_report = {
                "total_calls": len(self.tool_calls),
                "success": self.tool_success,
                "failure": self.tool_failure,
                "success_rate": self.tool_success / (self.tool_success + self.tool_failure) if (self.tool_success + self.tool_failure) > 0 else 0,
                "by_tool": tool_stats
            }
        
        return {
            "collector_name": self.name,
            "total_duration_ms": total_duration_ms,
            "llm": llm_report,
            "tool": tool_report,
            "stage_durations_ms": self.stage_durations,
            "custom_metrics": [asdict(m) for m in self.custom_metrics]
        }
    
    @staticmethod
    def _percentile(data: List[float], p: float) -> float:
        """計算百分位"""
        if not data:
            return 0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p)
        return sorted_data[min(idx, len(sorted_data) - 1)]


# ============================================================
# Stage 包裝器（自動追蹤）
# ============================================================

class TracedStage:
    """
    Stage 包裝器（自動追蹤）
    
    使用方式：
        traced_stage = TracedStage(stage4_agentic_extractor)
        
        result = await traced_stage.run(...)
        # 自動記錄執行時間、成功率等
    """
    
    def __init__(self, stage_func: Callable, stage_name: str):
        """
        初始化
        
        Args:
            stage_func: Stage 函數
            stage_name: Stage 名稱
        """
        self.stage_func = stage_func
        self.stage_name = stage_name
    
    async def run(self, *args, tracer: Optional[PipelineTracer] = None, **kwargs):
        """
        執行 Stage（帶追蹤）
        
        Args:
            *args, **kwargs: 傳給 Stage 函數的參數
            tracer: 追蹤器
            
        Returns:
            Stage 函數的執行結果
        """
        collector = MetricsCollector.get_current()
        start_time = time.perf_counter()
        
        try:
            if tracer:
                async with tracer.async_span(self.stage_name):
                    result = await self.stage_func(*args, **kwargs)
            else:
                result = await self.stage_func(*args, **kwargs)
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            collector.record_stage_duration(self.stage_name, duration_ms)
            
            return result
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            collector.record_stage_duration(self.stage_name, duration_ms)
            raise
