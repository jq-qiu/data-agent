from pathlib import Path

import pytest

from app.metadata.catalog import load_catalog
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.repair import (
    flatten_redundant_metric_subquery,
    normalize_calendar_numeric_literals,
)
from app.nl2sql.schema_linking import SchemaLinkingPlan
from app.nl2sql.validator import SQLValidator

ROOT = Path(__file__).parents[2]


def _calendar_plan() -> SchemaLinkingPlan:
    return SchemaLinkingPlan(
        tables=("dim_date",),
        columns=(
            "dim_date.year",
            "dim_date.quarter",
            "dim_date.date_id",
            "dim_date.month",
            "dim_date.date",
        ),
        calendar_table="dim_date",
        join_relations=(),
    )


def _order_count_plan() -> SchemaLinkingPlan:
    return SchemaLinkingPlan(
        metric_ids=("order_count",),
        tables=("dws_sales_region_daily",),
        columns=(
            "dws_sales_region_daily.order_count",
            "dws_sales_region_daily.date_id",
        ),
        required_metric_columns=("dws_sales_region_daily.order_count",),
        join_relations=(),
    )


def test_normalizes_plan_calendar_numeric_literals_with_aliases() -> None:
    sql = (
        "SELECT d.month FROM dim_date d "
        "WHERE d.year = '2018' AND '2' = d.quarter "
        "AND d.date_id IN ('20180501', '20180531') "
        "AND d.month = '2018-05' AND d.date = '2018-05-01'"
    )

    normalized = normalize_calendar_numeric_literals(sql, _calendar_plan())

    assert "d.year = 2018" in normalized
    assert "2 = d.quarter" in normalized
    assert "d.date_id IN (20180501, 20180531)" in normalized
    assert "d.month = '2018-05'" in normalized
    assert "d.date = '2018-05-01'" in normalized


def test_normalizes_unqualified_calendar_column_when_plan_is_unambiguous() -> None:
    sql = "SELECT month FROM dim_date WHERE year = '2018'"

    normalized = normalize_calendar_numeric_literals(sql, _calendar_plan())

    assert "year = 2018" in normalized


def test_leaves_non_calendar_and_noncanonical_literals_unchanged() -> None:
    sql = (
        "SELECT d.month FROM dim_date d "
        "WHERE d.year = '18' AND d.quarter = '5' AND d.date_id = 'date-id'"
    )
    unrelated = "SELECT order_id FROM fact_order WHERE date_id = '20180501'"

    assert normalize_calendar_numeric_literals(sql, _calendar_plan()) == sql
    assert normalize_calendar_numeric_literals(unrelated, _calendar_plan()) == unrelated


def test_leaves_sql_unchanged_without_eligible_plan_or_valid_parse() -> None:
    sql = "SELECT year FROM dim_date WHERE year = '2018'"
    other_calendar = SchemaLinkingPlan(
        tables=("fact_order",),
        columns=("fact_order.date_id",),
        calendar_table="fact_order",
        join_relations=(),
    )

    assert normalize_calendar_numeric_literals(sql, None) == sql
    assert normalize_calendar_numeric_literals(sql, other_calendar) == sql
    assert normalize_calendar_numeric_literals("SELECT 'unterminated", _calendar_plan()) == (
        "SELECT 'unterminated"
    )


def test_flattens_redundant_required_metric_subquery_and_passes_validator() -> None:
    sql = (
        "SELECT SUM(t.order_count) AS total_orders "
        "FROM (SELECT order_count, date_id, region_id "
        "FROM dws_sales_region_daily "
        "WHERE date_id >= 20180501 AND date_id < 20180601) t"
    )

    flattened = flatten_redundant_metric_subquery(sql, _order_count_plan())

    assert "FROM dws_sales_region_daily" in flattened
    assert "SUM(dws_sales_region_daily.order_count)" in flattened
    assert "region_id" not in flattened
    assert "date_id >= 20180501 AND date_id < 20180601" in flattened
    validator = SQLValidator(
        load_catalog(ROOT / "conf" / "meta_config.yaml"),
        load_sql_policy(ROOT / "conf" / "sql_policy.yaml"),
    )
    validated = validator.validate(
        flattened,
        ("order_count",),
        schema_linking_plan=_order_count_plan(),
    )
    assert set(validated.columns) == {
        "dws_sales_region_daily.order_count",
        "dws_sales_region_daily.date_id",
    }


def test_flattens_aliased_inner_projection_to_physical_column() -> None:
    sql = (
        "SELECT SUM(x.orders) AS total_orders "
        "FROM (SELECT r.order_count AS orders, r.date_id "
        "FROM dws_sales_region_daily r WHERE r.date_id >= 20180501) x"
    )

    flattened = flatten_redundant_metric_subquery(sql, _order_count_plan())

    assert "SUM(r.order_count)" in flattened
    assert "FROM dws_sales_region_daily AS r" in flattened
    assert "WHERE r.date_id >= 20180501" in flattened


@pytest.mark.parametrize(
    "sql",
    (
        (
            "SELECT SUM(t.order_count) FROM "
            "(SELECT SUM(order_count) AS order_count FROM dws_sales_region_daily) t"
        ),
        (
            "SELECT SUM(t.order_count) FROM "
            "(SELECT order_count FROM dws_sales_region_daily GROUP BY order_count) t"
        ),
        (
            "SELECT SUM(t.order_count) FROM "
            "(SELECT DISTINCT order_count FROM dws_sales_region_daily) t"
        ),
        (
            "SELECT SUM(t.order_count) FROM "
            "(SELECT order_count FROM dws_sales_region_daily LIMIT 5) t"
        ),
        (
            "SELECT SUM(t.order_count) FROM "
            "(SELECT order_count, region_id FROM dws_sales_region_daily "
            "WHERE region_id = 'SP') t"
        ),
        (
            "SELECT SUM(t.order_count) FROM "
            "(SELECT order_count FROM dws_sales_region_daily) t WHERE t.order_count > 0"
        ),
    ),
)
def test_leaves_unsafe_or_plan_divergent_subqueries_unchanged(sql: str) -> None:
    assert flatten_redundant_metric_subquery(sql, _order_count_plan()) == sql


def test_leaves_subquery_unchanged_without_required_metric_contract() -> None:
    sql = (
        "SELECT SUM(t.order_count) FROM "
        "(SELECT order_count FROM dws_sales_region_daily) t"
    )
    plan = _order_count_plan().model_copy(update={"required_metric_columns": ()})

    assert flatten_redundant_metric_subquery(sql, plan) == sql
