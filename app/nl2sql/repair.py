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


def normalize_calendar_numeric_literals(
    sql: str,
    schema_linking_plan: SchemaLinkingPlan | Mapping[str, Any] | None,
) -> str:
    """Convert quoted numeric dim_date literals without changing query semantics."""
    if schema_linking_plan is None:
        return sql
    try:
        plan = (
            schema_linking_plan
            if isinstance(schema_linking_plan, SchemaLinkingPlan)
            else SchemaLinkingPlan.model_validate(schema_linking_plan)
        )
    except (TypeError, ValueError):
        return sql
    if plan.calendar_table != "dim_date":
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
