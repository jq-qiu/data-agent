from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from app.diagnosis.analyzer import AnalysisResult, DeterministicAnalyzer
from app.diagnosis.evidence import (
    EvidenceChecker,
    EvidenceSupportLevel,
    EvidenceType,
)
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
from app.diagnosis.report import ReportGenerator, ReportStatementKind

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "data" / "evaluation" / "evidence_report_golden_v1.json"
REPORT_PATH = ROOT / "data" / "reports" / "ANA-007_evidence_report_evaluation.json"
_FORBIDDEN = ("导致", "造成", "证明", "唯一原因", "一定能够", "必然提升")


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
        scope=AnalysisScope(region="SP"),
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
    metrics = {
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
        sql_fingerprint="d" * 64,
        catalog_version="metadata-v1",
        metric_versions=tuple(
            MetricLineage(metric_id=metric, version="v1") for metric in metrics
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


def _contract(case: Mapping[str, Any]) -> tuple[AnalysisPlan, tuple[AnalysisResult, ...]]:
    case_input = case["input"]
    baseline = case_input["baseline_gmv"]
    current = case_input["current_gmv"]
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
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
    if case["kind"] == "candidate":
        factors = tuple(CandidateFactor(value) for value in case_input["factors"])
        downstream = _task(
            "T2", TaskMethod.CANDIDATE_VALIDATION, factors=factors
        )
        queries.append(
            _query(
                "Q002", downstream, "candidate_validation", case_input["rows"]
            )
        )
    elif case["kind"] == "shapley":
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
    else:
        downstream = _task(
            "T2",
            TaskMethod.DIMENSION_CONTRIBUTION,
            dimensions=(AnalysisDimension.REGION,),
        )
        queries.append(
            _query(
                "Q002",
                downstream,
                "dimension_contribution:region",
                case_input["rows"],
            )
        )
    plan = AnalysisPlan(
        tasks=(period, downstream),
        missing_evidence=tuple(case_input.get("missing_evidence", ())),
    )
    return plan, DeterministicAnalyzer().analyze(plan, queries)


def _path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_nested_keys(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(_nested_keys(item) for item in value))
    return set()


def _evaluate() -> dict[str, Any]:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    forbidden_keys = {"sql", "parameters", "sql_fingerprint", "validation"}
    for case in golden["cases"]:
        plan, analysis_results = _contract(case)
        bundle = EvidenceChecker().check(plan, analysis_results)
        report = ReportGenerator().generate(bundle)
        payload = {
            "bundle": bundle.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
        }
        actual = {path: _path(payload, path) for path in case["expected"]}
        evidence_ids_valid = [item.evidence_id for item in bundle.evidence] == [
            f"E{index:03d}" for index in range(1, len(bundle.evidence) + 1)
        ]
        lineage_complete = all(
            item.analysis_result_ids and item.query_ids and item.metric_versions
            for item in bundle.evidence
        )
        unsupported_conclusions = sum(
            statement.kind is ReportStatementKind.CONCLUSION
            and any(
                next(
                    item for item in bundle.evidence if item.evidence_id == evidence_id
                ).support_level
                is EvidenceSupportLevel.UNSUPPORTED
                for evidence_id in statement.evidence_ids
            )
            for section in report.sections
            for statement in section.statements
        )
        output_safe = not (forbidden_keys & _nested_keys(payload))
        causal_violations = sum(term in report.markdown for term in _FORBIDDEN)
        candidate_evidence_count = sum(
            item.evidence_type is EvidenceType.CANDIDATE_FACTOR
            for item in bundle.evidence
        )
        cases.append(
            {
                "case_id": case["case_id"],
                "group": case["group"],
                "expected": case["expected"],
                "actual": actual,
                "exact_match": actual == case["expected"],
                "evidence_ids_valid": evidence_ids_valid,
                "lineage_complete": lineage_complete,
                "unsupported_conclusion_count": unsupported_conclusions,
                "causal_language_violation_count": causal_violations,
                "output_safe": output_safe,
                "candidate_evidence_count": candidate_evidence_count,
            }
        )
    total = len(cases)
    exact = sum(case["exact_match"] for case in cases)
    ids = sum(case["evidence_ids_valid"] for case in cases)
    lineage = sum(case["lineage_complete"] for case in cases)
    safe = sum(case["output_safe"] for case in cases)
    unsupported = sum(case["unsupported_conclusion_count"] for case in cases)
    causal = sum(case["causal_language_violation_count"] for case in cases)
    return {
        "feature": "ANA-007",
        "golden_version": golden["version"],
        "case_count": total,
        "exact_match_count": exact,
        "valid_evidence_id_count": ids,
        "complete_lineage_count": lineage,
        "safe_output_count": safe,
        "unsupported_conclusion_count": unsupported,
        "causal_language_violation_count": causal,
        "passed": all(value == total for value in (exact, ids, lineage, safe))
        and unsupported == 0
        and causal == 0,
        "cases": cases,
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
