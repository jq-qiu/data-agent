from pathlib import Path

import pytest

from app.metadata.catalog import load_catalog
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.routing import route_after_validation
from app.nl2sql.validator import SQLValidationError, SQLValidator

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def validator() -> SQLValidator:
    return SQLValidator(
        load_catalog(ROOT / "conf" / "meta_config.yaml"),
        load_sql_policy(ROOT / "conf" / "sql_policy.yaml"),
    )


def test_valid_gmv_query_is_normalized_limited_and_traced(validator: SQLValidator) -> None:
    result = validator.validate(
        """
        SELECT SUM(i.price) AS gmv
        FROM fact_order_item i
        JOIN fact_order o ON i.order_id = o.order_id
        WHERE o.status NOT IN ('canceled', 'unavailable')
        """,
        ("gmv",),
    )

    assert result.sql.endswith("LIMIT 500")
    assert result.tables == ("fact_order", "fact_order_item")
    assert result.join_relations == ("order_item_to_order",)
    assert result.grain_warnings
    assert result.policy_version == "sql-policy-v1.1"


def test_existing_limit_is_reduced_to_policy_maximum(validator: SQLValidator) -> None:
    result = validator.validate("SELECT order_id FROM fact_order LIMIT 5000")

    assert result.sql.endswith("LIMIT 500")


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("SELECT order_id FROM fact_order; SELECT order_id FROM fact_order", "exactly one"),
        ("DELETE FROM fact_order", "only SELECT"),
        ("SELECT order_id FROM fact_order -- bypass", "comments"),
        ("SELECT * FROM fact_order", r"SELECT \*"),
        ("SELECT table_name FROM information_schema.tables", "database is not allowed"),
        ("SELECT order_id FROM unknown_table", "table is not registered"),
        ("SELECT imaginary FROM fact_order", "column is not registered"),
        ("SELECT SLEEP(10) FROM fact_order", "function is forbidden"),
        ("SELECT MD5(order_id) FROM fact_order", "function is not allowlisted"),
        ("SELECT @unsafe FROM fact_order", "variables are forbidden"),
    ],
)
def test_unsafe_or_unregistered_sql_is_rejected(
    validator: SQLValidator,
    sql: str,
    message: str,
) -> None:
    with pytest.raises(SQLValidationError, match=message):
        validator.validate(sql)


def test_unregistered_join_key_is_rejected(validator: SQLValidator) -> None:
    with pytest.raises(SQLValidationError, match="JOIN is not registered"):
        validator.validate(
            "SELECT i.price FROM fact_order_item i JOIN fact_order o ON i.product_id = o.order_id"
        )


def test_sensitive_customer_identifier_cannot_be_projected(validator: SQLValidator) -> None:
    with pytest.raises(SQLValidationError, match="sensitive column"):
        validator.validate("SELECT customer_id FROM dim_customer")


def test_payment_item_fanout_is_rejected(validator: SQLValidator) -> None:
    with pytest.raises(SQLValidationError, match="aggregated separately"):
        validator.validate(
            """
            SELECT SUM(i.price)
            FROM fact_order_item i
            JOIN fact_order o ON i.order_id = o.order_id
            JOIN fact_payment p ON p.order_id = o.order_id
            """
        )


def test_gmv_requires_status_exclusions(validator: SQLValidator) -> None:
    with pytest.raises(SQLValidationError, match="exclude canceled/unavailable"):
        validator.validate(
            "SELECT SUM(i.price) FROM fact_order_item i "
            "JOIN fact_order o ON i.order_id = o.order_id",
            ("gmv",),
        )


def test_aov_requires_region_dws_components(validator: SQLValidator) -> None:
    with pytest.raises(SQLValidationError, match="region-DWS"):
        validator.validate("SELECT AVG(price) FROM fact_order_item", ("aov",))


def test_category_order_count_requires_category_scope(validator: SQLValidator) -> None:
    with pytest.raises(SQLValidationError, match="category grouping"):
        validator.validate(
            "SELECT SUM(category_order_count) FROM dws_sales_category_daily",
            ("category_order_count",),
        )

    result = validator.validate(
        "SELECT category_id, SUM(category_order_count) "
        "FROM dws_sales_category_daily GROUP BY category_id",
        ("category_order_count",),
    )
    assert "GROUP BY category_id" in result.sql


def test_read_only_cte_is_allowed_and_limited(validator: SQLValidator) -> None:
    result = validator.validate(
        "WITH monthly AS ("
        "SELECT date_id, SUM(gmv) AS gmv FROM dws_sales_region_daily GROUP BY date_id"
        ") SELECT date_id, gmv FROM monthly"
    )

    assert result.sql.startswith("WITH monthly AS")
    assert result.sql.endswith("LIMIT 500")


def test_count_star_is_allowed_but_projection_stars_remain_forbidden(
    validator: SQLValidator,
) -> None:
    result = validator.validate("SELECT COUNT(*) AS row_count FROM fact_order")

    assert "COUNT(*)" in result.sql
    for sql in (
        "SELECT * FROM fact_order",
        "SELECT o.* FROM fact_order AS o",
        "SELECT SUM(*) FROM fact_order",
    ):
        with pytest.raises(SQLValidationError, match=r"SELECT \*"):
            validator.validate(sql)


def test_cte_alias_can_only_reference_declared_output_columns(
    validator: SQLValidator,
) -> None:
    result = validator.validate(
        "WITH monthly AS ("
        "SELECT date_id, SUM(gmv) AS gmv FROM dws_sales_region_daily GROUP BY date_id"
        ") SELECT m.date_id, m.gmv FROM monthly AS m"
    )

    assert result.tables == ("dws_sales_region_daily",)
    with pytest.raises(SQLValidationError, match="not exposed by CTE"):
        validator.validate(
            "WITH monthly AS (SELECT date_id FROM dws_sales_region_daily) "
            "SELECT m.gmv FROM monthly AS m"
        )


def test_grouped_topn_window_shape_is_allowlisted_and_constrained(
    validator: SQLValidator,
) -> None:
    result = validator.validate(
        "WITH state_product_gmv AS ("
        "SELECT c.state AS state, i.product_id AS product_id, SUM(i.price) AS gmv "
        "FROM fact_order_item AS i "
        "JOIN fact_order AS o ON i.order_id = o.order_id "
        "JOIN dim_customer AS c ON o.customer_id = c.customer_id "
        "WHERE o.purchase_date >= '2018-01-01' AND o.purchase_date < '2019-01-01' "
        "AND o.status NOT IN ('canceled', 'unavailable') "
        "GROUP BY c.state, i.product_id"
        "), ranked AS ("
        "SELECT state, product_id, gmv, "
        "ROW_NUMBER() OVER ("
        "PARTITION BY state ORDER BY gmv DESC, product_id ASC"
        ") AS rank_position FROM state_product_gmv"
        ") SELECT r.state, r.product_id, r.gmv, r.rank_position "
        "FROM ranked AS r WHERE r.rank_position <= 3 "
        "ORDER BY r.state, r.rank_position",
        ("gmv",),
    )

    assert result.tables == ("dim_customer", "fact_order", "fact_order_item")
    assert result.join_relations == ("order_item_to_order", "order_to_customer")
    assert "ROW_NUMBER() OVER" in result.sql

    invalid_shapes = (
        "SELECT ROW_NUMBER() AS rn FROM fact_order",
        "SELECT ROW_NUMBER() OVER (ORDER BY purchase_date) AS rn FROM fact_order",
        "SELECT ROW_NUMBER() OVER (PARTITION BY status) AS rn FROM fact_order",
    )
    for sql in invalid_shapes:
        with pytest.raises(SQLValidationError, match="ROW_NUMBER requires"):
            validator.validate(sql)

    for function in ("RANK()", "DENSE_RANK()", "LAG(purchase_date)"):
        sql = (
            f"SELECT {function} OVER (PARTITION BY status ORDER BY purchase_date) AS rn "
            "FROM fact_order"
        )
        with pytest.raises(SQLValidationError, match="not allowlisted"):
            validator.validate(sql)


def test_validation_route_allows_only_one_repair() -> None:
    assert route_after_validation({"error": None, "repair_attempts": 0}) == "execute_sql"
    assert route_after_validation({"error": "invalid", "repair_attempts": 0}) == "correct_sql"
    assert route_after_validation({"error": "still invalid", "repair_attempts": 1}) == "end"


def test_year_extraction_is_allowed_but_raw_ts_or_ds_to_date_is_not(
    validator: SQLValidator,
) -> None:
    result = validator.validate("SELECT YEAR(purchase_date) AS y FROM fact_order")

    assert "YEAR(" in result.sql
    with pytest.raises(SQLValidationError, match="not allowlisted"):
        validator.validate("SELECT TS_OR_DS_TO_DATE(purchase_date) FROM fact_order")


def test_derived_table_alias_resolves_declared_outputs(validator: SQLValidator) -> None:
    result = validator.validate(
        "SELECT t.state FROM (SELECT c.state FROM dim_customer AS c) AS t"
    )

    assert result.tables == ("dim_customer",)
    with pytest.raises(SQLValidationError, match="not exposed by CTE"):
        validator.validate(
            "SELECT t.gmv FROM (SELECT c.state FROM dim_customer AS c) AS t"
        )


def test_grouped_topn_derived_table_with_qualified_columns(
    validator: SQLValidator,
) -> None:
    result = validator.validate(
        "SELECT t.state AS state, t.product_id AS product_id, t.sales_amount AS sales_amount "
        "FROM ("
        "SELECT c.state, oi.product_id, SUM(oi.price) AS sales_amount, "
        "ROW_NUMBER() OVER ("
        "PARTITION BY c.state ORDER BY SUM(oi.price) DESC, oi.product_id ASC"
        ") AS rn "
        "FROM fact_order_item oi "
        "JOIN fact_order o ON oi.order_id = o.order_id "
        "JOIN dim_customer c ON o.customer_id = c.customer_id "
        "WHERE o.purchase_date >= '2018-01-01' AND o.purchase_date < '2019-01-01' "
        "AND o.status NOT IN ('canceled', 'unavailable') "
        "GROUP BY c.state, oi.product_id"
        ") t "
        "WHERE t.rn <= 3 ORDER BY t.state, t.sales_amount, t.product_id",
        ("gmv",),
    )

    assert result.tables == ("dim_customer", "fact_order", "fact_order_item")
    assert result.join_relations == ("order_item_to_order", "order_to_customer")
    assert "ROW_NUMBER() OVER" in result.sql
