"""在固定样本上评估 SQL 可执行性、结果正确性与 Schema/粒度安全。"""

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
REPLAY_SCHEMA_VERSION = "nl2sql-replay-v2"
GRAIN_RISK_TAGS = {
    "category_grain",
    "order_item_grain",
    "overall_order_grain",
    "payment_grain",
    "review_grain",
    "one_to_many_join",
}


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


@dataclass(frozen=True)
class ReplayCacheIdentity:
    dataset_sha256: str
    prompt_bundle_sha256: str
    runtime_bundle_sha256: str
    metadata_version: str
    sql_policy_version: str
    model_name: str
    source_commit: str
    source_dirty: bool
    evaluator_version: str = "sql-evaluator-v3"


@dataclass(frozen=True)
class ReplayCache:
    runs: dict[str, NL2SQLRun]
    strict_reference_sha256: dict[str, str]


def _encode_replay_cell(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": repr(value)}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"type": "time", "value": value.isoformat()}
    if isinstance(value, bytes):
        return {"type": "bytes", "value": value.hex()}
    if isinstance(value, str):
        return {"type": "text", "value": value}
    raise TypeError(f"unsupported replay cell type: {type(value).__name__}")


def _decode_replay_cell(payload: Mapping[str, Any]) -> Any:
    cell_type = str(payload.get("type", ""))
    value = payload.get("value")
    if cell_type == "null":
        return None
    if cell_type == "bool" and isinstance(value, bool):
        return value
    if not isinstance(value, str):
        raise TypeError(f"invalid replay cell payload for {cell_type or 'unknown'}")
    if cell_type == "int":
        return int(value)
    if cell_type == "float":
        return float(value)
    if cell_type == "decimal":
        return Decimal(value)
    if cell_type == "datetime":
        return datetime.fromisoformat(value)
    if cell_type == "date":
        return date.fromisoformat(value)
    if cell_type == "time":
        return time.fromisoformat(value)
    if cell_type == "bytes":
        return bytes.fromhex(value)
    if cell_type == "text":
        return value
    raise ValueError(f"unsupported replay cell type: {cell_type or 'unknown'}")


def _serialize_run(run: NL2SQLRun) -> dict[str, Any]:
    rows = None
    if run.rows is not None:
        rows = [
            {str(column): _encode_replay_cell(value) for column, value in row.items()}
            for row in run.rows
        ]
    return {
        "generated_sql": run.generated_sql,
        "validated_sql": run.validated_sql,
        "rows": rows,
        "metric_ids": list(run.metric_ids),
        "validation_trace": run.validation_trace,
        "repair_attempts": run.repair_attempts,
        "error": run.error,
        "failure_stage": run.failure_stage,
        "latency_seconds": run.latency_seconds,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
    }


def _deserialize_run(payload: Mapping[str, Any]) -> NL2SQLRun:
    raw_rows = payload.get("rows")
    rows = None
    if raw_rows is not None:
        if not isinstance(raw_rows, list):
            raise ValueError("replay rows must be a list or null")
        rows = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, Mapping):
                raise TypeError("each replay row must be an object")
            rows.append(
                {
                    str(column): _decode_replay_cell(cell)
                    for column, cell in raw_row.items()
                    if isinstance(cell, Mapping)
                }
            )
            if len(rows[-1]) != len(raw_row):
                raise ValueError("each replay cell must be a typed object")
    trace = payload.get("validation_trace")
    if trace is not None and not isinstance(trace, Mapping):
        raise ValueError("replay validation_trace must be an object or null")
    metric_ids = payload.get("metric_ids", [])
    if not isinstance(metric_ids, list):
        raise TypeError("replay metric_ids must be a list")
    return NL2SQLRun(
        generated_sql=str(payload.get("generated_sql", "")),
        validated_sql=str(payload.get("validated_sql", "")),
        rows=rows,
        metric_ids=tuple(str(item) for item in metric_ids),
        validation_trace=dict(trace) if trace is not None else None,
        repair_attempts=int(payload.get("repair_attempts", 0)),
        error=str(payload["error"]) if payload.get("error") is not None else None,
        failure_stage=(
            str(payload["failure_stage"])
            if payload.get("failure_stage") is not None
            else None
        ),
        latency_seconds=float(payload.get("latency_seconds", 0.0)),
        input_tokens=(
            int(payload["input_tokens"])
            if payload.get("input_tokens") is not None
            else None
        ),
        output_tokens=(
            int(payload["output_tokens"])
            if payload.get("output_tokens") is not None
            else None
        ),
    )


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def write_replay_cache(
    path: Path,
    identity: ReplayCacheIdentity,
    runs: Mapping[str, NL2SQLRun],
    strict_reference_sha256: Mapping[str, str] | None = None,
) -> None:
    body = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "identity": asdict(identity),
        "runs": {
            case_id: _serialize_run(run)
            for case_id, run in sorted(runs.items())
        },
        "strict_reference_sha256": dict(sorted((strict_reference_sha256 or {}).items())),
    }
    payload = {
        **body,
        "content_sha256": hashlib.sha256(_canonical_json(body)).hexdigest(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_replay_cache(
    path: Path,
    expected_identity: ReplayCacheIdentity,
    expected_case_ids: Sequence[str],
) -> ReplayCache:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("replay cache root must be an object")
    content_sha256 = payload.pop("content_sha256", None)
    actual_sha256 = hashlib.sha256(_canonical_json(payload)).hexdigest()
    if content_sha256 != actual_sha256:
        raise ValueError("replay cache content checksum mismatch")
    if payload.get("schema_version") != REPLAY_SCHEMA_VERSION:
        raise ValueError("unsupported replay cache schema version")
    if payload.get("identity") != asdict(expected_identity):
        raise ValueError("replay cache identity mismatch")
    raw_runs = payload.get("runs")
    if not isinstance(raw_runs, Mapping):
        raise TypeError("replay cache runs must be an object")
    if set(raw_runs) != set(expected_case_ids):
        raise ValueError("replay cache case IDs do not match the Golden Dataset")
    raw_strict_references = payload.get("strict_reference_sha256")
    if not isinstance(raw_strict_references, Mapping):
        raise TypeError("replay cache strict references must be an object")
    if not set(raw_strict_references).issubset(expected_case_ids):
        raise ValueError("replay cache strict reference IDs do not match the Golden Dataset")
    runs: dict[str, NL2SQLRun] = {}
    for case_id, run in raw_runs.items():
        if not isinstance(run, Mapping):
            raise TypeError(f"replay run must be an object: {case_id}")
        runs[str(case_id)] = _deserialize_run(run)
    strict_references = {
        str(case_id): str(checksum)
        for case_id, checksum in raw_strict_references.items()
    }
    return ReplayCache(runs=runs, strict_reference_sha256=strict_references)


class RecordingRunner:
    def __init__(
        self,
        candidate: Callable[[NL2SQLGoldenCase], Awaitable[NL2SQLRun]],
    ) -> None:
        self._candidate = candidate
        self.runs: dict[str, NL2SQLRun] = {}

    async def __call__(self, case: NL2SQLGoldenCase) -> NL2SQLRun:
        if case.case_id in self.runs:
            raise ValueError(f"duplicate replay case ID: {case.case_id}")
        try:
            run = await self._candidate(case)
        except Exception as error:  # noqa: BLE001 - replay the recorded failure deterministically
            run = NL2SQLRun(
                error=f"{type(error).__name__}: {error}",
                failure_stage="execution",
            )
        self.runs[case.case_id] = run
        return run


class ReplayRunner:
    def __init__(self, runs: Mapping[str, NL2SQLRun]) -> None:
        self._runs = dict(runs)

    async def __call__(self, case: NL2SQLGoldenCase) -> NL2SQLRun:
        try:
            run = self._runs[case.case_id]
        except KeyError as error:
            raise ValueError(f"missing replay case ID: {case.case_id}") from error
        return _deserialize_run(_serialize_run(run))


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


def normalize_strict_result_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    ordered: bool,
) -> list[list[tuple[str, str | None]]]:
    """Normalize values while retaining SELECT projection position and column count."""
    normalized = [
        [_normalize_scalar(value) for value in row.values()]
        for row in rows
    ]
    if not ordered:
        normalized.sort(key=lambda item: json.dumps(item, ensure_ascii=False))
    return normalized


def strict_result_checksum(
    rows: Sequence[Mapping[str, Any]],
    *,
    ordered: bool,
) -> str:
    payload = json.dumps(
        normalize_strict_result_rows(rows, ordered=ordered),
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
    valid: bool = True,
    metric_match: bool,
    table_match: bool,
    column_match: bool,
    join_match: bool,
    result_match: bool,
    strict_result_match: bool | None = None,
) -> str | None:
    if run.error:
        if run.failure_stage == "execution":
            return "SQL Execution Error"
        if run.failure_stage == "retrieval":
            return "Metadata Retrieval Error"
        return "SQL Generation Error"
    if not valid:
        return "SQL Generation Error"
    if not metric_match:
        return "Metric Recognition Error"
    if not table_match or not column_match or not join_match:
        return "Schema Linking Error"
    if not result_match or strict_result_match is False:
        return "SQL Generation Error"
    return None


def _failure_labels(
    run: NL2SQLRun,
    *,
    metric_match: bool,
    table_match: bool,
    column_match: bool,
    join_match: bool,
    executable: bool,
    result_match: bool,
    strict_result_match: bool | None,
    grain_contract_match: bool | None,
) -> list[str]:
    labels: list[str] = []
    if run.error:
        if run.failure_stage == "execution":
            labels.append("SQL Execution Error")
        elif run.failure_stage == "retrieval":
            labels.append("Metadata Retrieval Error")
        else:
            labels.append("SQL Generation Error")
    if not metric_match:
        labels.append("Metric Recognition Error")
    if not table_match or not column_match or not join_match:
        labels.append("Schema Linking Error")
    if executable and not result_match:
        labels.append("Result Value Mismatch")
    if executable and strict_result_match is False:
        labels.append("Result Shape Mismatch")
    if grain_contract_match is False:
        labels.append("Grain Contract Error")
    return list(dict.fromkeys(labels))


def summarize_case_results(case_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metric_names = (
        "sql_validity_rate",
        "sql_executability",
        "execution_accuracy",
        "strict_execution_accuracy",
        "metric_accuracy",
        "table_precision",
        "table_recall",
        "column_precision",
        "column_recall",
        "join_accuracy",
        "grain_safety_rate",
        "validator_acceptance_rate",
        "trace_conformance_rate",
        "grain_contract_accuracy",
    )
    by_bucket: dict[str, dict[str, float | None]] = {}
    for bucket in BUCKETS:
        bucket_rows = [item for item in case_results if item["bucket"] == bucket]
        if not bucket_rows:
            continue
        bucket_metrics: dict[str, float | None] = {}
        for name in metric_names:
            values = [
                float(item[name])
                for item in bucket_rows
                if item[name] is not None
            ]
            bucket_metrics[name] = sum(values) / len(values) if values else None
        by_bucket[bucket] = bucket_metrics
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
    run_reference: Callable[
        [NL2SQLGoldenCase],
        Awaitable[list[dict[str, Any]]],
    ]
    | None = None,
    strict_reference_sha256: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    aggregate: dict[str, list[float]] = {
        "sql_validity_rate": [],
        "sql_executability": [],
        "execution_accuracy": [],
        "strict_execution_accuracy": [],
        "metric_accuracy": [],
        "table_precision": [],
        "table_recall": [],
        "column_precision": [],
        "column_recall": [],
        "join_accuracy": [],
        "grain_safety_rate": [],
        "validator_acceptance_rate": [],
        "trace_conformance_rate": [],
        "grain_contract_accuracy": [],
    }
    correction_attempted = 0
    correction_succeeded = 0
    strict_correction_attempted = 0
    strict_correction_succeeded = 0
    reference_verified = 0
    strict_reference_available = 0

    for case in cases:
        if run_reference is None:
            # Compatibility mode uses the frozen Golden checksum without reference SQL.
            reference_sha = case.expected_result_sha256
            reference_matches = reference_sha is not None
            strict_reference_sha = (strict_reference_sha256 or {}).get(case.case_id)
            reference_verified += int(reference_matches)
        else:
            reference_rows = await run_reference(case)
            reference_sha = result_checksum(
                reference_rows,
                ordered=case.result_ordered,
            )
            strict_reference_sha = strict_result_checksum(
                reference_rows,
                ordered=case.result_ordered,
            )
            reference_matches = reference_sha == case.expected_result_sha256
            reference_verified += int(reference_matches)
        strict_reference_available += int(strict_reference_sha is not None)
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
        table_match = actual_tables == expected_tables
        column_match = actual_columns == expected_columns
        join_match = actual_joins == expected_joins
        valid = bool(run.validated_sql and trace and not run.error)
        executable = run.rows is not None and not run.error
        candidate_sha = (
            result_checksum(run.rows, ordered=case.result_ordered) if run.rows is not None else None
        )
        result_match = bool(reference_matches and candidate_sha == reference_sha)
        candidate_strict_sha = (
            strict_result_checksum(run.rows, ordered=case.result_ordered)
            if run.rows is not None
            else None
        )
        strict_result_match = (
            bool(
                reference_matches
                and candidate_strict_sha == strict_reference_sha
            )
            if strict_reference_sha is not None
            else None
        )
        trace_conformance = bool(
            valid
            and metric_match
            and table_match
            and column_match
            and join_match
        )
        grain_contract_applicable = bool(GRAIN_RISK_TAGS.intersection(case.risk_tags))
        grain_contract_match = (
            trace_conformance if grain_contract_applicable else None
        )
        if run.repair_attempts:
            correction_attempted += 1
            correction_succeeded += int(valid and executable and result_match)
            if strict_result_match is not None:
                strict_correction_attempted += 1
                strict_correction_succeeded += int(
                    valid and executable and strict_result_match
                )
        error_category = classify_failure(
            case,
            run,
            valid=valid,
            metric_match=metric_match,
            table_match=table_match,
            column_match=column_match,
            join_match=join_match,
            result_match=result_match,
            strict_result_match=strict_result_match,
        )
        failure_labels = _failure_labels(
            run,
            metric_match=metric_match,
            table_match=table_match,
            column_match=column_match,
            join_match=join_match,
            executable=executable,
            result_match=result_match,
            strict_result_match=strict_result_match,
            grain_contract_match=grain_contract_match,
        )

        values: dict[str, float | None] = {
            "sql_validity_rate": float(valid),
            "sql_executability": float(executable),
            "execution_accuracy": float(result_match),
            "strict_execution_accuracy": (
                float(strict_result_match)
                if strict_result_match is not None
                else None
            ),
            "metric_accuracy": float(metric_match),
            "table_precision": table_precision,
            "table_recall": table_recall,
            "column_precision": column_precision,
            "column_recall": column_recall,
            "join_accuracy": float(join_match),
            "grain_safety_rate": (
                float(grain_contract_match)
                if grain_contract_match is not None
                else None
            ),
            "validator_acceptance_rate": float(valid),
            "trace_conformance_rate": float(trace_conformance),
            "grain_contract_accuracy": (
                float(grain_contract_match)
                if grain_contract_match is not None
                else None
            ),
        }
        for name, value in values.items():
            if value is not None:
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
                "strict_reference_result_sha256": strict_reference_sha,
                "strict_candidate_result_sha256": candidate_strict_sha,
                "reference_checksum_verified": reference_matches,
                "strict_reference_available": strict_reference_sha is not None,
                "grain_contract_applicable": grain_contract_applicable,
                "repair_attempts": run.repair_attempts,
                "latency_seconds": round(run.latency_seconds, 6),
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "error": run.error,
                "error_category": error_category,
                "failure_labels": failure_labels,
                **values,
            }
        )

    metrics: dict[str, Any] = {
        name: sum(values) / len(values) if values else None
        for name, values in aggregate.items()
    }
    metrics["correction_success_rate"] = (
        correction_succeeded / correction_attempted if correction_attempted else None
    )
    metrics["correction_attempted_count"] = correction_attempted
    metrics["correction_succeeded_count"] = correction_succeeded
    metrics["strict_correction_success_rate"] = (
        strict_correction_succeeded / strict_correction_attempted
        if strict_correction_attempted
        else None
    )
    metrics["strict_correction_attempted_count"] = strict_correction_attempted
    metrics["strict_correction_succeeded_count"] = strict_correction_succeeded
    metrics["strict_reference_available_count"] = strict_reference_available
    metrics["grain_contract_case_count"] = len(aggregate["grain_contract_accuracy"])
    summaries = summarize_case_results(case_results)
    return {
        "case_count": len(cases),
        "bucket_counts": dict(sorted(Counter(case.bucket for case in cases).items())),
        "reference_checksums_verified": reference_verified,
        "compatible_result_mismatch_count": sum(
            item["execution_accuracy"] == 0 for item in case_results
        ),
        "strict_result_mismatch_count": sum(
            item["strict_execution_accuracy"] == 0 for item in case_results
        ),
        "trace_deviation_count": sum(
            item["trace_conformance_rate"] == 0 for item in case_results
        ),
        "metrics": metrics,
        "error_counts": dict(
            sorted(
                Counter(
                    item["error_category"] for item in case_results if item["error_category"]
                ).items()
            )
        ),
        "failure_label_counts": dict(
            sorted(
                Counter(
                    label
                    for item in case_results
                    for label in item["failure_labels"]
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
        "strict_execution_accuracy",
        "metric_accuracy",
        "table_precision",
        "table_recall",
        "column_precision",
        "column_recall",
        "join_accuracy",
        "grain_safety_rate",
        "validator_acceptance_rate",
        "trace_conformance_rate",
        "grain_contract_accuracy",
        "grain_contract_applicable",
        "repair_attempts",
        "latency_seconds",
        "error_category",
        "failure_labels",
        "error",
        "generated_sql",
        "validated_sql",
    ]
    with (run_dir / "nl2sql_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(case_rows)

    failures = [item for item in case_rows if item["failure_labels"]]
    lines = [
        f"# {result['run_id']} Error Analysis",
        "",
        f"Failed cases: {len(failures)}/{len(case_rows)}",
        (
            "Compatible result mismatches: "
            f"{result['evaluation']['compatible_result_mismatch_count']}"
        ),
        (
            "Strict result mismatches: "
            f"{result['evaluation']['strict_result_mismatch_count']}"
        ),
        f"Trace deviations: {result['evaluation']['trace_deviation_count']}",
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
                    f"- Failure labels: {', '.join(item['failure_labels'])}",
                    f"- Compatible execution match: {bool(item['execution_accuracy'])}",
                    f"- Strict execution match: {item['strict_execution_accuracy']}",
                    f"- Trace conformance: {bool(item['trace_conformance_rate'])}",
                    f"- Grain contract: {item['grain_contract_accuracy']}",
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
