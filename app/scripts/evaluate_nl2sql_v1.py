from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from loguru import logger

from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.state import DataAgentState
from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import dw_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.conf.app_config import app_config
from app.metadata.catalog import load_catalog
from app.nl2sql.evaluation import (
    NL2SQLGoldenCase,
    NL2SQLRun,
    evaluate_nl2sql_cases,
    evaluate_safety_probes,
    load_nl2sql_golden,
    result_checksum,
    write_evaluation_artifacts,
)
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.validator import SQLValidator
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository

ROOT = Path(__file__).parents[2]
DEFAULT_GOLDEN = ROOT / "data" / "evaluation" / "nl2sql_golden_v1.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "SQL-002_nl2sql_evaluation.json"
DEFAULT_RUN_DIR = ROOT / "eval_runs" / "sql-002-baseline-v1"
CATALOG_PATH = ROOT / "conf" / "meta_config.yaml"
POLICY_PATH = ROOT / "conf" / "sql_policy.yaml"
PROMPT_PATHS = (
    ROOT / "prompts" / "expand_recall_keywords.prompt",
    ROOT / "prompts" / "filter_table_info.prompt",
    ROOT / "prompts" / "filter_metric_info.prompt",
    ROOT / "prompts" / "generate_sql.prompt",
    ROOT / "prompts" / "correct_sql.prompt",
)


def _digest_paths(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class LiveGraphRunner:
    def __init__(self, validator: SQLValidator):
        self.validator = validator

    async def __call__(self, case: NL2SQLGoldenCase) -> NL2SQLRun:
        assert meta_mysql_client_manager.session_factory is not None
        assert dw_mysql_client_manager.session_factory is not None
        assert embedding_client_manager.client is not None
        assert qdrant_client_manager.client is not None
        assert es_client_manager.client is not None
        run = NL2SQLRun()
        started_at = perf_counter()
        state = DataAgentState(query=case.question, repair_attempts=0)
        async with (
            meta_mysql_client_manager.session_factory() as meta_session,
            dw_mysql_client_manager.session_factory() as dw_session,
        ):
            context = DataAgentContext(
                meta_mysql_repository=MetaMySQLRepository(meta_session),
                dw_mysql_repository=DWMySQLRepository(dw_session),
                embedding_client=embedding_client_manager.client,
                column_qdrant_repository=ColumnQdrantRepository(qdrant_client_manager.client),
                metric_qdrant_repository=MetricQdrantRepository(qdrant_client_manager.client),
                value_es_repository=ValueESRepository(es_client_manager.client),
                sql_validator=self.validator,
            )
            try:
                async for mode, chunk in graph.astream(
                    input=state,
                    context=context,
                    stream_mode=["updates", "custom"],
                ):
                    if mode == "custom":
                        if not isinstance(chunk, Mapping):
                            continue
                        if chunk.get("type") == "result":
                            data = chunk.get("data")
                            if isinstance(data, list):
                                run.rows = [
                                    dict(row)
                                    for row in data
                                    if isinstance(row, Mapping)
                                ]
                        continue
                    if not isinstance(chunk, Mapping):
                        continue
                    for node_name, update in chunk.items():
                        if not isinstance(update, dict):
                            continue
                        if node_name == "filter_metric":
                            run.metric_ids = tuple(
                                item["id"] for item in update.get("metric_infos", [])
                            )
                        if node_name in {"generate_sql", "correct_sql"} and update.get("sql"):
                            run.generated_sql = str(update["sql"])
                        if node_name == "correct_sql":
                            run.repair_attempts = int(update.get("repair_attempts", 0))
                        if node_name == "validate_sql":
                            run.validated_sql = str(update.get("validated_sql", ""))
                            run.validation_trace = dict(update.get("validation_trace", {}))
                            run.error = update.get("error")
                            run.failure_stage = "validation" if run.error else None
            except Exception as error:  # noqa: BLE001 - preserve partial graph evidence
                run.error = f"{type(error).__name__}: {error}"
                run.failure_stage = "execution" if run.validated_sql else "retrieval"
        run.latency_seconds = perf_counter() - started_at
        if run.rows is None and not run.error:
            run.error = "graph completed without an execution result"
            run.failure_stage = "execution" if run.validated_sql else "generation"
        return run


class ReferenceRunner:
    def __init__(self, validator: SQLValidator):
        self.validator = validator

    async def __call__(self, case: NL2SQLGoldenCase) -> list[dict[str, Any]]:
        assert dw_mysql_client_manager.session_factory is not None
        async with dw_mysql_client_manager.session_factory() as session:
            repository = DWMySQLRepository(session)
            validated = self.validator.validate(case.reference_sql, case.expected_metric_ids)
            if set(validated.tables) != set(case.expected_tables):
                raise ValueError(f"{case.case_id} reference table trace differs from Golden")
            if set(validated.columns) != set(case.expected_columns):
                raise ValueError(f"{case.case_id} reference column trace differs from Golden")
            if set(validated.join_relations) != set(case.expected_join_relations):
                raise ValueError(f"{case.case_id} reference JOIN trace differs from Golden")
            await repository.validate_sql(validated)
            return await repository.execute_sql(validated)


async def _freeze_reference_checksums(
    golden_path: Path,
    dataset_version: str,
    cases: tuple[NL2SQLGoldenCase, ...],
    reference_runner: ReferenceRunner,
) -> None:
    raw = json.loads(golden_path.read_text(encoding="utf-8"))
    if raw["dataset_version"] != dataset_version:
        raise ValueError("dataset version changed during checksum freeze")
    for item, case in zip(raw["cases"], cases, strict=True):
        rows = await reference_runner(case)
        item["expected_result_sha256"] = result_checksum(rows, ordered=case.result_ordered)
    golden_path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def run_evaluation(
    golden_path: Path,
    report_path: Path,
    run_dir: Path,
    *,
    freeze_reference: bool,
) -> dict[str, Any]:
    if app_config.db_dw.database != "data_agent_v1_dw":
        raise RuntimeError("SQL-002 may only query the isolated data_agent_v1_dw database")
    catalog = load_catalog(CATALOG_PATH)
    policy = load_sql_policy(POLICY_PATH)
    validator = SQLValidator(catalog, policy)
    dataset_version, cases = load_nl2sql_golden(golden_path)

    dw_mysql_client_manager.init()
    meta_mysql_client_manager.init()
    embedding_client_manager.init()
    qdrant_client_manager.init()
    es_client_manager.init()
    try:
        reference_runner = ReferenceRunner(validator)
        if freeze_reference:
            await _freeze_reference_checksums(
                golden_path,
                dataset_version,
                cases,
                reference_runner,
            )
            dataset_version, cases = load_nl2sql_golden(golden_path)
        if any(case.expected_result_sha256 is None for case in cases):
            raise RuntimeError("reference checksums are not frozen; run with --freeze-reference")

        evaluation = await evaluate_nl2sql_cases(
            cases,
            LiveGraphRunner(validator),
            reference_runner,
        )
        safety = evaluate_safety_probes(validator)
        failure_count = sum(evaluation["error_counts"].values())
        classified_failures = sum(
            1 for item in evaluation["cases"] if item["error_category"] is not None
        )
        gate_checks = {
            "all_30_cases_recorded": evaluation["case_count"] == 30,
            "six_buckets_have_five_cases": all(
                evaluation["bucket_counts"].get(bucket) == 5
                for bucket in ("simple", "aggregate", "time", "join", "topn", "comparison")
            ),
            "all_reference_checksums_verified": evaluation["reference_checksums_verified"] == 30,
            "all_required_metrics_reported": all(
                name in evaluation["metrics"]
                for name in (
                    "sql_validity_rate",
                    "sql_executability",
                    "execution_accuracy",
                    "metric_accuracy",
                    "table_precision",
                    "table_recall",
                    "column_precision",
                    "column_recall",
                    "join_accuracy",
                    "grain_safety_rate",
                    "correction_success_rate",
                )
            ),
            "dangerous_sql_allowed_count_is_zero": safety["dangerous_sql_allowed_count"] == 0,
            "all_failures_classified": classified_failures == failure_count,
        }
        result = {
            "run_id": "sql-002-baseline-v1",
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "source_commit": _source_commit(),
            "evaluator_version": "sql-evaluator-v1",
            "dataset_version": dataset_version,
            "dataset_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
            "metadata_version": catalog.version,
            "sql_policy_version": policy.version,
            "prompt_bundle_sha256": _digest_paths(PROMPT_PATHS),
            "model": {
                "name": app_config.llm.model,
                "temperature": 0,
                "timeout_seconds": app_config.llm.timeout,
                "max_retries": app_config.llm.max_retries,
                "token_usage_available": False,
                "cost_usd": None,
                "cost_note": "unavailable because the current graph does not expose token usage",
            },
            "database": "data_agent_v1_dw",
            "evaluation": evaluation,
            "safety_probes": safety,
            "gate_checks": gate_checks,
            "gate_3_passed": all(gate_checks.values()),
        }
        write_evaluation_artifacts(result, report_path=report_path, run_dir=run_dir)
        return result
    finally:
        await dw_mysql_client_manager.close()
        await meta_mysql_client_manager.close()
        await qdrant_client_manager.close()
        await es_client_manager.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the frozen Olist V1 NL2SQL baseline")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--freeze-reference", action="store_true")
    args = parser.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="ERROR")
    result = asyncio.run(
        run_evaluation(
            args.golden,
            args.report,
            args.run_dir,
            freeze_reference=args.freeze_reference,
        )
    )
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "case_count": result["evaluation"]["case_count"],
                "metrics": result["evaluation"]["metrics"],
                "dangerous_sql_allowed_count": result["safety_probes"][
                    "dangerous_sql_allowed_count"
                ],
                "gate_3_passed": result["gate_3_passed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
