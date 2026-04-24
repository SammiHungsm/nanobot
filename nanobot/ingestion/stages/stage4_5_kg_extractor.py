"""
Stage 4.5: Knowledge Graph Extractor (v4.5 - 實際實現)

功能：
1. 遍歷文本，提取實體關係（人物-公司並購-人事任命）
2. 寫入 entity_relations 表

⚠️ 原本是概念代碼，已完整實現
"""

import json
import asyncio
from typing import Dict, Any, List
from loguru import logger

from nanobot.ingestion.agentic_executor import AgenticExecutor
from nanobot.agent.tools.db_ingestion_tools import InsertEntityRelationTool


class Stage4_5_KGExtractor:
    """知識圖譜提取器 - 從文本中提取實體關係"""
    
    # 關係類型關鍵詞
    RELATION_TYPES = [
        "acquisition", "收購", "併購", "收買",
        "appointment", "任命", "委任", "董事", "高管",
        "resignation", "辭任", "離職", "辭職",
        "shareholder", "股東", "持股",
        "partner", "合作", "合資", " joint venture",
        "subsidiary", "附屬", "子公司", "附屬公司"
    ]
    
    @classmethod
    async def run(
        cls,
        artifacts: List[Dict[str, Any]],
        document_id: int,
        company_name_full: str,
        db_client
    ) -> Dict[str, Any]:
        """
        主入口：提取實體關係
        
        Args:
            artifacts: 所有 artifacts
            document_id: 文檔 ID
            company_name_full: 公司全名（用於解決「本公司」等代名詞）
            db_client: 數據庫客戶端
        
        Returns:
            {"status": "success/failed", "extracted_relations_count": int, ...}
        """
        logger.info(f"🕸️ Stage 4.5: KG Extraction (doc_id={document_id})")
        
        try:
            # 1. 構建 System Prompt
            system_prompt = cls._build_system_prompt(company_name_full)
            
            # 2. 準備文本內容（只取文字段落，排除表格和圖片）
            text_chunks = cls._prepare_text_chunks(artifacts)
            
            if not text_chunks:
                logger.info("   ⚠️ Stage 4.5: 沒有文本內容可處理")
                return {"status": "success", "extracted_relations_count": 0, "details": []}
            
            logger.info(f"   📝 準備處理 {len(text_chunks)} 個文本區塊")
            
            # 3. 構建 Tools Registry
            tools_registry = {
                "insert_entity_relation": InsertEntityRelationTool()
            }
            
            # 4. 遍歷每個文本區塊
            total_relations = 0
            extraction_details = []
            
            for i, chunk in enumerate(text_chunks[:20]):  # 限制最多 20 個區塊
                try:
                    user_message = f"""請從以下文本提取實體關係：

文本內容：
{chunk['content'][:3000]}

頁碼：{chunk.get('page', 'N/A')}

請提取以下類型的關係：
1. 公司並購（誰收購了誰）
2. 人事任命（某人被任命為某公司的高管/董事）
3. 股東結構（主要股東）
4. 合作關係（合資、合作夥伴）
5. 子公司關係（集团下辖子公司）

如果找到關係，請調用 insert_entity_relation Tool。
"""
                    
                    executor = AgenticExecutor(
                        tools_registry=tools_registry,
                        max_iterations=5
                    )
                    
                    result = await executor.run(
                        system_prompt=system_prompt,
                        user_message=user_message,
                        context={
                            "db_client": db_client,
                            "document_id": document_id
                        }
                    )
                    
                    # 統計提取的關係數量
                    tool_calls = result.get("tool_calls", [])
                    entity_relations = [tc for tc in tool_calls if tc["name"] == "insert_entity_relation"]
                    total_relations += len(entity_relations)
                    
                    if entity_relations:
                        extraction_details.append({
                            "chunk_index": i,
                            "page": chunk.get('page', 'N/A'),
                            "relations_found": len(entity_relations)
                        })
                
                except Exception as e:
                    logger.warning(f"   ⚠️ Chunk {i} 處理失敗: {e}")
                    continue
            
            logger.info(f"   ✅ Stage 4.5 完成：提取了 {total_relations} 個關係")
            
            return {
                "status": "success",
                "extracted_relations_count": total_relations,
                "chunks_processed": min(len(text_chunks), 20),
                "details": extraction_details
            }
            
        except Exception as e:
            logger.warning(f"   ⚠️ Stage 4.5 KG 抽取失敗: {e}")
            return {"status": "failed", "error": str(e), "extracted_relations_count": 0}
    
    @staticmethod
    def _build_system_prompt(company_name_full: str) -> str:
        """構建 System Prompt"""
        return f"""你是一個知識圖譜提取專家。

任務：從文本中提取實體關係並寫入 entity_relations 表。

⚠️ 重要提示：
- 文本中的「本公司」、「本集團」、「我們」指的都是『{company_name_full}』
- 如果文本提到「騰訊收購了XXX」，關係類型是 `acquisition`
- 如果文本提到「張三被任命為CEO」，關係類型是 `appointment`
- 所有人物關係都需要 source_entity_type='person'
- 所有公司關係都需要 source_entity_type='company'

可用 Tool：
- insert_entity_relation: 寫入實體關係

Schema:
- source_entity_type: 'person' | 'company'
- source_entity_name: 源實體名稱
- target_entity_type: 'person' | 'company' | 'position'
- target_entity_name: 目標實體名稱
- relation_type: 'acquisition' | 'appointment' | 'resignation' | 'shareholding' | 'partnership' | 'subsidiary'
- event_year: 事件年份（如果提到）

請盡可能多地提取關係！
"""
    
    @staticmethod
    def _prepare_text_chunks(artifacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """準備文本區塊（只取純文字，排除表格和圖片）"""
        text_chunks = []
        
        for artifact in artifacts:
            # 類型為 "text" 或 "text_chunk" 的是純文字
            artifact_type = artifact.get("type", "")
            content = artifact.get("content", "")
            
            if not content:
                continue
            
            # 跳過表格和圖片
            if artifact_type in ["table", "image", "chart"]:
                continue
            
            # 跳過太短的內容
            if len(content) < 100:
                continue
            
            text_chunks.append({
                "content": content,
                "page": artifact.get("page", artifact.get("page_num", "N/A")),
                "type": artifact_type
            })
        
        return text_chunks
