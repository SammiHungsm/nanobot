"""
Agentic Workflow Executor - Tool Calling Loop (v4.16)

执行真正的 Agentic Workflow：
1. 把 Tools Schema 传给 LLM
2. LLM 决定调用哪个 Tool
3. 执行 Tool 并返回结果给 LLM
4. 循环直到 LLM 完成

🌟 v4.3 Critical Fix:
- Context 現在正確傳入 Tools！
- Tools 可以訪問 db_client, document_id, company_id 等

🌟 v4.16 新特性：
- LLM 調用重試機制（網絡抖動、速率限制）
- Tool 執行重試機制（暫時性錯誤）
- 雙層重試：LLM 失敗重試 3 次，Tool 失敗重試 2 次

Usage:
    from nanobot.ingestion.agentic_executor import AgenticExecutor
    
    executor = AgenticExecutor(llm_core, tools_registry)
    result = await executor.run(prompt, context={"db_client": db, ...})
"""

import json
import asyncio
from typing import Dict, Any, List, Optional, Callable
from loguru import logger

from nanobot.core.llm_core import llm_core
from nanobot.providers.base import LLMResponse, ToolCallRequest
from nanobot.ingestion.utils.retry import AsyncRetry, LLMRateLimitError, ToolExecutionError


class AgenticExecutor:
    """
    Agentic Workflow Executor
    
    执行 Tool Calling Loop，让 LLM 真正调用 Tools
    """
    
    def __init__(
        self,
        tools_registry: Dict[str, Any],  # 🌟 改为 Any，可以是 Tool 实例或 execute 方法
        max_iterations: int = 10,
        model: str = None,
        # 🌟 v4.16: 重試配置
        max_llm_attempts: int = 3,
        max_tool_attempts: int = 2,
        llm_backoff_factor: float = 2.0,
        tool_backoff_factor: float = 0.5
    ):
        """
        初始化
        
        Args:
            tools_registry: Tool 名称 → Tool 实例或 execute 函数的映射
            max_iterations: 最大迭代次数（防止无限循环）
            model: LLM 模型
            max_llm_attempts: 🌟 v4.16 LLM 最大嘗試次數
            max_tool_attempts: 🌟 v4.16 Tool 最大嘗試次數
            llm_backoff_factor: 🌟 v4.16 LLM 退避因子（秒）
            tool_backoff_factor: 🌟 v4.16 Tool 退避因子（秒）
        """
        self.tools_registry = tools_registry
        self.max_iterations = max_iterations
        self.model = model or llm_core.default_model
        self.context = {}  # 🌟 v4.3: Store context for tool execution
        # 🌟 v4.16: 重試配置
        self.max_llm_attempts = max_llm_attempts
        self.max_tool_attempts = max_tool_attempts
        self.llm_backoff_factor = llm_backoff_factor
        self.tool_backoff_factor = tool_backoff_factor
    
    def _build_tools_schema(self) -> List[Dict[str, Any]]:
        """
        构建 OpenAI 格式的 Tools Schema
        
        🌟 v3.20: 支持两种格式
        - Tool 实例（有 .name, .parameters, .description 属性）
        - execute 方法（bound method，需要从 __self__ 获取属性）
        
        Returns:
            List[Dict]: OpenAI 格式的 tools 列表
        """
        tools_schema = []
        
        for name, tool_obj in self.tools_registry.items():
            # 🌟 检查是否是 Tool 实例
            if hasattr(tool_obj, 'execute'):
                # 是 Tool 实例
                tool_instance = tool_obj
                execute_func = tool_instance.execute
            else:
                # 是 execute 方法
                execute_func = tool_obj
                tool_instance = getattr(tool_obj, '__self__', None)
            
            # 🌟 获取 parameters 定义
            if tool_instance and hasattr(tool_instance, 'parameters'):
                parameters = tool_instance.parameters
            elif hasattr(execute_func, 'parameters_schema'):
                parameters = execute_func.parameters_schema
            else:
                # Fallback: 空参数
                parameters = {"type": "object", "properties": {}, "required": []}
            
            # 🌟 获取 description
            description = ""
            if tool_instance and hasattr(tool_instance, 'description'):
                description = tool_instance.description
            elif hasattr(execute_func, '__doc__'):
                description = execute_func.__doc__ or f"Execute {name}"
            
            # 🌟 构建 OpenAI Tool Schema
            tools_schema.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters
                }
            })
        
        return tools_schema
    
    async def _execute_tool(self, tool_call: ToolCallRequest) -> str:
        """
        执行单个 Tool
        
        🌟 v4.13 新特性：
        - 執行前驗證參數
        - 執行後保存 Tool Call Trace 到 DB
        - 執行後驗證結果
        
        Args:
            tool_call: Tool 调用请求
            
        Returns:
            str: Tool 执行结果
        """
        import time
        start_time = time.time()
        
        tool_name = tool_call.name
        tool_args = tool_call.arguments
        
        logger.info(f"   🔧 执行 Tool: {tool_name}({tool_args})")
        
        if tool_name not in self.tools_registry:
            error_msg = f"Tool '{tool_name}' not found"
            self._save_tool_trace(tool_name, tool_args, None, False, error_msg)
            return json.dumps({"error": error_msg})
        
        tool_obj = self.tools_registry[tool_name]
        
        # =================================================================
        # 🌟 Step 1: Pre-execution Validation (參數驗證)
        # =================================================================
        validation_error = self._validate_tool_parameters(tool_name, tool_obj, tool_args)
        if validation_error:
            logger.warning(f"   ⚠️ Tool '{tool_name}' 參數驗證失敗: {validation_error}")
            self._save_tool_trace(tool_name, tool_args, None, False, validation_error)
            return json.dumps({"error": f"Parameter validation failed: {validation_error}"})
        
        # =================================================================
        # 🌟 Step 2: Auto Type Casting (根據 Tool 的 Schema 自動轉型)
        # =================================================================
        if hasattr(tool_obj, 'parameters'):
            properties = tool_obj.parameters.get("properties", {})
            
            for key, val in tool_args.items():
                if key in properties and val is not None:
                    expected_type = properties[key].get("type")
                    
                    try:
                        if expected_type == "integer":
                            if isinstance(val, str):
                                tool_args[key] = int(float(val))
                            elif isinstance(val, float):
                                tool_args[key] = int(val)
                        elif expected_type == "number":
                            if isinstance(val, str):
                                tool_args[key] = float(val)
                        elif expected_type == "boolean":
                            if isinstance(val, str):
                                tool_args[key] = val.lower() in ("true", "1", "yes", "t")
                            elif isinstance(val, (int, float)):
                                tool_args[key] = bool(val)
                        elif expected_type == "string":
                            tool_args[key] = str(val)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"⚠️ 自動轉型失敗: {key}={val} (預期: {expected_type}), error: {e}")
        
        # =================================================================
        # 🌟 Step 3: 執行 Tool（帶重試機制）
        # =================================================================
        result = None
        success = False
        error_message = None
        
        async with AsyncRetry(
            max_attempts=self.max_tool_attempts,
            backoff_factor=self.tool_backoff_factor,
            backoff_max=10.0,
            retryable_exceptions=(ToolExecutionError, ConnectionError, TimeoutError),
            on_retry=lambda e, attempt: logger.warning(
                f"   ⚠️ Tool '{tool_name}' 重試 {attempt}/{self.max_tool_attempts}: {e}"
            )
        ) as retry:
            try:
                if hasattr(tool_obj, 'execute'):
                    execute_func = tool_obj.execute
                else:
                    execute_func = tool_obj
                
                import inspect
                sig = inspect.signature(execute_func)
                accepts_context = 'context' in sig.parameters
                
                if accepts_context:
                    tool_args_with_context = {**tool_args, 'context': self.context}
                else:
                    tool_args_with_context = tool_args
                
                result = await retry.execute(execute_func, **tool_args_with_context)
                success = True
                
                # 🌟 确保结果是字符串
                if isinstance(result, dict):
                    result_str = json.dumps(result, indent=2, ensure_ascii=False)
                else:
                    result_str = str(result)
                
                logger.debug(f"   ✅ Tool 结果: {result_str[:100]}...")
                
            except Exception as e:
                error_message = str(e)
                logger.warning(f"   ⚠️ Tool '{tool_name}' 執行失敗: {e}")
                result_str = json.dumps({"error": error_message})
                result = {"error": error_message}
        
        # =================================================================
        # 🌟 Step 4: 保存 Tool Call Trace 到 DB
        # =================================================================
        duration_ms = int((time.time() - start_time) * 1000)
        self._save_tool_trace(tool_name, tool_args, result, success, error_message, duration_ms)
        
        # =================================================================
        # 🌟 Step 5: Post-execution Validation (結果驗證)
        # =================================================================
        if success:
            post_validation = self._validate_tool_result(tool_name, result)
            if post_validation:
                logger.warning(f"   ⚠️ Tool '{tool_name}' 結果驗證警告: {post_validation}")
        
        return result_str
    
    def _validate_tool_parameters(self, tool_name: str, tool_obj: Any, tool_args: Dict) -> Optional[str]:
        """
        🌟 v4.13: 執行前參數驗證
        
        檢查必填參數是否存在、類型是否正確。
        
        Returns:
            Optional[str]: 錯誤訊息，None 表示通過驗證
        """
        if not hasattr(tool_obj, 'parameters'):
            return None
        
        schema = tool_obj.parameters
        required = schema.get('required', [])
        properties = schema.get('properties', {})
        
        # 檢查必填參數
        for req_param in required:
            if req_param not in tool_args or tool_args[req_param] is None:
                return f"Missing required parameter: {req_param}"
        
        # 檢查類型（寬鬆檢查）
        for key, val in tool_args.items():
            if key in properties and val is not None:
                expected_type = properties[key].get('type')
                # 只做簡單檢查，Auto Type Casting 會處理大部分情況
                if expected_type == 'integer' and not isinstance(val, (int, float, str)):
                    return f"Parameter '{key}' should be numeric, got {type(val).__name__}"
        
        return None
    
    def _validate_tool_result(self, tool_name: str, result: Any) -> Optional[str]:
        """
        🌟 v4.13: 執行後結果驗證
        
        檢查結果是否合理（例如 insert 操作是否返回成功訊息）。
        
        Returns:
            Optional[str]: 警告訊息，None 表示通過驗證
        """
        if result is None:
            return "Tool returned None"
        
        if isinstance(result, dict):
            if 'error' in result:
                return f"Tool returned error: {result['error']}"
        
        # 針對 insert 類 Tool，檢查是否返回成功訊息
        if tool_name.startswith('insert_') and isinstance(result, str):
            if 'success' not in result.lower() and 'error' in result.lower():
                return "Insert tool returned error"
        
        return None
    
    def _save_tool_trace(
        self,
        tool_name: str,
        tool_args: Dict,
        tool_result: Any,
        success: bool,
        error_message: str = None,
        duration_ms: int = 0
    ) -> None:
        """
        🌟 v4.13: 保存 Tool Call Trace 到 DB
        """
        # 從 context 獲取 db_client 和 document_id
        db_client = self.context.get('db_client')
        document_id = self.context.get('document_id')
        
        if not db_client or not document_id:
            logger.debug(f"   📝 Tool Trace (skip DB): {tool_name} -> {success}")
            return
        
        try:
            # 使用 sync wrapper 或直接調用 async
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在 running loop 中，使用 create_task
                asyncio.create_task(
                    db_client.save_tool_call_trace(
                        document_id=document_id,
                        trace_id=self.trace_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tool_result=tool_result,
                        success=success,
                        error_message=error_message,
                        duration_ms=duration_ms
                    )
                )
            else:
                loop.run_until_complete(
                    db_client.save_tool_call_trace(
                        document_id=document_id,
                        trace_id=self.trace_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tool_result=tool_result,
                        success=success,
                        error_message=error_message,
                        duration_ms=duration_ms
                    )
                )
        except Exception as e:
            logger.debug(f"   📝 Tool Trace (save failed): {e}"))
    
    async def run(
        self,
        system_prompt: str,
        user_message: str,
        context: Dict[str, Any] = None,
        on_tool_call: Callable[[str, Dict], None] = None,
        trace_id: str = None  # 🌟 v4.13: 追蹤 ID（用於 Debug）
    ) -> Dict[str, Any]:
        """
        执行 Agentic Workflow
        
        🌟 v4.13 新特性：
        - trace_id: 用於追蹤整個 workflow 的 Tool 調用
        - 自動保存 Tool Call Trace 到 DB
        
        Args:
            system_prompt: System Prompt
            user_message: 用户消息
            context: 上下文信息
            on_tool_call: Tool 调用回调
            trace_id: 🆕 追蹤 ID
            
        Returns:
            Dict: 执行结果 {"content": str, "tool_calls": List, "iterations": int, "trace_id": str}
        """
        # 🌟 v4.13: 生成或使用 trace_id
        import uuid
        self.trace_id = trace_id or f"trace_{uuid.uuid4().hex[:16]}"
        
        logger.info(f"🤖 Agentic Workflow 开始 (tools={len(self.tools_registry)}, trace_id={self.trace_id})")
        
        # 🌟 v4.3: Store context for tool execution
        self.context = context or {}
        
        # 🌟 构建初始 messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # 🌟 构建 Tools Schema
        tools_schema = self._build_tools_schema()
        
        # 🌟 Tool Calling Loop
        iterations = 0
        all_tool_calls = []
        
        while iterations < self.max_iterations:
            iterations += 1
            logger.debug(f"   🔄 Iteration {iterations}/{self.max_iterations}")
            
            # 🌟 v4.16: 调用 LLM（带重試機制）
            async with AsyncRetry(
                max_attempts=self.max_llm_attempts,
                backoff_factor=self.llm_backoff_factor,
                backoff_max=60.0,
                retryable_exceptions=(LLMRateLimitError, ConnectionError, TimeoutError),
                on_retry=lambda e, attempt: logger.warning(
                    f"   ⚠️ LLM 重試 {attempt}/{self.max_llm_attempts}: {e}"
                )
            ) as retry:
                response: LLMResponse = await retry.execute(
                    llm_core.chat,
                    messages=messages,
                    tools=tools_schema,
                    tool_choice="auto",
                    return_response=True,
                    model=self.model
                )
            
            # 🌟 Debug: 记录 LLM 响应状态
            logger.debug(f"   📨 LLM Response: has_tool_calls={response.has_tool_calls}, finish_reason={response.finish_reason}")
            if response.content:
                logger.debug(f"   📝 Content preview: {response.content[:200]}...")
            if response.tool_calls:
                logger.debug(f"   🔧 Tool calls: {[tc.name for tc in response.tool_calls]}")
            
            # 🌟 如果没有 Tool Calls，返回结果
            if not response.has_tool_calls:
                logger.info(f"✅ Agentic Workflow 完成 (iterations={iterations}, trace_id={self.trace_id})")
                logger.debug(f"   📝 LLM Response (no tool_calls): {response.content[:500] if response.content else 'None'}...")
                logger.debug(f"   🏁 Finish Reason: {response.finish_reason}")
                return {
                    "content": response.content,
                    "tool_calls": all_tool_calls,
                    "iterations": iterations,
                    "finish_reason": response.finish_reason,
                    "trace_id": self.trace_id  # 🌟 v4.13
                }
            
            # 🌟 执行 Tool Calls
            tool_results = []
            for tool_call in response.tool_calls:
                # 执行 Tool
                result = await self._execute_tool(tool_call)
                
                # 记录
                all_tool_calls.append({
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                    "result": result
                })
                
                # 回调
                if on_tool_call:
                    on_tool_call(tool_call.name, tool_call.arguments)
                
                # 🌟 构建 Tool Result Message
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })
            
            # 🌟 添加 Assistant Message（包含 Tool Calls）
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [tc.to_openai_tool_call() for tc in response.tool_calls]
            })
            
            # 🌟 添加 Tool Results
            messages.extend(tool_results)
        
        logger.warning(f"⚠️ Agentic Workflow 达到最大迭代次数 ({self.max_iterations}, trace_id={self.trace_id})")
        return {
            "content": response.content if response else "",
            "tool_calls": all_tool_calls,
            "iterations": iterations,
            "finish_reason": "max_iterations",
            "trace_id": self.trace_id  # 🌟 v4.13
        }


def build_tools_registry_from_classes(tool_classes: List[Any]) -> Dict[str, Any]:
    """
    从 Tool Classes 构建 Tools Registry
    
    🌟 v3.20: 返回 Tool 实例（不是 execute 方法）
    
    Args:
        tool_classes: Tool 类列表
        
    Returns:
        Dict[str, Any]: Tool 名称 → Tool 实例
    """
    registry = {}
    
    for tool_class in tool_classes:
        # 🌟 实例化 Tool
        tool_instance = tool_class()
        
        # 🌟 获取名称
        tool_name = tool_instance.name
        
        # 🌟 添加到 Registry（保存整个 Tool 实例）
        registry[tool_name] = tool_instance
    
    return registry