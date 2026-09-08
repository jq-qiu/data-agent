import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.metadata.catalog import load_catalog
from app.nl2sql.evaluation import (
    BUCKETS,
    NL2SQLGoldenCase,
    NL2SQLRun,
    RecordingRunner,
    ReplayCacheIdentity,
    ReplayRunner,
    evaluate_nl2sql_cases,
    evaluate_safety_probes,
    load_nl2sql_golden,
    load_replay_cache,
    result_checksum,
    strict_result_checksum,
    write_replay_cache,
)
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.validator import SQLValidator

ROOT = Path(__file__).parents[2]
GOLDEN_PATH = ROOT / "data" / "evaluation" / "nl2sql_golden_v1.json"


@pytest.fixture(scope="module")
def validator() -> SQLValidator:
    return SQLValidator(
        load_catalog(ROOT / "conf" / "meta_config.yaml"),
        load_sql_policy(ROOT / "conf" / "sql_policy.yaml"),
    )


def test_golden_has_30_balanced_cases_and_reference_traces(validator: SQLValidator) -> None:
    version, cases = load_nl2sql_golden(GOLDEN_PATH)

    assert version == "nl2sql-golden-v1"
    assert len(cases) == 30
    assert {bucket: sum(case.bucket == bucket for case in cases) for bucket in BUCKETS} == {
        bucket: 5 for bucket in BUCKETS
    }
    for case in cases:
        trace = validator.validate(case.reference_sql, case.expected_metric_ids)
        assert set(trace.tables) == set(case.expected_tables), case.case_id
        assert set(trace.columns) == set(case.expected_columns), case.case_id
        assert set(trace.join_relations) == set(case.expected_join_relations), case.case_id


def test_result_checksum_ignores_alias_column_order_and_decimal_representation() -> None:
    left = [{"month": "2018-05", "gmv": Decimal("10.00")}]
    right = [{"成交总额": 10, "月份": "2018-05"}]

    assert result_checksum(left, ordered=False) == result_checksum(right, ordered=False)
    assert strict_result_checksum(left, ordered=False) != strict_result_checksum(
        right,
        ordered=False,
    )


def test_result_checksum_preserves_topn_row_order() -> None:
    left = [{"category": "A", "gmv": 2}, {"category": "B", "gmv": 1}]
    reversed_rows = list(reversed(left))

    assert result_checksum(left, ordered=True) != result_checksum(reversed_rows, ordered=True)
    assert result_checksum(left, ordered=False) == result_checksum(reversed_rows, ordered=False)


def test_all_fixed_dangerous_sql_probes_are_rejected(validator: SQLValidator) -> None:
    result = evaluate_safety_probes(validator)

    assert result["probe_count"] == 12
    assert result["rejected_count"] == 12
    assert result["dangerous_sql_allowed_count"] == 0


@pytest.mark.asyncio
async def test_evaluator_compares_results_and_reports_all_metrics() -> None:
    reference_rows = [{"gmv": Decimal("10.00")}]
    case = NL2SQLGoldenCase(
        case_id="unit",
        bucket="aggregate",
        question="GMV是多少",
        expected_metric_ids=("gmv",),
        expected_tables=("dws_sales_region_daily",),
        expected_columns=("dws_sales_region_daily.gmv",),
        expected_join_relations=(),
        reference_sql="SELECT SUM(gmv) AS total_gmv FROM dws_sales_region_daily",
        expected_result_sha256=result_checksum(reference_rows, ordered=False),
        risk_tags=("metric_formula",),
        result_ordered=False,
    )

    async def run_reference(_: NL2SQLGoldenCase) -> list[dict]:
        return reference_rows

    async def run_candidate(_: NL2SQLGoldenCase) -> NL2SQLRun:
        return NL2SQLRun(
            generated_sql=case.reference_sql,
            validated_sql=f"{case.reference_sql} LIMIT 500",
            rows=[{"成交总额": 10}],
            metric_ids=("gmv",),
            validation_trace={
                "tables": ["dws_sales_region_daily"],
                "columns": ["dws_sales_region_daily.gmv"],
                "join_relations": [],
            },
        )

    result = await evaluate_nl2sql_cases((case,), run_candidate, run_reference)

    assert result["reference_checksums_verified"] == 1
    assert result["error_counts"] == {}
    assert result["metrics"]["execution_accuracy"] == 1
    assert result["metrics"]["strict_execution_accuracy"] == 1
    assert result["metrics"]["table_recall"] == 1
    assert result["metrics"]["column_precision"] == 1
    assert result["metrics"]["validator_acceptance_rate"] == 1
    assert result["metrics"]["trace_conformance_rate"] == 1
    assert result["metrics"]["grain_contract_accuracy"] is None
    assert result["metrics"]["grain_contract_case_count"] == 0
    assert result["metrics"]["correction_success_rate"] is None
    assert result["bucket_metrics"]["aggregate"]["execution_accuracy"] == 1
    assert result["latency_seconds"]["max"] >= 0


def _replay_identity() -> ReplayCacheIdentity:
    return ReplayCacheIdentity(
        dataset_sha256="dataset",
        prompt_bundle_sha256="prompts",
        runtime_bundle_sha256="runtime",
        metadata_version="metadata",
        sql_policy_version="policy",
        model_name="model",
        source_commit="commit",
        source_dirty=False,
    )


def test_replay_cache_round_trip_preserves_database_scalar_types() -> None:
    rows = [
        {
            "decimal": Decimal("10.00"),
            "date": date(2018, 5, 1),
            "datetime": datetime(2018, 5, 1, 12, 30, tzinfo=UTC),
            "time": time(12, 30),
            "bytes": b"data",
            "int": 2,
            "float": 1.5,
            "bool": True,
            "null": None,
            "text": "SP",
        }
    ]
    run = NL2SQLRun(
        generated_sql="SELECT 1",
        validated_sql="SELECT 1 LIMIT 500",
        rows=rows,
        metric_ids=("gmv",),
        validation_trace={"tables": ["dws_sales_region_daily"]},
        latency_seconds=0.25,
    )

    (ROOT / ".tmp").mkdir(exist_ok=True)
    with TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        cache_path = Path(directory) / "replay.json"
        write_replay_cache(
            cache_path,
            _replay_identity(),
            {"case": run},
            {"case": "strict-reference"},
        )
        loaded = load_replay_cache(cache_path, _replay_identity(), ("case",))

    assert loaded.runs["case"].rows == rows
    assert loaded.strict_reference_sha256 == {"case": "strict-reference"}
    assert result_checksum(loaded.runs["case"].rows or [], ordered=True) == result_checksum(
        rows,
        ordered=True,
    )


def test_replay_cache_rejects_tampering_and_stale_identity() -> None:
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        cache_path = Path(directory) / "replay.json"
        write_replay_cache(cache_path, _replay_identity(), {"case": NL2SQLRun()})

        identity_values = _replay_identity().__dict__
        stale = ReplayCacheIdentity(
            **{**identity_values, "runtime_bundle_sha256": "changed"}
        )
        with pytest.raises(ValueError, match="identity mismatch"):
            load_replay_cache(cache_path, stale, ("case",))

        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        payload["runs"]["case"]["generated_sql"] = "SELECT 2"
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="checksum mismatch"):
            load_replay_cache(cache_path, _replay_identity(), ("case",))


@pytest.mark.asyncio
async def test_recorded_run_replays_identical_evaluation() -> None:
    rows = [{"gmv": Decimal("10.00")}]
    case = NL2SQLGoldenCase(
        case_id="replay",
        bucket="aggregate",
        question="GMV是多少",
        expected_metric_ids=("gmv",),
        expected_tables=("dws_sales_region_daily",),
        expected_columns=("dws_sales_region_daily.gmv",),
        expected_join_relations=(),
        reference_sql="SELECT SUM(gmv) FROM dws_sales_region_daily",
        expected_result_sha256=result_checksum(rows, ordered=False),
        risk_tags=(),
        result_ordered=False,
    )

    async def candidate(_: NL2SQLGoldenCase) -> NL2SQLRun:
        return NL2SQLRun(
            generated_sql=case.reference_sql,
            validated_sql=f"{case.reference_sql} LIMIT 500",
            rows=rows,
            metric_ids=("gmv",),
            validation_trace={
                "tables": ["dws_sales_region_daily"],
                "columns": ["dws_sales_region_daily.gmv"],
                "join_relations": [],
            },
            latency_seconds=0.5,
        )

    recorder = RecordingRunner(candidate)

    async def reference(_: NL2SQLGoldenCase) -> list[dict]:
        return rows

    live_result = await evaluate_nl2sql_cases((case,), recorder, reference)
    strict_references = {
        item["case_id"]: item["strict_reference_result_sha256"]
        for item in live_result["cases"]
    }
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        cache_path = Path(directory) / "replay.json"
        write_replay_cache(
            cache_path,
            _replay_identity(),
            recorder.runs,
            strict_references,
        )
        cached = load_replay_cache(cache_path, _replay_identity(), (case.case_id,))
    replay_result = await evaluate_nl2sql_cases(
        (case,),
        ReplayRunner(cached.runs),
        strict_reference_sha256=cached.strict_reference_sha256,
    )

    assert replay_result == live_result


@pytest.mark.asyncio
async def test_missing_strict_reference_is_reported_as_unavailable() -> None:
    rows = [{"month": "2018-05", "gmv": Decimal("10.00")}]
    case = NL2SQLGoldenCase(
        case_id="no-strict-reference",
        bucket="aggregate",
        question="GMV是多少",
        expected_metric_ids=("gmv",),
        expected_tables=("dws_sales_region_daily",),
        expected_columns=("dws_sales_region_daily.gmv",),
        expected_join_relations=(),
        reference_sql="SELECT SUM(gmv) FROM dws_sales_region_daily",
        expected_result_sha256=result_checksum(rows, ordered=False),
        risk_tags=(),
        result_ordered=False,
    )

    async def candidate(_: NL2SQLGoldenCase) -> NL2SQLRun:
        return NL2SQLRun(
            validated_sql="SELECT 1 LIMIT 500",
            rows=rows,
            metric_ids=("gmv",),
            validation_trace={
                "tables": ["dws_sales_region_daily"],
                "columns": ["dws_sales_region_daily.gmv"],
                "join_relations": [],
            },
        )

    result = await evaluate_nl2sql_cases((case,), candidate)

    assert result["metrics"]["execution_accuracy"] == 1
    assert result["metrics"]["strict_execution_accuracy"] is None
    assert result["metrics"]["strict_reference_available_count"] == 0


@pytest.mark.asyncio
async def test_correction_requires_correct_result_and_reports_multiple_failures() -> None:
    reference_rows = [{"order_count": 10}]
    case = NL2SQLGoldenCase(
        case_id="correction",
        bucket="aggregate",
        question="整体订单量是多少",
        expected_metric_ids=("order_count",),
        expected_tables=("dws_sales_region_daily",),
        expected_columns=("dws_sales_region_daily.order_count",),
        expected_join_relations=(),
        reference_sql="SELECT SUM(order_count) FROM dws_sales_region_daily",
        expected_result_sha256=result_checksum(reference_rows, ordered=False),
        risk_tags=("overall_order_grain",),
        result_ordered=False,
    )

    async def reference(_: NL2SQLGoldenCase) -> list[dict]:
        return reference_rows

    async def candidate(_: NL2SQLGoldenCase) -> NL2SQLRun:
        return NL2SQLRun(
            validated_sql="SELECT COUNT(*) FROM fact_order_item LIMIT 500",
            rows=[{"order_count": 12}],
            metric_ids=("order_count",),
            validation_trace={
                "tables": ["fact_order_item"],
                "columns": ["fact_order_item.order_id"],
                "join_relations": [],
            },
            repair_attempts=1,
        )

    result = await evaluate_nl2sql_cases((case,), candidate, reference)
    evaluated_case = result["cases"][0]

    assert result["metrics"]["correction_success_rate"] == 0
    assert result["metrics"]["strict_correction_success_rate"] == 0
    assert result["metrics"]["validator_acceptance_rate"] == 1
    assert result["metrics"]["grain_contract_accuracy"] == 0
    assert evaluated_case["grain_safety_rate"] == 0
    assert set(evaluated_case["failure_labels"]) >= {
        "Schema Linking Error",
        "Result Value Mismatch",
        "Result Shape Mismatch",
        "Grain Contract Error",
    }


@pytest.mark.asyncio
async def test_extra_schema_trace_has_primary_classification_even_when_result_matches() -> None:
    rows = [{"month": "2018-05", "gmv": Decimal("10.00")}]
    case = NL2SQLGoldenCase(
        case_id="extra-trace",
        bucket="comparison",
        question="比较GMV",
        expected_metric_ids=("gmv",),
        expected_tables=("dws_sales_region_daily",),
        expected_columns=("dws_sales_region_daily.gmv",),
        expected_join_relations=(),
        reference_sql="SELECT month, SUM(gmv) FROM dws_sales_region_daily",
        expected_result_sha256=result_checksum(rows, ordered=False),
        risk_tags=(),
        result_ordered=False,
    )

    async def reference(_: NL2SQLGoldenCase) -> list[dict]:
        return rows

    async def candidate(_: NL2SQLGoldenCase) -> NL2SQLRun:
        return NL2SQLRun(
            validated_sql="SELECT month, SUM(gmv) FROM extra_join LIMIT 500",
            rows=rows,
            metric_ids=("gmv",),
            validation_trace={
                "tables": ["dws_sales_region_daily", "dim_date"],
                "columns": ["dws_sales_region_daily.gmv", "dim_date.month"],
                "join_relations": [],
            },
        )

    result = await evaluate_nl2sql_cases((case,), candidate, reference)
    evaluated_case = result["cases"][0]

    assert evaluated_case["execution_accuracy"] == 1
    assert evaluated_case["strict_execution_accuracy"] == 1
    assert evaluated_case["trace_conformance_rate"] == 0
    assert evaluated_case["failure_labels"] == ["Schema Linking Error"]
    assert evaluated_case["error_category"] == "Schema Linking Error"
    assert all(
        not item["failure_labels"] or item["error_category"]
        for item in result["cases"]
    )
