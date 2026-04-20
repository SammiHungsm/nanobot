"""
Table Merger - 跨页表格合并工具

从 pipeline.py 提取出来的独立工具类。

功能：
- 合并跨页的表格（例如表格从第 5 页延续到第 6 页）
- 使用表格结构和内容相似性判断是否应该合并

Usage:
    from nanobot.ingestion.utils.table_merger import cross_page_merger
    
    merged_table = cross_page_merger.merge_tables(tables_from_page_5, tables_from_page_6)
"""

from typing import List, Dict, Any
from loguru import logger


class CrossPageTableMerger:
    """
    跨页表格合并器
    
    功能：
    - 检测表格是否延续到下一页
    - 合并内容相似的表格
    - 处理表格标题和续表标识
    
    Example:
        merger = CrossPageTableMerger()
        
        # 检查是否应该合并
        if merger.should_merge(table_page5, table_page6):
            merged = merger.merge(table_page5, table_page6)
    """
    
    def __init__(self):
        """初始化"""
        pass
    
    def should_merge(self, table1: Dict[str, Any], table2: Dict[str, Any]) -> bool:
        """
        判断两个表格是否应该合并
        
        Args:
            table1: 第一个表格（来自前一页）
            table2: 第二个表格（来自后一页）
            
        Returns:
            bool: 是否应该合并
            
        判断依据：
        1. 表格结构相似（列数相同）
        2. 内容类型相似（都是财务数据）
        3. 表格标题包含"续表"关键词
        """
        # 1. 检查列数是否相同
        if table1.get("num_cols") != table2.get("num_cols"):
            return False
        
        # 2. 检查表格标题
        title1 = table1.get("title", "").lower()
        title2 = table2.get("title", "").lower()
        
        # 如果第二个表格标题包含"续表"、"continued"、"continued"等关键词
        if any(kw in title2 for kw in ["续表", "continued", "(续)", "(continued)"]):
            return True
        
        # 3. 检查内容相似性（表格结构相似）
        # 例如：两个表格都有相同的列标题
        headers1 = table1.get("headers", [])
        headers2 = table2.get("headers", [])
        
        if headers1 and headers2:
            # 如果列标题相同或大部分相同
            similarity = self._calculate_header_similarity(headers1, headers2)
            if similarity > 0.8:  # 80% 以上相似
                return True
        
        return False
    
    def _calculate_header_similarity(self, headers1: List[str], headers2: List[str]) -> float:
        """
        计算两个表格列标题的相似度
        
        Args:
            headers1: 第一个表格的列标题
            headers2: 第二个表格的列标题
            
        Returns:
            float: 相似度（0.0 - 1.0）
        """
        if not headers1 or not headers2:
            return 0.0
        
        # 标准化标题（去除空格、转换为小写）
        h1_normalized = [h.lower().strip() for h in headers1]
        h2_normalized = [h.lower().strip() for h in headers2]
        
        # 计算匹配数量
        matches = 0
        for h1 in h1_normalized:
            if h1 in h2_normalized:
                matches += 1
        
        similarity = matches / len(h1_normalized)
        return similarity
    
    def merge(self, table1: Dict[str, Any], table2: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并两个表格
        
        Args:
            table1: 第一个表格
            table2: 第二个表格
            
        Returns:
            Dict: 合合后的表格
        """
        logger.info(f"🔗 合并跨页表格: Page {table1.get('page_num')} + Page {table2.get('page_num')}")
        
        # 合合数据行
        merged_data = table1.get("data", []) + table2.get("data", [])
        
        # 创建合并后的表格
        merged_table = {
            "page_num": table1.get("page_num"),  # 使用第一个表格的页码
            "num_pages": 2,  # 标记跨页
            "title": table1.get("title", ""),
            "headers": table1.get("headers", []),
            "data": merged_data,
            "num_cols": table1.get("num_cols"),
            "num_rows": len(merged_data),
            "is_merged": True,
            "source_pages": [
                table1.get("page_num"),
                table2.get("page_num")
            ]
        }
        
        logger.debug(f"   合合后: {merged_table['num_rows']} 行, {merged_table['num_cols']} 列")
        
        return merged_table
    
    def merge_tables_batch(
        self,
        tables: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        批量合并表格
        
        Args:
            tables: 按页码排序的表格列表
            
        Returns:
            List[Dict]: 合合后的表格列表
        """
        if not tables:
            return []
        
        # 按页码排序
        sorted_tables = sorted(tables, key=lambda t: t.get("page_num", 0))
        
        merged_tables = []
        current_table = None
        
        for table in sorted_tables:
            if current_table is None:
                current_table = table
            elif self.should_merge(current_table, table):
                # 合合
                current_table = self.merge(current_table, table)
            else:
                # 不合并，保存当前表格
                merged_tables.append(current_table)
                current_table = table
        
        # 保存最后一个表格
        if current_table:
            merged_tables.append(current_table)
        
        logger.info(f"✅ 批量合并完成: {len(tables)} → {len(merged_tables)} 个表格")
        
        return merged_tables


# ===========================================
# 全局实例
# ===========================================

cross_page_merger = CrossPageTableMerger()


# ===========================================
# 便捷函数
# ===========================================

def merge_cross_page_tables(tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    便捷函数：批量合并跨页表格
    
    Args:
        tables: 表格列表
        
    Returns:
        List[Dict]: 合合后的表格列表
    """
    return cross_page_merger.merge_tables_batch(tables)