"""运行受控 AnalysisTask 查询构建与执行契约评测。"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
from collections.abc import Mapping
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from typing import Any

import sqlglot

from app.diagnosis.capability import (
    AnalysisMethod,
    CapabilityAssessment,
    CapabilityLevel,
    DataQualityStatus,
)
from app.diagnosis.planner import AnalysisPlanner
from app.diagnosis.query import (
    MAX_ANALYSIS_QUERIES,
    AnalysisQueryBuilder,
    AnalysisQueryContext,
    AnalysisTaskExecutor,
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
from app.metadata.catalog import load_catalog
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.validator import SQLValidator, ValidatedSQL

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "data" / "evaluation" / "analysis_task_executor_golden_v1.json"
REPORT_PATH = (
    ROOT / "data" / "reports" / "ANA-005_analysis_task_executor_evaluation.json"
)


class _EvaluationRepository:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def validate_sql(
        self,
        validated_sql: ValidatedSQL,
        parameters: Mapping[str, object] | None = None,
    ) -> None:
        self.events.append("explain")

    async def execute_sql(
        self,
        validated_sql: ValidatedSQL,
        parameters: Mapping[str, object] | None = None,
    ) -> list[dict[str, Any]]:
        self.events.append("execute")
        columns = sqlglot.parse_one(validated_sql.sql, read="mysql").named_selects
        return [
            {
                column: "baseline" if column == "period_role" else 1
                for column in columns
            }
        ]


def _question(case: dict[str, Any]) -> ParsedAnalysisQuestion:
    return ParsedAnalysisQuestion(
        target_metric="gmv",
        current_period=DatePeriod(start=date(2018, 5, 1), end=date(2018, 5, 31)),
        baseline_period=DatePeriod(start=date(2018, 4, 1), end=date(2018, 4, 30)),
        comparison_type=ComparisonType.PREVIOUS_PERIOD,
        scope=AnalysisScope.model_validate(case["scope"]),
        requested_dimensions=tuple(
            AnalysisDimension(value) for value in case["dimensions"]
        ),
        requested_factors=tuple(CandidateFactor(value) for value in case["factors"]),
    )


def _capability() -> CapabilityAssessment:
    return CapabilityAssessment(
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


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_nested_keys(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(_nested_keys(item) for item in value))
    return set()


async def _evaluate() -> dict[str, Any]:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    catalog = load_catalog(ROOT / "conf" / "meta_config.yaml")
    validator = SQLValidator(catalog, load_sql_policy(ROOT / "conf" / "sql_policy.yaml"))
    case_results: list[dict[str, Any]] = []

    for case in golden["cases"]:
        plan = AnalysisPlanner().plan(_question(case), _capability())
        builder = AnalysisQueryBuilder(
            catalog, AnalysisQueryContext.model_validate(case["context"])
        )
        queries = tuple(query for task in plan.tasks for query in builder.build(task))
        validated = [
            validator.validate(query.sql, query.validation_metric_ids) for query in queries
        ]
        actual = {
            "roles": [query.query_role for query in queries],
            "tables": [item.tables[0] for item in validated],
            "query_count": len(queries),
        }
        parameters_bound = all(
            all(str(value) not in query.sql for value in query.parameters.values())
            for query in queries
        )
        repository = _EvaluationRepository()
        results = await AnalysisTaskExecutor(builder, validator, repository).execute(plan)
        serialized = [result.model_dump(mode="json") for result in results]
        trace_safe = not ({"sql", "parameters"} & _nested_keys(serialized))
        ids_valid = [result.query_id for result in results] == [
            f"Q{index:03d}" for index in range(1, len(results) + 1)
        ]
        execution_order_valid = repository.events == ["explain", "execute"] * len(queries)
        bounded = len(queries) <= MAX_ANALYSIS_QUERIES
        matched = actual == case["expected"]
        case_results.append(
            {
                "case_id": case["case_id"],
                "group": case["group"],
                "expected": case["expected"],
                "actual": actual,
                "match": matched,
                "parameters_bound": parameters_bound,
                "trace_safe": trace_safe,
                "query_ids_valid": ids_valid,
                "execution_order_valid": execution_order_valid,
                "bounded": bounded,
            }
        )

    total = len(case_results)
    exact = sum(result["match"] for result in case_results)
    bound = sum(result["parameters_bound"] for result in case_results)
    safe = sum(result["trace_safe"] for result in case_results)
    ids = sum(result["query_ids_valid"] for result in case_results)
    ordered = sum(result["execution_order_valid"] for result in case_results)
    bounded_cases = sum(result["bounded"] for result in case_results)
    return {
        "feature": "ANA-005",
        "golden_version": golden["version"],
        "case_count": total,
        "exact_query_contract_count": exact,
        "bound_parameter_count": bound,
        "safe_trace_count": safe,
        "valid_query_id_count": ids,
        "valid_execution_order_count": ordered,
        "bounded_query_count": bounded_cases,
        "passed": all(
            value == total for value in (exact, bound, safe, ids, ordered, bounded_cases)
        ),
        "cases": case_results,
    }


async def _live_smoke() -> dict[str, Any]:
    from app.clients.mysql_client_manager import dw_mysql_client_manager
    from app.conf.app_config import app_config
    from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository

    if app_config.db_dw.database != "data_agent_v1_dw":
        raise RuntimeError("ANA-005 live smoke requires the isolated V1 database")

    catalog = load_catalog(ROOT / "conf" / "meta_config.yaml")
    validator = SQLValidator(catalog, load_sql_policy(ROOT / "conf" / "sql_policy.yaml"))
    case = {
        "scope": {"region": "SP", "category": "informatica_acessorios"},
        "dimensions": ["region", "category"],
        "factors": ["traffic", "promotion", "inventory"],
    }
    plan = AnalysisPlanner().plan(_question(case), _capability())
    builder = AnalysisQueryBuilder(
        catalog,
        AnalysisQueryContext(source=QueryDataSource.SYNTHETIC_CASE, case_id="D02"),
    )
    dw_mysql_client_manager.init()
    if dw_mysql_client_manager.session_factory is None:
        raise RuntimeError("isolated DW session factory did not initialize")
    try:
        async with dw_mysql_client_manager.session_factory() as session:
            captured_output = io.StringIO()
            with redirect_stdout(captured_output), redirect_stderr(captured_output):
                results = await AnalysisTaskExecutor(
                    builder,
                    validator,
                    DWMySQLRepository(session),
                ).execute(plan)
    finally:
        await dw_mysql_client_manager.close()

    queries = [
        {
            "query_id": result.query_id,
            "query_role": result.query_role,
            "row_count": len(result.rows),
            "sql_fingerprint": result.sql_fingerprint,
            "tables": list(result.validation.tables),
        }
        for result in results
    ]
    return {
        "database": "data_agent_v1_dw",
        "source": "synthetic_case",
        "case_id": "D02",
        "query_count": len(results),
        "all_queries_returned_rows": all(result.rows for result in results),
        "passed": len(results) == MAX_ANALYSIS_QUERIES and all(result.rows for result in results),
        "queries": queries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(_evaluate())
    if args.live:
        report["live_smoke"] = asyncio.run(_live_smoke())
        report["passed"] = bool(report["passed"] and report["live_smoke"]["passed"])
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
