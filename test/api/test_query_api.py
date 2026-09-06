from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import sqlglot
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.agent.diagnosis_graph import build_diagnosis_graph
from app.agent.nodes.execute_sql import execute_sql
from app.agent.nodes.validate_sql import validate_sql
from app.api.dependencies import _SerializedMetaMySQLRepository, get_query_service
from app.api.routers.query_router import query_router
from app.api.schemas.query_schema import QuerySchema
from app.diagnosis.capability import CapabilityAssessor
from app.diagnosis.grounding import (
    BindingField,
    DimensionGroundingCandidate,
    MetricGroundingCandidate,
    SemanticBindingResult,
    SemanticBindingStatus,
    SemanticCandidateBundle,
    ValueGroundingCandidate,
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
    ParsedAnalysisQuestion,
)
from app.diagnosis.runtime import WarehouseCapabilityProfileProvider
from app.metadata.catalog import load_catalog
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.validator import SQLValidator, ValidatedSQL
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.services import query_service as query_service_module
from app.services.query_service import (
    QueryService,
    _canonical_analysis_question,
    _diagnosis_result,
    _unsupported_result,
)

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_TRACE_KEYS = {
    "sql",
    "parameters",
    "rows",
    "sql_fingerprint",
    "connection_string",
    "password",
    "token",
    "cookie",
}


def _catalog_and_validator() -> tuple[Any, SQLValidator]:
    catalog = load_catalog(ROOT / "conf" / "meta_config.yaml")
    return catalog, SQLValidator(
        catalog,
        load_sql_policy(ROOT / "conf" / "sql_policy.yaml"),
    )


def _profile_row(table: str) -> dict[str, Any]:
    columns = {
        "dws_sales_region_daily": (
            "date_id",
            "region_id",
            "gmv",
            "order_count",
            "visitors",
            "promoted_sku_count",
            "active_sku_count",
            "available_sku_count",
            "required_sku_count",
        ),
        "dws_sales_category_daily": (
            "date_id",
            "region_id",
            "category_id",
            "gmv",
            "category_order_count",
            "category_visitors",
            "promoted_sku_count",
            "active_sku_count",
            "available_sku_count",
            "required_sku_count",
        ),
    }[table]
    row: dict[str, Any] = {"min_date": 20160904, "max_date": 20180903}
    for column in columns:
        row[f"{column}_non_null_count"] = (
            0
            if column
            in {
                "visitors",
                "category_visitors",
                "promoted_sku_count",
                "active_sku_count",
                "available_sku_count",
                "required_sku_count",
            }
            else 1
        )
    return row


class ControlledRepository:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def validate_sql(
        self,
        validated_sql: ValidatedSQL,
        parameters: Mapping[str, object] | None = None,
    ) -> None:
        self.events.append(f"explain:{validated_sql.tables[0]}")

    async def execute_sql(
        self,
        validated_sql: ValidatedSQL,
        parameters: Mapping[str, object] | None = None,
    ) -> list[dict[str, Any]]:
        table = validated_sql.tables[0]
        self.events.append(f"execute:{table}")
        columns = tuple(
            sqlglot.parse_one(validated_sql.sql, read="mysql").named_selects
        )
        if "min_date" in columns:
            return [_profile_row(table)]
        if "dimension_value" in columns:
            dimension = "SP" if table == "dws_sales_region_daily" else "books_general_interest"
            return [
                {"period_role": "baseline", "dimension_value": dimension, "gmv": "1000"},
                {"period_role": "current", "dimension_value": dimension, "gmv": "800"},
            ]
        if "order_count" in columns:
            return [
                {"period_role": "baseline", "gmv": "1000", "order_count": 10},
                {"period_role": "current", "gmv": "800", "order_count": 8},
            ]
        return [
            {"period_role": "baseline", "gmv": "1000"},
            {"period_role": "current", "gmv": "800"},
        ]


class StubSemanticGrounder:
    def __init__(self, result: SemanticBindingResult) -> None:
        self.result = result
        self.calls: list[tuple[str, Intent | str]] = []

    async def bind(self, question: str, intent: Intent | str) -> SemanticBindingResult:
        self.calls.append((question, intent))
        return self.result


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return set(value) | set().union(
            *(_nested_keys(item) for item in value.values()),
            set(),
        )
    if isinstance(value, (list, tuple)):
        return set().union(*(_nested_keys(item) for item in value), set())
    return set()


@pytest.mark.parametrize(
    "payload",
    (
        {"question": "  为什么2018年5月GMV下降？  "},
        {"query": "2018年5月GMV是多少？"},
    ),
)
def test_request_accepts_canonical_and_legacy_fields(payload: dict[str, str]) -> None:
    request = QuerySchema.model_validate(payload)

    assert request.resolved_question == next(iter(payload.values())).strip()


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"question": ""},
        {"query": "   "},
        {"question": "a", "query": "b"},
        {"question": "a", "extra": True},
    ),
)
def test_request_rejects_invalid_single_turn_shapes(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        QuerySchema.model_validate(payload)


@pytest.mark.asyncio
async def test_api_metadata_repository_serializes_parallel_session_reads(
    monkeypatch: Any,
) -> None:
    active_reads = 0
    maximum_active_reads = 0

    async def tracked_read(*_: Any) -> Any:
        nonlocal active_reads, maximum_active_reads
        active_reads += 1
        maximum_active_reads = max(maximum_active_reads, active_reads)
        await asyncio.sleep(0)
        active_reads -= 1
        return object()

    monkeypatch.setattr(
        MetaMySQLRepository,
        "get_v1_column_info_by_id",
        tracked_read,
    )
    monkeypatch.setattr(
        MetaMySQLRepository,
        "get_v1_metric_info_by_id",
        tracked_read,
    )
    repository = _SerializedMetaMySQLRepository(None)  # type: ignore[arg-type]

    await asyncio.gather(
        repository.get_v1_column_info_by_id("column"),
        repository.get_v1_metric_info_by_id("metric"),
    )

    assert maximum_active_reads == 1


@pytest.mark.asyncio
async def test_runtime_profile_uses_validated_probes_and_marks_empty_evidence() -> None:
    catalog, validator = _catalog_and_validator()
    repository = ControlledRepository()

    profile = await WarehouseCapabilityProfileProvider(
        catalog,
        validator,
        repository,
    ).load()

    assert profile.available_period.start.isoformat() == "2016-09-04"
    assert profile.available_period.end.isoformat() == "2018-09-03"
    assert "dws_sales_region_daily.gmv" in profile.non_empty_columns
    assert "dws_sales_category_daily.category_order_count" in profile.non_empty_columns
    assert "dws_sales_region_daily.visitors" not in profile.non_empty_columns
    assert repository.events == [
        "explain:dws_sales_region_daily",
        "execute:dws_sales_region_daily",
        "explain:dws_sales_category_daily",
        "execute:dws_sales_category_daily",
    ]


@pytest.mark.asyncio
async def test_diagnosis_graph_runs_seven_stages_and_public_trace_is_safe() -> None:
    catalog, validator = _catalog_and_validator()
    repository = ControlledRepository()
    profile = await WarehouseCapabilityProfileProvider(
        catalog,
        validator,
        repository,
    ).load()
    parser = AnalysisQuestionParser.from_catalog(catalog)
    executor = AnalysisTaskExecutor(
        AnalysisQueryBuilder(
            catalog,
            AnalysisQueryContext(source=QueryDataSource.WAREHOUSE),
        ),
        validator,
        repository,
    )
    graph = build_diagnosis_graph(
        parser,
        CapabilityAssessor(catalog),
        profile,
        executor,
    )
    question = "为什么2018年5月GMV下降？"

    state = await graph.ainvoke({"question": question, "intent": "DIAGNOSIS"})
    result = _diagnosis_result(IntentRouter().route(question), state)

    assert state["final_report"]["status"] == "DEGRADED"
    assert len(state["query_results"]) == 4
    assert [item["stage"] for item in result["analysis_trace"]] == [
        "intent_router",
        "analysis_question_parser",
        "capability_assessment",
        "analysis_planner",
        "analysis_task_executor",
        "deterministic_analyzer",
        "evidence_checker",
        "report_generator",
    ]
    assert not (_nested_keys(result["analysis_trace"]) & FORBIDDEN_TRACE_KEYS)
    assert "dws_sales_region_daily.visitors" in result["limitations"]


class FakeQueryService:
    async def query_answer(self, question: str):
        yield "data: " + json.dumps(
            {"type": "result", "intent": "QUERY", "data": [{"gmv": "1"}]}
        ) + "\n\n"

    async def synthetic_diagnosis_events(self, case_id: str, question: str):
        yield "data: " + json.dumps(
            {
                "type": "result",
                "intent": "DIAGNOSIS",
                "case_id": case_id,
                "data": [],
            }
        ) + "\n\n"


def test_http_endpoint_preserves_sse_and_legacy_query_contract() -> None:
    app = FastAPI()
    app.include_router(query_router)
    app.dependency_overrides[get_query_service] = FakeQueryService

    with TestClient(app) as client:
        response = client.post("/api/query", json={"query": "GMV是多少"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert '"type": "result"' in response.text
    assert '"data": [{"gmv": "1"}]' in response.text



def test_synthetic_demo_endpoint_rejects_unknown_case() -> None:
    app = FastAPI()
    app.include_router(query_router)
    app.dependency_overrides[get_query_service] = FakeQueryService

    with TestClient(app) as client:
        response = client.post("/api/demo/synthetic-diagnosis/D99")

    assert response.status_code == 422


def test_synthetic_demo_endpoint_streams_known_case() -> None:
    app = FastAPI()
    app.include_router(query_router)
    app.dependency_overrides[get_query_service] = FakeQueryService

    with TestClient(app) as client:
        response = client.post("/api/demo/synthetic-diagnosis/D01")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"case_id": "D01"' in response.text

class FakeNL2SQLGraph:
    async def astream(self, **_: Any):
        yield {"type": "progress", "step": "执行SQL", "status": "success"}
        yield {
            "type": "result",
            "data": [{"gmv": "992871.75"}],
            "validation": {
                "tables": ["dws_sales_region_daily"],
                "columns": ["dws_sales_region_daily.gmv"],
                "join_relations": [],
                "grain_warnings": [],
                "policy_version": "sql-policy-v1",
                "max_rows": 500,
                "timeout_seconds": 10,
            },
        }


class ValidationFailureGraph:
    async def astream(self, **_: Any):
        yield {"type": "progress", "step": "验证SQL", "status": "error"}


class ValidationHandoffRepository:
    def __init__(self) -> None:
        self.validated: list[str] = []
        self.executed: list[str] = []

    async def validate_sql(
        self,
        validated_sql: ValidatedSQL,
        parameters: Mapping[str, object] | None = None,
    ) -> None:
        self.validated.append(validated_sql.sql)

    async def execute_sql(
        self,
        validated_sql: ValidatedSQL,
        parameters: Mapping[str, object] | None = None,
    ) -> list[dict[str, Any]]:
        self.executed.append(validated_sql.sql)
        return [{"gmv_change": "-721.23"}]


@pytest.mark.asyncio
async def test_validation_handoff_revalidates_same_if_source_before_execution() -> None:
    _, validator = _catalog_and_validator()
    repository = ValidationHandoffRepository()
    writes: list[dict[str, Any]] = []
    runtime = Runtime(
        context={
            "sql_validator": validator,
            "dw_mysql_repository": repository,
        },
        stream_writer=writes.append,
    )
    source_sql = (
        "SELECT SUM(IF(date_id BETWEEN 20180501 AND 20180531, gmv, 0)) "
        "AS gmv_change FROM dws_sales_region_daily"
    )
    state: dict[str, Any] = {
        "sql": source_sql,
        "metric_infos": [],
        "repair_attempts": 1,
    }

    validation_update = await validate_sql(state, runtime)  # type: ignore[arg-type]
    assert "sql" not in validation_update
    state.update(validation_update)
    await execute_sql(state, runtime)  # type: ignore[arg-type]

    assert repository.validated == repository.executed
    assert any(item.get("type") == "result" for item in writes)


@pytest.mark.asyncio
async def test_query_branch_keeps_rows_and_adds_only_safe_trace(monkeypatch: Any) -> None:
    _, validator = _catalog_and_validator()
    monkeypatch.setattr(query_service_module, "nl2sql_graph", FakeNL2SQLGraph())
    service = QueryService(
        embedding_client=None,  # type: ignore[arg-type]
        column_qdrant_repository=None,  # type: ignore[arg-type]
        metric_qdrant_repository=None,  # type: ignore[arg-type]
        value_es_repository=None,  # type: ignore[arg-type]
        meta_mysql_repository=None,  # type: ignore[arg-type]
        dw_mysql_repository=ControlledRepository(),  # type: ignore[arg-type]
        sql_validator=validator,
    )

    encoded = [item async for item in service.query_answer("2018年5月GMV是多少？")]
    payloads = [json.loads(item.removeprefix("data: ")) for item in encoded]
    result = next(item for item in payloads if item["type"] == "result")

    assert result["intent"] == "QUERY"
    assert result["data"] == [{"gmv": "992871.75"}]
    assert not (_nested_keys(result["analysis_trace"]) & FORBIDDEN_TRACE_KEYS)


@pytest.mark.asyncio
async def test_reported_grouped_topn_question_enters_query_branch(monkeypatch: Any) -> None:
    _, validator = _catalog_and_validator()
    monkeypatch.setattr(query_service_module, "nl2sql_graph", FakeNL2SQLGraph())
    service = QueryService(
        embedding_client=None,  # type: ignore[arg-type]
        column_qdrant_repository=None,  # type: ignore[arg-type]
        metric_qdrant_repository=None,  # type: ignore[arg-type]
        value_es_repository=None,  # type: ignore[arg-type]
        meta_mysql_repository=None,  # type: ignore[arg-type]
        dw_mysql_repository=ControlledRepository(),  # type: ignore[arg-type]
        sql_validator=validator,
    )

    encoded = [
        item
        async for item in service.query_answer("2018 年各州前三的销售额的商品")
    ]
    result = next(
        json.loads(item.removeprefix("data: "))
        for item in encoded
        if json.loads(item.removeprefix("data: "))["type"] == "result"
    )

    assert result["intent"] == "QUERY"
    assert result["analysis_trace"][0]["reason"] == "explicit_data_query"


@pytest.mark.asyncio
async def test_query_graph_without_result_emits_safe_terminal_error(monkeypatch: Any) -> None:
    _, validator = _catalog_and_validator()
    monkeypatch.setattr(query_service_module, "nl2sql_graph", ValidationFailureGraph())
    service = QueryService(
        embedding_client=None,  # type: ignore[arg-type]
        column_qdrant_repository=None,  # type: ignore[arg-type]
        metric_qdrant_repository=None,  # type: ignore[arg-type]
        value_es_repository=None,  # type: ignore[arg-type]
        meta_mysql_repository=None,  # type: ignore[arg-type]
        dw_mysql_repository=None,  # type: ignore[arg-type]
        sql_validator=validator,
    )

    encoded = [item async for item in service.query_answer("各州GMV排名")]
    payloads = [json.loads(item.removeprefix("data: ")) for item in encoded]
    terminals = [item for item in payloads if item["type"] in {"result", "error"}]

    assert terminals == [
        {
            "type": "error",
            "code": "QUERY_VALIDATION_FAILED",
            "message": "生成的查询未能通过安全校验，请调整问题后重试。",
        }
    ]


@pytest.mark.asyncio
async def test_complete_diagnosis_is_ready_and_keeps_existing_graph() -> None:
    _, validator = _catalog_and_validator()
    service = QueryService(
        embedding_client=None,  # type: ignore[arg-type]
        column_qdrant_repository=None,  # type: ignore[arg-type]
        metric_qdrant_repository=None,  # type: ignore[arg-type]
        value_es_repository=None,  # type: ignore[arg-type]
        meta_mysql_repository=None,  # type: ignore[arg-type]
        dw_mysql_repository=ControlledRepository(),  # type: ignore[arg-type]
        sql_validator=validator,
    )

    encoded = [
        item
        async for item in service.query_answer("为什么2018年5月GMV下降？")
    ]
    payloads = [json.loads(item.removeprefix("data: ")) for item in encoded]
    result = next(item for item in payloads if item["type"] == "result")

    assert result["intent"] == "DIAGNOSIS"
    assert result["binding_status"] == "READY"
    assert result["report_status"] == "DEGRADED"
    assert [item["stage"] for item in result["analysis_trace"]] == [
        "intent_router",
        "semantic_grounding",
        "analysis_question_parser",
        "capability_assessment",
        "analysis_planner",
        "analysis_task_executor",
        "deterministic_analyzer",
        "evidence_checker",
        "report_generator",
    ]


@pytest.mark.asyncio
async def test_incomplete_diagnosis_returns_clarification_before_data_access() -> None:
    _, validator = _catalog_and_validator()
    binding = SemanticBindingResult(
        status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
        reason="missing_current_period",
        missing_fields=(BindingField.TIME,),
        suggested_question="为什么 2018 年 5 月 GMV 相比 2018 年 4 月下降？",
    )
    grounder = StubSemanticGrounder(binding)
    service = QueryService(
        embedding_client=None,  # type: ignore[arg-type]
        column_qdrant_repository=None,  # type: ignore[arg-type]
        metric_qdrant_repository=None,  # type: ignore[arg-type]
        value_es_repository=None,  # type: ignore[arg-type]
        meta_mysql_repository=None,  # type: ignore[arg-type]
        dw_mysql_repository=None,  # type: ignore[arg-type]
        sql_validator=validator,
        semantic_grounder=grounder,  # type: ignore[arg-type]
    )

    encoded = [item async for item in service.query_answer("为什么GMV下降？")]
    payloads = [json.loads(item.removeprefix("data: ")) for item in encoded]
    result = next(item for item in payloads if item["type"] == "result")

    assert grounder.calls == [("为什么GMV下降？", Intent.DIAGNOSIS)]
    assert result["intent"] == "DIAGNOSIS"
    assert result["binding_status"] == "CLARIFICATION_REQUIRED"
    assert result["report_status"] == "CLARIFICATION_REQUIRED"
    assert result["clarification"] == {
        "reason": "missing_current_period",
        "missing_fields": ["time"],
        "ambiguous_fields": [],
        "candidates": {"metrics": [], "dimensions": [], "values": []},
        "suggested_question": "为什么 2018 年 5 月 GMV 相比 2018 年 4 月下降？",
    }
    assert "时间" in result["answer"]
    assert result["evidence"] == []
    assert [item["stage"] for item in result["analysis_trace"]] == [
        "intent_router",
        "semantic_grounding",
    ]


@pytest.mark.asyncio
async def test_missing_metric_router_outcome_enters_controlled_clarification() -> None:
    _, validator = _catalog_and_validator()
    binding = SemanticBindingResult(
        status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
        reason="missing_or_unknown_metric",
        missing_fields=(BindingField.METRIC,),
        suggested_question="为什么 2018 年 5 月 GMV 相比 2018 年 4 月下降？",
    )
    grounder = StubSemanticGrounder(binding)
    service = QueryService(
        embedding_client=None,  # type: ignore[arg-type]
        column_qdrant_repository=None,  # type: ignore[arg-type]
        metric_qdrant_repository=None,  # type: ignore[arg-type]
        value_es_repository=None,  # type: ignore[arg-type]
        meta_mysql_repository=None,  # type: ignore[arg-type]
        dw_mysql_repository=None,  # type: ignore[arg-type]
        sql_validator=validator,
        semantic_grounder=grounder,  # type: ignore[arg-type]
    )

    encoded = [item async for item in service.query_answer("为什么2018年5月下降？")]
    result = json.loads(encoded[-1].removeprefix("data: "))

    assert grounder.calls == [("为什么2018年5月下降？", Intent.DIAGNOSIS)]
    assert result["intent"] == "DIAGNOSIS"
    assert result["binding_status"] == "CLARIFICATION_REQUIRED"
    assert result["clarification"]["missing_fields"] == ["metric"]


@pytest.mark.asyncio
async def test_binding_candidates_are_logical_and_unsupported_is_controlled() -> None:
    _, validator = _catalog_and_validator()
    binding = SemanticBindingResult(
        status=SemanticBindingStatus.UNSUPPORTED,
        reason="metric_not_supported",
        candidates=SemanticCandidateBundle(
            metrics=(
                MetricGroundingCandidate(
                    metric_id="order_count",
                    score=0.94,
                    supported_for_diagnosis=False,
                ),
            ),
            dimensions=(
                DimensionGroundingCandidate(
                    dimension=AnalysisDimension.REGION,
                    score=0.82,
                ),
            ),
            values=(
                ValueGroundingCandidate(
                    dimension=AnalysisDimension.REGION,
                    canonical_value="PR",
                ),
            ),
        ),
        retrieval_used=True,
    )
    service = QueryService(
        embedding_client=None,  # type: ignore[arg-type]
        column_qdrant_repository=None,  # type: ignore[arg-type]
        metric_qdrant_repository=None,  # type: ignore[arg-type]
        value_es_repository=None,  # type: ignore[arg-type]
        meta_mysql_repository=None,  # type: ignore[arg-type]
        dw_mysql_repository=None,  # type: ignore[arg-type]
        sql_validator=validator,
        semantic_grounder=StubSemanticGrounder(binding),  # type: ignore[arg-type]
    )

    encoded = [item async for item in service.query_answer("为什么订单量下降？")]
    result = json.loads(encoded[-1].removeprefix("data: "))

    assert result["intent"] == "UNSUPPORTED"
    assert result["binding_status"] == "UNSUPPORTED"
    assert result["clarification"]["candidates"] == {
        "metrics": ["order_count"],
        "dimensions": ["region"],
        "values": [{"dimension": "region", "value": "PR"}],
    }
    serialized = json.dumps(result)
    assert "score" not in serialized
    assert "retrieval_used" not in serialized
    assert not (_nested_keys(result) & FORBIDDEN_TRACE_KEYS)


def test_retrieval_ready_binding_can_be_reparsed_without_graph_changes() -> None:
    catalog, _ = _catalog_and_validator()
    parser = AnalysisQuestionParser.from_catalog(catalog)
    original = parser.parse(
        "为什么2018年5月圣保罗州GMV下降？",
        Intent.DIAGNOSIS,
    ).parsed_question
    assert original is not None

    canonical = _canonical_analysis_question(original)
    reparsed = parser.parse(canonical, Intent.DIAGNOSIS).parsed_question

    assert ParsedAnalysisQuestion.model_validate(reparsed) == original


@pytest.mark.asyncio
async def test_unsupported_request_degrades_without_touching_data_paths() -> None:
    _, validator = _catalog_and_validator()
    service = QueryService(
        embedding_client=None,  # type: ignore[arg-type]
        column_qdrant_repository=None,  # type: ignore[arg-type]
        metric_qdrant_repository=None,  # type: ignore[arg-type]
        value_es_repository=None,  # type: ignore[arg-type]
        meta_mysql_repository=None,  # type: ignore[arg-type]
        dw_mysql_repository=None,  # type: ignore[arg-type]
        sql_validator=validator,
    )

    encoded = [item async for item in service.query_answer("帮我自动调价")]
    result = json.loads(encoded[-1].removeprefix("data: "))

    assert result["type"] == "result"
    assert result["intent"] == "UNSUPPORTED"
    assert result["data"] == []
    assert result["limitations"] == ["future_or_external_action_unsupported"]
    assert result["answer"] == "V1 不支持预测或自动执行操作，可改为查询已有数据。"


@pytest.mark.parametrize(
    "reason,expected_text",
    (
        ("empty_question", "完整的单轮数据问题"),
        ("multi_turn_anaphora_unsupported", "省略式追问"),
        ("strict_causal_request_unsupported", "严格因果"),
        ("non_gmv_diagnosis_unsupported", "诊断仅支持 GMV"),
        ("semantic_low_confidence", "补充指标"),
        ("semantic_classifier_unavailable", "语义识别暂不可用"),
        ("semantic_domain_mismatch", "已注册的电商指标"),
        ("ambiguous_or_incomplete_question", "时间范围"),
    ),
)
def test_unsupported_guidance_is_reason_specific_and_safe(
    reason: str,
    expected_text: str,
) -> None:
    result = _unsupported_result(
        IntentDecision(intent=Intent.UNSUPPORTED, confidence=0.5, reason=reason)
    )

    assert expected_text in result["answer"]
    assert result["limitations"] == [reason]
    assert not (_nested_keys(result) & FORBIDDEN_TRACE_KEYS)
