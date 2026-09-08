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
    assert result["metrics"]["table_recall"] == 1
    assert result["metrics"]["column_precision"] == 1
    assert result["metrics"]["correction_success_rate"] is None
    assert result["bucket_metrics"]["aggregate"]["execution_accuracy"] == 1
    assert result["latency_seconds"]["max"] >= 0


def _replay_identity() -> ReplayCacheIdentity:
    return ReplayCacheIdentity(
        dataset_sha256="dataset",
        prompt_bundle_sha256="prompts",
        metadata_version="metadata",
        sql_policy_version="policy",
        model_name="model",
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
        write_replay_cache(cache_path, _replay_identity(), {"case": run})
        loaded = load_replay_cache(cache_path, _replay_identity(), ("case",))

    assert loaded["case"].rows == rows
    assert result_checksum(loaded["case"].rows or [], ordered=True) == result_checksum(
        rows,
        ordered=True,
    )


def test_replay_cache_rejects_tampering_and_stale_identity() -> None:
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        cache_path = Path(directory) / "replay.json"
        write_replay_cache(cache_path, _replay_identity(), {"case": NL2SQLRun()})

        identity_values = _replay_identity().__dict__
        stale = ReplayCacheIdentity(**{**identity_values, "model_name": "other"})
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
    live_result = await evaluate_nl2sql_cases((case,), recorder)
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        cache_path = Path(directory) / "replay.json"
        write_replay_cache(cache_path, _replay_identity(), recorder.runs)
        cached = load_replay_cache(cache_path, _replay_identity(), (case.case_id,))
    replay_result = await evaluate_nl2sql_cases((case,), ReplayRunner(cached))

    assert replay_result == live_result
