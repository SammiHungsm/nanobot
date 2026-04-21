"""
Agentic Workflow Executor - Tool Calling Loop

执行真正的 Agentic Workflow：
1. 把 Tools Schema 传给 LLM
2. LLM 决定调用哪个 Tool
3. 执行 Tool 并返回结果给 LLM
4. 循环直到 LLM 完成

Usage:
    from nanobot.ingestion.agentic_executor import AgenticExecutor
    
    executor = AgenticExecutor(llm_core, tools_registry)
    result = await executor.run(prompt, context)
"""

import json
import asyncio
from typing import Dict, Any, List, Optional, Callable
from loguru import logger

from nanobot.core.llm_core import llm_core
from nanobot.providers.base import LLMResponse, ToolCallRequest


class AgenticExecutor:
    """
    Agentic Workflow Executor
    
    执行 Tool Calling Loop，让 LLM 真正调用 Tools
    """
    
    def __init__(
        self,
        tools_registry: Dict[str, Any],  # 🌟 改为 Any，可以是 Tool 实例或 execute 方法
        max_iterations: int = 10,
        model: str = None
    ):
        """
        初始化
        
        Args:
            tools_registry: Tool 名称 → Tool 实例或 execute 函数的映射
            max_iterations: 最大迭代次数（防止无限循环）
            model: LLM 模型
        """
        self.tools_registry = tools_registry
        self.max_iterations = max_iterations
        self.model = model or llm_core.default_model
    
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
        
        Args:
            tool_call: Tool 调用请求
            
        Returns:
            str: Tool 执行结果
        """
        tool_name = tool_call.name
        tool_args = tool_call.arguments
        
        logger.info(f"   🔧 执行 Tool: {tool_name}({tool_args})")
        
        if tool_name not in self.tools_registry:
            return json.dumps({"error": f"Tool '{tool_name}' not found"})
        
        tool_obj = self.tools_registry[tool_name]
        
        # =================================================================
        # 🌟 系統級優化：Auto Type Casting (根據 Tool 的 Schema 自動轉型)
        # =================================================================
        # LLM 經常會傳遞錯誤的資料型態（例如 "1" 而不是 1），
        # 這裡根據 Tool 的 JSON Schema 自動進行類型轉換
        # =================================================================
        if hasattr(tool_obj, 'parameters'):
            properties = tool_obj.parameters.get("properties", {})
            
            for key, val in tool_args.items():
                if key in properties and val is not None:
                    # 獲取 Schema 中定義的預期類型
                    expected_type = properties[key].get("type")
                    
                    try:
                        if expected_type == "integer":
                            # 如果預期是整數，但 LLM 傳了字串 "1" 或浮點數 1.0
                            if isinstance(val, str):
                                tool_args[key] = int(float(val))
                            elif isinstance(val, float):
                                tool_args[key] = int(val)
                        elif expected_type == "number":
                            # 如果預期是浮點數，但 LLM 傳了字串 "123.45"
                            if isinstance(val, str):
                                tool_args[key] = float(val)
                        elif expected_type == "boolean":
                            # 處理 "true", "False", "1" 等各種布林字串
                            if isinstance(val, str):
                                tool_args[key] = val.lower() in ("true", "1", "yes", "t")
                            elif isinstance(val, (int, float)):
                                tool_args[key] = bool(val)
                        elif expected_type == "string":
                            # 強制轉字串
                            tool_args[key] = str(val)
                    except (ValueError, TypeError) as e:
                        # 如果 LLM 傳了完全無法轉換的東西 (例如 "abc" 轉 int)，
                        # 這裡放行保留原值，讓 Tool 執行時自己報錯
                        logger.warning(f"⚠️ 自動轉型失敗: {key}={val} (預期: {expected_type}), error: {e}")
                        pass
        
        try:
            # 🌟 v3.20: 获取 execute 方法
            if hasattr(tool_obj, 'execute'):
                execute_func = tool_obj.execute
            else:
                execute_func = tool_obj
            
            # 🌟 执行 Tool（支持 async 和 sync）
            if asyncio.iscoroutinefunction(execute_func):
                result = await execute_func(**tool_args)
            else:
                result = execute_func(**tool_args)
            
            # 🌟 确保结果是字符串
            if isinstance(result, dict):
                result_str = json.dumps(result, indent=2, ensure_ascii=False)
            else:
                result_str = str(result)
            
            logger.debug(f"   ✅ Tool 结果: {result_str[:100]}...")
            return result_str
            
        except Exception as e:
            logger.warning(f"   ⚠️ Tool 执行失败: {e}")
            return json.dumps({"error": str(e)})
    
    async def run(
        self,
        system_prompt: str,
        user_message: str,
        context: Dict[str, Any] = None,
        on_tool_call: Callable[[str, Dict], None] = None
    ) -> Dict[str, Any]:
        """
        执行 Agentic Workflow
        
        Args:
            system_prompt: System Prompt
            user_message: 用户消息
            context: 上下文信息
            on_tool_call: Tool 调用回调
            
        Returns:
            Dict: 执行结果 {"content": str, "tool_calls": List, "iterations": int}
        """
        logger.info(f"🤖 Agentic Workflow 开始 (tools={len(self.tools_registry)})")
        
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
            
            # 🌟 调用 LLM（带 Tools）
            response: LLMResponse = await llm_core.chat(
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
                logger.info(f"✅ Agentic Workflow 完成 (iterations={iterations})")
                logger.debug(f"   📝 LLM Response (no tool_calls): {response.content[:500] if response.content else 'None'}...")
                logger.debug(f"   🏁 Finish Reason: {response.finish_reason}")
                return {
                    "content": response.content,
                    "tool_calls": all_tool_calls,
                    "iterations": iterations,
                    "finish_reason": response.finish_reason
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
        
        logger.warning(f"⚠️ Agentic Workflow 达到最大迭代次数 ({self.max_iterations})")
        return {
            "content": response.content if response else "",
            "tool_calls": all_tool_calls,
            "iterations": iterations,
            "finish_reason": "max_iterations"
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