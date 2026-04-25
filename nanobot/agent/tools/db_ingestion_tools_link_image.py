"""
LinkImageTextTool - LLM-powered Image-Text Linker (v1.0)

解決方案：使用 LLM 理解語意，不只是 Regex 匹配

功能：
1. 讀取文檔中所有圖片 artifacts
2. 讀取文檔中所有文字 chunks
3. 用 LLM 理解圖文關係（including 「如圖所示」、「見下圖」等）
4. 寫入 artifact_relations 表

好處：
- 理解「如圖所示」、「as shown in chart」等自然語言
- 理解同一意思的不同表達方式
- 比 Regex 更智能、更準確
"""

import json
from typing import Any
from loguru import logger
from nanobot.agent.tools.base import Tool


class LinkImageTextTool(Tool):
    """
    [Tool] LLM 圖文匹配 - 取代傳統 Regex 匹配
    
    適用場景：
    - 圖片沒有明確的 "Figure X" 引用
    - 使用「如圖所示」、「見下圖」、「as shown below」等表達
    - 圖片和文字不在同一頁但有語意關聯
    
    使用方式：
    - Agent 在 Planning Phase 可以 call 呢個 tool
    - 一次過處理整個文檔的圖文匹配
    """
    
    @property
    def name(self) -> str:
        return "link_image_text"
    
    @property
    def description(self) -> str:
        return """
        將圖片和文字段落進行智能匹配，建立跨模態關聯。

        使用場景：
        - 圖片沒有明確的 Figure/Table 引用
        - 使用「如圖所示」、「見下圖」、「as shown in the chart」等表達
        - logo、示意圖等裝飾性圖片
        - 圖表和其解釋文字在不同位置

        輸入：文檔中所有圖片和文字（自動從 DB 讀取）
        輸出：圖文匹配關係，寫入 artifact_relations 表
        """
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "integer",
                    "description": "文檔 ID（可選，如果唔記得會自動搵最近嘅）"
                },
                "match_strategy": {
                    "type": "string",
                    "enum": ["semantic", "position", "mixed"],
                    "description": "匹配策略：semantic(語意理解) / position(同頁優先) / mixed(混合)",
                    "default": "semantic"
                }
            },
            "required": []
        }
    
    async def execute(
        self,
        document_id: int = None,
        match_strategy: str = "semantic",
        context: dict = None
    ) -> str:
        """
        執行 LLM 圖文匹配
        
        Args:
            document_id: 文檔 ID
            match_strategy: 匹配策略 (semantic/position/mixed)
            context: 上下文（包含 db_client 等）
        
        Returns:
            JSON 結果，包含匹配數量
        """
        try:
            # 🌟 v4.16: 優先使用 context 中的 db_client
            if context and context.get("db_client"):
                db_client = context["db_client"]
            else:
                from nanobot.ingestion.repository.db_client import DBClient
                db_client = DBClient.get_instance()
            
            if not document_id:
                document_id = context.get("document_id") if context else None
            
            if not document_id:
                # 嘗試從最近處理的 document 獲取 document_id
                try:
                    async with db_client.connection() as conn:
                        row = await conn.fetchrow(
                            "SELECT id FROM documents ORDER BY created_at DESC LIMIT 1"
                        )
                        if row:
                            document_id = row["id"]
                except Exception as e:
                    logger.warning(f"⚠️ Could not fetch latest document_id: {e}")
            
            if not document_id:
                return json.dumps({
                    "success": False,
                    "error": "document_id is required"
                }, ensure_ascii=False)
            
            # ===== 讀取所有圖片 artifacts =====
            async with db_client.connection() as conn:
                image_rows = await conn.fetch("""
                    SELECT id, name, type, page_num, content, metadata
                    FROM raw_artifacts
                    WHERE document_id = $1 AND type IN ('image', 'chart', 'vision_analysis')
                    ORDER BY page_num, id
                """, document_id)
            
            # ===== 讀取所有文字 chunks =====
            async with db_client.connection() as conn:
                text_rows = await conn.fetch("""
                    SELECT id, type, page_num, content, section_title
                    FROM raw_artifacts
                    WHERE document_id = $1 AND type IN ('text', 'text_chunk')
                    ORDER BY page_num, id
                """, document_id)
            
            if not image_rows:
                return json.dumps({
                    "success": True,
                    "message": "No images found in document",
                    "links_created": 0
                }, ensure_ascii=False)
            
            if not text_rows:
                return json.dumps({
                    "success": True,
                    "message": "No text chunks found in document",
                    "links_created": 0
                }, ensure_ascii=False)
            
            logger.info(f"   🔗 LLM Image-Text Linking: {len(image_rows)} images, {len(text_rows)} text chunks")
            
            # ===== 構建 LLM Prompt =====
            images_info = []
            for img in image_rows[:30]:  # 限制最多 30 張圖片
                metadata = img.get("metadata") or {}
                title = metadata.get("title", img.get("content", "")[:100] if img.get("content") else "No title")[:200]
                img_type = metadata.get("type", img.get("type", "unknown"))
                images_info.append({
                    "image_id": img["id"],
                    "page": img["page_num"],
                    "type": img_type,
                    "title": title
                })
            
            texts_info = []
            for txt in text_rows[:50]:  # 限制最多 50 個文字塊
                content_preview = (txt.get("content", "") or "")[:300]
                texts_info.append({
                    "text_id": txt["id"],
                    "page": txt["page_num"],
                    "section": txt.get("section_title", "Unknown"),
                    "preview": content_preview
                })
            
            # ===== LLM 匹配 =====
            from nanobot.core.llm_core import chat
            
            prompt = f"""你係圖文匹配專家。

任務：
分析以下圖片和文字，搵出佢哋之間的語意關聯。

**圖片列表 ({len(images_info)} 張)：**
{json.dumps(images_info, ensure_ascii=False, indent=2)}

**文字列表 ({len(texts_info)} 段)：**
{json.dumps(texts_info, ensure_ascii=False, indent=2)}

**匹配規則：**

1. **明確引用**：
   - "Figure 1", "如圖1所示", "見下圖" → 呢段文字描述緊附近的圖
   - "Table 2", "如表2所示" → 呢段描述緊附近既表格

2. **語意關聯**（即使冇明確引用）：
   - 如果一段文字提到「如圖所示」、「如圖」→ 佢描述緊下一張/上一張圖
   - 如果圖片係 chart/graph → 搵解釋呢個 chart 的段落
   - 如果文字提到某個數據（"如圖3顯示"）→ 匹配到圖3

3. **位置優先**（mixed 模式）：
   - 同一頁的圖片和文字優先匹配
   - 但如果語意明確指向其他頁，都算

4. **裝飾圖片**：
   - logo、icon、背景圖 → 通常匹配 page 1 或 company description
   - 如果文字提到公司名 + 圖片係 logo → 匹配

5. **唔好匹配**：
   - 完全無關的圖片和文字
   - 一張圖片匹配多個文字段落（只揀最相關的一個）

**輸出格式：**
```json
{{
  "links": [
    {{
      "image_id": 123,
      "text_chunk_id": 456,
      "confidence": 0.95,
      "reason": "文字提到「如圖3所示」，匹配圖3"
    }}
  ]
}}
```

請分析並輸出 JSON：
"""
            
            response = await chat(prompt=prompt, temperature=0.1, max_tokens=4000)
            content = response.strip() if isinstance(response, str) else str(response)
            
            # 解析 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            links = result.get("links", [])
            
            logger.info(f"   🤖 LLM matched {len(links)} image-text pairs")
            
            # ===== 寫入 artifact_relations =====
            links_created = 0
            async with db_client.connection() as conn:
                for link in links:
                    try:
                        await conn.execute("""
                            INSERT INTO artifact_relations
                            (source_id, target_id, relation_type, page_num, extraction_method, confidence, context)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT DO NOTHING
                        """,
                            link["image_id"],
                            link["text_chunk_id"],
                            "semantic_match",
                            images_info[0].get("page") if images_info else None,
                            "llm_semantic",
                            link.get("confidence", 0.8),
                            link.get("reason", "")
                        )
                        links_created += 1
                    except Exception as e:
                        logger.debug(f"Insert link error: {e}")
            
            logger.info(f"   ✅ Created {links_created} image-text links")
            
            return json.dumps({
                "success": True,
                "message": f"LLM matched {len(links)} pairs, {links_created} written to DB",
                "images_processed": len(images_info),
                "texts_processed": len(texts_info),
                "links_created": links_created
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"LinkImageTextTool error: {e}")
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
