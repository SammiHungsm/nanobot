"""
Document Indexer - 构建文档索引 (v3.2)

使用 LlamaParse 解析 PDF 并构建索引

🌟 v3.2: 移除 PyMuPDF 和 OpenDataLoader CLI
"""

import sys
import os
import json
import requests
from datetime import datetime
from pathlib import Path
from loguru import logger

# 🌟 v3.2: 使用 LlamaParse
from nanobot.core.pdf_core import PDFParser


def load_nanobot_config():
    """動態讀取 Nanobot 的 config.json"""
    config_paths = [
        "/app/config/config.json",
        os.path.expanduser("~/.nanobot/config.json"),
        "./config/config.json"
    ]
    for path in config_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


CONFIG = load_nanobot_config()


def update_status(status_path, message):
    """更新状态文件"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(status_path, "w", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}")


def call_llm(prompt, require_json=False):
    """呼叫 LLM 進行格式化提取"""
    agent_cfg = CONFIG.get("agents", {}).get("defaults", {})
    provider = agent_cfg.get("provider", "dashscope")
    model = agent_cfg.get("model", "qwen-max").split("/")[-1]
    provider_cfg = CONFIG.get("providers", {}).get(provider, {})
    api_base = provider_cfg.get("api_base", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    headers = {"Content-Type": "application/json"}
    if provider_cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {provider_cfg['api_key']}"
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }
    if require_json:
        payload["response_format"] = {"type": "json_object"}
    
    try:
        res = requests.post(f"{api_base}/chat/completions", headers=headers, json=payload, timeout=60)
        return res.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return "{}" if require_json else str(e)


def parse_pdf(pdf_path: str) -> dict:
    """
    🌟 v3.2: 使用 LlamaParse 解析 PDF
    
    Args:
        pdf_path: PDF 文件路径
        
    Returns:
        解析结果（包含表格、文本、图片）
    """
    try:
        parser = PDFParser(tier="agentic")
        result = parser.parse(pdf_path)
        
        logger.info(f"✅ LlamaParse 解析完成: {result.total_pages} 页, {len(result.tables)} 表格")
        
        return {
            "success": True,
            "total_pages": result.total_pages,
            "tables": result.tables,
            "markdown": result.markdown,
            "artifacts": result.artifacts,
            "images": result.images,
            "job_id": result.job_id,
            "raw_output_dir": result.raw_output_dir
        }
        
    except Exception as e:
        logger.error(f"❌ LlamaParse 解析失败: {e}")
        return {"success": False, "error": str(e)}


def build_indexes(pdf_dir: str, output_dir: str, status_path: str = None):
    """
    构建文档索引
    
    Args:
        pdf_dir: PDF 文件目录
        output_dir: 输出目录
        status_path: 状态文件路径
    """
    if status_path:
        update_status(status_path, "开始构建索引...")
    
    pdf_files = list(Path(pdf_dir).glob("*.pdf"))
    
    if not pdf_files:
        logger.warning(f"未找到 PDF 文件: {pdf_dir}")
        return
    
    logger.info(f"找到 {len(pdf_files)} 个 PDF 文件")
    
    results = []
    
    for i, pdf_file in enumerate(pdf_files):
        if status_path:
            update_status(status_path, f"正在处理 {i+1}/{len(pdf_files)}: {pdf_file.name}")
        
        logger.info(f"📄 处理: {pdf_file}")
        
        result = parse_pdf(str(pdf_file))
        
        if result.get("success"):
            # 保存结果
            output_file = Path(output_dir) / f"{pdf_file.stem}_index.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 保存索引: {output_file}")
            results.append({"file": pdf_file.name, "status": "success", "job_id": result.get("job_id")})
        else:
            logger.error(f"❌ 处理失败: {pdf_file.name}")
            results.append({"file": pdf_file.name, "status": "failed", "error": result.get("error")})
    
    if status_path:
        update_status(status_path, f"完成！成功: {sum(1 for r in results if r['status']=='success')}/{len(results)}")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="构建文档索引")
    parser.add_argument("--pdf-dir", required=True, help="PDF 文件目录")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--status-path", help="状态文件路径")
    
    args = parser.parse_args()
    
    build_indexes(args.pdf_dir, args.output_dir, args.status_path)