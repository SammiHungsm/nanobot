"""
Stage 3: 关键字扫描与目标页面路由 (v4.0 Configuration-Driven)

职责：
- 在 artifacts 中搜索关键字
- 返回候选页面列表
- 🌟 v4.0: 100% 配置驱动 - 关键字定义完全依赖外部 financial_terms_mapping.json
- 🌟 移除所有 hardcode 的 KEYWORD_MAP，Python 程式码纯粹负责逻辑运算
- 🌟 无缝接轨 Agentic 学习：Stage 4 发现新字眼写入 JSON 后立刻生效
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Set, Optional
from loguru import logger


class Stage3Router:
    """
    Stage 3: 关键字扫描与目标页面路由
    
    🌟 100% 配置驱动：关键字定义完全依赖外部 financial_terms_mapping.json
    不再在 Python 程式码中夹任何业务资料（财报术语）
    """
    
    # 🌟 移除原本龐大的 KEYWORD_MAP，改為等待被 JSON 覆蓋的空属性
    _keyword_map: Dict[str, List[str]] = {}
    _is_loaded: bool = False
    _config_path: str = "nanobot/ingestion/config/financial_terms_mapping.json"
    
    @classmethod
    def _load_keywords_from_json(
        cls, 
        config_path: str = None,
        force_reload: bool = False
    ) -> None:
        """
        🌟 强制从外部 JSON 载入关键字对应表
        
        Args:
            config_path: JSON 配置文件路径
            force_reload: 是否强制重新加载
        """
        if cls._is_loaded and not force_reload:
            return
        
        # 使用默认路径或传入的路径
        json_path = Path(config_path or cls._config_path)
        
        if not json_path.exists():
            # 🌟 如果檔案不存在，给予明确警告，初始化为空字典，而不是退回 hardcode
            logger.error(f"❌ 找不到关键字设定档: {json_path}")
            logger.warning("Stage 3 将无法进行任何路由！请确认 financial_terms_mapping.json 存在。")
            cls._keyword_map = {}
            cls._is_loaded = True
            return
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                cls._keyword_map = json.load(f)
            cls._is_loaded = True
            cls._config_path = str(json_path)
            logger.info(f"✅ 成功载入外部关键字设定档: {len(cls._keyword_map)} 个分类")
            
            # 打印每个分类的关键字数量
            for category, keywords in cls._keyword_map.items():
                logger.debug(f"   - {category}: {len(keywords)} 个关键字")
                
        except Exception as e:
            logger.error(f"❌ 读取关键字设定档失败: {e}")
            cls._keyword_map = {}
            cls._is_loaded = True
    
    @classmethod
    def get_keyword_map(
        cls, 
        config_path: str = None,
        force_reload: bool = False
    ) -> Dict[str, List[str]]:
        """
        🌟 获取当前的关键字对应表
        
        Args:
            config_path: JSON 配置文件路径
            force_reload: 是否强制重新加载
            
        Returns:
            Dict[str, List[str]]: 关键字对应表
        """
        cls._load_keywords_from_json(config_path, force_reload)
        return cls._keyword_map
    
    @classmethod
    def add_keywords(
        cls, 
        category: str, 
        new_keywords: List[str],
        save_to_json: bool = True
    ) -> None:
        """
        🌟 动态添加关键字（Agentic 学习）
        
        Args:
            category: 分类名称
            new_keywords: 新关键字列表
            save_to_json: 是否保存到 JSON 文件
        """
        cls._load_keywords_from_json()
        
        if category not in cls._keyword_map:
            cls._keyword_map[category] = []
        
        # 添加新关键字（避免重复）
        for kw in new_keywords:
            kw_lower = kw.lower()
            if kw_lower not in [k.lower() for k in cls._keyword_map[category]]:
                cls._keyword_map[category].append(kw_lower)
                logger.info(f"   🌟 新增关键字: '{kw}' → {category}")
        
        # 保存到 JSON
        if save_to_json:
            cls._save_keywords_to_json()
    
    @classmethod
    def _save_keywords_to_json(cls) -> None:
        """保存关键字到 JSON 文件"""
        json_path = Path(cls._config_path)
        
        try:
            # 确保目录存在
            json_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(cls._keyword_map, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 关键字设定档已更新: {json_path}")
            
        except Exception as e:
            logger.error(f"❌ 保存关键字设定档失败: {e}")
    
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
        
        # 🌟 强制从 JSON 加载关键字（如果还没有加载）
        Stage3Router._load_keywords_from_json(keyword_json_path, force_reload=bool(keyword_json_path))
        
        # 获取关键字对应表
        keyword_map = Stage3Router.get_keyword_map()
        
        # 如果 keyword_map 是空的，给出警告
        if not keyword_map:
            logger.warning("⚠️ 关键字对应表为空！Stage 3 无法进行路由。")
            return {}
        
        target_types = target_types or list(keyword_map.keys())
        
        # 🌟 构建 searches 关键字集合
        keywords_to_search = {}
        for target_type in target_types:
            if target_type in keyword_map:
                keywords_to_search[target_type] = set(keyword_map[target_type])
            else:
                logger.warning(f"   ⚠️ 未知的分类: {target_type}")
        
        if custom_keywords:
            keywords_to_search["custom"] = set(custom_keywords)
        
        # 扫描结果
        results = {target_type: [] for target_type in keywords_to_search.keys()}
        keyword_hits = {kw: [] for kw in Stage3Router._flatten_keywords(keywords_to_search)}
        
        # 扫描每个 artifact
        for artifact in artifacts:
            if artifact is None:
                continue
                
            artifact_type = artifact.get("type")
            # 🌟 v3.2: LlamaParse 使用 'page' 字段
            page_num = artifact.get("page")
            
            if page_num is None:
                continue
            
            # 只在有文字或表格的区块搜索
            if artifact_type == "text":
                content = str(artifact.get("content", "")).lower()
                Stage3Router._check_keywords(content, page_num, keywords_to_search, results, keyword_hits)
            
            elif artifact_type == "table":
                table_content = artifact.get("content", {})
                if isinstance(table_content, dict):
                    # 🌟 v4.4: 使用自定義序列化，忽略 BBox 等不可序列化的對象
                    try:
                        content = json.dumps(table_content, ensure_ascii=False, default=str).lower()
                    except Exception as e:
                        logger.warning(f"   ⚠️ 表格內容序列化失敗: {e}")
                        content = str(table_content).lower()
                else:
                    content = str(table_content).lower()
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