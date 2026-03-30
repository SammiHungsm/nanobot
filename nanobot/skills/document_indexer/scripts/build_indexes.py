import sys
import os
import fitz  # PyMuPDF
import requests
import json
import subprocess
from datetime import datetime
from pathlib import Path
from loguru import logger

def load_nanobot_config():
    """動態讀取 Nanobot 的 config.json"""
    config_paths = ["/app/config/config.json", os.path.expanduser("~/.nanobot/config.json"), "/home/nanobot/.nanobot/config.json", "./config/config.json"]
    for path in config_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
    return {}

CONFIG = load_nanobot_config()

def update_status(status_path, message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(status_path, "w", encoding="utf-8") as f: f.write(f"[{timestamp}] {message}")

def call_llm(prompt, require_json=False):
    """呼叫 LLM 進行格式化提取"""
    agent_cfg = CONFIG.get("agents", {}).get("defaults", {})
    provider = agent_cfg.get("provider", "ollama")
    model = agent_cfg.get("model", "qwen3.5:9b").split("/")[-1]
    provider_cfg = CONFIG.get("providers", {}).get(provider, {})
    api_base = provider_cfg.get("api_base", "http://host.docker.internal:11434/v1")
    if not api_base.endswith("/v1"): api_base = f"{api_base.rstrip('/')}/v1"
    
    headers = {"Content-Type": "application/json"}
    if provider_cfg.get("api_key"): headers["Authorization"] = f"Bearer {provider_cfg['api_key']}"
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }
    if require_json: payload["response_format"] = {"type": "json_object"}
    
    try:
        res = requests.post(f"{api_base}/chat/completions", headers=headers, json=payload, timeout=60)
        return res.json()["choices"][0]["message"]["content"]
    except Exception as e: return "{}" if require_json else str(e)

def call_opendataloader(pdf_path: str, pages: str = "all") -> dict:
    """
    使用 OpenDataLoader 解析複雜表格（尤其是財務報表）
    
    OpenDataLoader 已作為 nanobot 的依賴安裝 (opendataloader-pdf[hybrid])
    
    Args:
        pdf_path: PDF 文件路徑
        pages: 頁碼範圍，例如 "1-5" 或 "all"
    
    Returns:
        解析結果的字典，包含表格數據
    """
    try:
        # 檢查 OpenDataLoader 是否已安裝
        result = subprocess.run(
            ["opendataloader-pdf", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        
        if result.returncode != 0:
            logger.warning(
                f"OpenDataLoader 未安裝或無法執行 (returncode={result.returncode})，"
                f"使用 PyMuPDF 後備方案。"
                f"stderr: {result.stderr}"
            )
            return None
        
        # 調用 OpenDataLoader 提取表格
        cmd = [
            "opendataloader-pdf",
            "extract",
            pdf_path,
            "--pages", pages,
            "--format", "json",
            "--tables"  # 只提取表格
        ]
        
        logger.info(f"正在使用 OpenDataLoader 解析 PDF: {pdf_path}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 分鐘超時
            check=False
        )
        
        if result.returncode == 0:
            # 嘗試解析 JSON 輸出
            try:
                data = json.loads(result.stdout)
                logger.info(f"OpenDataLoader 成功解析 {len(data.get('tables', []))} 個表格")
                return data
            except json.JSONDecodeError as je:
                logger.warning(f"OpenDataLoader 輸出了非 JSON 格式：{result.stdout[:200]}")
                return None
        else:
            logger.warning(f"OpenDataLoader 失敗 (returncode={result.returncode})：{result.stderr}")
            return None
            
    except FileNotFoundError:
        logger.warning("OpenDataLoader 命令未找到，使用 PyMuPDF 後備方案")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("OpenDataLoader 超時，使用 PyMuPDF 後備方案")
        return None
    except Exception as e:
        logger.warning(f"OpenDataLoader 異常：{e}，使用 PyMuPDF 後備方案")
        return None

def extract_tables_with_pymupdf(doc, page_indices) -> list:
    """
    使用 PyMuPDF 提取表格作為後備方案
    
    Args:
        doc: PyMuPDF 文檔對象
        page_indices: 要提取的頁碼列表
    
    Returns:
        表格列表
    """
    tables = []
    for page_num in page_indices:
        if page_num < len(doc):
            page = doc[page_num]
            # 提取表格
            page_tables = page.find_tables()
            for i, table in enumerate(page_tables.tables):
                tables.append({
                    'page': page_num + 1,
                    'table_index': i,
                    'data': table.extract(),
                    'bbox': table.bbox
                })
    return tables

def build_indexes(pdf_path, workspace_dir="/app/workspace"):
    """
    建立 PDF 文檔索引，包括目錄、元數據、導航上下文同表格數據
    
    Args:
        pdf_path: PDF 文件路徑
        workspace_dir: 工作目錄路徑
    """
    try:
        doc = fitz.open(pdf_path)
        base_name = os.path.basename(pdf_path).replace(".pdf", "")
        index_dir = os.path.join(workspace_dir, "indexes", base_name)
        os.makedirs(index_dir, exist_ok=True)
        status_path = os.path.join(index_dir, "status.txt")

        # 1. Extract TOC from PDF
        update_status(status_path, "正在提取 PDF 內部目錄...")
        toc = doc.get_toc()
        with open(os.path.join(index_dir, "toc.md"), "w", encoding="utf-8") as f:
            f.write(f"# TOC: {base_name}\n\n")
            for item in toc:
                f.write(f"{'  '*(item[0]-1)}- {item[1]} (Physical Page: {item[2]})\n")
        
        logger.info(f"✅ 已提取目錄：{len(toc)} 個章節")

        # 2. Extract cover page metadata using PyMuPDF
        update_status(status_path, "正在解析封面元數據...")
        metadata = doc.metadata
        with open(os.path.join(index_dir, "metadata.md"), "w", encoding="utf-8") as f:
            f.write(f"# Metadata\n\n```json\n")
            f.write(f"{{\n")
            f.write(f'  "title": "{metadata.get("title", "")}",\n')
            f.write(f'  "author": "{metadata.get("author", "")}",\n')
            f.write(f'  "subject": "{metadata.get("subject", "")}",\n')
            f.write(f'  "creator": "{metadata.get("creator", "")}",\n')
            f.write(f'  "producer": "{metadata.get("producer", "")}",\n')
            f.write(f'  "creation_date": "{metadata.get("creationDate", "")}"\n')
            f.write(f"}}\n")
            f.write(f"```\n")
        
        logger.info("✅ 已提取元數據")

        # 3. 判斷是否使用 OpenDataLoader
        # 如果 PDF 超過 50 頁，或者用戶明確要求，使用 OpenDataLoader 解析複雜表格
        use_opendataloader = doc.page_count > 50
        
        tables_data = None
        if use_opendataloader:
            update_status(status_path, f"正在使用 OpenDataLoader 解析複雜表格 (共 {doc.page_count} 頁)...")
            tables_data = call_opendataloader(pdf_path, pages="all")
            
            if tables_data:
                # 儲存 OpenDataLoader 結果
                with open(os.path.join(index_dir, "tables.json"), "w", encoding="utf-8") as f:
                    json.dump(tables_data, f, ensure_ascii=False, indent=2)
                logger.info(f"✅ 已使用 OpenDataLoader 儲存 {len(tables_data.get('tables', []))} 個表格")
        
        # 如果 OpenDataLoader 失敗或未使用，使用 PyMuPDF 提取前 10 頁的表格
        if not tables_data:
            update_status(status_path, "正在使用 PyMuPDF 提取表格...")
            # 只提取前 10 頁作為樣本
            table_pages = list(range(min(10, doc.page_count)))
            tables = extract_tables_with_pymupdf(doc, table_pages)
            
            if tables:
                tables_data = {'tables': tables, 'source': 'pymupdf'}
                with open(os.path.join(index_dir, "tables.json"), "w", encoding="utf-8") as f:
                    json.dump(tables_data, f, ensure_ascii=False, indent=2)
                logger.info(f"✅ 已使用 PyMuPDF 儲存 {len(tables)} 個表格")

        # 4. Extract first 5 pages as "Navigation Context"
        update_status(status_path, "正在掃描前 5 頁建立背景導航...")
        context_text = ""
        for i in range(min(5, doc.page_count)):
            context_text += f"--- Page {i+1} ---\n" + doc[i].get_text() + "\n"
        
        with open(os.path.join(index_dir, "navigation_context.md"), "w", encoding="utf-8") as f:
            f.write("# Navigation Context (First 5 Pages)\n\n" + context_text)
        
        logger.info("✅ 已建立導航上下文")

        # 5. 建立表格索引（方便快速查找）
        if tables_data and 'tables' in tables_data:
            update_status(status_path, "正在建立表格索引...")
            table_index = []
            for table in tables_data['tables']:
                table_info = {
                    'page': table.get('page', 'N/A'),
                    'table_index': table.get('table_index', 'N/A'),
                    'row_count': len(table.get('data', [])) if isinstance(table.get('data'), list) else 0,
                }
                table_index.append(table_info)
            
            with open(os.path.join(index_dir, "table_index.json"), "w", encoding="utf-8") as f:
                json.dump(table_index, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 已建立表格索引：{len(table_index)} 個表格")

        update_status(status_path, "✅ 導航地圖建立完成")
        print(f"\n🚀 地圖已存儲：{index_dir}")
        print(f"   📑 目錄章節：{len(toc)} 個")
        print(f"   📊 提取表格：{len(tables_data['tables']) if tables_data else 0} 個")
        print(f"   📄 PDF 頁數：{doc.page_count} 頁")
        if use_opendataloader and tables_data:
            print(f"   ✨ 使用 OpenDataLoader 解析")

    except Exception as e:
        logger.error(f"❌ 建立索引失敗：{e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        doc.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python build_indexes.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"❌ PDF 文件不存在：{pdf_path}")
        sys.exit(1)
    
    build_indexes(pdf_path)
