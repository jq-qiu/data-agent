"""运行确定性 Analyzer 的数值与对账评测。"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from app.diagnosis.analyzer import MAX_ANALYSIS_RESULTS, DeterministicAnalyzer
from app.diagnosis.planner import AnalysisPlan, AnalysisTask, TaskMethod
from app.diagnosis.query import (
    AnalysisQueryResult,
    MetricLineage,
    QueryValidationTrace,
)
from app.diagnosis.question import (
    AnalysisDimension,
    AnalysisScope,
    CandidateFactor,
    DatePeriod,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "data" / "evaluation" / "deterministic_analyzer_golden_v1.json"
REPORT_PATH = (
    ROOT / "data" / "reports" / "ANA-006_deterministic_analyzer_evaluation.json"
)


def _task(
    task_id: str,
    method: TaskMethod,
    *,
    dimensions: tuple[AnalysisDimension, ...] = (),
    factors: tuple[CandidateFactor, ...] = (),
) -> AnalysisTask:
    return AnalysisTask(
        task_id=task_id,
        method=method,
        metric="gmv",
        current_period=DatePeriod(start=date(2018, 5, 1), end=date(2018, 5, 31)),
        baseline_period=DatePeriod(start=date(2018, 4, 1), end=date(2018, 4, 30)),
        scope=AnalysisScope(),
        dimensions=dimensions,
        factors=factors,
        depends_on=() if task_id == "T1" else ("T1",),
    )


def _query(
    query_id: str,
    task: AnalysisTask,
    role: str,
    rows: Sequence[dict[str, Any]],
) -> AnalysisQueryResult:
    metric_ids = {
        "period_comparison": ("gmv",),
        "metric_decomposition": ("gmv", "order_count", "aov"),
        "candidate_validation": (
            "order_count",
            "visitors",
            "conversion_rate",
            "promotion_coverage",
            "inventory_fill_rate",
        ),
    }.get(role, ("gmv",))
    return AnalysisQueryResult(
        query_id=query_id,
        task_id=task.task_id,
        method=task.method,
        query_role=role,
        sql_fingerprint="b" * 64,
        catalog_version="metadata-v1",
        metric_versions=tuple(
            MetricLineage(metric_id=metric_id, version="v1")
            for metric_id in metric_ids
        ),
        validation=QueryValidationTrace(
            tables=("evaluation_fixture",),
            columns=("evaluation_fixture.value",),
            join_relations=(),
            grain_warnings=(),
            policy_version="sql-policy-v1",
            max_rows=100,
            timeout_seconds=5,
        ),
        rows=tuple(rows),
    )


def _case_contract(case: Mapping[str, Any]) -> tuple[AnalysisPlan, list[AnalysisQueryResult]]:
    case_input = case["input"]
    kind = case["kind"]
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    if kind == "dimension":
        baseline = case_input["overall_baseline"]
        current = case_input["overall_current"]
    elif kind == "shapley":
        baseline = case_input["baseline_gmv"]
        current = case_input["current_gmv"]
    else:
        baseline = case_input.get("baseline", "100")
        current = case_input.get("current", "80")
    queries = [
        _query(
            "Q001",
            period,
            "period_comparison",
            [
                {"period_role": "baseline", "gmv": baseline},
                {"period_role": "current", "gmv": current},
            ],
        )
    ]
    if kind == "period":
        return AnalysisPlan(tasks=(period,)), queries
    if kind == "shapley":
        downstream = _task("T2", TaskMethod.METRIC_DECOMPOSITION)
        queries.append(
            _query(
                "Q002",
                downstream,
                "metric_decomposition",
                [
                    {
                        "period_role": "baseline",
                        "gmv": baseline,
                        "order_count": case_input["baseline_orders"],
                    },
                    {
                        "period_role": "current",
                        "gmv": current,
                        "order_count": case_input["current_orders"],
                    },
                ],
            )
        )
    elif kind == "dimension":
        dimension = AnalysisDimension(case_input["dimension"])
        downstream = _task(
            "T2",
            TaskMethod.DIMENSION_CONTRIBUTION,
            dimensions=(dimension,),
        )
        queries.append(
            _query(
                "Q002",
                downstream,
                f"dimension_contribution:{dimension.value}",
                case_input["rows"],
            )
        )
    else:
        factors = tuple(CandidateFactor(value) for value in case_input["factors"])
        downstream = _task(
            "T2", TaskMethod.CANDIDATE_VALIDATION, factors=factors
        )
        queries.append(
            _query(
                "Q002", downstream, "candidate_validation", case_input["rows"]
            )
        )
    return AnalysisPlan(tasks=(period, downstream)), queries


def _path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_nested_keys(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(_nested_keys(item) for item in value))
    return set()


def _evaluate() -> dict[str, Any]:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    case_results: list[dict[str, Any]] = []
    forbidden_keys = {"sql", "parameters", "sql_fingerprint", "validation"}
    for case in golden["cases"]:
        plan, queries = _case_contract(case)
        output = DeterministicAnalyzer().analyze(plan, queries)
        serialized = [result.model_dump(mode="json") for result in output]
        actual = {path: _path(serialized, path) for path in case["expected"]}
        exact = actual == case["expected"]
        ids_valid = [result.analysis_result_id for result in output] == [
            f"A{index:03d}" for index in range(1, len(output) + 1)
        ]
        lineage_complete = all(result.metric_versions for result in output)
        bounded = len(output) <= MAX_ANALYSIS_RESULTS
        output_safe = not (forbidden_keys & _nested_keys(serialized))
        case_results.append(
            {
                "case_id": case["case_id"],
                "group": case["group"],
                "expected": case["expected"],
                "actual": actual,
                "exact_match": exact,
                "analysis_result_ids_valid": ids_valid,
                "lineage_complete": lineage_complete,
                "bounded": bounded,
                "output_safe": output_safe,
            }
        )
    total = len(case_results)
    counters = {
        key: sum(bool(case[key]) for case in case_results)
        for key in (
            "exact_match",
            "analysis_result_ids_valid",
            "lineage_complete",
            "bounded",
            "output_safe",
        )
    }
    return {
        "feature": "ANA-006",
        "golden_version": golden["version"],
        "case_count": total,
        **{f"{key}_count": value for key, value in counters.items()},
        "passed": all(value == total for value in counters.values()),
        "cases": case_results,
    }


def main() -> int:
    report = _evaluate()
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
