from decimal import Decimal
from pathlib import Path

import pytest

from app.metadata.catalog import load_catalog
from app.nl2sql.evaluation import (
    BUCKETS,
    NL2SQLGoldenCase,
    NL2SQLRun,
    evaluate_nl2sql_cases,
    evaluate_safety_probes,
    load_nl2sql_golden,
    result_checksum,
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
