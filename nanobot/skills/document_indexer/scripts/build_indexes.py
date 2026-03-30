import sys
import os
import fitz  # PyMuPDF
import requests
import json
from datetime import datetime

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

def build_indexes(pdf_path, workspace_dir="/app/workspace"):
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

        # 3. Extract first 5 pages as "Navigation Context"
        update_status(status_path, "正在掃描前 5 頁建立背景導航...")
        context_text = ""
        for i in range(min(5, doc.page_count)):
            context_text += f"--- Page {i+1} ---\n" + doc[i].get_text() + "\n"
        
        with open(os.path.join(index_dir, "navigation_context.md"), "w", encoding="utf-8") as f:
            f.write("# Navigation Context (First 5 Pages)\n\n" + context_text)

        update_status(status_path, "✅ 導航地圖建立完成")
        print(f"🚀 地圖已存儲：{index_dir}")

    except Exception as e:
        print(f"❌ 錯誤：{e}")

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    build_indexes(sys.argv[1])
