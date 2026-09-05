from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import sqlglot
from pydantic import ValidationError

from app.diagnosis.capability import (
    AnalysisMethod,
    CapabilityAssessment,
    CapabilityLevel,
    DataQualityStatus,
)
from app.diagnosis.planner import AnalysisPlan, AnalysisPlanner
from app.diagnosis.query import (
    MAX_ANALYSIS_QUERIES,
    AnalysisQueryBuilder,
    AnalysisQueryBuildError,
    AnalysisQueryContext,
    AnalysisQueryExecutionError,
    AnalysisTaskExecutor,
    AnalysisTaskExecutorNode,
    QueryDataSource,
)
from app.diagnosis.question import (
    AnalysisDimension,
    AnalysisScope,
    CandidateFactor,
    ComparisonType,
    DatePeriod,
    ParsedAnalysisQuestion,
)
from app.metadata.catalog import MetadataCatalog, load_catalog
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.validator import SQLValidationError, SQLValidator, ValidatedSQL

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def catalog() -> MetadataCatalog:
    return load_catalog(ROOT / "conf" / "meta_config.yaml")


@pytest.fixture(scope="module")
def validator(catalog: MetadataCatalog) -> SQLValidator:
    return SQLValidator(catalog, load_sql_policy(ROOT / "conf" / "sql_policy.yaml"))


def _question(
    *,
    scope: AnalysisScope | None = None,
    dimensions: tuple[AnalysisDimension, ...] = tuple(AnalysisDimension),
    factors: tuple[CandidateFactor, ...] = tuple(CandidateFactor),
) -> ParsedAnalysisQuestion:
    return ParsedAnalysisQuestion(
        target_metric="gmv",
        current_period=DatePeriod(start=date(2018, 5, 1), end=date(2018, 5, 31)),
        baseline_period=DatePeriod(start=date(2018, 4, 1), end=date(2018, 4, 30)),
        comparison_type=ComparisonType.PREVIOUS_PERIOD,
        scope=scope or AnalysisScope(),
        requested_dimensions=dimensions,
        requested_factors=factors,
    )


def _plan(
    *,
    scope: AnalysisScope | None = None,
    dimensions: tuple[AnalysisDimension, ...] = tuple(AnalysisDimension),
    factors: tuple[CandidateFactor, ...] = tuple(CandidateFactor),
) -> AnalysisPlan:
    question = _question(scope=scope, dimensions=dimensions, factors=factors)
    capability = CapabilityAssessment(
        level=CapabilityLevel.ASSOCIATION_DIAGNOSIS,
        supported_methods=(
            AnalysisMethod.PERIOD_COMPARISON,
            AnalysisMethod.METRIC_DECOMPOSITION,
            AnalysisMethod.DIMENSION_CONTRIBUTION,
            AnalysisMethod.TRAFFIC_VALIDATION,
            AnalysisMethod.PROMOTION_VALIDATION,
            AnalysisMethod.INVENTORY_VALIDATION,
        ),
        unsupported_methods=(AnalysisMethod.CAUSAL_INFERENCE,),
        available_dimensions=tuple(AnalysisDimension),
        missing_evidence=(),
        data_quality_status=DataQualityStatus.PASS,
    )
    return AnalysisPlanner().plan(question, capability)


class RecordingRepository:
    def __init__(self, *, wrong_shape: bool = False) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []
        self.wrong_shape = wrong_shape

    async def validate_sql(
        self,
        validated_sql: ValidatedSQL,
        parameters: dict[str, object] | None = None,
    ) -> None:
        self.events.append(("explain", dict(parameters or {})))

    async def execute_sql(
        self,
        validated_sql: ValidatedSQL,
        parameters: dict[str, object] | None = None,
    ) -> list[dict[str, Any]]:
        self.events.append(("execute", dict(parameters or {})))
        if self.wrong_shape:
            return [{"unexpected": 1}]
        columns = tuple(sqlglot.parse_one(validated_sql.sql, read="mysql").named_selects)
        return [{column: "baseline" if column == "period_role" else 1 for column in columns}]


class RejectingValidator:
    def validate(self, sql: str, metric_ids: tuple[str, ...] = ()) -> ValidatedSQL:
        raise SQLValidationError("rejected for test")


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_nested_keys(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(_nested_keys(item) for item in value))
    return set()


@pytest.mark.parametrize(
    "payload",
    [
        {"source": "synthetic_case"},
        {"source": "warehouse", "case_id": "D01"},
        {"source": "synthetic_case", "case_id": "D11"},
        {"source": "warehouse", "unknown": True},
    ],
)
def test_query_context_rejects_invalid_source_scope(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AnalysisQueryContext.model_validate(payload)


def test_full_plan_builds_five_valid_queries_in_fixed_order(
    catalog: MetadataCatalog,
    validator: SQLValidator,
) -> None:
    builder = AnalysisQueryBuilder(
        catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
    )

    queries = tuple(query for task in _plan().tasks for query in builder.build(task))

    assert len(queries) == MAX_ANALYSIS_QUERIES
    assert [query.query_role for query in queries] == [
        "period_comparison",
        "metric_decomposition",
        "dimension_contribution:region",
        "dimension_contribution:category",
        "candidate_validation",
    ]
    assert all(validator.validate(query.sql, query.validation_metric_ids) for query in queries)


def test_dates_and_scope_are_bound_not_interpolated(catalog: MetadataCatalog) -> None:
    scope = AnalysisScope(region="SP", category="informatica_acessorios")
    builder = AnalysisQueryBuilder(
        catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
    )
    query = builder.build(_plan(scope=scope).tasks[0])[0]

    assert set(query.parameters) == {
        "baseline_start",
        "baseline_end",
        "current_start",
        "current_end",
        "region",
        "category",
    }
    assert query.parameters["baseline_start"] == 20180401
    assert query.parameters["current_end"] == 20180531
    assert "20180401" not in query.sql
    assert "SP" not in query.sql
    assert "informatica_acessorios" not in query.sql
    assert ":region" in query.sql and ":category" in query.sql


def test_overall_decomposition_uses_only_region_order_count(
    catalog: MetadataCatalog,
    validator: SQLValidator,
) -> None:
    builder = AnalysisQueryBuilder(
        catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
    )
    query = builder.build(_plan().tasks[1])[0]
    validated = validator.validate(query.sql, query.validation_metric_ids)

    assert validated.tables == ("dws_sales_region_daily",)
    assert "dws_sales_region_daily.order_count" in validated.columns
    assert "category_order_count" not in query.sql


def test_category_decomposition_uses_category_order_only_with_category_scope(
    catalog: MetadataCatalog,
    validator: SQLValidator,
) -> None:
    scope = AnalysisScope(category="informatica_acessorios")
    builder = AnalysisQueryBuilder(
        catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
    )
    query = builder.build(_plan(scope=scope).tasks[1])[0]
    validated = validator.validate(query.sql, query.validation_metric_ids)

    assert validated.tables == ("dws_sales_category_daily",)
    assert "dws_sales_category_daily.category_order_count" in validated.columns
    assert query.parameters["category"] == "informatica_acessorios"


def test_dimension_queries_keep_region_and_category_grains_separate(
    catalog: MetadataCatalog,
    validator: SQLValidator,
) -> None:
    builder = AnalysisQueryBuilder(
        catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
    )
    queries = builder.build(_plan().tasks[2])
    region = validator.validate(queries[0].sql, queries[0].validation_metric_ids)
    category = validator.validate(queries[1].sql, queries[1].validation_metric_ids)

    assert region.tables == ("dws_sales_region_daily",)
    assert "dws_sales_region_daily.region_id" in region.columns
    assert category.tables == ("dws_sales_category_daily",)
    assert "dws_sales_category_daily.category_id" in category.columns


def test_candidate_query_returns_additive_components_without_ratio_math(
    catalog: MetadataCatalog,
    validator: SQLValidator,
) -> None:
    builder = AnalysisQueryBuilder(
        catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
    )
    query = builder.build(_plan().tasks[3])[0]
    validated = validator.validate(query.sql, query.validation_metric_ids)

    assert set(query.output_columns) == {
        "period_role",
        "order_count",
        "visitors",
        "promoted_sku_count",
        "active_sku_count",
        "available_sku_count",
        "required_sku_count",
    }
    assert "/" not in query.sql
    assert set(validated.tables) == {"dws_sales_region_daily"}


def test_synthetic_queries_require_and_bind_case_id(
    catalog: MetadataCatalog,
    validator: SQLValidator,
) -> None:
    builder = AnalysisQueryBuilder(
        catalog,
        AnalysisQueryContext(source=QueryDataSource.SYNTHETIC_CASE, case_id="D05"),
    )
    queries = tuple(query for task in _plan().tasks for query in builder.build(task))

    assert all(query.parameters["case_id"] == "D05" for query in queries)
    assert all("D05" not in query.sql and ":case_id" in query.sql for query in queries)
    assert validator.validate(
        queries[0].sql, queries[0].validation_metric_ids
    ).tables == (
        "analysis_sales_region_daily",
    )
    assert validator.validate(
        queries[3].sql, queries[3].validation_metric_ids
    ).tables == (
        "analysis_sales_category_daily",
    )


def test_builder_rejects_missing_registry_column(catalog: MetadataCatalog) -> None:
    region = catalog.table_map["dws_sales_region_daily"]
    damaged_region = replace(
        region,
        columns=tuple(column for column in region.columns if column.name != "gmv"),
    )
    damaged_catalog = replace(
        catalog,
        tables=tuple(
            damaged_region if table.table_name == region.table_name else table
            for table in catalog.tables
        ),
    )

    with pytest.raises(AnalysisQueryBuildError, match="missing controlled query columns"):
        AnalysisQueryBuilder(
            damaged_catalog,
            AnalysisQueryContext(source=QueryDataSource.WAREHOUSE),
        )


@pytest.mark.asyncio
async def test_executor_validates_explains_then_executes_with_trace(
    catalog: MetadataCatalog,
    validator: SQLValidator,
) -> None:
    repository = RecordingRepository()
    executor = AnalysisTaskExecutor(
        AnalysisQueryBuilder(
            catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
        ),
        validator,
        repository,
    )

    results = await executor.execute(_plan())

    assert [result.query_id for result in results] == [
        "Q001",
        "Q002",
        "Q003",
        "Q004",
        "Q005",
    ]
    assert [event for event, _ in repository.events] == [
        "explain",
        "execute",
    ] * MAX_ANALYSIS_QUERIES
    payload = [result.model_dump(mode="json") for result in results]
    assert all(len(result["sql_fingerprint"]) == 64 for result in payload)
    assert "sql" not in _nested_keys(payload)
    assert "parameters" not in _nested_keys(payload)
    assert all(result["catalog_version"] == "metadata-v1" for result in payload)


@pytest.mark.asyncio
async def test_validator_failure_never_reaches_repository(catalog: MetadataCatalog) -> None:
    repository = RecordingRepository()
    executor = AnalysisTaskExecutor(
        AnalysisQueryBuilder(
            catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
        ),
        RejectingValidator(),  # type: ignore[arg-type]
        repository,
    )

    with pytest.raises(SQLValidationError, match="rejected for test"):
        await executor.execute(_plan(dimensions=(), factors=()))
    assert repository.events == []


@pytest.mark.asyncio
async def test_result_shape_mismatch_is_rejected(
    catalog: MetadataCatalog,
    validator: SQLValidator,
) -> None:
    executor = AnalysisTaskExecutor(
        AnalysisQueryBuilder(
            catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
        ),
        validator,
        RecordingRepository(wrong_shape=True),
    )

    with pytest.raises(AnalysisQueryExecutionError, match="unexpected result columns"):
        await executor.execute(_plan(dimensions=(), factors=()))


@pytest.mark.asyncio
async def test_empty_plan_executes_no_queries(
    catalog: MetadataCatalog,
    validator: SQLValidator,
) -> None:
    repository = RecordingRepository()
    executor = AnalysisTaskExecutor(
        AnalysisQueryBuilder(
            catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
        ),
        validator,
        repository,
    )
    empty = AnalysisPlan(tasks=(), stop_reason="INSUFFICIENT_DATA")

    assert await executor.execute(empty) == ()
    assert repository.events == []


@pytest.mark.asyncio
async def test_node_emits_only_serializable_query_results(
    catalog: MetadataCatalog,
    validator: SQLValidator,
) -> None:
    executor = AnalysisTaskExecutor(
        AnalysisQueryBuilder(
            catalog, AnalysisQueryContext(source=QueryDataSource.WAREHOUSE)
        ),
        validator,
        RecordingRepository(),
    )
    output = await AnalysisTaskExecutorNode(executor)(
        {
            "analysis_plan": _plan(dimensions=(), factors=()).model_dump(mode="json"),
            "repository": object(),
        }
    )

    assert set(output) == {"query_results"}
    assert "repository" not in str(output)
    assert "sql" not in _nested_keys(output)
    assert "parameters" not in _nested_keys(output)
