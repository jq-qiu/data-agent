from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.diagnosis.intent import Intent, IntentRouter

ROOT = Path(__file__).parents[2]
DEFAULT_GOLDEN = ROOT / "data" / "evaluation" / "intent_router_golden_v2.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "ROUTE-001_intent_router_evaluation.json"
EXPECTED_GROUP_COUNTS = Counter({"query": 24, "diagnosis": 12, "unsupported": 12})


def _source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def evaluate(golden_path: Path = DEFAULT_GOLDEN) -> dict[str, Any]:
    raw = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = raw["cases"]
    group_counts = Counter(item["group"] for item in cases)
    if group_counts != EXPECTED_GROUP_COUNTS:
        raise ValueError("ROUTE-001 Golden group counts do not match the frozen contract")

    router = IntentRouter()
    results: list[dict[str, Any]] = []
    for item in cases:
        decision = router.route(item["question"])
        results.append(
            {
                "case_id": item["case_id"],
                "group": item["group"],
                "expected_intent": item["expected_intent"],
                "expected_reason": item["expected_reason"],
                "actual_intent": decision.intent.value,
                "actual_confidence": decision.confidence,
                "actual_reason": decision.reason,
                "intent_match": decision.intent.value == item["expected_intent"],
                "reason_match": decision.reason == item["expected_reason"],
            }
        )

    failures = [
        item for item in results if not item["intent_match"] or not item["reason_match"]
    ]
    recall_by_intent = {
        intent.value: sum(
            item["intent_match"] and item["expected_intent"] == intent.value
            for item in results
        )
        / sum(item["expected_intent"] == intent.value for item in results)
        for intent in Intent
    }
    non_diagnosis = [
        item for item in results if item["expected_intent"] != Intent.DIAGNOSIS
    ]
    return {
        "run_id": "route-001-intent-router-v2",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": _source_commit(),
        "router_version": "hybrid-intent-router-v2",
        "dataset_version": raw["dataset_version"],
        "dataset_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
        "case_count": len(cases),
        "group_counts": dict(sorted(group_counts.items())),
        "metrics": {
            "intent_accuracy": sum(item["intent_match"] for item in results)
            / len(results),
            "reason_accuracy": sum(item["reason_match"] for item in results)
            / len(results),
            "recall_by_intent": recall_by_intent,
            "diagnosis_false_positive_count": sum(
                item["actual_intent"] == Intent.DIAGNOSIS for item in non_diagnosis
            ),
            "classifier_eligible_count": sum(
                item["actual_reason"] == "ambiguous_or_incomplete_question"
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
