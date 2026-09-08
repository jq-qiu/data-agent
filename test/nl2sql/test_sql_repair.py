from app.nl2sql.repair import normalize_calendar_numeric_literals
from app.nl2sql.schema_linking import SchemaLinkingPlan


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
