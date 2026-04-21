import re
from loguru import logger
import asyncpg

class ImageTextLinker:
    """
    專門負責將 PDF 中的圖片 (Chart/Image) 與跨頁的文字解釋進行關聯，
    並寫入 artifact_relations 表中。
    """
    def __init__(self, db_client):
        self.db = db_client

    async def link_image_and_text_context(self, document_id: int) -> int:
        links_created = 0
        try:
            async with self.db.connection() as conn:
                # 1. 找出這份文件所有的圖片/圖表
                images = await conn.fetch("""
                    SELECT artifact_id, content, metadata
                    FROM raw_artifacts
                    WHERE document_id = $1 AND artifact_type IN ('image', 'chart')
                """, document_id)

                if not images:
                    logger.info(f"   ℹ️ 文檔 {document_id} 沒有發現圖片/圖表，跳過圖文關聯")
                    return 0

                # 2. 找出這份文件所有的文字 Chunk
                text_chunks = await conn.fetch("""
                    SELECT artifact_id, content, page_num
                    FROM raw_artifacts
                    WHERE document_id = $1 AND artifact_type IN ('text', 'text_chunk')
                """, document_id)
                
                if not text_chunks:
                    logger.info(f"   ℹ️ 文檔 {document_id} 沒有發現文字 Chunk，跳過圖文關聯")
                    return 0

                # 提取圖片的 Figure 編號 (從 metadata 或 OCR content)
                figure_pattern = re.compile(r'(?i)(?:Figure|圖|Table|表)\s*([\w\.\-]+)')
                
                image_lookup = {}
                for img in images:
                    img_id = img['artifact_id']
                    # 嘗試從 content 提取編號 (因為 LlamaParse 通常將字塞喺 content)
                    content_match = figure_pattern.search(img.get('content', ''))
                    if content_match:
                        fig_num = content_match.group(1).lower()
                        image_lookup[fig_num] = img_id
                        continue
                    
                    # 嘗試從 metadata 提取
                    meta = img.get('metadata') or {}
                    if meta.get('figure_number'):
                        image_lookup[str(meta['figure_number']).lower()] = img_id

                logger.info(f"   📊 成功識別 {len(image_lookup)} 張有編號的圖片")

                # 3. 掃描文字，尋找提及這些 Figure 的段落
                for chunk in text_chunks:
                    chunk_text = chunk['content'] or ''
                    chunk_id = chunk['artifact_id']
                    
                    # 找出這段文字提到了哪些 Figure
                    mentioned_figs = figure_pattern.findall(chunk_text)
                    for fig in mentioned_figs:
                        fig_lower = fig.lower()
                        if fig_lower in image_lookup:
                            target_image_id = image_lookup[fig_lower]
                            logger.debug(f"   🔗 發現關聯: 圖片 {target_image_id} <- 文字 {chunk_id} (提及 {fig})")
                            
                            # 4. 寫入 artifact_relations
                            # 🌟 v1.3: 補充 document_id（必填字段）
                            try:
                                await conn.execute("""
                                    INSERT INTO artifact_relations 
                                    (document_id, source_artifact_id, target_artifact_id, relation_type, confidence_score, extraction_method)
                                    VALUES ($1, $2, $3, 'explained_by', 0.9, 'regex_linker')
                                    ON CONFLICT (source_artifact_id, target_artifact_id) DO NOTHING
                                """, document_id, target_image_id, chunk_id)
                                links_created += 1
                            except Exception as insert_err:
                                logger.warning(f"   ⚠️ 插入關聯失敗 {target_image_id} <- {chunk_id}: {insert_err}")
                
                logger.info(f"   ✅ 共成功建立 {links_created} 條圖文關聯")

                return links_created
        except Exception as e:
            logger.error(f"❌ 圖文關聯建立失敗: {e}")
            return 0