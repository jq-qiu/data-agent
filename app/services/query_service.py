"""编排单轮意图路由、语义绑定、问数或诊断 Graph，并输出安全 SSE 事件。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from types import MappingProxyType
from typing import Any

from langchain_core.embeddings import Embeddings

from app.agent.context import DataAgentContext
from app.agent.diagnosis_graph import build_diagnosis_graph
from app.agent.graph import graph as nl2sql_graph
from app.agent.state import DataAgentState
from app.core.log import logger
from app.diagnosis.capability import CapabilityAssessor
from app.diagnosis.evidence import evidence_limitation_label
from app.diagnosis.grounding import (
    SemanticBindingResult,
    SemanticBindingStatus,
    SemanticGrounder,
)
from app.diagnosis.intent import Intent, IntentDecision, IntentRouter
from app.diagnosis.query import (
    AnalysisQueryBuilder,
    AnalysisQueryContext,
    AnalysisTaskExecutor,
    QueryDataSource,
)
from app.diagnosis.question import (
    AnalysisDimension,
    AnalysisQuestionParser,
    CandidateFactor,
    ParsedAnalysisQuestion,
)
from app.diagnosis.runtime import (
    SyntheticCapabilityProfileProvider,
    WarehouseCapabilityProfileProvider,
)
from app.diagnosis.semantics import AnalysisSemanticRegistry
from app.nl2sql.validator import SQLValidator
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository

_UNSUPPORTED_GUIDANCE = MappingProxyType(
    {
        "empty_question": "请输入一个完整的单轮数据问题。",
        "multi_turn_anaphora_unsupported": "V1 暂不支持省略式追问，请在本轮补全指标、时间和维度。",
        "future_or_external_action_unsupported": "V1 不支持预测或自动执行操作，可改为查询已有数据。",
        "strict_causal_request_unsupported": "V1 只能提供关联证据，不能证明严格因果关系。",
        "non_gmv_diagnosis_unsupported": "V1 诊断仅支持 GMV；其他指标可改为单轮数据查询。",
        "semantic_low_confidence": "暂时无法可靠判断请求意图，请补充指标、时间和期望操作。",
        "semantic_classifier_unavailable": "语义识别暂不可用，请明确写出指标、时间和查询操作。",
        "semantic_domain_mismatch": "请使用已注册的电商指标或实体，并说明查询操作。",
        "semantic_request_unsupported": "当前请求不在 V1 单轮问数与 GMV 关联诊断范围内。",
        "ambiguous_or_incomplete_question": "请补充要查询的指标、时间范围和维度。",
    }
)

_BINDING_GUIDANCE = MappingProxyType(
    {
        "missing_current_period": "请补充要分析的当前时间，例如“2018 年 5 月”。",
        "ambiguous_calendar_months": "问题中有多个可能的分析月份，请明确当前期和对比基期。",
        "explicit_baseline_incomplete": "你提到了基期，请补充完整的基期月份。",
        "missing_or_unknown_metric": "请明确要诊断的指标；V1 归因诊断支持 GMV。",
        "ambiguous_metric": "识别到多个可能指标，请明确选择要诊断的指标。",
        "unknown_dimension": "请明确希望按地区还是按品类分析。",
        "ambiguous_dimension": "识别到多个可能维度，请明确选择地区或品类。",
        "unknown_scope_value": "请补充可识别的州代码或商品品类。",
        "ambiguous_scope_value": "识别到多个可能的范围值，请从候选中明确选择。",
        "multiple_scope_values_unsupported": "单轮诊断暂不支持同一维度的多个范围值，请只保留一个。",
        "semantic_retrieval_unavailable": "语义候选暂时不可用，请按推荐格式补全问题后重试。",
        "metric_not_supported": "V1 归因诊断仅支持 GMV；该指标可改为普通数据查询。",
        "non_adjacent_calendar_months": "V1 归因诊断仅支持相邻月份对比，请调整当前期和基期。",
        "too_many_calendar_months": "单轮诊断最多接受当前期和一个基期，请减少月份数量。",
        "invalid_calendar_month": "月份格式无效，请使用明确的年月。",
    }
)


class QueryService:
    """单轮请求编排器：按意图选择 NL2SQL 或诊断路径，并保证流中产生安全终态。"""

    def __init__(
        self,
        embedding_client: Embeddings,
        column_qdrant_repository: ColumnQdrantRepository,
        metric_qdrant_repository: MetricQdrantRepository,
        value_es_repository: ValueESRepository,
        meta_mysql_repository: MetaMySQLRepository,
        dw_mysql_repository: DWMySQLRepository,
        sql_validator: SQLValidator,
        intent_router: IntentRouter | None = None,
        semantic_grounder: SemanticGrounder | None = None,
    ):
        self.embedding_client = embedding_client
        self.column_qdrant_repository = column_qdrant_repository
        self.metric_qdrant_repository = metric_qdrant_repository
        self.value_es_repository = value_es_repository
        self.meta_mysql_repository = meta_mysql_repository
        self.dw_mysql_repository = dw_mysql_repository
        self.sql_validator = sql_validator
        self.intent_router = intent_router or IntentRouter.from_catalog(
            sql_validator.catalog
        )
        self.semantic_grounder = semantic_grounder or SemanticGrounder(
            sql_validator.catalog,
            AnalysisSemanticRegistry.from_catalog(sql_validator.catalog),
        )

    async def query_answer(self, question: str) -> AsyncIterator[str]:
        """路由一个完整问题并逐条产出 SSE；未处理异常收敛为公共错误事件。"""

        # aroute 先执行确定性规则，只有歧义场景才可能使用受限语义分类器。
        decision = await self.intent_router.aroute(question)
        yield _event(
            {"type": "progress", "step": "识别请求意图", "status": "running"}
        )
        yield _event(
            {"type": "progress", "step": "识别请求意图", "status": "success"}
        )
        try:
            # QUERY 复用开放 NL2SQL；DIAGNOSIS 进入受控分析链；其他意图直接返回能力边界。
            if decision.intent is Intent.QUERY:
                async for event in self._query_events(question, decision):
                    yield _event(event)
            elif decision.intent is Intent.DIAGNOSIS or (
                decision.reason == "non_gmv_diagnosis_unsupported"
            ):
                # 非 GMV 诊断仍交给 Grounder 输出具体“指标不支持”，比泛化的不支持提示更可解释。
                diagnosis_decision = (
                    decision
                    if decision.intent is Intent.DIAGNOSIS
                    else IntentDecision(
                        intent=Intent.DIAGNOSIS,
                        confidence=decision.confidence,
                        reason="semantic_grounding_diagnosis_candidate",
                    )
                )
                async for event in self._diagnosis_events(
                    question,
                    diagnosis_decision,
                ):
                    yield _event(event)
            else:
                yield _event(_unsupported_result(decision))
        except Exception as error:  # noqa: BLE001 - public stream must terminate safely
            logger.error("API request failed with error type {}", type(error).__name__)
            yield _event(
                {
                    "type": "error",
                    "code": "REQUEST_EXECUTION_FAILED",
                    "message": "请求未能安全完成，请检查服务依赖或请求范围。",
                }
            )

    async def _query_events(
        self,
        question: str,
        decision: IntentDecision,
    ) -> AsyncIterator[dict[str, Any]]:
        """运行开放式 NL2SQL Graph，并为结果补充不含敏感细节的统一 Trace。"""

        # State 只保存本次请求的可序列化数据；Repository、模型和 Validator 放在 Context。
        state = DataAgentState(query=question, repair_attempts=0)
        context = DataAgentContext(
            meta_mysql_repository=self.meta_mysql_repository,
            dw_mysql_repository=self.dw_mysql_repository,
            embedding_client=self.embedding_client,
            column_qdrant_repository=self.column_qdrant_repository,
            metric_qdrant_repository=self.metric_qdrant_repository,
            value_es_repository=self.value_es_repository,
            sql_validator=self.sql_validator,
        )
        # 记录是否收到结果/错误终态，防止 Graph 意外结束后浏览器一直等待。
        terminal_emitted = False
        async for chunk in nl2sql_graph.astream(
            input=state,
            context=context,
            stream_mode="custom",
        ):
            if not isinstance(chunk, Mapping):
                continue
            event = dict(chunk)
            if event.get("type") == "result":
                terminal_emitted = True
                # 内部校验对象只投影安全字段，原 SQL 和执行细节不进入公共 Trace。
                validation = _safe_validation(event.get("validation"))
                event.update(
                    {
                        "intent": decision.intent.value,
                        "answer": None,
                        "analysis_trace": [
                            _intent_trace(decision),
                            {
                                "stage": "query_execution",
                                "status": "success",
                                "validation": validation,
                            },
                        ],
                        "evidence": [],
                        "limitations": [],
                    }
                )
            elif event.get("type") == "error":
                terminal_emitted = True
            yield event
        if not terminal_emitted:
            yield {
                "type": "error",
                "code": "QUERY_VALIDATION_FAILED",
                "message": "生成的查询未能通过安全校验，请调整问题后重试。",
            }

    async def _diagnosis_events(
        self,
        question: str,
        decision: IntentDecision,
    ) -> AsyncIterator[dict[str, Any]]:
        """先完成语义绑定和能力探测，再运行有限的确定性诊断 Graph。"""

        grounding_step = "理解诊断问题"
        yield {"type": "progress", "step": grounding_step, "status": "running"}
        # Grounder 把自然语言绑定成规范指标、期间和 Scope；后续节点不再处理任意自由文本语义。
        binding = await self.semantic_grounder.bind(question, Intent.DIAGNOSIS)
        yield {"type": "progress", "step": grounding_step, "status": "success"}
        if binding.status is not SemanticBindingStatus.READY:
            # 非 READY 在读取运行时数据前结束，既避免无意义查询，也不会猜测缺失的分析范围。
            yield _binding_result(decision, binding)
            return

        parsed = binding.parsed_question
        if parsed is None:
            raise RuntimeError("READY semantic binding requires a parsed question")
        # 只有检索补全过的绑定才重写规范问题；纯确定性解析继续使用原问题，保持既有行为。
        graph_question = (
            _canonical_analysis_question(parsed)
            if binding.retrieval_used
            else question
        )

        profile_step = "读取运行时数据能力"
        yield {"type": "progress", "step": profile_step, "status": "running"}
        # 能力画像读取当前 DWS 的实际覆盖和非空 Evidence，Planner 只能使用真实可用能力。
        profile = await WarehouseCapabilityProfileProvider(
            self.sql_validator.catalog,
            self.sql_validator,
            self.dw_mysql_repository,
        ).load()
        yield {"type": "progress", "step": profile_step, "status": "success"}

        parser = AnalysisQuestionParser.from_catalog(self.sql_validator.catalog)
        assessor = CapabilityAssessor(self.sql_validator.catalog)
        query_builder = AnalysisQueryBuilder(
            self.sql_validator.catalog,
            AnalysisQueryContext(source=QueryDataSource.WAREHOUSE),
        )
        executor = AnalysisTaskExecutor(
            query_builder,
            self.sql_validator,
            self.dw_mysql_repository,
        )
        diagnosis_graph = build_diagnosis_graph(parser, assessor, profile, executor)
        latest_state: dict[str, Any] = {
            "question": graph_question,
            "intent": decision.intent.value,
        }
        # custom 流承载进度，values 流更新完整状态；只把 custom 事件直接发给客户端。
        async for mode, chunk in diagnosis_graph.astream(
            input=latest_state,
            stream_mode=["custom", "values"],
        ):
            if mode == "custom" and isinstance(chunk, Mapping):
                yield dict(chunk)
            elif mode == "values" and isinstance(chunk, Mapping):
                latest_state = dict(chunk)
        yield _diagnosis_result(decision, latest_state, binding)

    async def synthetic_diagnosis_events(
        self,
        case_id: str,
        question: str,
    ) -> AsyncIterator[str]:
        """在指定合成案例的数据隔离范围内运行同一诊断算法，用于可复现演示。"""

        profile_step = "读取合成诊断数据能力"
        yield _event({"type": "progress", "step": profile_step, "status": "running"})
        # 合成演示绑定到单个 case_id，避免不同 Ground Truth 案例的数据互相污染。
        profile = await SyntheticCapabilityProfileProvider(
            self.sql_validator.catalog,
            self.sql_validator,
            self.dw_mysql_repository,
            case_id,
        ).load()
        yield _event({"type": "progress", "step": profile_step, "status": "success"})

        parser = AnalysisQuestionParser.from_catalog(self.sql_validator.catalog)
        assessor = CapabilityAssessor(self.sql_validator.catalog)
        query_builder = AnalysisQueryBuilder(
            self.sql_validator.catalog,
            AnalysisQueryContext(
                source=QueryDataSource.SYNTHETIC_CASE,
                case_id=case_id,
            ),
        )
        executor = AnalysisTaskExecutor(
            query_builder,
            self.sql_validator,
            self.dw_mysql_repository,
        )
        diagnosis_graph = build_diagnosis_graph(parser, assessor, profile, executor)
        decision = IntentDecision(
            intent=Intent.DIAGNOSIS,
            confidence=0.95,
            reason="gmv_diagnosis_request",
        )
        latest_state: dict[str, Any] = {
            "question": question,
            "intent": decision.intent.value,
        }
        async for mode, chunk in diagnosis_graph.astream(
            input=latest_state,
            stream_mode=["custom", "values"],
        ):
            if mode == "custom" and isinstance(chunk, Mapping):
                yield _event(dict(chunk))
            elif mode == "values" and isinstance(chunk, Mapping):
                latest_state = dict(chunk)
        yield _event(_diagnosis_result(decision, latest_state))


def _event(payload: Mapping[str, Any]) -> str:
    """把一个结构化事件编码为 SSE data block，并保留中文字符。"""

    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _intent_trace(decision: IntentDecision) -> dict[str, Any]:
    return {
        "stage": "intent_router",
        "status": "success",
        "intent": decision.intent.value,
        "confidence": decision.confidence,
        "reason": decision.reason,
    }


def _unsupported_result(decision: IntentDecision) -> dict[str, Any]:
    return {
        "type": "result",
        "intent": decision.intent.value,
        "answer": _UNSUPPORTED_GUIDANCE.get(
            decision.reason,
            "当前请求不在 V1 单轮问数与 GMV 关联诊断范围内。",
        ),
        "data": [],
        "analysis_trace": [_intent_trace(decision)],
        "evidence": [],
        "limitations": [decision.reason],
    }


def _binding_result(
    decision: IntentDecision,
    binding: SemanticBindingResult,
) -> dict[str, Any]:
    """把澄清/不支持绑定转换为公共终态，只暴露逻辑候选和稳定原因。"""

    if binding.status is SemanticBindingStatus.READY:
        raise ValueError("READY binding must continue to diagnosis")
    reason = str(binding.reason or "semantic_binding_failed")
    public_intent = (
        Intent.UNSUPPORTED.value
        if binding.status is SemanticBindingStatus.UNSUPPORTED
        else Intent.DIAGNOSIS.value
    )
    candidates = {
        "metrics": [item.metric_id for item in binding.candidates.metrics],
        "dimensions": [
            item.dimension.value for item in binding.candidates.dimensions
        ],
        "values": [
            {
                "dimension": item.dimension.value,
                "value": item.canonical_value,
            }
            for item in binding.candidates.values
        ],
    }
    limitations = list(binding.limitations)
    if binding.status is SemanticBindingStatus.UNSUPPORTED:
        limitations.append(reason)
    return {
        "type": "result",
        "intent": public_intent,
        "binding_status": binding.status.value,
        "answer": _BINDING_GUIDANCE.get(
            reason,
            "当前问题无法安全绑定到 V1 归因能力，请补充指标、时间和分析范围。",
        ),
        "data": [],
        "report_status": binding.status.value,
        "clarification": {
            "reason": reason,
            "missing_fields": [item.value for item in binding.missing_fields],
            "ambiguous_fields": [item.value for item in binding.ambiguous_fields],
            "candidates": candidates,
            "suggested_question": binding.suggested_question,
        },
        "analysis_trace": [
            _intent_trace(decision),
            _semantic_grounding_trace(binding),
        ],
        "evidence": [],
        "limitations": list(dict.fromkeys(limitations)),
    }


def _diagnosis_result(
    decision: IntentDecision,
    state: Mapping[str, Any],
    binding: SemanticBindingResult | None = None,
) -> dict[str, Any]:
    """汇总 Graph 终态，并从 Evidence 中提取面向 API 的限制说明。"""

    bundle = state.get("validated_evidence")
    evidence = []
    limitations = list(state.get("api_limitations") or [])
    if isinstance(bundle, Mapping):
        raw_evidence = bundle.get("evidence")
        if isinstance(raw_evidence, list):
            evidence = raw_evidence
            for item in raw_evidence:
                if isinstance(item, Mapping):
                    values = item.get("limitations")
                    if isinstance(values, list):
                        limitations.extend(evidence_limitation_label(value) for value in values)
        missing = bundle.get("missing_evidence")
        if isinstance(missing, list):
            limitations.extend(str(value) for value in missing)
    # 没有通过 Report Generator 的结果一律按 DEGRADED 返回，不能伪装成完整诊断。
    report = state.get("final_report")
    report_status = report.get("status") if isinstance(report, Mapping) else "DEGRADED"
    result = {
        "type": "result",
        "intent": decision.intent.value,
        "answer": str(state.get("final_answer") or "当前诊断无法安全完成。"),
        "report_status": report_status,
        "analysis_trace": _diagnosis_trace(decision, state, binding),
        "evidence": evidence,
        "limitations": list(dict.fromkeys(limitations)),
    }
    if binding is not None:
        result["binding_status"] = binding.status.value
    return result


def _diagnosis_trace(
    decision: IntentDecision,
    state: Mapping[str, Any],
    binding: SemanticBindingResult | None = None,
) -> list[dict[str, Any]]:
    """按白名单投影公开 Trace，不返回 SQL、参数、原始行、连接信息或 Ground Truth。"""

    trace: list[dict[str, Any]] = [_intent_trace(decision)]
    if binding is not None:
        trace.append(_semantic_grounding_trace(binding))
    parsed = state.get("parsed_question")
    if isinstance(parsed, Mapping):
        trace.append(
            {
                "stage": "analysis_question_parser",
                "status": "success",
                "parsed_question": dict(parsed),
            }
        )
    capability = state.get("capability")
    if isinstance(capability, Mapping):
        trace.append(
            {
                "stage": "capability_assessment",
                "status": "success",
                "capability": dict(capability),
            }
        )
    plan = state.get("analysis_plan")
    if isinstance(plan, Mapping):
        trace.append(
            {
                "stage": "analysis_planner",
                "status": "success",
                "plan": dict(plan),
            }
        )
    queries = state.get("query_results")
    if isinstance(queries, list):
        trace.append(
            {
                "stage": "analysis_task_executor",
                "status": "success",
                "queries": [_safe_query_trace(item) for item in queries],
            }
        )
    analyses = state.get("analysis_results")
    if isinstance(analyses, list):
        trace.append(
            {
                "stage": "deterministic_analyzer",
                "status": "success",
                "results": [_safe_analysis_trace(item) for item in analyses],
            }
        )
    bundle = state.get("validated_evidence")
    if isinstance(bundle, Mapping):
        raw_evidence = bundle.get("evidence")
        evidence_items = raw_evidence if isinstance(raw_evidence, list) else []
        trace.append(
            {
                "stage": "evidence_checker",
                "status": "success",
                "evidence": [
                    {
                        key: item.get(key)
                        for key in (
                            "evidence_id",
                            "evidence_type",
                            "support_level",
                            "analysis_result_ids",
                            "query_ids",
                        )
                    }
                    for item in evidence_items
                    if isinstance(item, Mapping)
                ],
            }
        )
    report = state.get("final_report")
    if isinstance(report, Mapping):
        trace.append(
            {
                "stage": "report_generator",
                "status": "success",
                "report_status": report.get("status"),
            }
        )
    return trace


def _semantic_grounding_trace(
    binding: SemanticBindingResult,
) -> dict[str, Any]:
    return {
        "stage": "semantic_grounding",
        "status": "success",
        "binding_status": binding.status.value,
        "reason": binding.reason,
        "missing_fields": [item.value for item in binding.missing_fields],
        "ambiguous_fields": [item.value for item in binding.ambiguous_fields],
    }


def _canonical_analysis_question(parsed: ParsedAnalysisQuestion) -> str:
    """把检索补全后的规范绑定重写为完整单轮问题，交给既有确定性 Parser 复核。"""

    current = parsed.current_period.start
    baseline = parsed.baseline_period.start
    scope = ""
    if parsed.scope.region is not None:
        scope += f"{parsed.scope.region} 州"
    if parsed.scope.category is not None:
        scope += f"{parsed.scope.category} 品类"
    question = (
        f"为什么 {current.year} 年 {current.month} 月相比 "
        f"{baseline.year} 年 {baseline.month} 月 {scope}GMV 下降？"
    )

    dimension_labels = {
        AnalysisDimension.REGION: "地区",
        AnalysisDimension.CATEGORY: "品类",
    }
    factor_labels = {
        CandidateFactor.TRAFFIC: "流量",
        CandidateFactor.PROMOTION: "促销",
        CandidateFactor.INVENTORY: "库存",
    }
    requests: list[str] = []
    if parsed.requested_dimensions:
        requests.append(
            "、".join(
                f"按{dimension_labels[dimension]}"
                for dimension in parsed.requested_dimensions
            )
        )
    if parsed.requested_factors:
        requests.append(
            "分析"
            + "、".join(factor_labels[factor] for factor in parsed.requested_factors)
        )
    if requests:
        question += "请" + "，".join(requests) + "。"
    return question


def _safe_query_trace(item: Any) -> dict[str, Any]:
    """从内部 Query Result 提取允许公开的标识、血缘版本和校验摘要。"""

    if not isinstance(item, Mapping):
        return {}
    return {
        key: item.get(key)
        for key in (
            "query_id",
            "task_id",
            "method",
            "query_role",
            "catalog_version",
            "metric_versions",
        )
    } | {"validation": _safe_validation(item.get("validation"))}


def _safe_analysis_trace(item: Any) -> dict[str, Any]:
    """从 Analyzer Result 提取方法与对账摘要，不暴露内部数值载荷。"""

    if not isinstance(item, Mapping):
        return {}
    reconciliation = item.get("reconciliation")
    safe_reconciliation = None
    if isinstance(reconciliation, Mapping):
        safe_reconciliation = {
            key: reconciliation.get(key)
            for key in ("status", "difference", "tolerance")
        }
    return {
        key: item.get(key)
        for key in (
            "analysis_result_id",
            "method",
            "input_query_ids",
            "metric_versions",
            "warnings",
        )
    } | {"reconciliation": safe_reconciliation}


def _safe_validation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: value.get(key)
        for key in (
            "tables",
            "columns",
            "join_relations",
            "grain_warnings",
            "policy_version",
            "max_rows",
            "timeout_seconds",
        )
    }
