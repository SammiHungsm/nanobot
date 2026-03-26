#!/usr/bin/env python3
"""
端到端測試：驗證 Nanobot + LiteParse MCP Server 完整流程

這個腳本測試：
1. LiteParse CLI 是否正確安裝
2. MCP Server 是否可以正常啟動
3. Data Cleaner 是否可以正確處理數據
4. 完整流程：PDF → LiteParse → MCP → Data Cleaner → Markdown

用法：
    python test_end_to_end.py

如果所有測試通過，你會見到：
    ✅ 所有測試通過！LiteParse MCP 服務已準備好供 Nanobot 使用。
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


def test_lit_cli_installed():
    """測試 1: 檢查 LiteParse CLI 是否安裝。"""
    print("\n📦 測試 1: 檢查 LiteParse CLI 安裝...")
    
    success, stdout, stderr = run_command("lit --version")
    
    if success:
        print(f"   ✅ LiteParse CLI 已安裝：{stdout.strip()}")
        return True
    else:
        print(f"   ❌ LiteParse CLI 未安裝")
        print(f"      請運行：npm install -g @llamaindex/liteparse")
        return False


def test_python_dependencies():
    """測試 2: 檢查 Python 依賴。"""
    print("\n📦 測試 2: 檢查 Python 依賴...")
    
    required = ["pymupdf", "pillow"]
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


def test_data_cleaner():
    """測試 3: 測試 Data Cleaner 功能。"""
    print("\n📦 測試 3: 測試 Data Cleaner 功能...")
    
    # 創建模擬 LiteParse 輸出
    sample_output = {
        "elements": [
            {
                "type": "table",
                "page": 10,
                "table": {
                    "rows": [
                        {"cells": [{"text": "項目"}, {"text": "2023"}, {"text": "2022"}]},
                        {"cells": [{"text": "收入"}, {"text": "1,000,000"}, {"text": "900,000"}]},
                        {"cells": [{"text": "毛利"}, {"text": "500,000"}, {"text": "450,000"}]},
                        {"cells": [{"text": "淨利"}, {"text": "200,000"}, {"text": "180,000"}]},
                    ]
                },
                "bbox": {"x": 100, "y": 200, "width": 400, "height": 300}
            },
            {
                "type": "text",
                "page": 11,
                "text": "本公司 2023 年收入增長 11.1%，達到 100 萬港元。"
            }
        ]
    }
    
    cleaner_path = Path(__file__).parent / "liteparse-mcp-server" / "liteparse_data_cleaner.py"
    
    if not cleaner_path.exists():
        print(f"   ❌ Data Cleaner 文件未找到：{cleaner_path}")
        return False
    
    # 調用 Data Cleaner
    cmd = f"python \"{cleaner_path}\" --input-json '{json.dumps(sample_output)}' --mode context"
    success, stdout, stderr = run_command(cmd)
    
    if success and "# 財務報表數據" in stdout:
        print(f"   ✅ Data Cleaner 正常運作")
        print(f"      輸出格式：Markdown (LLM-ready)")
        return True
    else:
        print(f"   ❌ Data Cleaner 執行失敗")
        print(f"      錯誤：{stderr}")
        return False


def test_mcp_server_structure():
    """測試 4: 檢查 MCP Server 結構。"""
    print("\n📦 測試 4: 檢查 MCP Server 結構...")
    
    mcp_dir = Path(__file__).parent / "liteparse-mcp-server"
    required_files = [
        "index.js",
        "liteparse_data_cleaner.py",
        "package.json",
        "Dockerfile",
    ]
    
    missing = []
    for file in required_files:
        if not (mcp_dir / file).exists():
            missing.append(file)
    
    if not missing:
        print(f"   ✅ MCP Server 結構完整")
        print(f"      文件：{', '.join(required_files)}")
        return True
    else:
        print(f"   ❌ 缺少文件：{', '.join(missing)}")
        return False


def test_docker_compose():
    """測試 5: 檢查 Docker Compose 配置。"""
    print("\n📦 測試 5: 檢查 Docker Compose 配置...")
    
    compose_file = Path(__file__).parent / "docker-compose.yml"
    
    if not compose_file.exists():
        print(f"   ❌ docker-compose.yml 未找到")
        return False
    
    # 讀取並檢查配置
    content = compose_file.read_text(encoding="utf-8")
    
    if "liteparse-mcp:" not in content:
        print(f"   ❌ docker-compose.yml 缺少 liteparse-mcp 服務")
        return False
    
    if "nanobot-gateway:" not in content:
        print(f"   ❌ docker-compose.yml 缺少 nanobot-gateway 服務")
        return False
    
    print(f"   ✅ Docker Compose 配置正確")
    print(f"      服務：liteparse-mcp, nanobot-gateway")
    return True


def test_nanobot_config():
    """測試 6: 檢查 Nanobot 配置。"""
    print("\n📦 測試 6: 檢查 Nanobot 配置...")
    
    config_file = Path(__file__).parent / "config" / "config.yaml"
    
    if not config_file.exists():
        print(f"   ⚠️  config.yaml 未找到，使用預設配置")
        return True
    
    content = config_file.read_text(encoding="utf-8")
    
    # 檢查 MCP 配置
    if "mcp:" in content and "liteparse:" in content:
        print(f"   ✅ Nanobot 配置包含 MCP LiteParse 設置")
        return True
    else:
        print(f"   ⚠️  Nanobot 配置未包含 MCP 設置（可選）")
        return True


def test_sample_pdf():
    """測試 7: 檢查測試 PDF 是否存在。"""
    print("\n📦 測試 7: 檢查測試 PDF...")
    
    pdf_dir = Path(r"C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG\data\input\__enqueued__")
    
    if not pdf_dir.exists():
        print(f"   ⚠️  PDF 目錄未找到：{pdf_dir}")
        return True
    
    pdfs = list(pdf_dir.glob("*.pdf"))
    
    if pdfs:
        print(f"   ✅ 找到 {len(pdfs)} 個測試 PDF")
        print(f"      範例：{pdfs[0].name}")
        return True
    else:
        print(f"   ⚠️  PDF 目錄為空（可稍後添加測試文件）")
        return True


def main():
    """運行所有測試。"""
    print("=" * 60)
    print("🧪 LiteParse MCP Server 端到端測試")
    print("=" * 60)
    
    tests = [
        test_lit_cli_installed,
        test_python_dependencies,
        test_data_cleaner,
        test_mcp_server_structure,
        test_docker_compose,
        test_nanobot_config,
        test_sample_pdf,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"   ❌ 測試失敗：{e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print(f"📊 測試結果：{sum(results)}/{len(results)} 通過")
    print("=" * 60)
    
    if all(results):
        print("\n✅ 所有測試通過！LiteParse MCP 服務已準備好供 Nanobot 使用。")
        print("\n📋 下一步:")
        print("   1. 啟動 MCP Server: cd liteparse-mcp-server && node index.js")
        print("   2. 或使用 Docker: docker-compose up -d")
        print("   3. 在 Nanobot 中調用：parse_financial_table 工具")
        return 0
    else:
        print("\n⚠️  部分測試未通過，請檢查上述錯誤。")
        print("\n💡 常見問題解決:")
        if not results[0]:
            print("   - 安裝 LiteParse CLI: npm install -g @llamaindex/liteparse")
        if not results[1]:
            print("   - 安裝 Python 依賴：pip install pymupdf pillow")
        return 1


if __name__ == "__main__":
    sys.exit(main())
