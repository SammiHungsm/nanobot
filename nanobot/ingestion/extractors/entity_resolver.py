"""
Entity Resolver - 財務名詞標準化 (v3.0)

核心功能：
1. 統一不同公司的會計名詞到標準名稱 (Canonical Name)
2. 支援中英文對照
3. 確保 Vanna 查詢的一致性

v3.0 改進：
- 移除冗餘的雙重定義（只保留 core_metrics）
- 支援動態地區/業務分類（不自動歸類）
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger
from functools import lru_cache


class EntityResolver:
    """
    實體對齊器 (v3.1)
    
    將不同公司的會計名詞強制統一為標準名稱
    
    🎯 v3.1 新增：圖文關聯映射 (Relational Mapping)
    - 解決「圖表在第 5 頁，解釋在第 50 頁」的跨頁斷裂問題
    - 使用 Regex 自動偵測文字中提及的圖表（Figure 3, 表 5 等）
    - 將關聯寫入 artifact_relations 表
    """
    
    def __init__(self, mapping_path: Optional[str] = None, db_client=None):
        """
        初始化
        
        Args:
            mapping_path: 財務名詞對照表路徑
            db_client: DBClient 例（用于寫入 artifact_relations）
        """
        if mapping_path is None:
            mapping_path = Path(__file__).parent.parent / "config" / "financial_terms_mapping.json"
        
        self.mapping_path = Path(mapping_path)
        self.mapping: Dict[str, Any] = {}
        self._alias_to_canonical: Dict[str, Tuple[str, str, str]] = {}  # alias -> (canonical_en, canonical_zh, category)
        self.db = db_client  # 🎯 新增：DBClient 實例
        self._load_mapping()
    
    async def link_image_and_text_context(self, document_id: int) -> int:
        """
        🎯 [Step 2: 入庫魔法] 掃描所有 Text Chunk，尋找提及圖表的關鍵字，並建立關聯
        
        核心邏輯：
        1. 從 raw_artifacts 抽取該文檔的所有 Text 類 Artifacts
        2. 從 raw_artifacts 抽取該文檔的所有 Chart/Image 類 Artifacts
        3. 使用 Regex 偵測 "Figure 3", "圖 5", "Table 2" 等關鍵字
        4. 在 Chart/Image 的 metadata 中查找對應的標題/編號
        5. 建立關聯並寫入 artifact_relations 表
        
        Args:
            document_id: 文檔 ID（整數）
            
        Returns:
            int: 建立的關聯數量
            
        Example:
            # 在 PDF 入庫完成後執行
            resolver = EntityResolver(db_client=db)
            links_count = await resolver.link_image_and_text_context(document_id=123)
            print(f"✅ 完成！共建立 {links_count} 條跨頁圖文關聯。")
        """
        if not self.db:
            logger.warning("⚠️ DBClient 未初始化，無法建立圖文關聯")
            return 0
        
        import re
        from loguru import logger
        
        logger.info(f"🔍 正在為 Document {document_id} 執行圖文關聯映射 (Relational Mapping)...")
        
        # 1. 從 Database 抽取該文檔所有 Text 類 Artifacts
        text_artifacts = await self.db.fetch_all(
            """
            SELECT artifact_id, content, page_num, metadata 
            FROM raw_artifacts 
            WHERE document_id = $1 AND artifact_type = 'text_chunk'
            """,
            document_id
        )
        
        # 2. 從 Database 抽取該文檔所有 Chart/Image 類 Artifacts
        image_artifacts = await self.db.fetch_all(
            """
            SELECT artifact_id, content, page_num, metadata, artifact_type
            FROM raw_artifacts 
            WHERE document_id = $1 AND artifact_type IN ('image', 'chart', 'table')
            """,
            document_id
        )
        
        if not text_artifacts or not image_artifacts:
            logger.info(f"ℹ️ Document {document_id} 暫無 Text 或 Chart/Image Artifacts")
            return 0
        
        # 3. 定義 Regex 來捉 "Figure 3", "圖 5", "Table 2" 等
        # 支援中英文：Fig, Figure, 圖, 表, Table
        pattern = re.compile(
            r'(?:fig\.?|figure|圖|圖表|表|table|chart)\s*(\d+[a-zA-Z]?)',
            re.IGNORECASE
        )
        
        # 4. 建立快速查找表：{figure_number: artifact_id}
        # 假設 Chart/Image 的 metadata 中有 title 或 AI 解析出的編號
        image_lookup: Dict[str, Dict[str, Any]] = {}
        for img in image_artifacts:
            img_meta = img.get('metadata', {})
            if isinstance(img_meta, str):
                import json
                try:
                    img_meta = json.loads(img_meta)
                except:
                    img_meta = {}
            
            # 從 metadata 提取可能的標題/編號
            # 假設 ODL/Vision 模型會解析出類似 "Figure 3" 或 "表 5" 的標題
            img_title = img_meta.get('title', '')
            img_caption = img_meta.get('caption', '')
            img_number = img_meta.get('figure_number', '')  # 例如: "3", "5A"
            
            # 多種可能的標識符
            identifiers = [
                img_title,
                img_caption,
                f"Figure {img_number}" if img_number else None,
                f"圖 {img_number}" if img_number else None,
                f"Table {img_number}" if img_number else None,
                f"表 {img_number}" if img_number else None,
            ]
            
            for identifier in identifiers:
                if identifier:
                    # 提取編號部分（如 "Figure 3" -> "3"，"圖 5A" -> "5A"）
                    match = pattern.search(identifier)
                    if match:
                        figure_num = match.group(1)
                        image_lookup[figure_num] = img
        
        # 5. 開始掃描 Text Artifacts
        links_created = 0
        for text_chunk in text_artifacts:
            content = text_chunk.get('content', '')
            text_artifact_id = text_chunk.get('artifact_id')
            
            # 偵測提及的圖表編號
            matches = pattern.findall(content)
            
            for match in matches:
                figure_num = str(match).strip()
                
                # 在 image_lookup 中查找對應的圖表
                if figure_num in image_lookup:
                    img_artifact = image_lookup[figure_num]
                    img_artifact_id = img_artifact.get('artifact_id')
                    
                    # 搞到啦！寫入 Database
                    success = await self.db.save_artifact_relation(
                        document_id=document_id,
                        source_artifact_id=img_artifact_id,  # 圖表 ID
                        target_artifact_id=text_artifact_id,  # 文字 ID
                        relation_type="explained_by",
                        confidence=0.9,  # Regex match 置信度
                        extraction_method="regex"
                    )
                    
                    if success:
                        links_created += 1
                        logger.debug(
                            f"🔗 建立關聯: {img_artifact_id} (Page {img_artifact.get('page_num')}) "
                            f"-> {text_artifact_id} (Page {text_chunk.get('page_num')})"
                        )
        
        logger.info(f"✅ 完成！共建立 {links_created} 條跨頁圖文關聯。")
        return links_created
    
    def _load_mapping(self):
        """載入對照表"""
        try:
            with open(self.mapping_path, 'r', encoding='utf-8') as f:
                self.mapping = json.load(f)
            
            # 構建快速查找表（只從 core_metrics）
            for metric in self.mapping.get("core_metrics", []):
                canonical_en = metric["standard_name"]
                canonical_zh = metric["canonical_zh"]
                category = metric.get("category", "unknown")
                
                # 標準名稱本身
                self._alias_to_canonical[canonical_en.lower()] = (canonical_en, canonical_zh, category)
                self._alias_to_canonical[canonical_zh] = (canonical_en, canonical_zh, category)
                
                # 同義詞
                for alias in metric.get("synonyms", []):
                    self._alias_to_canonical[alias.lower()] = (canonical_en, canonical_zh, category)
            
            # 公司屬性
            for attr in self.mapping.get("company_attributes", []):
                canonical_en = attr["standard_name"]
                canonical_zh = attr["canonical_zh"]
                category = attr.get("category", "unknown")
                
                self._alias_to_canonical[canonical_en.lower()] = (canonical_en, canonical_zh, category)
                self._alias_to_canonical[canonical_zh] = (canonical_en, canonical_zh, category)
                
                for alias in attr.get("synonyms", []):
                    self._alias_to_canonical[alias.lower()] = (canonical_en, canonical_zh, category)
            
            logger.info(f"✅ EntityResolver 載入 {len(self._alias_to_canonical)} 個名詞對照（v3.0）")
            
        except Exception as e:
            logger.error(f"❌ 載入名詞對照表失敗: {e}")
            self.mapping = {}
    
    @lru_cache(maxsize=1000)
    def resolve_metric_name(self, raw_name: str) -> Tuple[str, str]:
        """
        解析財務指標名稱，返回標準化名稱
        
        Args:
            raw_name: 原始名稱（可能是英文或中文）
            
        Returns:
            Tuple[str, str]: (canonical_en, canonical_zh)
        """
        if not raw_name:
            return raw_name, raw_name
        
        # 直接查找
        result = self._alias_to_canonical.get(raw_name.lower())
        if result:
            return result[0], result[1]
        
        result = self._alias_to_canonical.get(raw_name)
        if result:
            return result[0], result[1]
        
        # 模糊匹配（處理大小寫、空格差異）
        normalized = raw_name.lower().strip()
        for alias, canonical_tuple in self._alias_to_canonical.items():
            if normalized == alias.lower().strip():
                return canonical_tuple[0], canonical_tuple[1]
        
        # 未找到對照 → 使用 Fallback 規則
        # 轉換為小寫英文底線格式
        fallback_name = self._apply_fallback_rule(raw_name)
        logger.info(f"ℹ️ 未找到名詞對照: '{raw_name}' → 使用 Fallback: '{fallback_name}'")
        return fallback_name, raw_name
    
    def _apply_fallback_rule(self, raw_name: str) -> str:
        """
        應用 Fallback 規則
        
        v3.0 改進：
        - 不自動歸類地區或業務分類
        - 直接轉換為小寫英文底線格式
        
        Args:
            raw_name: 原始名稱
            
        Returns:
            str: Fallback 名稱
        """
        # 簡單的中文轉拼音或英文轉底線
        # 這裡只是示意，實際應該用更智能的方法
        
        # 如果是純英文，轉小寫加底線
        if raw_name.replace(' ', '').replace('-', '').replace('&', '').isalpha():
            return raw_name.lower().replace(' ', '_').replace('-', '_').replace('&', 'and')
        
        # 如果包含中文，保留原文（實際應該用翻譯）
        return raw_name
    
    def resolve_region_name(self, raw_name: str) -> Tuple[str, str]:
        """
        解析地區名稱（Revenue Breakdown 用）
        
        v3.0 重要改變：
        - 不再自動歸類到預定義的地區
        - 直接返回原文的小寫英文底線格式
        
        Args:
            raw_name: 原始地區名稱
            
        Returns:
            Tuple[str, str]: (canonical_en, canonical_zh)
        """
        # 不再使用硬編碼的地區對照
        # 直接使用 Fallback 規則
        fallback_name = self._apply_fallback_rule(raw_name)
        return fallback_name, raw_name
    
    def get_all_canonical_terms(self) -> List[Dict[str, str]]:
        """
        獲取所有標準名稱列表（用於 Vanna 訓練）
        
        Returns:
            List[Dict]: 標準名稱列表
        """
        terms = []
        
        # 從 core_metrics 提取
        for metric in self.mapping.get("core_metrics", []):
            terms.append({
                "standard_name": metric["standard_name"],
                "canonical_zh": metric["canonical_zh"],
                "category": metric.get("category", "unknown"),
                "synonyms": metric.get("synonyms", [])
            })
        
        return terms
    
    def generate_vanna_training_data(self) -> str:
        """
        生成 Vanna 訓練文檔（包含所有標準名稱）
        
        Returns:
            str: 訓練文檔
        """
        lines = [
            "# 財務指標標準名稱對照表 (v3.0)",
            "",
            "以下是所有財務指標的標準名稱。查詢時請使用這些標準名稱：",
            ""
        ]
        
        # 按類別分組
        categories = {}
        for metric in self.mapping.get("core_metrics", []):
            cat = metric.get("category", "unknown")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(metric)
        
        # 生成文檔
        category_names = {
            "income_statement": "損益表 (Income Statement)",
            "balance_sheet": "資產負債表 (Balance Sheet)",
            "cash_flow": "現金流量表 (Cash Flow)",
            "per_share": "每股數據 (Per Share)",
            "market_data": "市場數據 (Market Data)"
        }
        
        for cat_key, cat_name in category_names.items():
            if cat_key in categories:
                lines.append(f"## {cat_name}")
                lines.append("")
                
                for metric in categories[cat_key]:
                    lines.append(f"- **{metric['standard_name']}** ({metric['canonical_zh']})")
                    synonyms = metric.get("synonyms", [])
                    if synonyms:
                        # 只顯示前 5 個同義詞
                        lines.append(f"  - 別名: {', '.join(synonyms[:5])}")
                
                lines.append("")
        
        # 添加 Fallback 規則說明
        fallback = self.mapping.get("fallback_rule", {})
        if fallback:
            lines.extend([
                "## 動態指標處理規則",
                "",
                "對於未在上述列表中的指標（如地區收入、業務分類）：",
                ""
            ])
            
            for rule in fallback.get("rules", []):
                lines.append(f"- {rule}")
        
        return "\n".join(lines)


# 全局實體對齊器
_entity_resolver: Optional[EntityResolver] = None


def get_entity_resolver() -> EntityResolver:
    """獲取全局實體對齊器"""
    global _entity_resolver
    if _entity_resolver is None:
        _entity_resolver = EntityResolver()
    return _entity_resolver


def resolve_metric_name(raw_name: str) -> Tuple[str, str]:
    """便捷函數：解析財務指標名稱"""
    return get_entity_resolver().resolve_metric_name(raw_name)


def resolve_region_name(raw_name: str) -> Tuple[str, str]:
    """便捷函數：解析地區名稱（v3.0 不自動歸類）"""
    return get_entity_resolver().resolve_region_name(raw_name)


# 測試
if __name__ == "__main__":
    resolver = EntityResolver()
    
    # 測試財務指標
    test_cases = [
        "Revenue",
        "營業額",
        "R&D Expenses",
        "研發費用",
        "Net Profit",
        "淨利潤",
        "Total Assets",
        "總資產"
    ]
    
    print("\n📊 財務指標對照測試 (v3.0)：")
    for name in test_cases:
        canonical_en, canonical_zh = resolver.resolve_metric_name(name)
        print(f"  '{name}' → {canonical_en} / {canonical_zh}")
    
    # 測試地區（不再自動歸類）
    test_regions = [
        "Hong Kong",
        "大灣區",
        "APAC",
        "雲端服務"
    ]
    
    print("\n🌍 地區對照測試（v3.0 不自動歸類）：")
    for name in test_regions:
        canonical_en, canonical_zh = resolver.resolve_region_name(name)
        print(f"  '{name}' → {canonical_en} / {canonical_zh}")