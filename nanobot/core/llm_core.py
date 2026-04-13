"""
LLM Core - 统一的 LLM 与视觉模型客户端

🎯 解决的问题：
1. LLM 客户端分散在 ingestion/utils/llm_client.py、providers/registry.py 等多处
2. Vision 模型分散在 ollama_vision.py、vision_api_client.py 等
3. API Key 配置读取逻辑重复
4. Provider 路由逻辑不一致

统一架构：
- 使用 nanobot/providers/ 的配置系统
- 提供统一的 chat() 和 vision() 接口
- 自动路由到正确的 Provider（OpenAI/Anthropic/Ollama）
- 支持本地模型和云端模型

Usage:
    from nanobot.core.llm_core import llm_core
    
    # 文字对话
    response = await llm_core.chat("Hello, how are you?")
    
    # 视觉解析
    result = await llm_core.vision(image_base64, "提取表格数据")
"""

import os
import base64
from typing import List, Dict, Any, Optional, Union
from loguru import logger

# 🌟 使用现有的 Provider Registry
try:
    from nanobot.providers.registry import PROVIDERS, ProviderSpec
    from nanobot.config.loader import load_config, resolve_config_env_vars
    from pathlib import Path
    NANOBOT_CONFIG_AVAILABLE = True
except ImportError:
    NANOBOT_CONFIG_AVAILABLE = False
    logger.warning("⚠️ nanobot config system not available, using env vars")

# 🌟 使用 OpenAI SDK（兼容多种 Provider）
try:
    from openai import AsyncOpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    logger.warning("⚠️ OpenAI SDK not installed")


# ===========================================
# Provider 路由逻辑
# ===========================================

def detect_provider(model_name: str) -> Optional[str]:
    """
    根据模型名称检测 Provider
    
    Args:
        model_name: 模型名称（如 "gpt-4o", "claude-3", "ollama/llava"）
        
    Returns:
        str: Provider 名称（如 "openai", "anthropic", "ollama"）
    """
    if not NANOBOT_CONFIG_AVAILABLE:
        return "openai"  # Fallback
    
    model_lower = model_name.lower()
    
    # 🌟 使用 PROVIDERS 的 keywords 匹配
    for provider_name, spec in PROVIDERS.items():
        if any(kw in model_lower for kw in spec.keywords):
            return provider_name
    
    # 特殊处理：ollama/ 前缀
    if model_name.startswith("ollama/"):
        return "ollama"
    
    # 默认：OpenAI
    return "openai"


def get_api_config() -> Dict[str, Any]:
    """
    获取 API 配置（从 nanobot config 或环境变量）
    
    Returns:
        Dict: {
            "api_key": str,
            "api_base": str,
            "default_model": str,
            "vision_model": str
        }
    """
    config = {
        "api_key": None,
        "api_base": None,
        "default_model": os.getenv("DEFAULT_LLM_MODEL", "gpt-4o-mini"),
        "vision_model": os.getenv("VISION_MODEL", "gpt-4o")
    }
    
    # 🌟 优先使用 nanobot config
    if NANOBOT_CONFIG_AVAILABLE:
        try:
            nanobot_config_env = os.getenv("NANOBOT_CONFIG")
            config_path = Path(nanobot_config_env) if nanobot_config_env else None
            
            loaded_config = resolve_config_env_vars(load_config(config_path))
            provider = loaded_config.get_provider()
            
            if provider:
                # 🌟 检查 placeholder keys
                api_key = provider.api_key
                if api_key and not api_key.startswith("sk-YOUR"):
                    config["api_key"] = api_key
                
                api_base = provider.api_base
                if api_base:
                    config["api_base"] = api_base
            
            # 🌟 从 agents.defaults 读取模型
            try:
                config["default_model"] = loaded_config.agents.defaults.model
            except AttributeError:
                pass
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to load nanobot config: {e}")
    
    # 🌟 Fallback: 环境变量
    if not config["api_key"]:
        # 按优先级检查环境变量
        for key in ["DASHSCOPE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
            val = os.getenv(key)
            if val and not val.startswith("sk-YOUR"):
                config["api_key"] = val
                break
    
    if not config["api_base"]:
        config["api_base"] = os.getenv("OPENAI_API_BASE")
    
    return config


# ===========================================
# UnifiedLLMCore - 核心类
# ===========================================

class UnifiedLLMCore:
    """
    统一的 LLM 与 Vision 模型客户端
    
    🎯 整合所有 LLM/Vision 调用，提供统一接口
    
    支持的 Provider：
    - OpenAI (GPT-4o, GPT-4o-mini)
    - Anthropic (Claude-3)
    - DashScope (Qwen)
    - Ollama (本地模型)
    - 其他 OpenAI-compatible API
    
    Example:
        llm = UnifiedLLMCore()
        
        # 文字对话
        response = await llm.chat([{"role": "user", "content": "Hello"}])
        
        # Vision 解析
        result = await llm.vision(img_base64, "提取表格")
    """
    
    def __init__(self):
        """
        初始化
        
        🌟 自动检测配置（从 nanobot config 或环境变量）
        """
        self.config = get_api_config()
        self.default_model = self.config["default_model"]
        self.vision_model = self.config["vision_model"]
        
        # 🌟 初始化 OpenAI Client（兼容多种 Provider）
        if OPENAI_SDK_AVAILABLE and self.config["api_key"]:
            self.client = AsyncOpenAI(
                api_key=self.config["api_key"],
                base_url=self.config["api_base"] if self.config["api_base"] else None
            )
            logger.info(f"✅ UnifiedLLMCore initialized (model={self.default_model})")
        else:
            self.client = None
            logger.warning("⚠️ OpenAI client not initialized (missing API key or SDK)")
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """
        🎯 统一的文字对话接口
        
        Args:
            messages: OpenAI 格式的 messages 列表
            model: 模型名称（默认使用 default_model）
            temperature: 温度参数
            max_tokens: 最大输出长度
            
        Returns:
            str: LLM 的回复文本
            
        Example:
            response = await llm.chat([
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello"}
            ])
        """
        target_model = model or self.default_model
        provider = detect_provider(target_model)
        
        logger.debug(f"🤖 Calling LLM: {target_model} (provider={provider})")
        
        try:
            # 🌟 Provider 路由逻辑
            
            # 处理 Ollama（本地模型）
            if provider == "ollama":
                return await self._call_ollama_chat(messages, target_model, temperature, max_tokens, **kwargs)
            
            # 处理 Anthropic（Claude）
            elif provider == "anthropic":
                return await self._call_anthropic_chat(messages, target_model, temperature, max_tokens, **kwargs)
            
            # 处理 DashScope（Qwen）
            elif provider == "dashscope":
                # DashScope 使用 OpenAI-compatible API（如果配置正确）
                return await self._call_openai_compatible(messages, target_model, temperature, max_tokens, **kwargs)
            
            # 默认：OpenAI-compatible Provider
            else:
                return await self._call_openai_compatible(messages, target_model, temperature, max_tokens, **kwargs)
            
        except Exception as e:
            logger.error(f"❌ LLM call failed: {e}")
            raise
    
    async def _call_openai_compatible(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> str:
        """
        🌟 调用 OpenAI-compatible API（标准格式）
        
        支持：
        - OpenAI (GPT-4o, GPT-4o-mini)
        - DashScope (Qwen) - 如果 api_base 正确配置
        - 其他 OpenAI-compatible Gateway（LiteLLM, OneAPI）
        """
        if not self.client:
            raise RuntimeError("OpenAI client not initialized. Check API key.")
        
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        content = response.choices[0].message.content
        logger.debug(f"✅ OpenAI response: {len(content)} chars")
        return content
    
    async def _call_ollama_chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> str:
        """
        🌟 调用 Ollama 本地模型
        
        Args:
            messages: OpenAI 格式的 messages
            model: Ollama 模型名称（如 "ollama/llama3"）
            
        Returns:
            str: Ollama 的回复
            
        注意：Ollama 的 API 地址通常是 http://localhost:11434/v1
        """
        import httpx
        
        # 🌟 移除 ollama/ 前缀
        ollama_model = model.replace("ollama/", "")
        
        # 🌟 Ollama API 地址（默认 localhost）
        ollama_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
        
        logger.debug(f"🦙 Calling Ollama: {ollama_model} at {ollama_url}")
        
        try:
            # 🌟 使用 OpenAI-compatible 格式（Ollama 支持）
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{ollama_url}/chat/completions",
                    json={
                        "model": ollama_model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": False
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    logger.debug(f"✅ Ollama response: {len(content)} chars")
                    return content
                else:
                    logger.error(f"❌ Ollama failed: {response.status_code}")
                    raise RuntimeError(f"Ollama API failed: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"❌ Ollama chat call failed: {e}")
            raise
    
    async def _call_anthropic_chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> str:
        """
        🌟 调用 Anthropic Claude
        
        Args:
            messages: OpenAI 格式的 messages（需要转换）
            model: Claude 模型名称（如 "claude-3-opus"）
            
        Returns:
            str: Claude 的回复
            
        注意：
        - Anthropic 的 API 格式与 OpenAI 不同
        - 需要使用 anthropic SDK 或 LiteLLM Gateway
        """
        # 🌟 如果使用 LiteLLM Gateway，可以直接用 OpenAI SDK
        # 检查 api_base 是否指向 LiteLLM
        if self.config.get("api_base") and "litellm" in self.config.get("api_base", "").lower():
            logger.debug("Using LiteLLM Gateway for Anthropic")
            return await self._call_openai_compatible(messages, model, temperature, max_tokens, **kwargs)
        
        # 🌟 否则，需要使用 Anthropic SDK
        try:
            import anthropic
            
            # 🌟 提取 API Key
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")
            if not anthropic_key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")
            
            # 🌟 转换 messages 格式（Anthropic 不支持 system 在 messages 中）
            system_message = ""
            anthropic_messages = []
            
            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    anthropic_messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
            
            # 🌟 调用 Anthropic SDK
            client = anthropic.AsyncAnthropic(api_key=anthropic_key)
            
            response = await client.messages.create(
                model=model.replace("anthropic/", ""),
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_message,
                messages=anthropic_messages
            )
            
            content = response.content[0].text
            logger.debug(f"✅ Anthropic response: {len(content)} chars")
            return content
            
        except ImportError:
            logger.warning("⚠️ anthropic SDK not installed, trying OpenAI-compatible")
            # Fallback: 尝试使用 OpenAI SDK（可能通过 Gateway）
            return await self._call_openai_compatible(messages, model, temperature, max_tokens, **kwargs)
        
        except Exception as e:
            logger.error(f"❌ Anthropic call failed: {e}")
            raise
    
    async def vision(
        self,
        image_base64: str,
        prompt: str,
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> str:
        """
        🎯 统一的视觉解析接口
        
        Args:
            image_base64: 图片的 Base64 编码（不带 data:image 前缀）
            prompt: 给 Vision 模型的提示词
            model: Vision 模型名称（默认使用 vision_model）
            temperature: 温度参数
            max_tokens: 最大输出长度
            
        Returns:
            str: Vision 模型的分析结果
            
        Example:
            # 从文件读取图片
            with open("chart.png", "rb") as f:
                img_base64 = base64.b64encode(f.read()).decode()
            
            result = await llm.vision(img_base64, "提取表格数据")
        """
        if not self.client:
            logger.error("❌ OpenAI client not initialized")
            raise RuntimeError("OpenAI client not initialized. Check API key.")
        
        target_model = model or self.vision_model
        provider = detect_provider(target_model)
        
        logger.debug(f"👁️ Calling Vision: {target_model} (provider={provider})")
        
        # 🌟 构建 Vision 请求（OpenAI 格式）
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]
        
        # 🌟 特殊处理：Ollama 需要不同的 API 格式
        if provider == "ollama":
            return await self._call_ollama_vision(target_model, image_base64, prompt)
        
        # 🌟 其他 Provider：使用标准 OpenAI Vision API
        try:
            response = await self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            content = response.choices[0].message.content
            logger.debug(f"✅ Vision response: {len(content)} chars")
            return content
            
        except Exception as e:
            logger.error(f"❌ Vision call failed: {e}")
            raise
    
    async def _call_ollama_vision(self, model: str, image_base64: str, prompt: str) -> str:
        """
        🌟 Ollama Vision API 调用（特殊处理）
        
        Ollama 使用不同的 API 格式，需要单独处理
        
        Args:
            model: Ollama 模型名称（如 "ollama/llava"）
            image_base64: 图片的 Base64 编码
            prompt: 提示词
            
        Returns:
            str: Vision 模型的分析结果
        """
        import httpx
        
        # 🌟 移除 ollama/ 前缀
        ollama_model = model.replace("ollama/", "")
        
        # 🌟 Ollama API 地址（默认 localhost）
        ollama_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
        
        logger.debug(f"🦙 Calling Ollama Vision: {ollama_model}")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": prompt,
                        "images": [image_base64],
                        "stream": False
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("response", "")
                    logger.debug(f"✅ Ollama response: {len(content)} chars")
                    return content
                else:
                    logger.error(f"❌ Ollama failed: {response.status_code}")
                    raise RuntimeError(f"Ollama API failed: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"❌ Ollama Vision call failed: {e}")
            raise
    
    async def batch_chat(
        self,
        prompts: List[str],
        model: str = None,
        **kwargs
    ) -> List[str]:
        """
        🎯 批量文字对话（并发调用）
        
        Args:
            prompts: 多个提示词列表
            model: 模型名称
            
        Returns:
            List[str]: 多个回复文本
        """
        import asyncio
        
        tasks = [
            self.chat([{"role": "user", "content": p}], model=model, **kwargs)
            for p in prompts
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        output = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"⚠️ Batch item {i} failed: {result}")
                output.append("")
            else:
                output.append(result)
        
        return output
    
    async def batch_vision(
        self,
        images: List[str],
        prompt: str,
        model: str = None
    ) -> List[str]:
        """
        🎯 批量视觉解析（并发调用）
        
        Args:
            images: 多个图片的 Base64 编码列表
            prompt: 统一的提示词
            model: Vision 模型
            
        Returns:
            List[str]: 多个分析结果
        """
        import asyncio
        
        tasks = [
            self.vision(img, prompt, model=model)
            for img in images
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        output = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"⚠️ Batch vision item {i} failed: {result}")
                output.append("")
            else:
                output.append(result)
        
        return output


# ===========================================
# 全域單例
# ===========================================

# 🌟 创建全局单例（类似 llm_client.py 的 Singleton）
llm_core = UnifiedLLMCore()


# ===========================================
# 便捷函数
# ===========================================

async def chat(prompt: str, model: str = None, **kwargs) -> str:
    """
    便捷函数：快速文字对话
    
    Args:
        prompt: 提示词（字符串）
        model: 模型名称
        
    Returns:
        str: LLM 回复
    """
    return await llm_core.chat([{"role": "user", "content": prompt}], model=model, **kwargs)


async def vision(image_path_or_base64: str, prompt: str, model: str = None) -> str:
    """
    便捷函数：快速视觉解析
    
    Args:
        image_path_or_base64: 图片路径或 Base64 编码
        prompt: 提示词
        model: Vision 模型
        
    Returns:
        str: Vision 分析结果
        
    Example:
        # 从文件读取
        result = await vision("chart.png", "提取表格")
        
        # 使用 Base64
        with open("chart.png", "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()
        result = await vision(img_base64, "提取表格")
    """
    # 🌟 自动处理图片输入（文件路径或 Base64）
    if os.path.exists(image_path_or_base64):
        # 是文件路径
        with open(image_path_or_base64, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()
    else:
        # 已经是 Base64
        img_base64 = image_path_or_base64
    
    return await llm_core.vision(img_base64, prompt, model=model)


# ===========================================
# 测试
# ===========================================

if __name__ == "__main__":
    import asyncio
    
    print("🧪 测试 UnifiedLLMCore...")
    
    # 测试配置
    print("\n1. 测试配置检测:")
    config = get_api_config()
    print(f"   API Key: {'已设置' if config['api_key'] else '未设置'}")
    print(f"   API Base: {config['api_base'] or '默认'}")
    print(f"   Default Model: {config['default_model']}")
    print(f"   Vision Model: {config['vision_model']}")
    
    # 测试 Provider 检测
    print("\n2. 测试 Provider 检测:")
    test_models = ["gpt-4o", "claude-3", "qwen-plus", "ollama/llava"]
    for model in test_models:
        provider = detect_provider(model)
        print(f"   {model} → {provider}")
    
    # 测试 chat
    print("\n3. 测试 chat:")
    try:
        response = asyncio.run(chat("Hello, 你是谁？"))
        print(f"   回复: {response[:100]}...")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    print("\n✅ 测试完成")