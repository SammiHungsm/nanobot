# stage4_5_kg_extractor.py 概念代碼
class Stage4_5_KGExtractor:
    @staticmethod
    async def run(artifacts, document_id, company_name_full, db_client):
        logger.info("🕸️ Stage 4.5: 啟動專屬 KG Extraction Skill...")
        
        # 1. 載入上面設計好的 Hard Guide Prompt
        system_prompt = load_skill_prompt("kg_extractor")
        
        # 2. 將全名傳入，幫助 LLM 解決「本公司」的代名詞問題
        system_prompt += f"\n\n⚠️ 提示：文本中的「本公司」、「本集團」指的都是『{company_name_full}』。"
        
        # 3. 遍歷文本（建議按章節或每 3-5 頁為一個 Chunk 處理，避免 Context 遺忘）
        for chunk in chunk_artifacts(artifacts):
            user_message = f"請提取以下文本的關係：\n\n{chunk}"
            
            # 4. 使用專門的 AgenticExecutor，只給它 1 個 Tool
            executor = AgenticExecutor(
                tools_registry={"insert_entity_relation": InsertEntityRelationTool},
                max_iterations=10
            )
            
            await executor.run(system_prompt, user_message, context={"db_client": db_client})