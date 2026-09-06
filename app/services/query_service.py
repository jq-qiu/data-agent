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
from app.diagnosis.intent import Intent, IntentDecision, IntentRouter
from app.diagnosis.query import (
    AnalysisQueryBuilder,
    AnalysisQueryContext,
    AnalysisTaskExecutor,
    QueryDataSource,
)
from app.diagnosis.question import AnalysisQuestionParser
from app.diagnosis.runtime import (
    SyntheticCapabilityProfileProvider,
    WarehouseCapabilityProfileProvider,
)
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


class QueryService:
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

    async def query_answer(self, question: str) -> AsyncIterator[str]:
        decision = await self.intent_router.aroute(question)
        yield _event(
            {"type": "progress", "step": "识别请求意图", "status": "running"}
        )
        yield _event(
            {"type": "progress", "step": "识别请求意图", "status": "success"}
        )
        try:
            if decision.intent is Intent.QUERY:
                async for event in self._query_events(question, decision):
                    yield _event(event)
            elif decision.intent is Intent.DIAGNOSIS:
                async for event in self._diagnosis_events(question, decision):
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
        profile_step = "读取运行时数据能力"
        yield {"type": "progress", "step": profile_step, "status": "running"}
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
            "question": question,
            "intent": decision.intent.value,
        }
        async for mode, chunk in diagnosis_graph.astream(
            input=latest_state,
            stream_mode=["custom", "values"],
        ):
            if mode == "custom" and isinstance(chunk, Mapping):
                yield dict(chunk)
            elif mode == "values" and isinstance(chunk, Mapping):
                latest_state = dict(chunk)
        yield _diagnosis_result(decision, latest_state)

    async def synthetic_diagnosis_events(
        self,
        case_id: str,
        question: str,
    ) -> AsyncIterator[str]:
        profile_step = "读取合成诊断数据能力"
        yield _event({"type": "progress", "step": profile_step, "status": "running"})
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


def _diagnosis_result(
    decision: IntentDecision,
    state: Mapping[str, Any],
) -> dict[str, Any]:
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
                        limitations.extend(str(value) for value in values)
        missing = bundle.get("missing_evidence")
        if isinstance(missing, list):
            limitations.extend(str(value) for value in missing)
    report = state.get("final_report")
    report_status = report.get("status") if isinstance(report, Mapping) else "DEGRADED"
    return {
        "type": "result",
        "intent": decision.intent.value,
        "answer": str(state.get("final_answer") or "当前诊断无法安全完成。"),
        "report_status": report_status,
        "analysis_trace": _diagnosis_trace(decision, state),
        "evidence": evidence,
        "limitations": list(dict.fromkeys(limitations)),
    }


def _diagnosis_trace(
    decision: IntentDecision,
    state: Mapping[str, Any],
) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = [_intent_trace(decision)]
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


def _safe_query_trace(item: Any) -> dict[str, Any]:
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
