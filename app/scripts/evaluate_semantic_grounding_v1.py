from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.diagnosis.grounding import (
    SemanticBindingResult,
    SemanticCandidateBundle,
    SemanticGrounder,
)
from app.diagnosis.semantics import AnalysisSemanticRegistry
from app.metadata.catalog import load_catalog

ROOT = Path(__file__).parents[2]
DEFAULT_GOLDEN = ROOT / "data" / "evaluation" / "semantic_grounding_golden_v1.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "SEM-002_semantic_grounding_evaluation.json"
DEFAULT_CATALOG = ROOT / "conf" / "meta_config.yaml"


class _FixedCandidateRetriever:
    def __init__(self, candidates: SemanticCandidateBundle) -> None:
        self._candidates = candidates

    async def retrieve(self, question: str) -> SemanticCandidateBundle:
        del question
        return self._candidates


def _source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _project(result: SemanticBindingResult) -> dict[str, Any]:
    parsed = result.parsed_question
    return {
        "status": result.status.value,
        "target_metric": parsed.target_metric if parsed else None,
        "scope": parsed.scope.model_dump(mode="json") if parsed else None,
        "requested_dimensions": (
            [item.value for item in parsed.requested_dimensions] if parsed else []
        ),
        "reason": result.reason,
        "missing_fields": [item.value for item in result.missing_fields],
        "ambiguous_fields": [item.value for item in result.ambiguous_fields],
        "retrieval_used": result.retrieval_used,
    }


async def _evaluate_cases(
    cases: list[dict[str, Any]],
    catalog_path: Path,
) -> list[dict[str, Any]]:
    catalog = load_catalog(catalog_path)
    registry = AnalysisSemanticRegistry.from_catalog(catalog)
    results: list[dict[str, Any]] = []
    for item in cases:
        candidates = SemanticCandidateBundle.model_validate(item.get("candidates", {}))
        grounder = SemanticGrounder(
            catalog,
            registry,
            _FixedCandidateRetriever(candidates),
        )
        binding = await grounder.bind(item["question"], item["intent"])
        actual = _project(binding)
        expected = item["expected"]
        results.append(
            {
                "case_id": item["case_id"],
                "group": item["group"],
                "question": item["question"],
                "expected": expected,
                "actual": actual,
                "exact_match": actual == expected,
                "physical_schema_leakage": any(
                    token in binding.model_dump_json().casefold()
                    for token in (
                        "dws_",
                        "fact_",
                        "dim_",
                        "analysis_sales_",
                        "select ",
                        " join ",
                        "ground_truth",
                    )
                ),
            }
        )
    return results


def evaluate(
    golden_path: Path = DEFAULT_GOLDEN,
    catalog_path: Path = DEFAULT_CATALOG,
) -> dict[str, Any]:
    raw = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = raw["cases"]
    group_counts = Counter(item["group"] for item in cases)
    expected_groups = Counter(
        {
            "exact_ready": 2,
            "retrieval_ready": 3,
            "clarification": 4,
            "unsupported": 3,
        }
    )
    if len(cases) != 12 or group_counts != expected_groups:
        raise ValueError("SEM-002 Golden must contain the frozen twelve-case distribution")
    case_ids = [item["case_id"] for item in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("SEM-002 Golden case IDs must be unique")

    results = asyncio.run(_evaluate_cases(cases, catalog_path))
    failures = [item for item in results if not item["exact_match"]]
    status_matches = sum(
        item["actual"]["status"] == item["expected"]["status"] for item in results
    )
    return {
        "run_id": "sem-002-semantic-grounding-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": _source_commit(),
        "dataset_version": raw["dataset_version"],
        "dataset_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
        "metadata_version": load_catalog(catalog_path).version,
        "retrieval_evaluation_mode": "stubbed_qdrant_es_contract",
        "live_external_retrieval_evaluated": False,
        "case_count": len(cases),
        "group_counts": dict(sorted(group_counts.items())),
        "metrics": {
            "exact_match_count": sum(item["exact_match"] for item in results),
            "binding_status_accuracy_count": status_matches,
            "ready_exact_count": sum(
                item["exact_match"] and item["actual"]["status"] == "READY"
                for item in results
            ),
            "clarification_exact_count": sum(
                item["exact_match"]
                and item["actual"]["status"] == "CLARIFICATION_REQUIRED"
                for item in results
            ),
            "unsupported_exact_count": sum(
                item["exact_match"] and item["actual"]["status"] == "UNSUPPORTED"
                for item in results
            ),
            "retrieval_policy_match_count": sum(
                item["actual"]["retrieval_used"]
                == item["expected"]["retrieval_used"]
                for item in results
            ),
            "physical_schema_leakage_count": sum(
                item["physical_schema_leakage"] for item in results
            ),
            "llm_call_count": 0,
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
                "live_external_retrieval_evaluated": result[
                    "live_external_retrieval_evaluated"
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
