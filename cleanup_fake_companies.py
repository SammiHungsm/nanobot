#!/usr/bin/env python3
"""
🧹 Cleanup Script: Remove Fake/Pseudo Companies Created by Agent Bug

Purpose:
  Remove duplicate companies with fake stock codes (SUB_XX, PARENT, etc.)
  that were created before the _resolve_company_id() fix (v1.4)

Safe by design:
  - Only removes companies with OBVIOUSLY FAKE stock codes
  - Preserves legitimate companies (00001, 0001.HK, etc.)
  - Dry-run mode enabled by default (--apply to actually delete)

Usage:
  python cleanup_fake_companies.py                    # Dry-run: show what would be deleted
  python cleanup_fake_companies.py --apply            # Actually delete
  python cleanup_fake_companies.py --db postgres://... --apply
"""

import asyncio
import asyncpg
import sys
import io
from typing import List, Dict

# Fix encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def cleanup_fake_companies(db_url: str, dry_run: bool = True):
    """
    🧹 移除假公司記錄
    
    Args:
        db_url: PostgreSQL 連接字符串
        dry_run: 如果 True，只列出要刪除的記錄（不實際刪除）
    """
    try:
        conn = await asyncpg.connect(db_url)
        
        # 🎯 識別要刪除的假公司
        fake_patterns = [
            "SUB_%",      # SUB_FF1110, SUB_XX etc
            "PARENT",     # PARENT
            "%_fake%",    # Any with _fake in name
            "%_temp%",    # Any with _temp in name
        ]
        
        print("=" * 60)
        print("🧹 Fake Companies Cleanup Script")
        print("=" * 60)
        print(f"Database: {db_url}")
        print(f"Mode: {'DRY-RUN (no changes)' if dry_run else 'APPLY (actual deletion)'}")
        print()
        
        # 查詢要刪除的公司
        fake_companies: List[Dict] = []
        
        for pattern in fake_patterns:
            rows = await conn.fetch(
                """
                SELECT id, stock_code, name_en, name_zh, created_at 
                FROM companies 
                WHERE stock_code LIKE $1
                ORDER BY created_at DESC
                """,
                pattern
            )
            fake_companies.extend([dict(row) for row in rows])
        
        if not fake_companies:
            print("✅ 沒有發現假公司記錄")
            await conn.close()
            return
        
        print(f"📊 發現 {len(fake_companies)} 條假公司記錄：\n")
        
        total_records = 0
        for company in fake_companies:
            print(f"  ID: {company['id']:6d} | Stock: {company['stock_code']:15s} | "
                  f"Name: {company['name_en'] or company['name_zh'] or '(unknown)'}")
            total_records += 1
        
        print()
        
        if dry_run:
            print("⚠️  DRY-RUN MODE: 以上記錄不會被刪除")
            print("   執行 'python cleanup_fake_companies.py --apply' 來實際刪除")
        else:
            # 🧹 實際刪除
            print("🗑️  正在刪除假公司記錄...")
            
            # 先刪除 FK 關聯
            await conn.execute(
                """
                DELETE FROM financial_metrics 
                WHERE company_id IN (
                    SELECT id FROM companies WHERE stock_code LIKE 'SUB_%' 
                    OR stock_code = 'PARENT'
                )
                """
            )
            print("  ✅ 已刪除 financial_metrics 中的關聯")
            
            await conn.execute(
                """
                DELETE FROM shareholding_structure 
                WHERE company_id IN (
                    SELECT id FROM companies WHERE stock_code LIKE 'SUB_%' 
                    OR stock_code = 'PARENT'
                )
                """
            )
            print("  ✅ 已刪除 shareholding_structure 中的關聯")
            
            # 再刪除公司記錄本身
            deleted = await conn.execute(
                """
                DELETE FROM companies 
                WHERE stock_code LIKE 'SUB_%' 
                OR stock_code = 'PARENT'
                """
            )
            
            print(f"\n✅ 已成功刪除 {len(fake_companies)} 條假公司記錄")
        
        print()
        print("=" * 60)
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)

async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Remove fake/pseudo companies created by agent bug"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports",
        help="PostgreSQL connection string"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete records (default: dry-run only)"
    )
    
    args = parser.parse_args()
    
    # Confirm before applying
    if args.apply:
        print("⚠️  WARNING: This will DELETE fake company records from the database!")
        response = input("Are you sure? Type 'yes' to confirm: ")
        if response.lower() != "yes":
            print("Aborted.")
            return
    
    await cleanup_fake_companies(args.db, dry_run=not args.apply)

if __name__ == "__main__":
    asyncio.run(main())
