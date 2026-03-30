#!/usr/bin/env python3
"""
端到端測試：驗證 Nanobot 文檔索引功能完整流程

這個腳本測試：
1. PyMuPDF 是否正確安裝
2. 文檔索引腳本是否可以正常運行
3. 索引文件是否正確生成
4. 完整流程：PDF → 索引生成 → 導航地圖

用法：
    python test_end_to_end.py

如果所有測試通過，你會見到：
    ✅ 所有測試通過！Nanobot 文檔索引服務已準備好。
"""

import json
import subprocess
import sys
from pathlib import Path


def run_command(cmd, check=True):
    """運行命令並返回結果。"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=check,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr


def test_pymupdf_installed():
    """測試 1: 檢查 PyMuPDF 是否安裝。"""
    print("\n📦 測試 1: 檢查 PyMuPDF 安裝...")
    
    success, stdout, stderr = run_command("python -c \"import fitz; print(fitz.__version__)\"")
    
    if success:
        print(f"   ✅ PyMuPDF 已安裝：{stdout.strip()}")
        return True
    else:
        print(f"   ❌ PyMuPDF 未安裝")
        print(f"      請運行：pip install pymupdf")
        return False


def test_python_dependencies():
    """測試 2: 檢查 Python 依賴。"""
    print("\n📦 測試 2: 檢查 Python 依賴...")
    
    required = ["pymupdf", "requests"]
    missing = []
    
    for pkg in required:
        success, _, _ = run_command(f"python -c \"import {pkg}\"")
        if not success:
            missing.append(pkg)
    
    if not missing:
        print(f"   ✅ 所有 Python 依賴已安裝：{', '.join(required)}")
        return True
    else:
        print(f"   ❌ 缺少 Python 依賴：{', '.join(missing)}")
        print(f"      請運行：pip install {' '.join(missing)}")
        return False


def test_index_script_exists():
    """測試 3: 檢查索引腳本是否存在。"""
    print("\n📦 測試 3: 檢查索引腳本是否存在...")
    
    script_path = Path("nanobot/skills/document_indexer/scripts/build_indexes.py")
    
    if script_path.exists():
        print(f"   ✅ 索引腳本存在：{script_path}")
        return True
    else:
        print(f"   ❌ 索引腳本不存在：{script_path}")
        return False


def test_build_indexes():
    """測試 4: 測試索引生成功能。"""
    print("\n📦 測試 4: 測試索引生成功能...")
    
    # 創建測試目錄
    test_dir = Path("/tmp/nanobot_test")
    test_dir.mkdir(exist_ok=True)
    
    # 檢查是否有測試 PDF
    test_pdf = test_dir / "test.pdf"
    
    # 使用 PyMuPDF 創建一個簡單的測試 PDF
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 72), "Test Financial Report\nCompany: Test Corp\nYear: 2024")
        doc.save(str(test_pdf))
        doc.close()
        
        print(f"   ✅ 創建測試 PDF: {test_pdf}")
    except Exception as e:
        print(f"   ❌ 無法創建測試 PDF: {e}")
        return False
    
    # 運行索引生成腳本
    workspace_dir = test_dir / "workspace"
    workspace_dir.mkdir(exist_ok=True)
    
    success, stdout, stderr = run_command(
        f"python nanobot/skills/document_indexer/scripts/build_indexes.py \"{test_pdf}\"",
        check=False
    )
    
    if success:
        print(f"   ✅ 索引生成成功")
        
        # 檢查生成的索引文件
        index_dir = workspace_dir / "indexes" / "test"
        expected_files = ["toc.md", "metadata.md", "navigation_context.md"]
        
        all_exist = True
        for fname in expected_files:
            fpath = index_dir / fname
            if fpath.exists():
                print(f"      ✓ {fname} 已生成")
            else:
                print(f"      ✗ {fname} 缺失")
                all_exist = False
        
        return all_exist
    else:
        print(f"   ❌ 索引生成失敗")
        print(f"      stderr: {stderr}")
        return False


def test_index_content():
    """測試 5: 檢查索引內容質量。"""
    print("\n📦 測試 5: 檢查索引內容質量...")
    
    test_dir = Path("/tmp/nanobot_test")
    index_dir = test_dir / "workspace" / "indexes" / "test"
    
    # 檢查 TOC
    toc_path = index_dir / "toc.md"
    if toc_path.exists():
        toc_content = toc_path.read_text(encoding="utf-8")
        if "# TOC:" in toc_content:
            print(f"   ✅ TOC 格式正確")
        else:
            print(f"   ❌ TOC 格式錯誤")
            return False
    
    # 檢查 Metadata
    meta_path = index_dir / "metadata.md"
    if meta_path.exists():
        meta_content = meta_path.read_text(encoding="utf-8")
        if "```json" in meta_content and "title" in meta_content:
            print(f"   ✅ Metadata 格式正確")
        else:
            print(f"   ❌ Metadata 格式錯誤")
            return False
    
    # 檢查 Navigation Context
    nav_path = index_dir / "navigation_context.md"
    if nav_path.exists():
        nav_content = nav_path.read_text(encoding="utf-8")
        if "Navigation Context" in nav_content:
            print(f"   ✅ Navigation Context 格式正確")
        else:
            print(f"   ❌ Navigation Context 格式錯誤")
            return False
    
    return True


def cleanup():
    """清理測試文件。"""
    print("\n🧹 清理測試文件...")
    test_dir = Path("/tmp/nanobot_test")
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
        print(f"   ✅ 已清理：{test_dir}")


def main():
    """主測試流程。"""
    print("=" * 60)
    print("Nanobot 文檔索引端到端測試")
    print("=" * 60)
    
    tests = [
        ("PyMuPDF 安裝", test_pymupdf_installed),
        ("Python 依賴", test_python_dependencies),
        ("索引腳本存在", test_index_script_exists),
        ("索引生成功能", test_build_indexes),
        ("索引內容質量", test_index_content),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ 測試 '{name}' 異常：{e}")
            results.append((name, False))
    
    # 清理
    cleanup()
    
    # 總結
    print("\n" + "=" * 60)
    print("測試總結")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通過" if result else "❌ 失敗"
        print(f"  {status}: {name}")
    
    print(f"\n總計：{passed}/{total} 測試通過")
    
    if passed == total:
        print("\n✅ 所有測試通過！Nanobot 文檔索引服務已準備好。")
        return 0
    else:
        print(f"\n❌ {total - passed} 個測試失敗。請檢查上述錯誤。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
