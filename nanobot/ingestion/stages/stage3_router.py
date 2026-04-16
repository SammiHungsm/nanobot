"""
Stage 3: 关键字扫描与目标页面路由 (v3.2)

职责：
- 在 artifacts 中搜索关键字
- 返回候选页面列表
- 🌟 v3.2: 处理 LlamaParse 的 artifacts（使用 'page' 字段）
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Set, Optional
from loguru import logger


class Stage3Router:
    """Stage 3: 关键字扫描与目标页面路由"""
    
    # 预定义关键词映射
    KEYWORD_MAP = {
        "revenue_breakdown": [
            "revenue breakdown", "geographical", "geographic",
            "region", "segment", "business segment",
            "收入分佈", "地區收入", "業務分佈",
            "revenue by", "revenue from", "sales breakdown"
        ],
        "key_personnel": [
            "director", "management", "高管", "董事", "委员会",
            "board of directors", "executive", "ceo", "cfo",
            "董事会", "管理层", "关键人员"
        ],
        "financial_metrics": [
            "profit", "assets", "liabilities", "收入", "利润", "资产",
            "balance sheet", "income statement", "cash flow",
            "财务指标", "净利润", "营业收入"
        ],
        "market_data": [
            "share price", "market cap", "股价", "市值",
            "trading volume", "stock price", "股价走势"
        ],
        "shareholding": [
            "shareholder", "持股", "股东结构", "ownership",
            "major shareholder", "股权结构", "持股比例"
        ],
        "esg": [
            "ESG", "碳排放", "sustainability", "environmental",
            "社会责任", "可持续发展"
        ],
    }
    
    @staticmethod
    async def find_target_pages(
        artifacts: List[Dict[str, Any]],
        target_types: List[str] = None,
        custom_keywords: List[str] = None,
        keyword_json_path: str = None
    ) -> Dict[str, List[int]]:
        """
        扫描 artifacts，找出包含关键词的页面
        
        Args:
            artifacts: artifact 列表
            target_types: 目标类型列表 ["revenue_breakdown", "key_personnel", ...]
            custom_keywords: 自定义关键词
            keyword_json_path: 关键词 JSON 文件路径
            
        Returns:
            Dict: {"revenue_breakdown": [12, 45], "key_personnel": [23, 24], ...}
        """
        logger.info(f"🔍 Stage 3: 开始关键字扫描...")
        
        target_types = target_types or list(Stage3Router.KEYWORD_MAP.keys())
        
        # 🌟 从 JSON 加载关键词（支持 Agent 动态学习）
        keywords_to_search = {}
        
        if keyword_json_path:
            keywords_to_search = Stage3Router._load_keywords_from_json(keyword_json_path, target_types)
        
        # 如果 JSON 没有或空白，使用预定义关键词
        for target_type in target_types:
            if target_type not in keywords_to_search or not keywords_to_search[target_type]:
                keywords_to_search[target_type] = set(Stage3Router.KEYWORD_MAP.get(target_type, []))
        
        if custom_keywords:
            keywords_to_search["custom"] = set(custom_keywords)
        
        # 扫描结果
        results = {target_type: [] for target_type in keywords_to_search.keys()}
        keyword_hits = {kw: [] for kw in Stage3Router._flatten_keywords(keywords_to_search)}
        
        # 扫描每个 artifact
        for artifact in artifacts:
            artifact_type = artifact.get("type")
            # 🌟 v3.2: LlamaParse 使用 'page' 字段
            page_num = artifact.get("page")
            
            # 只在有文字或表格的区块搜索
            if artifact_type == "text_chunk":
                content = str(artifact.get("content", "")).lower()
                Stage3Router._check_keywords(content, page_num, keywords_to_search, results, keyword_hits)
            
            elif artifact_type == "table":
                table_json = artifact.get("content_json", {})
                content = json.dumps(table_json, ensure_ascii=False).lower()
                Stage3Router._check_keywords(content, page_num, keywords_to_search, results, keyword_hits)
            
            elif artifact_type == "image":
                # 图片可能已有 enriched content
                content = artifact.get("content", "").lower()
                if content:
                    Stage3Router._check_keywords(content, page_num, keywords_to_search, results, keyword_hits)
        
        # 总结
        for target_type, pages in results.items():
            if pages:
                logger.info(f"   ✅ {target_type}: {len(pages)} 个候选页面 {sorted(pages)}")
        
        return results
    
    @staticmethod
    def _load_keywords_from_json(json_path: str, target_types: List[str]) -> Dict[str, Set[str]]:
        """从 JSON 文件加载关键词"""
        
        keywords = {}
        
        try:
            if Path(json_path).exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                for target_type in target_types:
                    if target_type in data:
                        keywords[target_type] = set(data[target_type].get("keywords", []))
                        
        except Exception as e:
            logger.warning(f"   ⚠️ 关键词 JSON 加载失败: {e}")
        
        return keywords
    
    @staticmethod
    def _flatten_keywords(keywords_dict: Dict[str, Set[str]]) -> List[str]:
        """扁平化所有关键词"""
        all_keywords = []
        for kw_set in keywords_dict.values():
            all_keywords.extend(list(kw_set))
        return all_keywords
    
    @staticmethod
    def _check_keywords(
        content: str,
        page_num: int,
        keywords_to_search: Dict[str, Set[str]],
        results: Dict[str, List[int]],
        keyword_hits: Dict[str, List[int]]
    ):
        """检查内容是否包含关键词"""
        
        for target_type, keywords in keywords_to_search.items():
            for keyword in keywords:
                if keyword.lower() in content:
                    if page_num not in results[target_type]:
                        results[target_type].append(page_num)
                        logger.debug(f"   Page {page_num}: 命中 '{keyword}' → {target_type}")
                    
                    if keyword in keyword_hits and page_num not in keyword_hits[keyword]:
                        keyword_hits[keyword].append(page_num)
    
    @staticmethod
    def get_all_candidate_pages(results: Dict[str, List[int]]) -> List[int]:
        """合并所有候选页面"""
        all_pages = set()
        for pages in results.values():
            all_pages.update(pages)
        
        return sorted(list(all_pages))