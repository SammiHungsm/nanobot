"""Configuration module for nanobot."""

from nanobot.config.loader import get_config_path, load_config
from nanobot.config.paths import (
    NANOBOT_HOME,  # 🌟 新增：统一基础路径常量
    DEFAULT_WORKSPACE,  # 🌟 新增：默认 workspace 常量
    get_bridge_install_dir,
    get_cli_history_path,
    get_cron_dir,
    get_data_dir,
    get_legacy_sessions_dir,
    is_default_workspace,
    get_logs_dir,
    get_media_dir,
    get_runtime_subdir,
    get_workspace_path,
)
from nanobot.config.schema import Config

__all__ = [
    "Config",
    "load_config",
    "get_config_path",
    # 🌟 新增导出
    "NANOBOT_HOME",
    "DEFAULT_WORKSPACE",
    # 原有导出
    "get_data_dir",
    "get_runtime_subdir",
    "get_media_dir",
    "get_cron_dir",
    "get_logs_dir",
    "get_workspace_path",
    "is_default_workspace",
    "get_cli_history_path",
    "get_bridge_install_dir",
    "get_legacy_sessions_dir",
]
