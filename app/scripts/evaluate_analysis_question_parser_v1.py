from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.diagnosis.question import AnalysisQuestionParser
from app.metadata.catalog import load_catalog

ROOT = Path(__file__).parents[2]
DEFAULT_GOLDEN = ROOT / "data" / "evaluation" / "analysis_question_parser_golden_v1.json"
DEFAULT_REPORT = (
    ROOT / "data" / "reports" / "ANA-002_analysis_question_parser_evaluation.json"
)
DEFAULT_CATALOG = ROOT / "conf" / "meta_config.yaml"
PARSED_FIELDS = (
    "target_metric",
    "current_period",
    "baseline_period",
    "comparison_type",
    "scope",
    "requested_dimensions",
    "requested_factors",
)


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
    group_counts = Counter(item["group"] for item in cases)
    case_ids = [item["case_id"] for item in cases]
    if len(cases) != 18 or group_counts != Counter({"parsed": 10, "error": 8}):
        raise ValueError("ANA-002 Golden must contain ten parsed and eight error cases")
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("ANA-002 Golden case IDs must be unique")

    parser = AnalysisQuestionParser.from_catalog(load_catalog(catalog_path))
    results: list[dict[str, Any]] = []
    field_matches = Counter({field: 0 for field in PARSED_FIELDS})
    for item in cases:
        actual = parser.parse(item["question"], item["intent"]).model_dump(mode="json")
        expected = item["expected"]
        exact_match = actual == expected
        if item["group"] == "parsed":
            actual_parsed = actual["parsed_question"] or {}
            expected_parsed = expected["parsed_question"] or {}
            for field in PARSED_FIELDS:
                field_matches[field] += actual_parsed.get(field) == expected_parsed.get(
                    field
                )
        results.append(
            {
                "case_id": item["case_id"],
                "group": item["group"],
                "question": item["question"],
                "intent": item["intent"],
                "expected": expected,
                "actual": actual,
                "exact_match": exact_match,
            }
        )

    failures = [item for item in results if not item["exact_match"]]
    return {
        "run_id": "ana-002-analysis-question-parser-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": _source_commit(),
        "parser_version": "analysis-question-parser-v1",
        "dataset_version": raw["dataset_version"],
        "dataset_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
        "metadata_version": load_catalog(catalog_path).version,
        "case_count": len(cases),
        "group_counts": dict(sorted(group_counts.items())),
        "metrics": {
            "exact_match_count": sum(item["exact_match"] for item in results),
            "successful_parse_match_count": sum(
                item["exact_match"] and item["group"] == "parsed" for item in results
            ),
            "structured_error_match_count": sum(
                item["exact_match"] and item["group"] == "error" for item in results
            ),
            "parsed_field_match_counts": dict(field_matches),
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
