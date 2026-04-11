"""
Core Configuration Module
🌟 统一的配置中心 - 使用 Pydantic BaseSettings 管理所有环境变量

Benefits:
- IDE 代码提示支持
- 类型安全
- 环境变量验证
- 单一配置来源 (Single Source of Truth)
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application Settings"""
    
    # Project Info
    PROJECT_NAME: str = "Nanobot WebUI"
    VERSION: str = "2.3.0"
    ENV: str = "production"
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports"
    DB_POOL_MIN: int = 2
    DB_POOL_MAX: int = 10
    
    # Gateway / AI Engine
    GATEWAY_URL: str = "http://nanobot-gateway:8081"
    NANOBOT_API_URL: str = "http://nanobot-gateway:8081"
    
    # Data Storage
    DATA_DIR: str = "/app/data/raw"
    UPLOAD_DIR: str = "/app/data/uploads"
    OUTPUT_DIR: str = "/app/data/output"
    
    # 🌟 Upload Settings (抽離硬編碼常量)
    MAX_UPLOAD_SIZE_MB: int = 50  # 最大上傳檔案大小 (MB)
    
    # Security
    SECRET_KEY: Optional[str] = None
    ALLOWED_HOSTS: list[str] = ["*"]
    
    # Feature Flags
    ENABLE_RAG: bool = True
    ENABLE_VANA_TRAINING: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()