"""
Vanna Training Script

Trains Vanna AI on the financial database schema.
Run this after database initialization.

Usage:
    uv run python train_vanna.py
"""

import sys
from pathlib import Path
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from nanobot.agent.tools.vanna_tool import VannaSQL
from nanobot.agent.tools.financial import FinancialTools


def print_header(text: str):
    print(f"\n{'='*60}")
    print(f"{text:^60}")
    print(f"{'='*60}\n")


def main():
    """Train Vanna AI on financial schema"""
    print_header("🤖 VANNA AI TRAINING")
    
    try:
        # Initialize Vanna
        logger.info("Initializing Vanna AI...")
        vanna = VannaSQL()
        
        # Check database connection
        logger.info("Checking database connection...")
        tools = FinancialTools()
        result = tools.list_companies()
        
        if not result.success:
            print(f"✗ Database not accessible: {result.message}")
            return 1
        
        print(f"✓ Database connected: {result.message}")
        
        # Train schema
        print_header("📚 TRAINING SCHEMA")
        stats = vanna.train_schema(force=True)
        
        if stats.get('status') == 'trained':
            print("✓ Schema training completed:")
            print(f"  - DDL statements: {stats.get('ddl_statements', 0)}")
            print(f"  - Documentation: {stats.get('documentation', 0)}")
            print(f"  - Example queries: {stats.get('sql_queries', 0)}")
        else:
            print(f"⚠ Training status: {stats.get('status')}")
            if 'error' in stats:
                print(f"  Error: {stats['error']}")
        
        # Test queries
        print_header("🧪 TEST QUERIES")
        
        test_questions = [
            "Show Tencent's revenue for the most recent years",
            "What are the top 5 companies by revenue in 2023?",
            "Which company has the highest net margin?",
        ]
        
        for question in test_questions:
            print(f"\nQuestion: {question}")
            result = vanna.query(question)
            
            if result['success']:
                print(f"✓ Generated SQL: {result['sql'][:150]}...")
                print(f"✓ Results: {result['row_count']} rows")
                if result['results']:
                    print(f"  Sample: {result['results'][0]}")
            else:
                print(f"✗ Failed: {result.get('error')}")
        
        print_header("✅ TRAINING COMPLETE")
        print("\nVanna AI is now ready to generate SQL queries!")
        print("\nNext steps:")
        print("1. Test with more complex questions")
        print("2. Add more example queries if needed")
        print("3. Integrate with Nanobot skill")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Training failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
