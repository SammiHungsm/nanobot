"""
Stage 3.5: Context Builder - 構建文檔結構化上下文

職責：
1. 從 LlamaParse items 中提取結構化信息（headings, tables, images）
2. 建立標題層級樹（Section Tree）
3. 為每個表格/圖片建立上下文關係
4. 輸出結構化上下文供 Stage 4 Agent 使用

🌟 核心理念：
- 不要讓 Agent 同時做「理解文檔」和「提取數據」兩件事
- 先理解結構，再提取數據
"""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class Section:
    """文檔章節"""
    page_num: int
    level: int
    title: str
    content: str = ""
    tables: List[Dict] = field(default_factory=list)
    images: List[Dict] = field(default_factory=list)
    subsections: List['Section'] = field(default_factory=list)
    parent_title: Optional[str] = None


@dataclass
class TableContext:
    """表格上下文"""
    page_num: int
    table_id: str
    rows: List[List[str]]
    md: str
    section_title: str
    nearby_text: str = ""
    column_hints: List[str] = field(default_factory=list)


class Stage3_5_ContextBuilder:
    """
    Stage 3.5: 文檔結構化上下文構建器
    
    輸入：LlamaParse raw output (items.pages[])
    輸出：結構化上下文 JSON
    """
    
    @classmethod
    async def build_context(
        cls,
        raw_output: Dict[str, Any],
        candidate_pages: Dict[str, List[int]],
        max_pages: int = 50
    ) -> Dict[str, Any]:
        """
        構建結構化上下文
        
        Args:
            raw_output: LlamaParse raw output
            candidate_pages: Stage 3 路由結果 {data_type: [page_nums]}
            max_pages: 最大處理頁數
            
        Returns:
            {
                "sections": [...],  # 章節樹
                "tables": [...],    # 帶上下文的表格
                "images": [...],    # 帶上下文的圖片
                "content_by_type": {...}  # 按數據類型分組的內容
            }
        """
        logger.info(f"🏗️ Stage 3.5: 構建文檔結構化上下文...")
        
        # 1. 提取所有候選頁面
        all_candidate_pages = set()
        for pages in candidate_pages.values():
            all_candidate_pages.update(pages)
        sorted_pages = sorted(all_candidate_pages)[:max_pages]
        
        logger.info(f"   📄 處理 {len(sorted_pages)} 個候選頁面")
        
        # 2. 提取結構化元素
        items_pages = raw_output.get("items", {}).get("pages", [])
        md_pages = raw_output.get("markdown", {}).get("pages", [])
        
        all_headings = []
        all_tables = []
        all_images = []
        page_contents = {}  # page_num -> content
        
        for page_num in sorted_pages:
            if page_num > len(items_pages):
                continue
            
            # 頁碼從 1 開始，索引從 0 開始
            items_page = items_pages[page_num - 1]
            md_page = md_pages[page_num - 1] if page_num <= len(md_pages) else {}
            
            # 提取 markdown 內容
            page_content = md_page.get("markdown", "")
            page_contents[page_num] = page_content
            
            # 提取結構化元素
            items = items_page.get("items", [])
            
            for item in items:
                item_type = item.get("type", "")
                
                if item_type == "heading":
                    all_headings.append({
                        "page_num": page_num,
                        "level": item.get("level", 1),
                        "title": item.get("value", ""),
                        "md": item.get("md", "")
                    })
                
                elif item_type == "table":
                    all_tables.append({
                        "page_num": page_num,
                        "rows": item.get("rows", []),
                        "csv": item.get("csv", ""),
                        "md": item.get("md", ""),
                        "html": item.get("html", "")
                    })
                
                elif item_type == "image":
                    all_images.append({
                        "page_num": page_num,
                        "bbox": item.get("bbox", [])
                    })
        
        logger.info(f"   📊 提取: {len(all_headings)} headings, {len(all_tables)} tables, {len(all_images)} images")
        
        # 3. 構建章節樹
        sections = cls._build_section_tree(all_headings, page_contents, all_tables, all_images)
        
        # 4. 為表格添加上下文
        tables_with_context = cls._add_table_context(all_tables, all_headings, page_contents)
        
        # 5. 按數據類型分組內容
        content_by_type = cls._group_content_by_type(
            candidate_pages, 
            page_contents, 
            sections, 
            tables_with_context
        )
        
        result = {
            "sections": sections,
            "tables": tables_with_context,
            "images": all_images,
            "content_by_type": content_by_type,
            "stats": {
                "total_pages": len(sorted_pages),
                "total_headings": len(all_headings),
                "total_tables": len(all_tables),
                "total_images": len(all_images),
                "total_sections": len(sections)
            }
        }
        
        logger.info(f"   ✅ 上下文構建完成: {len(sections)} 章節, {len(tables_with_context)} 帶上下文表格")
        
        return result
    
    @classmethod
    def _build_section_tree(
        cls,
        headings: List[Dict],
        page_contents: Dict[int, str],
        tables: List[Dict],
        images: List[Dict]
    ) -> List[Dict]:
        """
        構建章節樹結構
        
        Returns:
            [
                {
                    "title": "Financial Highlights",
                    "level": 1,
                    "page_num": 7,
                    "content": "...",
                    "tables": [...],
                    "images": [...],
                    "subsections": [...]
                }
            ]
        """
        if not headings:
            return []
        
        sections = []
        
        for i, heading in enumerate(headings):
            section = {
                "title": heading["title"],
                "level": heading["level"],
                "page_num": heading["page_num"],
                "md_heading": heading["md"],
                "content": "",
                "tables": [],
                "images": [],
                "subsections": []
            }
            
            # 提取該章節的內容（從當前 heading 到下一個 heading 之間）
            next_heading = headings[i + 1] if i + 1 < len(headings) else None
            
            # 提取內容
            page_num = heading["page_num"]
            content = page_contents.get(page_num, "")
            
            # 簡化：取 heading 之後的內容
            if content and heading["md"] in content:
                start_idx = content.find(heading["md"])
                if start_idx >= 0:
                    section_content = content[start_idx:]
                    if next_heading and next_heading["md"] in section_content:
                        end_idx = section_content.find(next_heading["md"])
                        section_content = section_content[:end_idx]
                    section["content"] = section_content[:2000]  # 限制長度
            
            # 添加該頁的表格
            section["tables"] = [
                t for t in tables 
                if t["page_num"] == page_num
            ]
            
            # 添加該頁的圖片
            section["images"] = [
                img for img in images 
                if img["page_num"] == page_num
            ]
            
            sections.append(section)
        
        return sections
    
    @classmethod
    def _add_table_context(
        cls,
        tables: List[Dict],
        headings: List[Dict],
        page_contents: Dict[int, str]
    ) -> List[Dict]:
        """
        為表格添加上下文（所屬章節、附近文本）
        """
        tables_with_context = []
        
        for table in tables:
            page_num = table["page_num"]
            
            # 找到該頁最近嘅 heading
            page_headings = [h for h in headings if h["page_num"] == page_num]
            section_title = page_headings[0]["title"] if page_headings else "Unknown"
            
            # 提取表格附近嘅文本
            nearby_text = ""
            content = page_contents.get(page_num, "")
            if content and table["md"] and table["md"] in content:
                idx = content.find(table["md"])
                # 取表格前後各 200 字符
                start = max(0, idx - 200)
                end = min(len(content), idx + len(table["md"]) + 200)
                nearby_text = content[start:end]
            
            # 提取列標題提示
            column_hints = []
            if table["rows"]:
                column_hints = table["rows"][0] if table["rows"] else []
            
            tables_with_context.append({
                **table,
                "section_title": section_title,
                "nearby_text": nearby_text,
                "column_hints": column_hints
            })
        
        return tables_with_context
    
    @classmethod
    def _group_content_by_type(
        cls,
        candidate_pages: Dict[str, List[int]],
        page_contents: Dict[int, str],
        sections: List[Dict],
        tables: List[Dict]
    ) -> Dict[str, Dict]:
        """
        按數據類型分組內容
        
        Returns:
            {
                "revenue_breakdown": {
                    "pages": [6, 7],
                    "sections": [...],
                    "tables": [...],
                    "content": "..."
                },
                "financial_metrics": {...}
            }
        """
        result = {}
        
        for data_type, pages in candidate_pages.items():
            # 收集該類型的內容
            type_pages = [p for p in pages if p in page_contents]
            
            # 提取相關章節
            type_sections = [
                s for s in sections 
                if s["page_num"] in type_pages
            ]
            
            # 提取相關表格
            type_tables = [
                t for t in tables 
                if t["page_num"] in type_pages
            ]
            
            # 合併內容
            type_content = "\n\n".join([
                f"=== 第 {p} 頁 ===\n{page_contents[p]}"
                for p in sorted(type_pages)[:20]  # 每類最多 20 頁
            ])
            
            if len(type_content) > 30000:
                type_content = type_content[:30000] + "\n\n... (內容已截斷)"
            
            result[data_type] = {
                "pages": type_pages,
                "sections": type_sections,
                "tables": type_tables,
                "content": type_content
            }
        
        return result
    
    @classmethod
    def format_context_for_llm(cls, context: Dict[str, Any]) -> str:
        """
        格式化上下文供 LLM 使用
        
        輸出結構化提示：
        1. 數據提取任務清單（直接告訴 Agent 要調用哪些 Tools）
        2. 文檔結構概覽
        3. 按數據類型分組的表格內容
        """
        parts = []
        
        # 1. 🌟 核心任務清單（直接告訴 Agent 要做什麼）
        parts.append("""## 🎯 數據提取任務清單

**你必須調用以下 Tools 來提取數據：**

| 數據類型 | Tool 名稱 | 來源頁面 | 表格數量 |
|---------|----------|---------|---------|""")
        
        content_by_type = context.get("content_by_type", {})
        for data_type, type_data in content_by_type.items():
            pages = type_data.get("pages", [])
            tables = type_data.get("tables", [])
            tool_name = {
                "revenue_breakdown": "insert_revenue_breakdown",
                "financial_metrics": "insert_financial_metrics",
                "key_personnel": "insert_key_personnel",
                "shareholding": "insert_shareholding",
                "market_data": "insert_market_data"
            }.get(data_type, f"insert_{data_type}")
            parts.append(f"| {data_type} | {tool_name} | {pages[:5]}... | {len(tables)} |")
        
        parts.append("""
⚠️ **重要：請直接調用上述 Tools，不要只是搜索！**

---
""")
        
        # 2. 文檔結構概覽
        parts.append("## 📋 文檔結構概覽\n")
        for section in context.get("sections", [])[:15]:
            indent = "  " * (section["level"] - 1)
            tables_info = f" ({len(section['tables'])} tables)" if section.get("tables") else ""
            parts.append(f"{indent}- {section['title']} (Page {section['page_num']}){tables_info}")
        
        # 3. 按數據類型分組的表格內容
        parts.append("\n\n## 📊 按數據類型分組的表格內容\n")
        for data_type, type_data in content_by_type.items():
            tables = type_data.get("tables", [])
            if not tables:
                continue
            
            parts.append(f"\n### {data_type.upper()}\n")
            parts.append(f"- 候選頁面: {type_data['pages'][:10]}...")
            parts.append(f"- 表格數量: {len(tables)}\n")
            
            # 顯示表格內容
            for i, tbl in enumerate(tables[:2]):  # 每類最多 2 個表格
                parts.append(f"\n**表格 {i+1} @ Page {tbl['page_num']} - Section: {tbl.get('section_title', 'N/A')}**\n")
                tbl_md = tbl.get("md", "")[:1500]
                if tbl_md:
                    parts.append(f"```\n{tbl_md}\n```\n")
        
        return "\n".join(parts)
