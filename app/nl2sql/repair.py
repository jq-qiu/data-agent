"""Deterministic, plan-bounded normalization for one-shot SQL repair output."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from app.nl2sql.schema_linking import SchemaLinkingPlan

_NUMERIC_CALENDAR_PATTERNS = {
    "year": re.compile(r"\d{4}"),
    "quarter": re.compile(r"[1-4]"),
    "date_id": re.compile(r"\d{8}"),
}
_COMPARISONS = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)


def _coerce_plan(
    schema_linking_plan: SchemaLinkingPlan | Mapping[str, Any] | None,
) -> SchemaLinkingPlan | None:
    if schema_linking_plan is None:
        return None
    try:
        return (
            schema_linking_plan
            if isinstance(schema_linking_plan, SchemaLinkingPlan)
            else SchemaLinkingPlan.model_validate(schema_linking_plan)
        )
    except (TypeError, ValueError):
        return None


def normalize_calendar_numeric_literals(
    sql: str,
    schema_linking_plan: SchemaLinkingPlan | Mapping[str, Any] | None,
) -> str:
    """Convert quoted numeric dim_date literals without changing query semantics."""
    plan = _coerce_plan(schema_linking_plan)
    if plan is None or plan.calendar_table != "dim_date":
        return sql
    try:
        statement = sqlglot.parse_one(sql, read="mysql")
    except (ParseError, TokenError):
        return sql

    aliases = {
        table.alias_or_name: table.name
        for table in statement.find_all(exp.Table)
    }
    changed = False

    def calendar_column_name(column: exp.Column) -> str | None:
        if column.name not in _NUMERIC_CALENDAR_PATTERNS:
            return None
        if column.table:
            table_name = aliases.get(column.table, column.table)
            return column.name if table_name == "dim_date" else None
        if "dim_date" not in aliases.values():
            return None
        matches = [
            item
            for item in plan.columns
            if item == f"dim_date.{column.name}"
        ]
        return column.name if len(matches) == 1 else None

    def replace_literal(column: exp.Expression, literal: exp.Expression) -> None:
        nonlocal changed
        if not isinstance(column, exp.Column) or not isinstance(literal, exp.Literal):
            return
        column_name = calendar_column_name(column)
        if column_name is None or not literal.is_string:
            return
        value = str(literal.this)
        if _NUMERIC_CALENDAR_PATTERNS[column_name].fullmatch(value) is None:
            return
        literal.replace(exp.Literal.number(value))
        changed = True

    for expression in tuple(statement.walk()):
        if isinstance(expression, exp.In):
            for literal in tuple(expression.expressions):
                replace_literal(expression.this, literal)
        elif isinstance(expression, _COMPARISONS):
            replace_literal(expression.this, expression.expression)
            replace_literal(expression.expression, expression.this)

    return statement.sql(dialect="mysql") if changed else sql


def flatten_redundant_metric_subquery(
    sql: str,
    schema_linking_plan: SchemaLinkingPlan | Mapping[str, Any] | None,
) -> str:
    """Flatten one safe single-table projection subquery used by a metric repair."""
    plan = _coerce_plan(schema_linking_plan)
    if plan is None or not plan.required_metric_columns:
        return sql
    try:
        statement = sqlglot.parse_one(sql, read="mysql")
    except (ParseError, TokenError):
        return sql
    if not isinstance(statement, exp.Select):
        return sql
    if any(
        statement.args.get(key)
        for key in ("joins", "where", "group", "having", "order", "limit", "distinct")
    ):
        return sql
    from_clause = statement.args.get("from_")
    if not isinstance(from_clause, exp.From) or not isinstance(from_clause.this, exp.Subquery):
        return sql
    subquery = from_clause.this
    subquery_alias = subquery.alias_or_name
    inner = subquery.this
    if not subquery_alias or not isinstance(inner, exp.Select):
        return sql
    if any(
        inner.args.get(key)
        for key in ("joins", "group", "having", "order", "limit", "distinct")
    ):
        return sql
    if next(inner.find_all(exp.AggFunc), None) is not None:
        return sql
    if next(inner.find_all(exp.Window), None) is not None:
        return sql
    inner_from = inner.args.get("from_")
    if not isinstance(inner_from, exp.From) or not isinstance(inner_from.this, exp.Table):
        return sql
    source_table = inner_from.this
    if source_table.name not in plan.tables:
        return sql

    source_aliases = {source_table.name, source_table.alias_or_name}
    projection_map: dict[str, exp.Column] = {}
    for projection in inner.expressions:
        source = projection.this if isinstance(projection, exp.Alias) else projection
        if not isinstance(source, exp.Column):
            return sql
        if source.table and source.table not in source_aliases:
            return sql
        output_name = projection.alias_or_name
        if not output_name or output_name in projection_map:
            return sql
        projection_map[output_name] = source

    outer_columns = [
        column
        for column in statement.find_all(exp.Column)
        if column.find_ancestor(exp.Select) is statement
    ]
    replacements: list[tuple[exp.Column, exp.Column]] = []
    used_columns: set[str] = set()
    for column in outer_columns:
        if column.table != subquery_alias or column.name not in projection_map:
            return sql
        source = projection_map[column.name]
        column_id = f"{source_table.name}.{source.name}"
        if column_id not in plan.columns:
            return sql
        used_columns.add(column_id)
        replacements.append(
            (
                column,
                exp.column(source.name, table=source_table.alias_or_name),
            )
        )

    inner_where = inner.args.get("where")
    if isinstance(inner_where, exp.Where):
        for column in inner_where.find_all(exp.Column):
            if column.table and column.table not in source_aliases:
                return sql
            column_id = f"{source_table.name}.{column.name}"
            if column_id not in plan.columns:
                return sql
            used_columns.add(column_id)
    if not set(plan.required_metric_columns).issubset(used_columns):
        return sql

    for original, replacement in replacements:
        original.replace(replacement)
    statement.set("from_", exp.From(this=source_table.copy()))
    if isinstance(inner_where, exp.Where):
        statement.set("where", inner_where.copy())
    return statement.sql(dialect="mysql")
