"""
Vanna Training Module - Data-Driven Training for Annual Report Analysis

特性：
1. 從 JSON 檔案載入訓練資料（資料與代碼分離）
2. DDL 白名單驗證（防止 Vanna 學到垃圾表）
3. 支援熱更新（更新 JSON 後重新訓練）
4. 🚀 並行訓練（ThreadPoolExecutor 加速）
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger


class VannaTrainingData:
    """
    Vanna 訓練資料管理器
    
    負責：
    - 從 JSON 檔案載入訓練資料
    - 驗證 SQL 查詢安全性
    - 提供訓練介面
    """
    
    def __init__(self, data_dir: str = None):
        """
        初始化
        
        Args:
            data_dir: 訓練資料目錄路徑
        """
        self.data_dir = Path(data_dir or os.path.join(os.path.dirname(__file__), "data"))
        self._ddl_data = None
        self._documentation_data = None
        self._sql_pairs_data = None
        self._whitelist_data = None
        
        logger.info(f"📁 VannaTrainingData 初始化，資料目錄：{self.data_dir}")
    
    # ===========================================
    # 資料載入方法
    # ===========================================
    
    def load_ddl(self) -> List[str]:
        """
        從 JSON 檔案載入 DDL 訓練資料
        
        Returns:
            List[str]: DDL 語句列表
        """
        if self._ddl_data is not None:
            return self._ddl_data
        
        ddl_path = self.data_dir / "ddl.json"
        
        if not ddl_path.exists():
            logger.warning(f"⚠️ DDL 檔案不存在：{ddl_path}")
            return []
        
        try:
            with open(ddl_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._ddl_data = [
                table["ddl"] 
                for table in data.get("tables", []) 
                if table.get("enabled", True)
            ]
            
            logger.info(f"✅ 載入 {len(self._ddl_data)} 個 DDL")
            return self._ddl_data
            
        except Exception as e:
            logger.error(f"❌ 載入 DDL 失敗：{e}")
            return []
    
    def load_documentation(self) -> List[str]:
        """
        從 JSON 檔案載入 Documentation 訓練資料
        
        Returns:
            List[str]: Documentation 列表
        """
        if self._documentation_data is not None:
            return self._documentation_data
        
        doc_path = self.data_dir / "documentation.json"
        
        if not doc_path.exists():
            logger.warning(f"⚠️ Documentation 檔案不存在：{doc_path}")
            return []
        
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._documentation_data = [
                item["content"] 
                for item in data.get("items", [])
            ]
            
            logger.info(f"✅ 載入 {len(self._documentation_data)} 個 Documentation")
            return self._documentation_data
            
        except Exception as e:
            logger.error(f"❌ 載入 Documentation 失敗：{e}")
            return []
    
    def load_sql_pairs(self) -> List[Dict[str, str]]:
        """
        從 JSON 檔案載入 SQL 訓練配對
        
        Returns:
            List[Dict]: SQL 配對列表 [{question, sql}, ...]
        """
        if self._sql_pairs_data is not None:
            return self._sql_pairs_data
        
        sql_path = self.data_dir / "sql_pairs.json"
        
        if not sql_path.exists():
            logger.warning(f"⚠️ SQL Pairs 檔案不存在：{sql_path}")
            return []
        
        try:
            with open(sql_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._sql_pairs_data = [
                {
                    "question": pair["question"],
                    "sql": pair["sql"]
                }
                for pair in data.get("pairs", [])
            ]
            
            logger.info(f"✅ 載入 {len(self._sql_pairs_data)} 個 SQL Pairs")
            return self._sql_pairs_data
            
        except Exception as e:
            logger.error(f"❌ 載入 SQL Pairs 失敗：{e}")
            return []
    
    def load_whitelist(self) -> Dict[str, Any]:
        """
        載入 DDL 白名單
        
        Returns:
            Dict: 白名單配置
        """
        if self._whitelist_data is not None:
            return self._whitelist_data
        
        whitelist_path = self.data_dir / "ddl_whitelist.json"
        
        if not whitelist_path.exists():
            logger.warning(f"⚠️ Whitelist 檔案不存在：{whitelist_path}")
            return {"allowed_tables": [], "forbidden_keywords": []}
        
        try:
            with open(whitelist_path, 'r', encoding='utf-8') as f:
                self._whitelist_data = json.load(f)
            
            logger.info(f"✅ 載入白名單：{len(self._whitelist_data.get('allowed_tables', []))} 個表")
            return self._whitelist_data
            
        except Exception as e:
            logger.error(f"❌ 載入 Whitelist 失敗：{e}")
            return {"allowed_tables": [], "forbidden_keywords": []}
    
    def get_all_training_data(self) -> Dict[str, Any]:
        """
        獲取所有訓練資料
        
        Returns:
            Dict: {ddl: [...], documentation: [...], sql_examples: [...]}
        """
        return {
            "ddl": self.load_ddl(),
            "documentation": self.load_documentation(),
            "sql_examples": self.load_sql_pairs()
        }
    
    # ===========================================
    # 安全驗證方法
    # ===========================================
    
    def validate_sql(self, sql: str) -> Tuple[bool, str]:
        """
        驗證 SQL 查詢是否安全
        
        Args:
            sql: SQL 查詢語句
            
        Returns:
            Tuple[bool, str]: (是否安全, 原因)
        """
        whitelist = self.load_whitelist()
        
        # 檢查禁用關鍵字
        forbidden_keywords = whitelist.get("forbidden_keywords", [])
        sql_upper = sql.upper()
        
        for keyword in forbidden_keywords:
            if keyword.upper() in sql_upper:
                return False, f"包含禁用關鍵字：{keyword}"
        
        # 檢查表名是否在白名單中
        allowed_tables = [t["name"].lower() for t in whitelist.get("allowed_tables", [])]
        
        # 提取 SQL 中的表名（簡單的正則匹配）
        table_pattern = r'\b(?:FROM|JOIN|INTO|UPDATE)\s+(\w+)'
        tables_in_sql = re.findall(table_pattern, sql, re.IGNORECASE)
        
        for table in tables_in_sql:
            if table.lower() not in allowed_tables:
                return False, f"表名不在白名單中：{table}"
        
        return True, "驗證通過"
    
    def validate_all_sql_pairs(self) -> Dict[str, Any]:
        """
        驗證所有 SQL 配對
        
        Returns:
            Dict: 驗證結果統計
        """
        sql_pairs = self.load_sql_pairs()
        
        results = {
            "total": len(sql_pairs),
            "valid": 0,
            "invalid": 0,
            "details": []
        }
        
        for pair in sql_pairs:
            is_valid, reason = self.validate_sql(pair["sql"])
            
            if is_valid:
                results["valid"] += 1
            else:
                results["invalid"] += 1
                results["details"].append({
                    "id": pair.get("id", "unknown"),
                    "question": pair["question"][:50] + "...",
                    "reason": reason
                })
        
        logger.info(f"📊 SQL 驗證完成：{results['valid']}/{results['total']} 通過")
        
        if results["invalid"] > 0:
            logger.warning(f"⚠️ {results['invalid']} 個 SQL 未通過驗證")
            for detail in results["details"]:
                logger.warning(f"   - {detail['id']}: {detail['reason']}")
        
        return results
    
    # ===========================================
    # 訓練方法
    # ===========================================
    
    def _train_single_ddl(self, vn, ddl: str) -> Tuple[bool, str]:
        """訓練單個 DDL（用於並行執行）"""
        try:
            vn.train(ddl=ddl)
            return True, ""
        except Exception as e:
            return False, str(e)
    
    def _train_single_doc(self, vn, doc: str) -> Tuple[bool, str]:
        """訓練單個 Documentation（用於並行執行）"""
        try:
            vn.train(documentation=doc)
            return True, ""
        except Exception as e:
            return False, str(e)
    
    def _train_single_sql(self, vn, pair: dict, validate: bool) -> Tuple[bool, str, str]:
        """訓練單個 SQL（用於並行執行）"""
        try:
            if validate:
                is_valid, reason = self.validate_sql(pair["sql"])
                if not is_valid:
                    return False, reason, pair['question'][:30]
            
            vn.train(
                question=pair["question"],
                sql=pair["sql"]
            )
            return True, "", pair['question'][:50]
        except Exception as e:
            return False, str(e), pair.get('question', 'unknown')[:30]
    
    def train_vanna(self, vn, validate: bool = True, max_workers: int = 4) -> Dict[str, Any]:
        """
        使用所有訓練資料訓練 Vanna（並行版本）
        
        Args:
            vn: Vanna 實例
            validate: 是否在訓練前驗證 SQL
            max_workers: 並行線程數
            
        Returns:
            Dict: 訓練統計
        """
        logger.info("🧠 開始訓練 Vanna (並行模式)...")
        
        stats = {
            "ddl_trained": 0,
            "documentation_trained": 0,
            "sql_trained": 0,
            "errors": []
        }
        
        # 1. 驗證 SQL 配對
        if validate:
            validation = self.validate_all_sql_pairs()
            if validation["invalid"] > 0:
                logger.warning(f"⚠️ 發現 {validation['invalid']} 個無效 SQL，請檢查白名單配置")
        
        # 2. 並行訓練 DDL
        logger.info("\n📝 訓練 DDL...")
        ddl_list = self.load_ddl()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._train_single_ddl, vn, ddl): ddl for ddl in ddl_list}
            for future in as_completed(futures):
                success, error = future.result()
                if success:
                    stats["ddl_trained"] += 1
                else:
                    stats["errors"].append(f"DDL: {error}")
        logger.info(f"   ✅ DDL 訓練完成: {stats['ddl_trained']}")
        
        # 3. 並行訓練 Documentation
        logger.info("\n📚 訓練 Documentation...")
        doc_list = self.load_documentation()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._train_single_doc, vn, doc): doc for doc in doc_list}
            for future in as_completed(futures):
                success, error = future.result()
                if success:
                    stats["documentation_trained"] += 1
                else:
                    stats["errors"].append(f"Documentation: {error}")
        logger.info(f"   ✅ Documentation 訓練完成: {stats['documentation_trained']}")
        
        # 4. 並行訓練 SQL Examples
        logger.info("\n💾 訓練 SQL Examples...")
        sql_pairs = self.load_sql_pairs()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._train_single_sql, vn, pair, validate): pair for pair in sql_pairs}
            for future in as_completed(futures):
                success, error, question = future.result()
                if success:
                    stats["sql_trained"] += 1
                    logger.debug(f"   ✅ SQL trained: {question}")
                elif error:
                    logger.warning(f"   ⚠️ 跳過/失敗: {question}... ({error})")
        logger.info(f"   ✅ SQL 訓練完成: {stats['sql_trained']}")
        
        logger.info(f"\n✅ Vanna 訓練完成！")
        logger.info(f"   DDL: {stats['ddl_trained']}")
        logger.info(f"   Documentation: {stats['documentation_trained']}")
        logger.info(f"   SQL: {stats['sql_trained']}")
        
        if stats["errors"]:
            logger.warning(f"   錯誤: {len(stats['errors'])}")
        
        return stats
    
    def reload(self):
        """重新載入所有訓練資料（用於熱更新）"""
        self._ddl_data = None
        self._documentation_data = None
        self._sql_pairs_data = None
        self._whitelist_data = None
        
        logger.info("🔄 已清除快取，下次載入將重新讀取 JSON 檔案")
        
        return self.get_all_training_data()


# ===========================================
# 向後兼容的函數（保持舊 API 可用）
# ===========================================

# 全域實例
_training_data_instance = None

def _get_training_data_instance():
    """獲取全域訓練資料實例"""
    global _training_data_instance
    if _training_data_instance is None:
        _training_data_instance = VannaTrainingData()
    return _training_data_instance


def get_all_training_data():
    """返回所有訓練資料（向後兼容）"""
    return _get_training_data_instance().get_all_training_data()


def train_vanna(vn):
    """使用所有訓練資料訓練 Vanna（向後兼容）"""
    return _get_training_data_instance().train_vanna(vn)


# ===========================================
# CLI 介面
# ===========================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Vanna Training Data Manager")
    parser.add_argument("--validate", action="store_true", help="驗證所有 SQL 配對")
    parser.add_argument("--stats", action="store_true", help="顯示訓練資料統計")
    parser.add_argument("--data-dir", type=str, help="訓練資料目錄路徑")
    
    args = parser.parse_args()
    
    training_data = VannaTrainingData(args.data_dir)
    
    if args.validate:
        print("\n🔍 驗證 SQL 配對...")
        validation = training_data.validate_all_sql_pairs()
        print(f"\n結果：{validation['valid']}/{validation['total']} 通過驗證")
        
        if validation["invalid"] > 0:
            print("\n無效 SQL 列表：")
            for detail in validation["details"]:
                print(f"  - {detail['id']}: {detail['reason']}")
    
    if args.stats or not (args.validate or args.stats):
        # 預設顯示統計
        print("\n📊 訓練資料統計：")
        print(f"  DDL: {len(training_data.load_ddl())} 個")
        print(f"  Documentation: {len(training_data.load_documentation())} 個")
        print(f"  SQL Pairs: {len(training_data.load_sql_pairs())} 個")
        print(f"  允許的表: {len(training_data.load_whitelist().get('allowed_tables', []))} 個")