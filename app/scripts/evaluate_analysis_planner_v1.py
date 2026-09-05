from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.diagnosis.capability import AnalysisMethod, CapabilityAssessment
from app.diagnosis.planner import AnalysisPlanner, TaskMethod
from app.diagnosis.question import ParsedAnalysisQuestion

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "data" / "evaluation" / "analysis_planner_golden_v1.json"
REPORT_PATH = ROOT / "data" / "reports" / "ANA-004_analysis_planner_evaluation.json"


def _summary(plan_payload: dict[str, Any]) -> dict[str, Any]:
    tasks = plan_payload["tasks"]
    dimensions: list[Any] = next(
        (task["dimensions"] for task in tasks if task["method"] == "dimension_contribution"),
        [],
    )
    factors: list[Any] = next(
        (task["factors"] for task in tasks if task["method"] == "candidate_validation"),
        [],
    )
    return {
        "task_ids": [task["task_id"] for task in tasks],
        "methods": [task["method"] for task in tasks],
        "dimensions": dimensions,
        "factors": factors,
        "stop_reason": plan_payload["stop_reason"],
        "missing_evidence": plan_payload["missing_evidence"],
    }


def main() -> int:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    planner = AnalysisPlanner()
    results: list[dict[str, Any]] = []
    bounded_count = 0
    dependency_count = 0
    parameter_reuse_count = 0
    unsupported_selection_count = 0
    sql_field_count = 0

    factor_capability = {
        "traffic": AnalysisMethod.TRAFFIC_VALIDATION.value,
        "promotion": AnalysisMethod.PROMOTION_VALIDATION.value,
        "inventory": AnalysisMethod.INVENTORY_VALIDATION.value,
    }
    method_capability = {
        TaskMethod.PERIOD_COMPARISON.value: AnalysisMethod.PERIOD_COMPARISON.value,
        TaskMethod.METRIC_DECOMPOSITION.value: AnalysisMethod.METRIC_DECOMPOSITION.value,
        TaskMethod.DIMENSION_CONTRIBUTION.value: AnalysisMethod.DIMENSION_CONTRIBUTION.value,
    }

    for case in golden["cases"]:
        question = ParsedAnalysisQuestion.model_validate(case["question"])
        capability = CapabilityAssessment.model_validate(case["capability"])
        payload = planner.plan(question, capability).model_dump(mode="json")
        actual = _summary(payload)
        supported = set(case["capability"]["supported_methods"])
        selected_methods = actual["methods"]
        selected_factors = actual["factors"]
        bounded = len(payload["tasks"]) <= 4
        dependencies_valid = all(
            task["depends_on"] == ([] if index == 0 else ["T1"])
            for index, task in enumerate(payload["tasks"])
        )
        parameters_reused = all(
            task["metric"] == question.target_metric
            and task["current_period"] == question.current_period.model_dump(mode="json")
            and task["baseline_period"] == question.baseline_period.model_dump(mode="json")
            and task["scope"] == question.scope.model_dump(mode="json")
            for task in payload["tasks"]
        )
        unsupported_selected = sum(
            method_capability[method] not in supported
            for method in selected_methods
            if method in method_capability
        ) + sum(factor_capability[factor] not in supported for factor in selected_factors)
        sql_fields = _count_key(payload, "sql")
        matched = actual == case["expected"]

        bounded_count += int(bounded)
        dependency_count += int(dependencies_valid)
        parameter_reuse_count += int(parameters_reused)
        unsupported_selection_count += unsupported_selected
        sql_field_count += sql_fields
        results.append(
            {
                "case_id": case["case_id"],
                "group": case["group"],
                "expected": case["expected"],
                "actual": actual,
                "match": matched,
                "bounded": bounded,
                "dependencies_valid": dependencies_valid,
                "parameters_reused": parameters_reused,
                "unsupported_selected": unsupported_selected,
                "sql_fields": sql_fields,
            }
        )

    total = len(results)
    exact = sum(result["match"] for result in results)
    report = {
        "feature": "ANA-004",
        "golden_version": golden["version"],
        "case_count": total,
        "exact_match_count": exact,
        "exact_match_rate": exact / total,
        "bounded_plan_count": bounded_count,
        "valid_dependency_count": dependency_count,
        "parameter_reuse_count": parameter_reuse_count,
        "unsupported_method_selection_count": unsupported_selection_count,
        "sql_field_count": sql_field_count,
        "passed": (
            exact == total
            and bounded_count == total
            and dependency_count == total
            and parameter_reuse_count == total
            and unsupported_selection_count == 0
            and sql_field_count == 0
        ),
        "cases": results,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}))
    return 0 if report["passed"] else 1


def _count_key(value: Any, target: str) -> int:
    if isinstance(value, dict):
        return int(target in value) + sum(_count_key(item, target) for item in value.values())
    if isinstance(value, list):
        return sum(_count_key(item, target) for item in value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
