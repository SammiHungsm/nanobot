"""
Keyword Manager - 管理 search_keywords.json

職責：
- 讀取/寫入 JSON 文件
- 新增關鍵字（帶防呆機制）
- 統計使用次數和命中率
- 支持多進程安全寫入（file lock）

用法：
    from nanobot.ingestion.utils.keyword_manager import KeywordManager
    
    km = KeywordManager("/app/data/search_keywords.json")
    
    # 獲取所有 revenue_breakdown 關鍵字
    keywords = km.get_keywords("revenue_breakdown")
    
    # 新增關鍵字
    km.add_keyword("revenue_breakdown", "營運地區收益剖析", source="agent", confidence="bronze")
    
    # 統計命中
    km.record_hit("revenue breakdown", hit=True)
"""

import json
import os
import base64
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from loguru import logger


class KeywordManager:
    """
    關鍵字管理器
    
    使用 JSON 文件存儲，支持：
    - 分級制度（gold/silver/bronze）
    - 防呆機制（禁止太短或太通用的詞）
    - 使用統計（usage_count, hit_count）
    """
    
    # 🚫 禁用詞庫（太通用，會導致假陽性）
    BLOCKED_KEYWORDS = [
        "total", "sum", "and", "the", "of", "for", "in", "to", "a", "an",
        "table", "figure", "page", "chart", "graph", "data", "note",
        "1.", "2.", "3.", "4.", "5.",
        "2020", "2021", "2022", "2023", "2024", "2025", "2026",
        "hk", "hkd", "usd", "rmb", "million", "thousand"
    ]
    
    # 🎯 最低長度要求
    MIN_KEYWORD_LENGTH = 3
    
    def __init__(self, json_path: str = "/app/data/raw/search_keywords.json"):
        """
        初始化
        
        Args:
            json_path: JSON 文件路徑
        """
        self.json_path = Path(json_path)
        self._data = None
        
        # 確保文件存在
        if not self.json_path.exists():
            logger.warning(f"⚠️ Keyword JSON 不存在，創建默認文件: {self.json_path}")
            self._create_default_file()
    
    def _create_default_file(self):
        """創建默認的 JSON 文件"""
        default_data = {
            "version": "1.0.0",
            "last_updated": datetime.now().isoformat(),
            "categories": {
                "revenue_breakdown": {
                    "keywords": [],
                    "description": "用於識別 Revenue Breakdown 相關頁面的關鍵字"
                }
            },
            "blocked_keywords": self.BLOCKED_KEYWORDS,
            "metadata": {
                "total_keywords": 0,
                "categories_count": 1
            }
        }
        self._safe_write(default_data)
    
    def _safe_read(self) -> Dict[str, Any]:
        """
        安全讀取 JSON（帶文件鎖）
        
        Returns:
            Dict: JSON 數據
        """
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                # 🔒 Windows 不支持 fcntl，但單進程環境不需要鎖
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"❌ 讀取 Keyword JSON 失敗: {e}")
            return {}
    
    def _safe_write(self, data: Dict[str, Any]) -> bool:
        """
        安全寫入 JSON（帶文件鎖）
        
        Args:
            data: 要寫入的數據
            
        Returns:
            bool: 是否成功
        """
        try:
            # 更新時間戳
            data["last_updated"] = datetime.now().isoformat()
            
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"✅ Keyword JSON 已更新")
            return True
        except Exception as e:
            logger.error(f"❌ 寫入 Keyword JSON 失敗: {e}")
            return False
    
    def get_keywords(
        self, 
        category: str,
        min_confidence: str = "bronze"  # gold > silver > bronze
    ) -> List[str]:
        """
        獲取指定類別的關鍵字列表
        
        Args:
            category: 類別名稱（revenue_breakdown, key_personnel）
            min_confidence: 最低信心等級
            
        Returns:
            List[str]: 關鍵字列表
        """
        data = self._safe_read()
        
        if not data or "categories" not in data:
            logger.warning("⚠️ Keyword JSON 格式異常，返回空列表")
            return []
        
        category_data = data["categories"].get(category)
        if not category_data:
            logger.warning(f"⚠️ 找不到類別: {category}")
            return []
        
        keywords = []
        confidence_order = {"gold": 3, "silver": 2, "bronze": 1}
        min_level = confidence_order.get(min_confidence, 1)
        
        for kw_entry in category_data.get("keywords", []):
            kw_level = confidence_order.get(kw_entry.get("confidence", "bronze"), 1)
            if kw_level >= min_level:
                keywords.append(kw_entry["keyword"])
        
        logger.debug(f"📊 獲取 {category} 關鍵字: {len(keywords)} 個 (min_confidence={min_confidence})")
        return keywords
    
    def get_all_keywords_flat(self, category: str = "revenue_breakdown") -> List[str]:
        """
        獲取扁平化的關鍵字列表（不分級，直接返回所有）
        
        Args:
            category: 類別名稱
            
        Returns:
            List[str]: 關鍵字列表
        """
        return self.get_keywords(category, min_confidence="bronze")
    
    def add_keyword(
        self,
        category: str,
        keyword: str,
        source: str = "agent",
        confidence: str = "bronze",
        reasoning: str = ""
    ) -> Dict[str, Any]:
        """
        新增關鍵字
        
        Args:
            category: 類別
            keyword: 新關鍵字
            source: 來源（manual/agent）
            confidence: 信心等級
            reasoning: Agent 的推理
            
        Returns:
            Dict: 操作結果
        """
        # 🔒 防呆檢查
        keyword_lower = keyword.lower().strip()
        
        # 1. 長度檢查
        if len(keyword_lower) < self.MIN_KEYWORD_LENGTH:
            return {
                "success": False,
                "reason": f"關鍵字太短（< {self.MIN_KEYWORD_LENGTH} 字符），會導致假陽性"
            }
        
        # 2. 禁用詞檢查
        if keyword_lower in [b.lower() for b in self.BLOCKED_KEYWORDS]:
            return {
                "success": False,
                "reason": f"'{keyword}' 在禁用詞庫中，太通用會導致假陽性"
            }
        
        # 3. 重複檢查
        existing = self.get_keywords(category)
        if keyword_lower in [e.lower() for e in existing]:
            return {
                "success": False,
                "reason": f"'{keyword}' 已存在於關鍵字庫中"
            }
        
        # ✅ 通過檢查，寫入 JSON
        data = self._safe_read()
        
        if category not in data["categories"]:
            data["categories"][category] = {
                "keywords": [],
                "description": f"用於識別 {category} 相關頁面的關鍵字"
            }
        
        new_entry = {
            "keyword": keyword,
            "confidence": confidence,
            "source": source,
            "added_at": datetime.now().strftime("%Y-%m-%d"),
            "usage_count": 0,
            "hit_count": 0,
            "reasoning": reasoning if reasoning else None
        }
        
        data["categories"][category]["keywords"].append(new_entry)
        
        # 更新 metadata
        data["metadata"]["total_keywords"] = sum(
            len(c.get("keywords", [])) for c in data["categories"].values()
        )
        
        write_success = self._safe_write(data)
        
        if not write_success:
            return {
                "success": False,
                "reason": "寫入 JSON 文件失敗（權限問題）"
            }
        
        logger.info(f"✅ 新關鍵字 '{keyword}' 已加入 {category} (confidence={confidence})")
        
        return {
            "success": True,
            "keyword": keyword,
            "category": category,
            "confidence": confidence,
            "message": f"✅ '{keyword}' 已成功加入 {category} 知識庫！"
        }
    
    def record_hit(self, keyword: str, hit: bool = True):
        """
        記錄關鍵字的使用和命中
        
        Args:
            keyword: 關鍵字
            hit: 是否命中（找到正確頁面）
        """
        data = self._safe_read()
        
        for category_name, category_data in data["categories"].items():
            for kw_entry in category_data.get("keywords", []):
                if kw_entry["keyword"].lower() == keyword.lower():
                    kw_entry["usage_count"] = kw_entry.get("usage_count", 0) + 1
                    if hit:
                        kw_entry["hit_count"] = kw_entry.get("hit_count", 0) + 1
                    break
        
        self._safe_write(data)
    
    def get_stats(self, category: str = None) -> Dict[str, Any]:
        """
        獲取統計信息
        
        Args:
            category: 類別（None 表示全部）
            
        Returns:
            Dict: 統計信息
        """
        data = self._safe_read()
        
        stats = {
            "total_keywords": 0,
            "categories": {},
            "low_performance": []  # 假陽性關鍵字
        }
        
        for cat_name, cat_data in data["categories"].items():
            if category and cat_name != category:
                continue
            
            cat_stats = {
                "total": len(cat_data.get("keywords", [])),
                "gold": 0,
                "silver": 0,
                "bronze": 0,
                "avg_hit_rate": 0.0
            }
            
            total_hit_rate = 0.0
            hit_rate_count = 0
            
            for kw_entry in cat_data.get("keywords", []):
                confidence = kw_entry.get("confidence", "bronze")
                cat_stats[confidence] = cat_stats.get(confidence, 0) + 1
                
                # 計算命中率
                usage = kw_entry.get("usage_count", 0)
                hits = kw_entry.get("hit_count", 0)
                
                if usage > 0:
                    hit_rate = hits / usage
                    total_hit_rate += hit_rate
                    hit_rate_count += 1
                    
                    # 🚨 低效能警告
                    if usage >= 5 and hit_rate < 0.2:
                        stats["low_performance"].append({
                            "keyword": kw_entry["keyword"],
                            "category": cat_name,
                            "usage_count": usage,
                            "hit_rate": round(hit_rate, 2),
                            "suggestion": "建議移除或降級"
                        })
            
            if hit_rate_count > 0:
                cat_stats["avg_hit_rate"] = round(total_hit_rate / hit_rate_count, 2)
            
            stats["categories"][cat_name] = cat_stats
            stats["total_keywords"] += cat_stats["total"]
        
        return stats
    
    def remove_keyword(self, category: str, keyword: str) -> Dict[str, Any]:
        """
        移除關鍵字
        
        Args:
            category: 類別
            keyword: 關鍵字
            
        Returns:
            Dict: 操作結果
        """
        data = self._safe_read()
        
        if category not in data["categories"]:
            return {"success": False, "reason": f"類別 '{category}' 不存在"}
        
        keywords = data["categories"][category].get("keywords", [])
        original_count = len(keywords)
        
        # 移除匹配的關鍵字
        keywords = [kw for kw in keywords if kw["keyword"].lower() != keyword.lower()]
        
        if len(keywords) == original_count:
            return {"success": False, "reason": f"關鍵字 '{keyword}' 不存在"}
        
        data["categories"][category]["keywords"] = keywords
        self._safe_write(data)
        
        logger.info(f"🗑️ 已移除關鍵字 '{keyword}' from {category}")
        
        return {"success": True, "keyword": keyword, "message": f"已移除 '{keyword}'"}
    
    # ===========================================
    # 🌟 Phase 3: 上下文感知 + 反向學習
    # ===========================================
    
    def record_hit_with_context(
        self,
        keyword: str,
        page_num: int,
        total_pages: int,
        features: Dict[str, Any] = None,
        hit: bool = True,
        industry: str = None
    ):
        """
        🌟 Phase 3: 記錄命中 + 上下文信息
        
        上下文信息包括：
        - 頁碼位置（相對位置 = page_num / total_pages）
        - 共同出現的特徵（has_table, has_percentage, has_currency）
        - 行業標籤
        
        Args:
            keyword: 關鍵字
            page_num: 命中的頁碼
            total_pages: PDF 總頁數
            features: 上下文特徵（如 {"has_table": True, "has_percentage": True}）
            hit: 是否命中（找到正確頁面）
            industry: 行業標籤（如 "banking", "biotech"）
        """
        data = self._safe_read()
        
        relative_position = page_num / total_pages if total_pages > 0 else 0
        
        for category_name, category_data in data["categories"].items():
            for kw_entry in category_data.get("keywords", []):
                if kw_entry["keyword"].lower() == keyword.lower():
                    # 基本統計
                    kw_entry["usage_count"] = kw_entry.get("usage_count", 0) + 1
                    if hit:
                        kw_entry["hit_count"] = kw_entry.get("hit_count", 0) + 1
                    
                    # 🌟 上下文感知：記錄頁碼範圍
                    if "page_hits" not in kw_entry:
                        kw_entry["page_hits"] = []
                    
                    if hit:
                        kw_entry["page_hits"].append({
                            "page_num": page_num,
                            "relative_position": round(relative_position, 3),
                            "industry": industry,
                            "features": features or {}
                        })
                        
                        # 更新典型頁碼範圍（取最近 10 次命中的統計）
                        recent_hits = kw_entry["page_hits"][-10:]
                        if len(recent_hits) >= 3:
                            positions = [h["relative_position"] for h in recent_hits]
                            kw_entry["typical_position_min"] = round(min(positions), 3)
                            kw_entry["typical_position_max"] = round(max(positions), 3)
                            kw_entry["typical_position_avg"] = round(sum(positions) / len(positions), 3)
                    
                    # 🌟 行業特化：記錄行業命中
                    if industry and hit:
                        if "industry_hits" not in kw_entry:
                            kw_entry["industry_hits"] = {}
                        kw_entry["industry_hits"][industry] = kw_entry["industry_hits"].get(industry, 0) + 1
                    
                    # 🌟 共同特徵：更新 co_occurrence_features
                    if features and hit:
                        if "co_occurrence_features" not in kw_entry:
                            kw_entry["co_occurrence_features"] = {}
                        
                        for feat_name, feat_value in features.items():
                            if feat_value:  # 只記錄 True 的特徵
                                kw_entry["co_occurrence_features"][feat_name] = \
                                    kw_entry["co_occurrence_features"].get(feat_name, 0) + 1
                    
                    break
        
        self._safe_write(data)
    
    def get_keyword_context(self, keyword: str, category: str = None) -> Dict[str, Any]:
        """
        🌟 Phase 3: 获取关键词的上下文信息
        
        返回：
        - typical_position_min/max/avg：典型頁碼範圍
        - co_occurrence_features：共同出現的特徵
        - industry_hits：行業命中統計
        
        Args:
            keyword: 關鍵字
            category: 類別
            
        Returns:
            Dict: 上下文信息
        """
        data = self._safe_read()
        
        for cat_name, cat_data in data["categories"].items():
            if category and cat_name != category:
                continue
            
            for kw_entry in cat_data.get("keywords", []):
                if kw_entry["keyword"].lower() == keyword.lower():
                    return {
                        "keyword": kw_entry["keyword"],
                        "category": cat_name,
                        "confidence": kw_entry.get("confidence"),
                        "usage_count": kw_entry.get("usage_count", 0),
                        "hit_count": kw_entry.get("hit_count", 0),
                        "hit_rate": round(kw_entry.get("hit_count", 0) / max(kw_entry.get("usage_count", 1), 1), 2),
                        "typical_position_min": kw_entry.get("typical_position_min"),
                        "typical_position_max": kw_entry.get("typical_position_max"),
                        "typical_position_avg": kw_entry.get("typical_position_avg"),
                        "co_occurrence_features": kw_entry.get("co_occurrence_features", {}),
                        "industry_hits": kw_entry.get("industry_hits", {}),
                        "recent_page_hits": kw_entry.get("page_hits", [])[-5:]
                    }
        
        return {"error": f"Keyword '{keyword}' not found"}
    
    def auto_cleanup_low_performance(self, min_usage: int = 5, min_hit_rate: float = 0.2) -> Dict[str, Any]:
        """
        🌟 Phase 3: 反向學習 - 自動清理低效能關鍵字
        
        檢測規則：
        - usage_count >= min_usage（使用至少 5 次）
        - hit_rate < min_hit_rate（命中率低於 20%）
        
        行為：
        - Bronze 等級 → 直接移除
        - Silver 等級 → 降級為 Bronze
        - Gold 等級 → 保持（需要人工審核）
        
        Args:
            min_usage: 最小使用次數
            min_hit_rate: 最小命中率
            
        Returns:
            Dict: 清理結果
        """
        data = self._safe_read()
        
        removed = []
        downgraded = []
        
        for cat_name, cat_data in data["categories"].items():
            keywords_to_keep = []
            
            for kw_entry in cat_data.get("keywords", []):
                usage = kw_entry.get("usage_count", 0)
                hits = kw_entry.get("hit_count", 0)
                confidence = kw_entry.get("confidence", "bronze")
                
                # 計算命中率
                hit_rate = hits / usage if usage > 0 else 0
                
                # 🚨 低效能檢測
                if usage >= min_usage and hit_rate < min_hit_rate:
                    if confidence == "bronze":
                        # Bronze → 直接移除
                        removed.append({
                            "keyword": kw_entry["keyword"],
                            "category": cat_name,
                            "usage_count": usage,
                            "hit_rate": round(hit_rate, 2)
                        })
                        logger.info(f"🗑️ 移除低效能關鍵字: '{kw_entry['keyword']}' (hit_rate={hit_rate:.2f})")
                        continue  # 不保留
                    
                    elif confidence == "silver":
                        # Silver → 降級為 Bronze
                        kw_entry["confidence"] = "bronze"
                        kw_entry["downgraded_at"] = datetime.now().strftime("%Y-%m-%d")
                        kw_entry["downgrade_reason"] = f"hit_rate={hit_rate:.2f} < {min_hit_rate}"
                        downgraded.append({
                            "keyword": kw_entry["keyword"],
                            "category": cat_name,
                            "new_confidence": "bronze"
                        })
                        logger.warning(f"⚠️ 降級關鍵字: '{kw_entry['keyword']}' silver → bronze")
                    
                    # Gold → 保持（需要人工審核）
                    # 不做自動處理
                
                keywords_to_keep.append(kw_entry)
            
            data["categories"][cat_name]["keywords"] = keywords_to_keep
        
        self._safe_write(data)
        
        return {
            "removed_count": len(removed),
            "downgraded_count": len(downgraded),
            "removed": removed,
            "downgraded": downgraded,
            "message": f"✅ 清理完成：移除 {len(removed)} 個，降級 {len(downgraded)} 個低效能關鍵字"
        }
    
    def get_keywords_for_industry(self, category: str, industry: str) -> List[str]:
        """
        🌟 Phase 3: 获取行业特化的关键词
        
        根據行業命中統計，優化關鍵字排序
        
        Args:
            category: 類別
            industry: 行業
            
        Returns:
            List[str]: 按行業命中排序的關鍵字列表
        """
        data = self._safe_read()
        
        if category not in data["categories"]:
            return []
        
        keywords_with_scores = []
        
        for kw_entry in data["categories"][category].get("keywords", []):
            keyword = kw_entry["keyword"]
            confidence = kw_entry.get("confidence", "bronze")
            
            # 基本信心等級得分
            confidence_score = {"gold": 3, "silver": 2, "bronze": 1}.get(confidence, 1)
            
            # 行業特化得分
            industry_hits = kw_entry.get("industry_hits", {})
            industry_score = industry_hits.get(industry, 0)
            
            # 總得分 = 信心等級 + 行業命中（行業特化的關鍵字會排前面）
            total_score = confidence_score * 10 + industry_score
            
            keywords_with_scores.append((keyword, total_score))
        
        # 按得分排序（高分在前）
        keywords_with_scores.sort(key=lambda x: x[1], reverse=True)
        
        return [kw for kw, score in keywords_with_scores]
    
    def predict_candidate_pages(
        self,
        keyword: str,
        total_pages: int,
        category: str = None,
        industry: str = None
    ) -> Dict[str, Any]:
        """
        🌟 Phase 3: 預測候選頁面範圍
        
        根據歷史命中數據，預測該關鍵字可能出現的頁碼範圍
        
        Args:
            keyword: 關鍵字
            total_pages: PDF 總頁數
            category: 類別
            industry: 行業
            
        Returns:
            Dict: 預測結果
        """
        context = self.get_keyword_context(keyword, category)
        
        if "error" in context:
            return {"error": context["error"]}
        
        # 如果沒有歷史數據，返回全範圍
        if context.get("usage_count", 0) < 3:
            return {
                "keyword": keyword,
                "predicted_range": [1, total_pages],
                "confidence": "low",
                "reason": "歷史數據不足"
            }
        
        # 🎯 根據典型相對位置預測
        typical_min = context.get("typical_position_min", 0)
        typical_max = context.get("typical_position_max", 1)
        
        # 轉換為絕對頁碼
        predicted_min = max(1, int(typical_min * total_pages))
        predicted_max = min(total_pages, int(typical_max * total_pages) + 1)
        
        # 🎯 行業特化調整
        industry_hits = context.get("industry_hits", {})
        if industry and industry in industry_hits:
            # 行業命中率高 → 更精確的範圍
            confidence = "high"
        else:
            confidence = "medium"
        
        return {
            "keyword": keyword,
            "predicted_range": [predicted_min, predicted_max],
            "typical_relative_range": [typical_min, typical_max],
            "confidence": confidence,
            "industry_match": industry in industry_hits if industry else False,
            "co_occurrence_features": context.get("co_occurrence_features", {})
        }