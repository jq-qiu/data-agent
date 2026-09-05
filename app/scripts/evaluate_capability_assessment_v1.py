from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.diagnosis.capability import CapabilityAssessor, DataCapabilityProfile
from app.diagnosis.question import ParsedAnalysisQuestion
from app.metadata.catalog import load_catalog

ROOT = Path(__file__).parents[2]
DEFAULT_GOLDEN = ROOT / "data" / "evaluation" / "capability_assessment_golden_v1.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "ANA-003_capability_assessment_evaluation.json"
DEFAULT_CATALOG = ROOT / "conf" / "meta_config.yaml"


def _source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def evaluate(
    golden_path: Path = DEFAULT_GOLDEN,
    catalog_path: Path = DEFAULT_CATALOG,
) -> dict[str, Any]:
    raw = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = raw["cases"]
    case_ids = [item["case_id"] for item in cases]
    if len(cases) != 13 or len(case_ids) != len(set(case_ids)):
        raise ValueError("ANA-003 Golden must contain 13 unique cases")

    catalog = load_catalog(catalog_path)
    assessor = CapabilityAssessor(catalog)
    all_columns = catalog.column_ids
    results: list[dict[str, Any]] = []
    for item in cases:
        available = tuple(sorted(all_columns - set(item.get("remove_columns", []))))
        non_empty = tuple(
            column for column in available if column not in item.get("empty_columns", [])
        )
        profile = DataCapabilityProfile(
            source=item["source"],
            available_period=item.get("available_period", raw["default_available_period"]),
            available_columns=available,
            non_empty_columns=non_empty,
            data_quality_status=item.get("data_quality_status", "pass"),
            data_quality_issues=item.get("data_quality_issues", []),
            experimental_design_present=item.get("experimental_design_present", False),
        )
        question = ParsedAnalysisQuestion.model_validate(item["question"])
        actual = assessor.assess(question, profile).model_dump(mode="json")
        exact_match = actual == item["expected"]
        results.append(
            {
                "case_id": item["case_id"],
                "group": item["group"],
                "source": item["source"],
                "expected": item["expected"],
                "actual": actual,
                "exact_match": exact_match,
            }
        )

    failures = [item for item in results if not item["exact_match"]]
    group_counts = Counter(item["group"] for item in cases)
    return {
        "run_id": "ana-003-capability-assessment-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": _source_commit(),
        "assessor_version": "capability-assessor-v1",
        "dataset_version": raw["dataset_version"],
        "dataset_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
        "metadata_version": catalog.version,
        "case_count": len(cases),
        "group_counts": dict(sorted(group_counts.items())),
        "metrics": {
            "exact_match_count": sum(item["exact_match"] for item in results),
            "correct_degradation_count": sum(
                item["exact_match"]
                and item["group"]
                in {
                    "partial_evidence",
                    "partial_dimension",
                    "blocked_period",
                    "blocked_metric",
                    "blocked_quality",
                    "synthetic_degrade",
                }
                for item in results
            ),
            "causal_method_allowed_count": sum(
                "causal_inference" in item["actual"]["supported_methods"]
                for item in results
            ),
            "failed_quality_method_allowed_count": sum(
                bool(item["actual"]["supported_methods"])
                and item["actual"]["data_quality_status"] == "fail"
                for item in results
            ),
        },
        "failure_count": len(failures),
        "failures": failures,
        "cases": results,
    }


def main() -> None:
    result = evaluate()
    DEFAULT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_REPORT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "case_count": result["case_count"],
                "metrics": result["metrics"],
                "failure_count": result["failure_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
