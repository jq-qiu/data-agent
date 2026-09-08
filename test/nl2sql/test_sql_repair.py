from pathlib import Path

import pytest

from app.metadata.catalog import load_catalog
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.repair import (
    build_structured_repair_constraints,
    canonicalize_group_join_keys,
    flatten_redundant_metric_subquery,
    normalize_calendar_numeric_literals,
)
from app.nl2sql.schema_linking import (
    SchemaLinkingFilter,
    SchemaLinkingJoin,
    SchemaLinkingOrder,
    SchemaLinkingPlan,
)
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


def _status_comparison_plan() -> SchemaLinkingPlan:
    return SchemaLinkingPlan(
        tables=("fact_order", "dim_date"),
        columns=(
            "fact_order.order_id",
            "fact_order.status",
            "fact_order.date_id",
            "dim_date.date_id",
            "dim_date.month",
        ),
        calendar_table="dim_date",
        join_relations=(
            SchemaLinkingJoin(
                relation_id="order_to_date",
                left_table="fact_order",
                left_column="date_id",
                right_table="dim_date",
                right_column="date_id",
            ),
        ),
        group_by_columns=("dim_date.month", "fact_order.status"),
        filters=(
            SchemaLinkingFilter(
                column_id="fact_order.status",
                values=("delivered", "canceled"),
                exclude=False,
            ),
        ),
        order_by=(
            SchemaLinkingOrder(column="dim_date.month"),
            SchemaLinkingOrder(column="fact_order.status"),
        ),
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


def test_structured_repair_constraints_make_grouping_plan_explicit() -> None:
    constraints = build_structured_repair_constraints(
        "SQL GROUP BY differs from SchemaLinkingPlan",
        _status_comparison_plan(),
    )

    assert "Allowed tables only: fact_order, dim_date" in constraints
    assert "Required calendar table: dim_date" in constraints
    assert (
        "fact_order.date_id = dim_date.date_id (order_to_date)"
        in constraints
    )
    assert "Required GROUP BY exactly: dim_date.month, fact_order.status" in constraints
    assert "Required ORDER BY exactly: dim_date.month ASC, fact_order.status ASC" in constraints
    assert "fact_order.status IN ('delivered', 'canceled')" in constraints
    assert "do not pivot group values" in constraints


def test_structured_repair_constraints_do_not_infer_without_plan() -> None:
    constraints = build_structured_repair_constraints("invalid", None)

    assert constraints == (
        "SchemaLinkingPlan unavailable; do not infer missing schema constraints."
    )


def test_sql015_t03_shape_is_normalized_flattened_and_validated() -> None:
    sql = (
        "SELECT SUM(order_count) AS 整体订单数 FROM "
        "(SELECT order_count, date_id, region_id FROM dws_sales_region_daily "
        "WHERE date_id >= '2018-05-01' AND date_id < '2018-06-01') t"
    )
    normalized = normalize_calendar_numeric_literals(sql, _order_count_plan())
    flattened = flatten_redundant_metric_subquery(normalized, _order_count_plan())

    assert "date_id >= 20180501 AND date_id < 20180601" in flattened
    assert "SUM(dws_sales_region_daily.order_count)" in flattened
    assert "region_id" not in flattened
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


def test_normalizes_iso_date_id_literals_only_for_dim_date() -> None:
    sql = (
        "SELECT d.month FROM dim_date d "
        "WHERE d.date_id = '2018-05-01' AND d.month = '2018-05'"
    )
    normalized = normalize_calendar_numeric_literals(sql, _calendar_plan())

    assert "d.date_id = 20180501" in normalized
    assert "d.month = '2018-05'" in normalized
    unrelated = "SELECT order_id FROM fact_order WHERE date_id = '2018-05-01'"
    assert normalize_calendar_numeric_literals(unrelated, _calendar_plan()) == unrelated


def test_flattens_unqualified_derived_column_references() -> None:
    sql = (
        "SELECT SUM(order_count) AS total_orders "
        "FROM (SELECT order_count, date_id FROM dws_sales_region_daily) t"
    )

    flattened = flatten_redundant_metric_subquery(sql, _order_count_plan())

    assert "SUM(dws_sales_region_daily.order_count)" in flattened
    assert "FROM dws_sales_region_daily" in flattened



def test_canonicalizes_group_by_to_equality_join_plan_column() -> None:
    sql = (
        "SELECT dc.category_name_en AS 英文品类, SUM(foi.price) AS 成交总额 "
        "FROM fact_order_item foi "
        "JOIN fact_order fo ON foi.order_id = fo.order_id "
        "JOIN dim_product dp ON foi.product_id = dp.product_id "
        "JOIN dim_category dc ON dp.category_id = dc.category_id "
        "WHERE fo.status NOT IN ('canceled','unavailable') "
        "GROUP BY dp.category_id, dc.category_name_en "
        "ORDER BY dc.category_name_en ASC"
    )
    plan = SchemaLinkingPlan(
        tables=(
            "fact_order_item",
            "fact_order",
            "dim_product",
            "dim_category",
        ),
        columns=(
            "fact_order_item.price",
            "fact_order_item.order_id",
            "fact_order_item.product_id",
            "fact_order.order_id",
            "fact_order.status",
            "dim_product.product_id",
            "dim_product.category_id",
            "dim_category.category_id",
            "dim_category.category_name_en",
        ),
        join_relations=(
            SchemaLinkingJoin(
                relation_id="product_to_category",
                left_table="dim_product",
                left_column="category_id",
                right_table="dim_category",
                right_column="category_id",
            ),
            SchemaLinkingJoin(
                relation_id="order_item_to_product",
                left_table="fact_order_item",
                left_column="product_id",
                right_table="dim_product",
                right_column="product_id",
            ),
            SchemaLinkingJoin(
                relation_id="order_item_to_order",
                left_table="fact_order_item",
                left_column="order_id",
                right_table="fact_order",
                right_column="order_id",
            ),
        ),
        group_by_columns=("dim_category.category_id",),
        display_columns=("dim_category.category_name_en",),
    )

    normalized = canonicalize_group_join_keys(sql, plan)

    assert "GROUP BY dc.category_id, dc.category_name_en" in normalized
    assert "GROUP BY dp.category_id" not in normalized


def test_group_join_key_rewrite_requires_unique_plan_target() -> None:
    sql = (
        "SELECT dp.category_id, SUM(foi.price) FROM fact_order_item foi "
        "JOIN dim_product dp ON foi.product_id = dp.product_id "
        "GROUP BY dp.category_id"
    )
    plan = SchemaLinkingPlan(
        tables=("fact_order_item", "dim_product"),
        columns=(
            "fact_order_item.price",
            "fact_order_item.product_id",
            "dim_product.product_id",
            "dim_product.category_id",
        ),
        join_relations=(
            SchemaLinkingJoin(
                relation_id="order_item_to_product",
                left_table="fact_order_item",
                left_column="product_id",
                right_table="dim_product",
                right_column="product_id",
            ),
        ),
        group_by_columns=(),
    )

    assert canonicalize_group_join_keys(sql, plan) == sql
