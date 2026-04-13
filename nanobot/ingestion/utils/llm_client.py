"""
LLM Client - 統一的 LLM 客戶端管理

所有 Agent 和 Parser 都應該使用這個模組來獲取 LLM 客戶端。
不要再在各個文件中重複寫 API Key 讀取邏輯。
"""

import os
from typing import Optional, Tuple
from loguru import logger

try:
    from openai import AsyncOpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    logger.warning("⚠️ OpenAI SDK 未安裝")


class LLMClientManager:
    """
    LLM 客戶端管理器（Singleton Pattern）
    
    統一管理：
    - API Key 讀取
    - API Base URL 配置
    - Model 選擇
    - OpenAI Client 初始化
    """
    
    _instance = None
    _client: Optional[AsyncOpenAI] = None
    _api_key: Optional[str] = None
    _api_base: Optional[str] = None
    _model: Optional[str] = None
    _vision_model: Optional[str] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _load_config(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        從 config.json 讀取 API 憑證
        
        Returns:
            tuple: (api_key, api_base, model)
        """
        # 先嘗試從 nanobot config.json 讀取
        try:
            from nanobot.config.loader import load_config, resolve_config_env_vars
            from pathlib import Path
            
            config_path = None
            nanobot_config_env = os.getenv("NANOBOT_CONFIG")
            if nanobot_config_env:
                config_path = Path(nanobot_config_env)
                if not config_path.exists():
                    config_path = None
            
            # 🌟 关键修复：必须解析环境变量 ${VAR} 格式
            config = resolve_config_env_vars(load_config(config_path))
            provider = config.get_provider()
            
            # 從 agents.defaults 讀取模型
            model = None
            try:
                model = config.agents.defaults.model
            except AttributeError:
                pass
            
            if provider:
                api_key = provider.api_key or None
                api_base = provider.api_base or None
                
                if api_key and api_key.startswith("sk-YOUR"):
                    api_key = None
                
                if api_key:
                    return api_key, api_base, model
        except Exception as e:
            logger.debug(f"⚠️ 無法從 config.json 載入配置: {e}")
        
        return None, None, None
    
    def _init_credentials(self):
        """初始化憑證（延遲載入）"""
        if self._api_key is not None:
            return
        
        # 優先順序：config.json > 環境變數
        config_key, config_base, config_model = self._load_config()
        
        self._api_key = config_key or os.getenv("CUSTOM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self._api_base = config_base or os.getenv("CUSTOM_API_BASE") or os.getenv("OPENAI_API_BASE")
        self._model = config_model or os.getenv("LLM_MODEL", "qwen3.5-plus")
        
        # Vision 模型映射
        self._vision_model = os.getenv("VISION_MODEL", self._get_vision_model_fallback())
    
    def _get_vision_model_fallback(self) -> str:
        """根據 LLM 模型推斷 Vision 模型"""
        if not self._model:
            return "qwen-vl-max"
        
        model_lower = self._model.lower()
        if "qwen" in model_lower:
            if "qwen3" in model_lower:
                return model_lower.replace("qwen3", "qwen-vl")
            elif "qwen2" in model_lower:
                return model_lower.replace("qwen2", "qwen-vl")
            return "qwen-vl-max"
        elif "gpt-4" in model_lower and "vision" not in model_lower:
            if "gpt-4o-mini" in model_lower:
                return "gpt-4o"
            elif "gpt-4-turbo" in model_lower:
                return "gpt-4-turbo"
            return "gpt-4-vision-preview"
        elif "glm" in model_lower and "glm-4" in model_lower:
            return "glm-4v"
        
        return self._model  # 假設模型本身支持 Vision
    
    def get_client(self) -> Optional[AsyncOpenAI]:
        """
        獲取 AsyncOpenAI 客戶端
        
        Returns:
            AsyncOpenAI 客戶端，或 None（如果配置無效）
        """
        if not OPENAI_SDK_AVAILABLE:
            logger.error("❌ OpenAI SDK 未安裝")
            return None
        
        self._init_credentials()
        
        if not self._api_key or self._api_key.startswith("sk-YOUR"):
            logger.error("❌ 未配置有效的 API Key")
            return None
        
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._api_base
            )
        
        return self._client
    
    def get_model(self) -> str:
        """獲取 LLM 模型名稱"""
        self._init_credentials()
        return self._model or "qwen3.5-plus"
    
    def get_vision_model(self) -> str:
        """獲取 Vision 模型名稱"""
        self._init_credentials()
        return self._vision_model or "qwen-vl-max"
    
    def get_api_base(self) -> Optional[str]:
        """獲取 API Base URL"""
        self._init_credentials()
        return self._api_base


# ===========================================
# 便捷函數（全局訪問點）
# ===========================================

_manager = LLMClientManager()

def get_llm_client() -> Optional[AsyncOpenAI]:
    """獲取 LLM 客戶端"""
    return _manager.get_client()

def get_llm_model() -> str:
    """獲取 LLM 模型名稱"""
    return _manager.get_model()

def get_vision_model() -> str:
    """獲取 Vision 模型名稱"""
    return _manager.get_vision_model()

def get_api_base() -> Optional[str]:
    """獲取 API Base URL"""
    return _manager.get_api_base()