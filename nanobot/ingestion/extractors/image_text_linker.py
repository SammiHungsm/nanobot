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
                    SELECT artifact_id, content, metadata, page_num
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
                    # 🌟 v4.4: 確保 content 是字符串
                    content = img.get('content') or ''
                    if isinstance(content, dict):
                        content = str(content)
                    
                    # 嘗試從 content 提取編號 (因為 LlamaParse 通常將字塞喺 content)
                    content_match = figure_pattern.search(content)
                    if content_match:
                        fig_num = content_match.group(1).lower()
                        image_lookup[fig_num] = img_id
                        continue
                    
                    # 嘗試從 metadata 提取
                    meta = img.get('metadata') or {}
                    if isinstance(meta, str):
                        try:
                            import json
                            meta = json.loads(meta)
                        except:
                            meta = {}
                    if meta.get('figure_number'):
                        image_lookup[str(meta['figure_number']).lower()] = img_id

                logger.info(f"   📊 成功識別 {len(image_lookup)} 張有編號的圖片")

                # 3. 掃描文字，尋找提及這些 Figure 的段落
                # 🌟 v4.4: 新增 Markdown 圖片引用模式
                md_img_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
                
                for chunk in text_chunks:
                    chunk_text = chunk['content'] or ''
                    chunk_id = chunk['artifact_id']
                    
                    # 策略 1: 傳統 Figure 引用
                    mentioned_figs = figure_pattern.findall(chunk_text)
                    for fig in mentioned_figs:
                        fig_lower = fig.lower()
                        if fig_lower in image_lookup:
                            target_image_id = image_lookup[fig_lower]
                            logger.debug(f"   🔗 發現關聯: 圖片 {target_image_id} <- 文字 {chunk_id} (提及 {fig})")
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
                    
                    # 策略 2: 🌟 v4.4 Markdown 圖片引用
                    md_images = md_img_pattern.findall(chunk_text)
                    for alt_text, img_filename in md_images:
                        # 嘗試根據文件名匹配 image artifact
                        img_filename_lower = img_filename.lower()
                        for img in images:
                            img_content = img.get('content', '')
                            if isinstance(img_content, str) and img_filename_lower in img_content.lower():
                                target_image_id = img['artifact_id']
                                logger.debug(f"   🔗 發現 Markdown 關聯: 圖片 {target_image_id} <- 文字 {chunk_id} ({img_filename})")
                                try:
                                    await conn.execute("""
                                        INSERT INTO artifact_relations 
                                        (document_id, source_artifact_id, target_artifact_id, relation_type, confidence_score, extraction_method)
                                        VALUES ($1, $2, $3, 'referenced_by', 0.95, 'markdown_linker')
                                        ON CONFLICT (source_artifact_id, target_artifact_id) DO NOTHING
                                    """, document_id, target_image_id, chunk_id)
                                    links_created += 1
                                except Exception as insert_err:
                                    logger.warning(f"   ⚠️ 插入 Markdown 關聯失敗: {insert_err}")
                                break  # 找到匹配後跳出
                
                logger.info(f"   ✅ 共成功建立 {links_created} 條圖文關聯")
                
                # 🌟 v4.4 策略 3: 基於頁面位置的關聯 (同頁圖片與文字)
                # 如果前兩種策略都沒有建立關聯，則為同頁的圖片和文字建立關聯
                if links_created == 0:
                    logger.info(f"   📍 嘗試基於頁面位置建立關聯...")
                    
                    try:
                        # 獲取每張圖片所在的頁碼
                        image_pages = {}
                        for img in images:
                            img_id = img['artifact_id']
                            page_num = img.get('page_num') or img.get('page')
                            logger.debug(f"      圖片 {img_id} 在第 {page_num} 頁")
                            if page_num:
                                if page_num not in image_pages:
                                    image_pages[page_num] = []
                                image_pages[page_num].append(img_id)
                        
                        logger.info(f"      圖片頁碼分布: {image_pages}")
                        
                        # 獲取每個文字塊所在的頁碼
                        text_pages = {}
                        for chunk in text_chunks:
                            chunk_id = chunk['artifact_id']
                            page_num = chunk.get('page_num')
                            logger.debug(f"      文字 {chunk_id} 在第 {page_num} 頁")
                            if page_num:
                                if page_num not in text_pages:
                                    text_pages[page_num] = []
                                text_pages[page_num].append(chunk_id)
                        
                        logger.info(f"      文字頁碼分布: {text_pages}")
                        
                        # 為同頁的圖片和文字建立關聯
                        for page_num, img_ids in image_pages.items():
                            if page_num in text_pages:
                                chunk_ids = text_pages[page_num]
                                for img_id in img_ids:
                                    for chunk_id in chunk_ids:
                                        try:
                                            await conn.execute("""
                                                INSERT INTO artifact_relations 
                                                (document_id, source_artifact_id, target_artifact_id, relation_type, confidence_score, extraction_method)
                                                VALUES ($1, $2, $3, 'same_page', 0.7, 'page_position')
                                                ON CONFLICT (source_artifact_id, target_artifact_id) DO NOTHING
                                            """, document_id, img_id, chunk_id)
                                            links_created += 1
                                            logger.debug(f"      建立關聯: {img_id} -> {chunk_id}")
                                        except Exception as insert_err:
                                            logger.warning(f"   ⚠️ 插入同頁關聯失敗: {insert_err}")
                        
                        if links_created > 0:
                            logger.info(f"   ✅ 基於頁面位置建立了 {links_created} 條關聯")
                    except Exception as e:
                        logger.error(f"   ❌ 策略 3 執行失敗: {e}")

                return links_created
        except Exception as e:
            logger.error(f"❌ 圖文關聯建立失敗: {e}")
            return 0