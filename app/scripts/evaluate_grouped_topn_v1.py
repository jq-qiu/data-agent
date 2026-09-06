from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.clients.mysql_client_manager import dw_mysql_client_manager
from app.conf.app_config import app_config
from app.metadata.catalog import load_catalog
from app.nl2sql.evaluation import result_checksum
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.validator import SQLValidator
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository

ROOT = Path(__file__).parents[2]
DEFAULT_GOLDEN = ROOT / "data" / "evaluation" / "grouped_topn_golden_v1.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "SQL-003_grouped_topn_evaluation.json"


@dataclass(frozen=True)
class GroupedTopNCase:
    case_id: str
    question: str
    n: int
    group_column: str
    rank_column: str
    expected_metric_ids: tuple[str, ...]
    expected_tables: tuple[str, ...]
    expected_columns: tuple[str, ...]
    expected_join_relations: tuple[str, ...]
    reference_sql: str
    expected_result_sha256: str | None


def load_grouped_topn_golden(
    path: Path = DEFAULT_GOLDEN,
) -> tuple[str, tuple[GroupedTopNCase, ...]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = tuple(
        GroupedTopNCase(
            case_id=item["case_id"],
            question=item["question"],
            n=int(item["n"]),
            group_column=item["group_column"],
            rank_column=item["rank_column"],
            expected_metric_ids=tuple(item["expected_metric_ids"]),
            expected_tables=tuple(item["expected_tables"]),
            expected_columns=tuple(item["expected_columns"]),
            expected_join_relations=tuple(item["expected_join_relations"]),
            reference_sql=item["reference_sql"],
            expected_result_sha256=item.get("expected_result_sha256"),
        )
        for item in raw["cases"]
    )
    if len(cases) != 4 or len({case.case_id for case in cases}) != 4:
        raise ValueError("SQL-003 Golden must contain exactly four unique cases")
    if any(case.n <= 0 or not case.reference_sql.strip() for case in cases):
        raise ValueError("SQL-003 cases require a positive N and reference SQL")
    return str(raw["dataset_version"]), cases


def evaluate_rows(case: GroupedTopNCase, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranks_by_group: dict[str, list[int]] = {}
    ordered_keys: list[tuple[str, int]] = []
    for row in rows:
        group = str(row[case.group_column])
        rank = int(Decimal(str(row[case.rank_column])))
        ranks_by_group.setdefault(group, []).append(rank)
        ordered_keys.append((group, rank))
    rank_sequences_valid = all(
        ranks == list(range(1, len(ranks) + 1)) for ranks in ranks_by_group.values()
    )
    per_group_limit_valid = all(len(ranks) <= case.n for ranks in ranks_by_group.values())
    deterministic_order_valid = ordered_keys == sorted(ordered_keys)
    return {
        "row_count": len(rows),
        "group_count": len(ranks_by_group),
        "rank_sequences_valid": rank_sequences_valid,
        "per_group_limit_valid": per_group_limit_valid,
        "deterministic_order_valid": deterministic_order_valid,
        "result_sha256": result_checksum(rows, ordered=True),
    }


def _source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _freeze_checksums(path: Path, checksums: dict[str, str]) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for item in raw["cases"]:
        item["expected_result_sha256"] = checksums[item["case_id"]]
    path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def run_evaluation(
    golden_path: Path = DEFAULT_GOLDEN,
    report_path: Path = DEFAULT_REPORT,
    *,
    freeze_reference: bool = False,
) -> dict[str, Any]:
    if app_config.db_dw.database != "data_agent_v1_dw":
        raise RuntimeError("SQL-003 may only query the isolated data_agent_v1_dw database")
    catalog = load_catalog(ROOT / "conf" / "meta_config.yaml")
    policy = load_sql_policy(ROOT / "conf" / "sql_policy.yaml")
    validator = SQLValidator(catalog, policy)
    dataset_version, cases = load_grouped_topn_golden(golden_path)

    results: list[dict[str, Any]] = []
    checksums: dict[str, str] = {}
    dw_mysql_client_manager.init()
    try:
        assert dw_mysql_client_manager.session_factory is not None
        async with dw_mysql_client_manager.session_factory() as session:
            repository = DWMySQLRepository(session)
            for case in cases:
                validated = validator.validate(case.reference_sql, case.expected_metric_ids)
                trace_matches = (
                    set(validated.tables) == set(case.expected_tables)
                    and set(validated.columns) == set(case.expected_columns)
                    and set(validated.join_relations) == set(case.expected_join_relations)
                )
                await repository.validate_sql(validated)
                rows = await repository.execute_sql(validated)
                shape = evaluate_rows(case, rows)
                checksums[case.case_id] = shape["result_sha256"]
                checksum_matches = (
                    case.expected_result_sha256 is None
                    if freeze_reference
                    else shape["result_sha256"] == case.expected_result_sha256
                )
                results.append(
                    {
                        "case_id": case.case_id,
                        "validation_trace_matches": trace_matches,
                        "explain_succeeded": True,
                        "execution_succeeded": True,
                        "checksum_matches": checksum_matches,
                        **shape,
                    }
                )
        if freeze_reference:
            _freeze_checksums(golden_path, checksums)
            dataset_version, cases = load_grouped_topn_golden(golden_path)
            for result, case in zip(results, cases, strict=True):
                result["checksum_matches"] = (
                    result["result_sha256"] == case.expected_result_sha256
                )
    finally:
        await dw_mysql_client_manager.close()

    passed_count = sum(
        all(
            bool(item[name])
            for name in (
                "validation_trace_matches",
                "explain_succeeded",
                "execution_succeeded",
                "checksum_matches",
                "rank_sequences_valid",
                "per_group_limit_valid",
                "deterministic_order_valid",
            )
        )
        for item in results
    )
    result = {
        "run_id": "sql-003-grouped-topn-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": _source_commit(),
        "dataset_version": dataset_version,
        "dataset_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
        "metadata_version": catalog.version,
        "sql_policy_version": policy.version,
        "database": "data_agent_v1_dw",
        "case_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "raw_rows_persisted": False,
        "cases": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate SQL-003 grouped TopN references")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--freeze-reference", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(
        run_evaluation(
            args.golden,
            args.report,
            freeze_reference=args.freeze_reference,
        )
    )
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "case_count": result["case_count"],
                "passed_count": result["passed_count"],
                "failed_count": result["failed_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
