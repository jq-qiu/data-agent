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
_DATE_ID_ISO_PATTERN = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])")


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
    if plan is None:
        return sql
    if plan.calendar_table != "dim_date" and not any(
        column.endswith(".date_id") for column in plan.columns
    ):
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
            if table_name == "dim_date":
                return column.name
            if column.name == "date_id" and f"{table_name}.date_id" in plan.columns:
                return column.name
            return None
        candidates = [
            table
            for table in aliases.values()
            if f"{table}.{column.name}" in plan.columns
            and (column.name == "date_id" or table == "dim_date")
        ]
        return column.name if len(candidates) == 1 else None

    def replace_literal(column: exp.Expression, literal: exp.Expression) -> None:
        nonlocal changed
        if not isinstance(column, exp.Column) or not isinstance(literal, exp.Literal):
            return
        column_name = calendar_column_name(column)
        if column_name is None or not literal.is_string:
            return
        value = str(literal.this)
        numeric_value = value
        if column_name == "date_id" and _DATE_ID_ISO_PATTERN.fullmatch(value):
            numeric_value = value.replace("-", "")
        if _NUMERIC_CALENDAR_PATTERNS[column_name].fullmatch(numeric_value) is None:
            return
        literal.replace(exp.Literal.number(numeric_value))
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
        if column.table and column.table != subquery_alias:
            return sql
        if column.table == subquery_alias or column.name in projection_map:
            output_name = column.name
        else:
            return sql
        source = projection_map[output_name]
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


def canonicalize_group_join_keys(
    sql: str,
    schema_linking_plan: SchemaLinkingPlan | Mapping[str, Any] | None,
) -> str:
    """Rewrite GROUP BY columns that are equality-joined to the planned group column."""
    plan = _coerce_plan(schema_linking_plan)
    if plan is None:
        return sql
    target_columns = {*plan.group_by_columns, *plan.display_columns}
    if not target_columns:
        return sql
    if not plan.join_relations:
        return sql
    try:
        statement = sqlglot.parse_one(sql, read="mysql")
    except (ParseError, TokenError):
        return sql
    if not isinstance(statement, exp.Select):
        return sql

    table_aliases: dict[str, str] = {}
    alias_to_table: dict[str, str] = {}
    table_names: set[str] = set()
    for table in statement.find_all(exp.Table):
        table_names.add(table.name)
        table_aliases[table.name] = table.alias_or_name
        alias_to_table[table.alias_or_name] = table.name

    targets_by_table: dict[str, set[str]] = {}
    for column_id in target_columns:
        table_name, _, column_name = column_id.partition(".")
        targets_by_table.setdefault(table_name, set()).add(column_name)

    changed = False

    def physical_column_id(column: exp.Column) -> str | None:
        if not column.table:
            return None
        table_name = alias_to_table.get(column.table, column.table)
        if table_name not in table_names:
            return None
        return f"{table_name}.{column.name}"

    for group in statement.find_all(exp.Group):
        for grouped in tuple(group.expressions):
            if not isinstance(grouped, exp.Column):
                continue
            current_id = physical_column_id(grouped)
            if current_id is None or current_id in target_columns:
                continue
            replacements: list[str] = []
            for join in plan.join_relations:
                left_id = f"{join.left_table}.{join.left_column}"
                right_id = f"{join.right_table}.{join.right_column}"
                if current_id == left_id and right_id in target_columns:
                    replacements.append(right_id)
                elif current_id == right_id and left_id in target_columns:
                    replacements.append(left_id)
            if len(replacements) != 1:
                continue
            target_id = replacements[0]
            target_table, _, target_column = target_id.partition(".")
            if target_table not in table_names or target_column not in targets_by_table.get(
                target_table,
                set(),
            ):
                continue
            grouped.replace(
                exp.column(
                    target_column,
                    table=table_aliases.get(target_table, target_table),
                )
            )
            changed = True

    return statement.sql(dialect="mysql") if changed else sql


def build_structured_repair_constraints(
    error: str,
    schema_linking_plan: SchemaLinkingPlan | Mapping[str, Any] | None,
) -> str:
    """Render the frozen plan as concise, error-directed repair constraints."""
    plan = _coerce_plan(schema_linking_plan)
    if plan is None:
        return "SchemaLinkingPlan unavailable; do not infer missing schema constraints."

    groups = (*plan.group_by_columns, *plan.display_columns)
    joins = tuple(
        f"{item.left_table}.{item.left_column} = "
        f"{item.right_table}.{item.right_column} ({item.relation_id})"
        for item in plan.join_relations
    )
    orders = tuple(f"{item.column} {item.direction.upper()}" for item in plan.order_by)
    filters = tuple(
        f"{item.column_id} {'NOT IN' if item.exclude else 'IN'} "
        f"({', '.join(repr(value) for value in item.values)})"
        for item in plan.filters
    )

    def render(values: tuple[str, ...]) -> str:
        return ", ".join(values) if values else "none"

    lines = [
        f"Validator error: {error}",
        f"Allowed tables only: {render(plan.tables)}",
        f"Required metric source columns: {render(plan.required_metric_columns)}",
        f"Required calendar table: {plan.calendar_table or 'none'}",
        f"Allowed JOIN equalities only: {render(joins)}",
        f"Required GROUP BY exactly: {render(groups)}",
        f"Required ORDER BY exactly: {render(orders)}",
        f"Required filters: {render(filters)}",
    ]
    if plan.source_table is not None:
        lines.append(f"Exact source table only: {plan.source_table}")
    if plan.result_projections:
        projections = ", ".join(
            f"{item.kind}({item.column})" for item in plan.result_projections
        )
        lines.append(f"Exact result projections in order: {projections}")
    if "GROUP BY differs from SchemaLinkingPlan" in error:
        lines.append(
            "Return one row per required group; do not pivot group values into "
            "separate conditional aggregate columns."
        )
    return "\n".join(lines)
