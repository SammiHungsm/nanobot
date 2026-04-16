"""
Resume Pipeline CLI - 从 raw output 加载（v3.2）

🌟 v3.2: 使用 LlamaParse raw output（移除 OpenDataLoader/RawResultManager）

用法：
    # 列出已保存的 raw output
    python resume_pipeline.py list
    
    # 从 raw output 加载（不扣费）
    python resume_pipeline.py load --pdf-filename report.pdf
    
    # 清理旧的 raw output
    python resume_pipeline.py clean --days 30 --dry-run
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from nanobot.core.pdf_core import PDFParser, get_raw_output_dir


def cmd_list(args):
    """命令：列出已保存的 raw output"""
    raw_dir = get_raw_output_dir()
    
    print("\n" + "=" * 70)
    print("📋 已保存的 LlamaParse Raw Output")
    print("=" * 70)
    
    if not raw_dir.exists():
        print(f"目录不存在: {raw_dir}")
        return
    
    pdf_folders = sorted(raw_dir.iterdir())
    
    if not pdf_folders:
        print("暂无已保存的结果")
        return
    
    for pdf_folder in pdf_folders:
        if not pdf_folder.is_dir():
            continue
        
        # 查找 job_id JSON 文件
        json_files = list(pdf_folder.glob("*.json"))
        meta_files = [f for f in json_files if f.stem.endswith("_meta")]
        
        for meta_file in meta_files:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            
            job_id = meta.get("job_id", "unknown")
            created_at = meta.get("created_at", "unknown")
            tier = meta.get("tier", "unknown")
            
            print(f"\n📄 {pdf_folder.name}")
            print(f"   job_id: {job_id}")
            print(f"   tier: {tier}")
            print(f"   created_at: {created_at}")


def cmd_load(args):
    """命令：从 raw output 加载"""
    pdf_filename = args.pdf_filename
    
    print("\n" + "=" * 70)
    print("📂 从 raw output 加载（不扣费）")
    print("=" * 70)
    
    parser = PDFParser()
    
    try:
        result = parser.load_from_raw_output(pdf_filename)
        
        print(f"\n✅ 加载成功!")
        print(f"   total_pages: {result.total_pages}")
        print(f"   tables_count: {len(result.tables)}")
        print(f"   images_count: {len(result.images)}")
        print(f"   job_id: {result.job_id}")
        print(f"   raw_output_dir: {result.raw_output_dir}")
        
        print(f"\n📝 Markdown 预览（前 500 字符）:")
        print(result.markdown[:500])
        
    except FileNotFoundError as e:
        print(f"\n❌ 加载失败: {e}")
        print("请先运行 Pipeline 解析该 PDF")


def cmd_clean(args):
    """命令：清理旧的 raw output"""
    days_old = args.days
    dry_run = args.dry_run
    
    print("\n" + "=" * 70)
    print(f"🧹 清理 {days_old} 天前的 raw output")
    print("=" * 70)
    print(f"dry_run: {dry_run}")
    
    raw_dir = get_raw_output_dir()
    
    if not raw_dir.exists():
        print("目录不存在，无需清理")
        return
    
    cutoff_date = datetime.now() - timedelta(days=days_old)
    count = 0
    
    for pdf_folder in raw_dir.iterdir():
        if not pdf_folder.is_dir():
            continue
        
        # 检查 meta 文件的创建时间
        meta_files = list(pdf_folder.glob("*_meta.json"))
        
        for meta_file in meta_files:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            
            created_at_str = meta.get("created_at")
            if not created_at_str:
                continue
            
            try:
                created_at = datetime.fromisoformat(created_at_str)
                
                if created_at < cutoff_date:
                    count += 1
                    
                    if not dry_run:
                        # 删除整个文件夹
                        import shutil
                        shutil.rmtree(pdf_folder)
                        print(f"   ✅ 已删除: {pdf_folder.name}")
                    else:
                        print(f"   📋 可删除: {pdf_folder.name}")
                        
            except Exception as e:
                logger.warning(f"解析日期失败: {e}")
    
    print("\n" + "=" * 70)
    if dry_run:
        print(f"✅ 找到 {count} 个可清理的结果（dry run）")
        print("使用 --no-dry-run 实际删除")
    else:
        print(f"✅ 已删除 {count} 个结果")
    print("=" * 70)


def main():
    """CLI 主函数"""
    parser = argparse.ArgumentParser(
        description="Resume Pipeline CLI - LlamaParse raw output 管理"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 命令：list
    list_parser = subparsers.add_parser("list", help="列出已保存的 raw output")
    list_parser.set_defaults(func=cmd_list)
    
    # 命令：load
    load_parser = subparsers.add_parser("load", help="从 raw output 加载")
    load_parser.add_argument("--pdf-filename", required=True, help="PDF 文件名")
    load_parser.set_defaults(func=cmd_load)
    
    # 命令：clean
    clean_parser = subparsers.add_parser("clean", help="清理旧的 raw output")
    clean_parser.add_argument("--days", type=int, default=30, help="清理多少天前的结果")
    clean_parser.add_argument("--dry-run", action="store_true", default=True, help="只列出，不实际删除")
    clean_parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="实际删除")
    clean_parser.set_defaults(func=cmd_clean)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()