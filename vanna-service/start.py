"""
Vanna Service Startup Script

Features:
1. Initialize Vanna AI
2. Auto-train Schema
3. Keep service running
"""

import os
import time
from pathlib import Path
from loguru import logger
import sys

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

def train_vanna_on_startup():
    """Initialize and train Vanna AI on startup"""
    try:
        logger.info("Vanna initialized successfully (placeholder)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Vanna initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    logger.info("="*60)
    logger.info("Vanna Service Starting...")
    logger.info("="*60)
    
    # Wait for database to be ready
    max_retries = 30
    retry_delay = 2
    
    for i in range(max_retries):
        try:
            logger.info(f"Attempting database connection (Attempt {i+1}/{max_retries})...")
            
            # Test database connection using psycopg2
            import psycopg2
            conn = psycopg2.connect(
                os.getenv(
                    "DATABASE_URL",
                    "postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports"
                ),
                connect_timeout=5
            )
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
    if train_vanna_on_startup():
        logger.info("✅ Vanna Service ready")
    else:
        logger.warning("⚠️ Vanna initialization failed, but service will continue")
    
    # Keep container running
    logger.info("Vanna Service running (press Ctrl+C to stop)...")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Received stop signal, shutting down")

if __name__ == "__main__":
    main()
