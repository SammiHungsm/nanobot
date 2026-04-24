"""
Retry Utilities - 統一的重試機制 (v4.16)

提供：
1. AsyncRetry - 異步函數重試裝飾器
2. LLMRetryMixin - LLM 調用專用重試
3. ToolRetryMixin - Tool 執行專用重試

使用方式：
    from nanobot.ingestion.utils.retry import with_retry, AsyncRetry
    
    # 方式1: 裝飾器
    @with_retry(max_attempts=3, backoff_factor=1.0)
    async def my_function():
        ...
    
    # 方式2: 上下文管理器
    async with AsyncRetry(max_attempts=3) as retry:
        await retry.execute(llm_core.chat, messages, tools)
"""

import asyncio
import functools
from typing import Any, Callable, Optional, Type, Tuple
from loguru import logger
from datetime import datetime


# ============================================================
# 異常類型定義
# ============================================================

class RetryableError(Exception):
    """可重試的異常基類"""
    pass


class NonRetryableError(Exception):
    """不可重試的異常（直接拋出）"""
    pass


class LLMRateLimitError(RetryableError):
    """LLM 速率限制"""
    pass


class ToolExecutionError(RetryableError):
    """Tool 執行失敗"""
    pass


class DatabaseConnectionError(RetryableError):
    """數據庫連接錯誤"""
    pass


# ============================================================
# AsyncRetry 上下文管理器
# ============================================================

class AsyncRetry:
    """
    異步重試上下文管理器
    
    使用方式：
        async with AsyncRetry(max_attempts=3, backoff_factor=1.0) as retry:
            result = await retry.execute(some_async_function, arg1, arg2)
    """
    
    # 可重試的異常（默認）
    RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
        RetryableError,
        LLMRateLimitError,
        ToolExecutionError,
        DatabaseConnectionError,
        ConnectionError,
        TimeoutError,
    )
    
    def __init__(
        self,
        max_attempts: int = 3,
        backoff_factor: float = 1.0,
        backoff_max: float = 30.0,
        retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
        on_retry: Optional[Callable[[Exception, int], None]] = None,
        retry_on_any_error: bool = False
    ):
        """
        初始化
        
        Args:
            max_attempts: 最大嘗試次數
            backoff_factor: 退避因子（秒），失敗後等待時間 = backoff_factor * (2 ** attempt)
            backoff_max: 最大退避時間（秒）
            retryable_exceptions: 可重試的異常類型元組
            on_retry: 回調函數，接收 (exception, attempt_number)
            retry_on_any_error: 是否對所有異常進行重試（不推薦）
        """
        self.max_attempts = max_attempts
        self.backoff_factor = backoff_factor
        self.backoff_max = backoff_max
        self.retryable_exceptions = retryable_exceptions or self.RETRYABLE_EXCEPTIONS
        self.on_retry = on_retry
        self.retry_on_any_error = retry_on_any_error
        
        # 內部狀態
        self.attempt = 0
        self.last_exception: Optional[Exception] = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False  # 不吞掉異常
    
    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        執行函數，失敗時自動重試
        
        Args:
            func: 異步函數
            *args: 函數參數
            **kwargs: 函數關鍵字參數
            
        Returns:
            函數執行結果
            
        Raises:
            最後一次失敗的異常
        """
        for attempt in range(1, self.max_attempts + 1):
            self.attempt = attempt
            try:
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
                
            except self.retryable_exceptions as e:
                self.last_exception = e
                
                if attempt == self.max_attempts:
                    logger.warning(
                        f"❌ 重試耗盡 ({attempt}/{self.max_attempts}): "
                        f"{type(e).__name__}: {e}"
                    )
                    raise
                
                # 計算退避時間
                sleep_time = min(
                    self.backoff_factor * (2 ** (attempt - 1)),
                    self.backoff_max
                )
                
                # 日誌
                logger.warning(
                    f"⚠️ 嘗試 {attempt}/{self.max_attempts} 失敗: "
                    f"{type(e).__name__}: {str(e)[:100]}"
                )
                
                # 調用回調
                if self.on_retry:
                    try:
                        self.on_retry(e, attempt)
                    except Exception as cb_err:
                        logger.warning(f"⚠️ on_retry 回調失敗: {cb_err}")
                
                # 等待後重試
                logger.debug(f"   ⏳ 等待 {sleep_time:.1f}s 後重試...")
                await asyncio.sleep(sleep_time)
                
            except NonRetryableError:
                # 直接拋出，不重試
                raise
                
            except Exception as e:
                # 其他異常
                self.last_exception = e
                
                if self.retry_on_any_error:
                    # 配置為重試所有錯誤
                    if attempt == self.max_attempts:
                        raise
                    
                    sleep_time = min(
                        self.backoff_factor * (2 ** (attempt - 1)),
                        self.backoff_max
                    )
                    logger.warning(f"⚠️ 重試所有錯誤 {attempt}/{self.max_attempts}: {e}")
                    await asyncio.sleep(sleep_time)
                else:
                    # 不重試，直接拋出
                    raise
        
        # 不應該到達這裡
        raise self.last_exception


# ============================================================
# 函數裝飾器
# ============================================================

def with_retry(
    max_attempts: int = 3,
    backoff_factor: float = 1.0,
    backoff_max: float = 30.0,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    retry_on_any_error: bool = False
):
    """
    重試裝飾器
    
    使用方式：
        @with_retry(max_attempts=3, backoff_factor=1.0)
        async def my_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async with AsyncRetry(
                max_attempts=max_attempts,
                backoff_factor=backoff_factor,
                backoff_max=backoff_max,
                retryable_exceptions=retryable_exceptions,
                retry_on_any_error=retry_on_any_error
            ) as retry:
                return await retry.execute(func, *args, **kwargs)
        return wrapper
    return decorator


# ============================================================
# LLM 專用重試
# ============================================================

class LLMRetryMixin:
    """
    LLM 調用專用重試 Mixin
    
    使用方式：
        class MyAgent(LLMRetryMixin):
            async def chat_with_retry(self, messages, tools=None):
                return await self.llm_execute_with_retry(
                    llm_core.chat,
                    messages=messages,
                    tools=tools
                )
    """
    
    # LLM 相關的可重試異常
    LLM_RETRYABLE = (
        LLMRateLimitError,
        ConnectionError,
        TimeoutError,
        # 底層網絡錯誤
        asyncio.TimeoutError,
    )
    
    def __init__(
        self,
        max_llm_attempts: int = 3,
        llm_backoff_factor: float = 2.0,
        llm_backoff_max: float = 60.0,
        *args,
        **kwargs
    ):
        self.max_llm_attempts = max_llm_attempts
        self.llm_backoff_factor = llm_backoff_factor
        self.llm_backoff_max = llm_backoff_max
        super().__init__(*args, **kwargs)
    
    async def llm_execute_with_retry(
        self,
        llm_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        LLM 執行並重試
        
        Args:
            llm_func: LLM 調用函數（如 llm_core.chat）
            *args, **kwargs: 傳給 llm_func 的參數
            
        Returns:
            LLM 執行結果
        """
        async with AsyncRetry(
            max_attempts=self.max_llm_attempts,
            backoff_factor=self.llm_backoff_factor,
            backoff_max=self.llm_backoff_max,
            retryable_exceptions=self.LLM_RETRYABLE,
            on_retry=lambda e, attempt: logger.warning(
                f"⚠️ LLM 重試 {attempt}/{self.max_llm_attempts}: {e}"
            )
        ) as retry:
            return await retry.execute(llm_func, *args, **kwargs)


# ============================================================
# Tool 執行專用重試
# ============================================================

class ToolRetryMixin:
    """
    Tool 執行專用重試 Mixin
    
    使用方式：
        class MyExecutor(ToolRetryMixin):
            async def execute_tool_with_retry(self, tool, tool_args):
                return await self.tool_execute_with_retry(
                    tool.execute,
                    **tool_args
                )
    """
    
    # Tool 相關的可重試異常
    TOOL_RETRYABLE = (
        ToolExecutionError,
        DatabaseConnectionError,
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
    )
    
    def __init__(
        self,
        max_tool_attempts: int = 3,
        tool_backoff_factor: float = 0.5,
        tool_backoff_max: float = 10.0,
        *args,
        **kwargs
    ):
        self.max_tool_attempts = max_tool_attempts
        self.tool_backoff_factor = tool_backoff_factor
        self.tool_backoff_max = tool_backoff_max
        super().__init__(*args, **kwargs)
    
    async def tool_execute_with_retry(
        self,
        tool_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Tool 執行並重試
        
        Args:
            tool_func: Tool 的 execute 方法
            *args, **kwargs: 傳給 execute 的參數
            
        Returns:
            Tool 執行結果
        """
        async with AsyncRetry(
            max_attempts=self.max_tool_attempts,
            backoff_factor=self.tool_backoff_factor,
            backoff_max=self.tool_backoff_max,
            retryable_exceptions=self.TOOL_RETRYABLE,
            on_retry=lambda e, attempt: logger.warning(
                f"⚠️ Tool 重試 {attempt}/{self.max_tool_attempts}: {e}"
            )
        ) as retry:
            return await retry.execute(tool_func, *args, **kwargs)


# ============================================================
# 便捷函數
# ============================================================

async def retry_llm_call(
    llm_func: Callable,
    *args,
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
    **kwargs
) -> Any:
    """
    便捷函數：帶重試的 LLM 調用
    
    Args:
        llm_func: LLM 函數
        *args, **kwargs: LLM 函數參數
        max_attempts: 最大嘗試次數
        backoff_factor: 退避因子
        
    Returns:
        LLM 執行結果
    """
    async with AsyncRetry(
        max_attempts=max_attempts,
        backoff_factor=backoff_factor,
        backoff_max=60.0,
        retryable_exceptions=LLMRetryMixin.LLM_RETRYABLE
    ) as retry:
        return await retry.execute(llm_func, *args, **kwargs)


async def retry_tool_call(
    tool_func: Callable,
    *args,
    max_attempts: int = 3,
    backoff_factor: float = 0.5,
    **kwargs
) -> Any:
    """
    便捷函數：帶重試的 Tool 調用
    
    Args:
        tool_func: Tool 的 execute 方法
        *args, **kwargs: execute 參數
        max_attempts: 最大嘗試次數
        backoff_factor: 退避因子
        
    Returns:
        Tool 執行結果
    """
    async with AsyncRetry(
        max_attempts=max_attempts,
        backoff_factor=backoff_factor,
        backoff_max=10.0,
        retryable_exceptions=ToolRetryMixin.TOOL_RETRYABLE
    ) as retry:
        return await retry.execute(tool_func, *args, **kwargs)
