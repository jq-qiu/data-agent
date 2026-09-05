from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

from app.nl2sql.validator import SQLValidationError, SQLValidator

BUCKETS = ("simple", "aggregate", "time", "join", "topn", "comparison")
ERROR_CATEGORIES = (
    "Metadata Retrieval Error",
    "Metric Recognition Error",
    "Schema Linking Error",
    "SQL Generation Error",
    "SQL Execution Error",
)


@dataclass(frozen=True)
class NL2SQLGoldenCase:
    case_id: str
    bucket: str
    question: str
    expected_metric_ids: tuple[str, ...]
    expected_tables: tuple[str, ...]
    expected_columns: tuple[str, ...]
    expected_join_relations: tuple[str, ...]
    reference_sql: str
    expected_result_sha256: str | None
    risk_tags: tuple[str, ...]
    result_ordered: bool


@dataclass
class NL2SQLRun:
    generated_sql: str = ""
    validated_sql: str = ""
    rows: list[dict[str, Any]] | None = None
    metric_ids: tuple[str, ...] = ()
    validation_trace: dict[str, Any] | None = None
    repair_attempts: int = 0
    error: str | None = None
    failure_stage: str | None = None
    latency_seconds: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None


def load_nl2sql_golden(path: Path) -> tuple[str, tuple[NL2SQLGoldenCase, ...]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = tuple(
        NL2SQLGoldenCase(
            case_id=item["case_id"],
            bucket=item["bucket"],
            question=item["question"],
            expected_metric_ids=tuple(item.get("expected_metric_ids", [])),
            expected_tables=tuple(item["expected_tables"]),
            expected_columns=tuple(item["expected_columns"]),
            expected_join_relations=tuple(item.get("expected_join_relations", [])),
            reference_sql=item["reference_sql"],
            expected_result_sha256=item.get("expected_result_sha256"),
            risk_tags=tuple(item.get("risk_tags", [])),
            result_ordered=bool(item.get("result_ordered", False)),
        )
        for item in raw["cases"]
    )
    validate_golden_contract(cases)
    return str(raw["dataset_version"]), cases


def validate_golden_contract(cases: Sequence[NL2SQLGoldenCase]) -> None:
    if len(cases) != 30:
        raise ValueError("NL2SQL Golden Dataset must contain exactly 30 cases")
    counts = Counter(case.bucket for case in cases)
    if counts != Counter({bucket: 5 for bucket in BUCKETS}):
        raise ValueError("NL2SQL Golden Dataset must contain five cases in every bucket")
    identifiers = [case.case_id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("NL2SQL Golden case IDs must be unique")
    if any(not case.reference_sql.strip() for case in cases):
        raise ValueError("every NL2SQL Golden case requires reference_sql")


def _normalize_scalar(value: Any) -> tuple[str, str | None]:
    if value is None:
        return ("null", None)
    if isinstance(value, bool):
        return ("bool", "true" if value else "false")
    if isinstance(value, (int, float, Decimal)):
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return ("text", str(value))
        if not number.is_finite():
            return ("number", str(number))
        normalized = format(number.normalize(), "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        return ("number", normalized or "0")
    if isinstance(value, (datetime, date, time)):
        return ("temporal", value.isoformat())
    if isinstance(value, bytes):
        return ("bytes", value.hex())
    return ("text", str(value))


def normalize_result_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    ordered: bool,
) -> list[list[tuple[str, str | None]]]:
    normalized = [
        sorted((_normalize_scalar(value) for value in row.values()), key=lambda item: repr(item))
        for row in rows
    ]
    if not ordered:
        normalized.sort(key=lambda item: json.dumps(item, ensure_ascii=False))
    return normalized


def result_checksum(rows: Sequence[Mapping[str, Any]], *, ordered: bool) -> str:
    payload = json.dumps(
        normalize_result_rows(rows, ordered=ordered),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _set_scores(expected: set[str], actual: set[str]) -> tuple[float, float]:
    precision = len(expected & actual) / len(actual) if actual else float(not expected)
    recall = len(expected & actual) / len(expected) if expected else float(not actual)
    return precision, recall


def classify_failure(
    case: NL2SQLGoldenCase,
    run: NL2SQLRun,
    *,
    metric_match: bool,
    table_recall: float,
    column_recall: float,
    join_match: bool,
    result_match: bool,
) -> str | None:
    if run.error:
        if run.failure_stage == "execution":
            return "SQL Execution Error"
        if run.failure_stage == "retrieval":
            return "Metadata Retrieval Error"
        return "SQL Generation Error"
    if not metric_match:
        return "Metric Recognition Error"
    if table_recall < 1 or column_recall < 1 or not join_match:
        return "Schema Linking Error"
    if not result_match:
        return "SQL Generation Error"
    return None


def summarize_case_results(case_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metric_names = (
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
    )
    by_bucket: dict[str, dict[str, float]] = {}
    for bucket in BUCKETS:
        bucket_rows = [item for item in case_results if item["bucket"] == bucket]
        if not bucket_rows:
            continue
        by_bucket[bucket] = {
            name: sum(float(item[name]) for item in bucket_rows) / len(bucket_rows)
            for name in metric_names
        }
    latencies = [float(item["latency_seconds"]) for item in case_results]
    return {
        "bucket_metrics": by_bucket,
        "latency_seconds": {
            "mean": sum(latencies) / len(latencies),
            "median": median(latencies),
            "max": max(latencies),
        },
    }


SAFETY_PROBES: tuple[tuple[str, str], ...] = (
    ("multi_statement", "SELECT order_id FROM fact_order; DROP TABLE fact_order"),
    ("dml", "DELETE FROM fact_order"),
    ("ddl", "CREATE TABLE unsafe(id INT)"),
    ("comment", "SELECT order_id FROM fact_order -- bypass"),
    ("system_schema", "SELECT table_name FROM information_schema.tables"),
    ("file_access", "SELECT order_id INTO OUTFILE '/tmp/x' FROM fact_order"),
    ("session_variable", "SELECT @unsafe FROM fact_order"),
    ("unknown_table", "SELECT id FROM unregistered_table"),
    ("star", "SELECT * FROM fact_order"),
    ("unsafe_function", "SELECT SLEEP(5) FROM fact_order"),
    (
        "unregistered_join",
        "SELECT i.price FROM fact_order_item i JOIN fact_order o ON i.product_id=o.order_id",
    ),
    ("sensitive_projection", "SELECT customer_id FROM dim_customer"),
)


def evaluate_safety_probes(validator: SQLValidator) -> dict[str, Any]:
    allowed: list[str] = []
    for probe_id, sql in SAFETY_PROBES:
        try:
            validator.validate(sql)
        except SQLValidationError:
            continue
        allowed.append(probe_id)
    return {
        "probe_count": len(SAFETY_PROBES),
        "rejected_count": len(SAFETY_PROBES) - len(allowed),
        "dangerous_sql_allowed_count": len(allowed),
        "allowed_probe_ids": allowed,
    }


async def evaluate_nl2sql_cases(
    cases: Sequence[NL2SQLGoldenCase],
    run_candidate: Callable[[NL2SQLGoldenCase], Awaitable[NL2SQLRun]],
    run_reference: Callable[[NL2SQLGoldenCase], Awaitable[list[dict[str, Any]]]],
) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    aggregate: dict[str, list[float]] = {
        "sql_validity_rate": [],
        "sql_executability": [],
        "execution_accuracy": [],
        "metric_accuracy": [],
        "table_precision": [],
        "table_recall": [],
        "column_precision": [],
        "column_recall": [],
        "join_accuracy": [],
        "grain_safety_rate": [],
    }
    correction_attempted = 0
    correction_succeeded = 0
    reference_verified = 0

    for case in cases:
        reference_rows = await run_reference(case)
        reference_sha = result_checksum(reference_rows, ordered=case.result_ordered)
        reference_matches = reference_sha == case.expected_result_sha256
        reference_verified += int(reference_matches)
        started_at = perf_counter()
        try:
            run = await run_candidate(case)
        except Exception as error:  # noqa: BLE001 - retain one record for every case
            run = NL2SQLRun(
                error=f"{type(error).__name__}: {error}",
                failure_stage="execution",
            )
        if not run.latency_seconds:
            run.latency_seconds = perf_counter() - started_at

        trace = run.validation_trace or {}
        actual_tables = set(trace.get("tables", []))
        actual_columns = set(trace.get("columns", []))
        actual_joins = set(trace.get("join_relations", []))
        expected_tables = set(case.expected_tables)
        expected_columns = set(case.expected_columns)
        expected_joins = set(case.expected_join_relations)
        table_precision, table_recall = _set_scores(expected_tables, actual_tables)
        column_precision, column_recall = _set_scores(expected_columns, actual_columns)
        metric_match = set(run.metric_ids) == set(case.expected_metric_ids)
        join_match = actual_joins == expected_joins
        valid = bool(run.validated_sql and trace and not run.error)
        executable = run.rows is not None and not run.error
        candidate_sha = (
            result_checksum(run.rows, ordered=case.result_ordered) if run.rows is not None else None
        )
        result_match = bool(reference_matches and candidate_sha == reference_sha)
        grain_safe = valid
        if run.repair_attempts:
            correction_attempted += 1
            correction_succeeded += int(valid and executable)
        error_category = classify_failure(
            case,
            run,
            metric_match=metric_match,
            table_recall=table_recall,
            column_recall=column_recall,
            join_match=join_match,
            result_match=result_match,
        )

        values = {
            "sql_validity_rate": float(valid),
            "sql_executability": float(executable),
            "execution_accuracy": float(result_match),
            "metric_accuracy": float(metric_match),
            "table_precision": table_precision,
            "table_recall": table_recall,
            "column_precision": column_precision,
            "column_recall": column_recall,
            "join_accuracy": float(join_match),
            "grain_safety_rate": float(grain_safe),
        }
        for name, value in values.items():
            aggregate[name].append(value)

        case_results.append(
            {
                "case_id": case.case_id,
                "bucket": case.bucket,
                "question": case.question,
                "risk_tags": list(case.risk_tags),
                "generated_sql": run.generated_sql,
                "validated_sql": run.validated_sql,
                "expected_metric_ids": list(case.expected_metric_ids),
                "actual_metric_ids": list(run.metric_ids),
                "expected_tables": list(case.expected_tables),
                "actual_tables": sorted(actual_tables),
                "expected_columns": list(case.expected_columns),
                "actual_columns": sorted(actual_columns),
                "expected_join_relations": list(case.expected_join_relations),
                "actual_join_relations": sorted(actual_joins),
                "reference_result_sha256": reference_sha,
                "candidate_result_sha256": candidate_sha,
                "reference_checksum_verified": reference_matches,
                "repair_attempts": run.repair_attempts,
                "latency_seconds": round(run.latency_seconds, 6),
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "error": run.error,
                "error_category": error_category,
                **values,
            }
        )

    metrics: dict[str, Any] = {
        name: sum(values) / len(values) for name, values in aggregate.items()
    }
    metrics["correction_success_rate"] = (
        correction_succeeded / correction_attempted if correction_attempted else None
    )
    metrics["correction_attempted_count"] = correction_attempted
    metrics["correction_succeeded_count"] = correction_succeeded
    summaries = summarize_case_results(case_results)
    return {
        "case_count": len(cases),
        "bucket_counts": dict(sorted(Counter(case.bucket for case in cases).items())),
        "reference_checksums_verified": reference_verified,
        "metrics": metrics,
        "error_counts": dict(
            sorted(
                Counter(
                    item["error_category"] for item in case_results if item["error_category"]
                ).items()
            )
        ),
        **summaries,
        "cases": case_results,
    }


def write_evaluation_artifacts(
    result: dict[str, Any],
    *,
    report_path: Path,
    run_dir: Path,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n"
    report_path.write_text(serialized, encoding="utf-8")
    (run_dir / "summary.json").write_text(serialized, encoding="utf-8")

    case_rows = result["evaluation"]["cases"]
    fields = [
        "case_id",
        "bucket",
        "question",
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
        "repair_attempts",
        "latency_seconds",
        "error_category",
        "error",
        "generated_sql",
        "validated_sql",
    ]
    with (run_dir / "nl2sql_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(case_rows)

    failures = [item for item in case_rows if item["error_category"]]
    lines = [
        "# SQL-002 Error Analysis",
        "",
        f"Failed cases: {len(failures)}/{len(case_rows)}",
        "",
    ]
    if not failures:
        lines.append("No failed cases.")
    else:
        for item in failures:
            lines.extend(
                (
                    f"## {item['case_id']} - {item['error_category']}",
                    "",
                    f"- Bucket: {item['bucket']}",
                    f"- Question: {item['question']}",
                    f"- Error: {item['error'] or 'result or structure mismatch'}",
                    f"- Execution match: {bool(item['execution_accuracy'])}",
                    "",
                )
            )
    (run_dir / "error_analysis.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


def golden_payload(dataset_version: str, cases: Sequence[NL2SQLGoldenCase]) -> dict[str, Any]:
    return {
        "dataset_version": dataset_version,
        "cases": [asdict(case) for case in cases],
    }
