"""
Stage 6: Validator & Normalizer (v4.0)

职责：
- 数学验证（百分比总和、财务公式）
- 数值标准化（单位换算、汇率转换）
- 实体对齐（公司名称、财务指标）
- 标记需要人工审核的数据

🌟 v4.0: 简化后的 Stage 6（原 Stage 7）
🌟 防止 LLM 幻觉，确保数据质量
"""

from typing import Dict, Any, List, Tuple, Optional
from loguru import logger

from nanobot.ingestion.validators.math_rules import (
    validate_revenue_percentage,
    validate_financial_amount,
    validate_json_structure,
    ValidationResult
)
from nanobot.ingestion.extractors.value_normalizer import (
    ValueNormalizer,
    normalize_financial_value
)
from nanobot.ingestion.extractors.entity_resolver import (
    EntityResolver,
    resolve_metric_name,
    resolve_region_name
)


class Stage6Validator:
    """Stage 6: Validator & Normalizer"""
    
    def __init__(self, db_client: Any = None):
        """
        初始化
        
        Args:
            db_client: DB 客户端（用于更新审核状态）
        """
        self.db = db_client
        self.value_normalizer = ValueNormalizer()
        self.entity_resolver = EntityResolver(db_client=db_client)
    
    async def validate_revenue_breakdown(
        self,
        revenue_data: Dict[str, Any],
        company_id: int,
        year: int,
        document_id: int
    ) -> Dict[str, Any]:
        """
        验证 Revenue Breakdown 数据
        
        🌟 检查项：
        1. 百分比总和是否接近 100%
        2. 数值格式是否正确
        3. 实体名称是否标准化
        
        Args:
            revenue_data: 提取的收入分解数据
            company_id: 公司 ID
            year: 年份
            document_id: 文档 ID
            
        Returns:
            Dict: {"is_valid", "total_percentage", "normalized_data", "needs_review"}
        """
        logger.info(f"🔍 Stage 6: 验证 Revenue Breakdown...")
        
        result = {
            "is_valid": True,
            "total_percentage": 0.0,
            "normalized_data": {},
            "needs_review": False,
            "validation_errors": []
        }
        
        # 1. 验证百分比总和
        is_valid_sum, total_pct = validate_revenue_percentage(revenue_data)
        result["total_percentage"] = total_pct
        
        if not is_valid_sum:
            result["is_valid"] = False
            result["validation_errors"].append(
                f"百分比总和 {total_pct}% 不等于 100%"
            )
            result["needs_review"] = True
        
        # 2. 标准化每个分类
        normalized_data = {}
        
        for segment_name, data in revenue_data.items():
            # 🌟 实体对齐：标准化地区名称
            canonical_en, canonical_zh = resolve_region_name(segment_name)
            
            # 🌟 数值标准化：换算单位
            percentage = data.get("percentage")
            amount = data.get("amount")
            unit = data.get("unit", "")
            
            # 验证百分比
            if percentage is not None:
                if not validate_financial_amount(percentage, min_value=0, max_value=100):
                    result["is_valid"] = False
                    result["validation_errors"].append(
                        f"分类 '{segment_name}' 百分比 {percentage} 不在 [0, 100] 范围内"
                    )
                    result["needs_review"] = True
            
            # 标准化金额
            standardized_amount = None
            if amount is not None and unit:
                try:
                    standardized_amount, currency = normalize_financial_value(
                        raw_value=amount,
                        unit_str=unit,
                        target_currency='HKD'
                    )
                except Exception as e:
                    logger.warning(f"   ⚠️ 数值标准化失败: {e}")
                    result["needs_review"] = True
            
            normalized_data[canonical_en] = {
                "original_name": segment_name,
                "canonical_zh": canonical_zh,
                "percentage": percentage,
                "amount": amount,
                "standardized_amount": float(standardized_amount) if standardized_amount else None,
                "unit": unit,
                "currency": currency if standardized_amount else None
            }
        
        result["normalized_data"] = normalized_data
        
        # 3. 如果需要审核，创建审核记录
        if result["needs_review"] and self.db:
            try:
                await self.db.create_review_record(
                    document_id=document_id,
                    review_type="data_quality",
                    priority=5,
                    issue_description=f"Revenue Breakdown 验证失败: {', '.join(result['validation_errors'])}"
                )
                logger.info(f"   📋 已创建审核记录 (document_id={document_id})")
            except Exception as e:
                logger.warning(f"   ⚠️ 创建审核记录失败: {e}")
        
        logger.info(f"✅ Stage 6 Revenue 验证完成: valid={result['is_valid']}, total_pct={total_pct}%")
        
        return result
    
    async def validate_financial_metrics(
        self,
        metrics_data: List[Dict[str, Any]],
        company_id: int,
        year: int,
        document_id: int
    ) -> Dict[str, Any]:
        """
        验证 Financial Metrics 数据
        
        🌟 检查项：
        1. 数值是否在合理范围
        2. 财务指标名称是否标准化
        3. 单位是否正确换算
        
        Args:
            metrics_data: 提取的财务指标列表
            company_id: 公司 ID
            year: 年份
            document_id: 文档 ID
            
        Returns:
            Dict: {"is_valid", "normalized_metrics", "needs_review"}
        """
        logger.info(f"🔍 Stage 6: 验证 Financial Metrics...")
        
        result = {
            "is_valid": True,
            "normalized_metrics": [],
            "needs_review": False,
            "validation_errors": []
        }
        
        for metric in metrics_data:
            metric_name = metric.get("metric_name")
            value = metric.get("value")
            unit = metric.get("unit", "")
            
            # 🌟 实体对齐：标准化指标名称
            canonical_en, canonical_zh = resolve_metric_name(metric_name)
            
            # 🌟 数值标准化
            standardized_value = None
            currency = None
            
            if value is not None and unit:
                try:
                    standardized_value, currency = normalize_financial_value(
                        raw_value=value,
                        unit_str=unit,
                        target_currency='HKD'
                    )
                except Exception as e:
                    logger.warning(f"   ⚠️ 数值标准化失败 ({metric_name}): {e}")
                    result["needs_review"] = True
            
            # 验证数值范围（根据指标类型）
            if value is not None:
                # 收入类指标应该 > 0
                if "revenue" in canonical_en.lower() or "income" in canonical_en.lower():
                    if value <= 0:
                        result["is_valid"] = False
                        result["validation_errors"].append(
                            f"{metric_name} = {value} (应该 > 0)"
                        )
                        result["needs_review"] = True
            
            normalized_metric = {
                "original_name": metric_name,
                "canonical_en": canonical_en,
                "canonical_zh": canonical_zh,
                "value": value,
                "standardized_value": float(standardized_value) if standardized_value else None,
                "unit": unit,
                "currency": currency
            }
            
            result["normalized_metrics"].append(normalized_metric)
        
        logger.info(f"✅ Stage 6 Metrics 验证完成: valid={result['is_valid']}, count={len(metrics_data)}")
        
        return result
    
    async def validate_key_personnel(
        self,
        personnel_data: List[Dict[str, Any]],
        company_id: int,
        document_id: int
    ) -> Dict[str, Any]:
        """
        验证 Key Personnel 数据
        
        🌟 检查项：
        1. 名称是否为空
        2. Board Role 是否在预设范围内
        
        Args:
            personnel_data: 提取的人员列表
            company_id: 公司 ID
            document_id: 文档 ID
            
        Returns:
            Dict: {"is_valid", "normalized_personnel", "needs_review"}
        """
        logger.info(f"🔍 Stage 6: 验证 Key Personnel...")
        
        result = {
            "is_valid": True,
            "normalized_personnel": [],
            "needs_review": False,
            "validation_errors": []
        }
        
        valid_board_roles = [
            "Executive",
            "Non-Executive",
            "Independent Non-Executive",
            "Executive Director",
            "Non-Executive Director",
            "Independent Non-Executive Director"
        ]
        
        for person in personnel_data:
            name_en = person.get("name_en")
            name_zh = person.get("name_zh")
            position = person.get("position_title_en")
            board_role = person.get("board_role")
            
            # 验证名称
            if not name_en and not name_zh:
                result["is_valid"] = False
                result["validation_errors"].append("缺少人员名称")
                result["needs_review"] = True
                continue
            
            # 验证 Board Role
            if board_role and board_role not in valid_board_roles:
                logger.warning(f"   ⚠️ 未知的 Board Role: {board_role}")
                # 不标记为 invalid，只记录
            
            normalized_person = {
                "name_en": name_en,
                "name_zh": name_zh,
                "position_title_en": position,
                "board_role": board_role
            }
            
            result["normalized_personnel"].append(normalized_person)
        
        logger.info(f"✅ Stage 6 Personnel 验证完成: valid={result['is_valid']}, count={len(personnel_data)}")
        
        return result
    
    async def run(
        self,
        extraction_result: Dict[str, Any],
        company_id: int,
        year: int,
        document_id: int
    ) -> Dict[str, Any]:
        """
        🌟 执行完整验证
        
        Args:
            extraction_result: Stage 4/5 提取的结果
            company_id: 公司 ID
            year: 年份
            document_id: 文档 ID
            
        Returns:
            Dict: {"revenue_validation", "metrics_validation", "personnel_validation", "overall_valid"}
        """
        logger.info(f"🎯 Stage 6: Validator & Normalizer 开始...")
        
        result = {
            "revenue_validation": None,
            "metrics_validation": None,
            "personnel_validation": None,
            "overall_valid": True,
            "needs_review": False
        }
        
        # 1. 验证 Revenue Breakdown
        if extraction_result.get("revenue_breakdown"):
            revenue_validation = await self.validate_revenue_breakdown(
                revenue_data=extraction_result["revenue_breakdown"],
                company_id=company_id,
                year=year,
                document_id=document_id
            )
            result["revenue_validation"] = revenue_validation
            
            if not revenue_validation["is_valid"]:
                result["overall_valid"] = False
            
            if revenue_validation["needs_review"]:
                result["needs_review"] = True
        
        # 2. 验证 Financial Metrics
        if extraction_result.get("financial_metrics"):
            metrics_validation = await self.validate_financial_metrics(
                metrics_data=extraction_result["financial_metrics"],
                company_id=company_id,
                year=year,
                document_id=document_id
            )
            result["metrics_validation"] = metrics_validation
            
            if not metrics_validation["is_valid"]:
                result["overall_valid"] = False
            
            if metrics_validation["needs_review"]:
                result["needs_review"] = True
        
        # 3. 验证 Key Personnel
        if extraction_result.get("key_personnel"):
            personnel_validation = await self.validate_key_personnel(
                personnel_data=extraction_result["key_personnel"],
                company_id=company_id,
                document_id=document_id
            )
            result["personnel_validation"] = personnel_validation
            
            if not personnel_validation["is_valid"]:
                result["overall_valid"] = False
        
        # 4. 更新文档状态
        if self.db:
            try:
                status = "completed" if result["overall_valid"] else "review"
                await self.db.update_document_status(document_id, status)
                logger.info(f"   📄 文档状态已更新: {status}")
            except Exception as e:
                logger.warning(f"   ⚠️ 更新文档状态失败: {e}")
        
        logger.info(f"✅ Stage 6 完成: overall_valid={result['overall_valid']}, needs_review={result['needs_review']}")
        
        return result