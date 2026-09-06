from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.metadata.catalog import MetadataCatalog
from app.nl2sql.policy import SQLPolicy


class SQLValidationError(ValueError):
    """Raised when SQL violates the frozen V1 query policy."""


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str
    tables: tuple[str, ...]
    columns: tuple[str, ...]
    join_relations: tuple[str, ...]
    grain_warnings: tuple[str, ...]
    policy_version: str
    max_rows: int
    timeout_seconds: float

    def as_trace(self) -> dict[str, Any]:
        return {
            "tables": list(self.tables),
            "columns": list(self.columns),
            "join_relations": list(self.join_relations),
            "grain_warnings": list(self.grain_warnings),
            "policy_version": self.policy_version,
            "max_rows": self.max_rows,
            "timeout_seconds": self.timeout_seconds,
        }


class SQLValidator:
    def __init__(self, catalog: MetadataCatalog, policy: SQLPolicy):
        self.catalog = catalog
        self.policy = policy
        self.table_columns = {
            table.table_name: {column.name for column in table.columns} for table in catalog.tables
        }
        self.sensitive_columns = {
            f"{table.table_name}.{column.name}"
            for table in catalog.tables
            for column in table.columns
            if column.is_sensitive
        }
        self.relationships = {
            frozenset(
                (
                    f"{item.left_table}.{item.left_column}",
                    f"{item.right_table}.{item.right_column}",
                )
            ): item
            for item in catalog.relationships
            if item.allowed
        }

    def validate(self, sql: str, metric_ids: tuple[str, ...] = ()) -> ValidatedSQL:
        self._validate_raw_text(sql)
        try:
            statements = sqlglot.parse(sql, read="mysql")
        except ParseError as error:
            raise SQLValidationError(f"SQL parse error: {error}") from error
        if len(statements) != 1:
            raise SQLValidationError("exactly one SQL statement is required")
        statement = statements[0]
        if not isinstance(statement, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
            raise SQLValidationError("only SELECT or read-only CTE queries are allowed")
        self._reject_mutating_nodes(statement)
        self._validate_stars(statement)

        cte_outputs = {
            cte.alias: set(cte.this.named_selects)
            for cte in statement.find_all(exp.CTE)
            if cte.alias
        }
        tables, alias_map = self._resolve_tables(statement, set(cte_outputs))
        columns = self._validate_columns(statement, tables, alias_map, cte_outputs)
        join_relations, grain_warnings = self._validate_joins(statement, alias_map, cte_outputs)
        self._validate_window_functions(statement)
        self._validate_functions(statement)
        self._validate_sensitive_projection(statement, tables, alias_map)
        self._validate_grain_rules(statement, tables, columns, metric_ids)

        statement = self._enforce_limit(statement)
        normalized_sql = statement.sql(dialect="mysql", pretty=False)
        return ValidatedSQL(
            sql=normalized_sql,
            tables=tuple(sorted(tables)),
            columns=tuple(sorted(columns)),
            join_relations=tuple(join_relations),
            grain_warnings=tuple(dict.fromkeys(grain_warnings)),
            policy_version=self.policy.version,
            max_rows=self.policy.max_rows,
            timeout_seconds=self.policy.timeout_seconds,
        )

    def _validate_raw_text(self, sql: str) -> None:
        if not sql.strip():
            raise SQLValidationError("SQL must not be empty")
        if re.search(r"(--|#|/\*)", sql):
            raise SQLValidationError("SQL comments are forbidden")
        if re.search(r"(?i)\b(into\s+outfile|into\s+dumpfile|load\s+data)\b", sql):
            raise SQLValidationError("file access SQL is forbidden")
        if "@" in sql:
            raise SQLValidationError("session and system variables are forbidden")

    def _reject_mutating_nodes(self, statement: exp.Expression) -> None:
        forbidden_names = (
            "Alter",
            "Command",
            "Commit",
            "Copy",
            "Create",
            "Delete",
            "Drop",
            "Grant",
            "Insert",
            "Merge",
            "Rollback",
            "Set",
            "Transaction",
            "TruncateTable",
            "Update",
            "Use",
        )
        forbidden_types = tuple(
            node_type
            for name in forbidden_names
            if (node_type := getattr(exp, name, None)) is not None
        )
        if forbidden_types and any(statement.find_all(*forbidden_types)):
            raise SQLValidationError("mutating, administrative, or transaction SQL is forbidden")
        if next(statement.find_all(exp.Into), None) is not None:
            raise SQLValidationError("SELECT INTO is forbidden")

    def _validate_stars(self, statement: exp.Expression) -> None:
        for star in statement.find_all(exp.Star):
            if isinstance(star.parent, exp.Count):
                continue
            raise SQLValidationError("SELECT * is forbidden; columns must be explicit")

    def _resolve_tables(
        self,
        statement: exp.Expression,
        cte_names: set[str],
    ) -> tuple[set[str], dict[str, str]]:
        tables: set[str] = set()
        aliases: dict[str, str] = {}
        for table in statement.find_all(exp.Table):
            name = table.name
            if name in cte_names:
                aliases[table.alias_or_name] = name
                continue
            database = table.db
            if database and database.casefold() != self.policy.allowed_database.casefold():
                raise SQLValidationError(f"database is not allowed: {database}")
            if database and database.casefold() in self.policy.forbidden_schemas:
                raise SQLValidationError(f"system schema is forbidden: {database}")
            if name not in self.table_columns:
                raise SQLValidationError(f"table is not registered: {name}")
            tables.add(name)
            aliases[table.alias_or_name] = name
            aliases[name] = name
        if not tables:
            raise SQLValidationError("query must read at least one registered table")
        return tables, aliases

    def _validate_columns(
        self,
        statement: exp.Expression,
        tables: set[str],
        aliases: dict[str, str],
        cte_outputs: dict[str, set[str]],
    ) -> set[str]:
        select_aliases = {
            expression.alias
            for select in statement.find_all(exp.Select)
            for expression in select.expressions
            if expression.alias
        }
        resolved: set[str] = set()
        for column in statement.find_all(exp.Column):
            qualifier = column.table
            name = column.name
            if qualifier:
                source_name = aliases.get(qualifier)
                if source_name is None:
                    raise SQLValidationError(f"unknown table alias: {qualifier}")
                if source_name in cte_outputs:
                    if name not in cte_outputs[source_name]:
                        raise SQLValidationError(
                            f"column is not exposed by CTE {source_name}: {name}"
                        )
                    continue
                if name not in self.table_columns[source_name]:
                    raise SQLValidationError(f"column is not registered: {source_name}.{name}")
                resolved.add(f"{source_name}.{name}")
                continue
            if name in select_aliases or any(name in outputs for outputs in cte_outputs.values()):
                continue
            candidate_tables = [table for table in tables if name in self.table_columns[table]]
            if not candidate_tables:
                raise SQLValidationError(f"column is not registered: {name}")
            if len(candidate_tables) > 1:
                raise SQLValidationError(f"ambiguous unqualified column: {name}")
            resolved.add(f"{candidate_tables[0]}.{name}")
        return resolved

    def _validate_joins(
        self,
        statement: exp.Expression,
        aliases: dict[str, str],
        cte_outputs: dict[str, set[str]],
    ) -> tuple[list[str], list[str]]:
        relation_ids: list[str] = []
        warnings: list[str] = []
        for join in statement.find_all(exp.Join):
            if join.args.get("kind") == "CROSS" or join.args.get("on") is None:
                raise SQLValidationError("cross joins and joins without ON are forbidden")
            matched = False
            for equality in join.args["on"].find_all(exp.EQ):
                left = equality.left
                right = equality.right
                if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                    continue
                left_id = self._qualified_column_id(left, aliases, cte_outputs)
                right_id = self._qualified_column_id(right, aliases, cte_outputs)
                if left_id is None or right_id is None:
                    continue
                relation = self.relationships.get(frozenset((left_id, right_id)))
                if relation is None:
                    raise SQLValidationError(f"JOIN is not registered: {left_id} = {right_id}")
                matched = True
                relation_ids.append(relation.relation_id)
                if relation.grain_warning:
                    warnings.append(relation.grain_warning)
            if not matched:
                raise SQLValidationError("JOIN must use a registered equality relation")
        return list(dict.fromkeys(relation_ids)), warnings

    def _qualified_column_id(
        self,
        column: exp.Column,
        aliases: dict[str, str],
        cte_outputs: dict[str, set[str]],
    ) -> str | None:
        if not column.table:
            return None
        table = aliases.get(column.table)
        if table is None or table in cte_outputs:
            return None
        return f"{table}.{column.name}"

    def _validate_functions(self, statement: exp.Expression) -> None:
        for function in statement.find_all(exp.Func):
            if isinstance(function, exp.Connector):
                continue
            name = (
                function.name.casefold()
                if isinstance(function, exp.Anonymous)
                else function.sql_name().casefold()
            )
            if name in self.policy.forbidden_functions:
                raise SQLValidationError(f"function is forbidden: {name}")
            if name not in self.policy.allowed_functions:
                raise SQLValidationError(f"function is not allowlisted: {name}")

    def _validate_window_functions(self, statement: exp.Expression) -> None:
        for row_number in statement.find_all(exp.RowNumber):
            window = row_number.parent
            if (
                not isinstance(window, exp.Window)
                or not window.args.get("partition_by")
                or window.args.get("order") is None
            ):
                raise SQLValidationError(
                    "ROW_NUMBER requires OVER with PARTITION BY and ORDER BY"
                )

    def _validate_sensitive_projection(
        self,
        statement: exp.Expression,
        tables: set[str],
        aliases: dict[str, str],
    ) -> None:
        for select in statement.find_all(exp.Select):
            for projection in select.expressions:
                expression = projection.this if isinstance(projection, exp.Alias) else projection
                if not isinstance(expression, exp.Column):
                    continue
                column_id = self._qualified_column_id(expression, aliases, {})
                if column_id is None and not expression.table:
                    candidates = [
                        table for table in tables if expression.name in self.table_columns[table]
                    ]
                    if len(candidates) == 1:
                        column_id = f"{candidates[0]}.{expression.name}"
                if column_id in self.sensitive_columns:
                    raise SQLValidationError(f"sensitive column cannot be projected: {column_id}")

    def _validate_grain_rules(
        self,
        statement: exp.Expression,
        tables: set[str],
        columns: set[str],
        metric_ids: tuple[str, ...],
    ) -> None:
        if {"fact_order_item", "fact_payment"}.issubset(tables):
            risky = {"fact_order_item.price", "fact_payment.payment_value"} & columns
            if risky and next(statement.find_all(exp.AggFunc), None) is not None:
                raise SQLValidationError(
                    "order items and payments must be aggregated separately before joining"
                )
        if (
            "gmv" in metric_ids
            and "dws_sales_region_daily.gmv" not in columns
            and "dws_sales_category_daily.gmv" not in columns
        ):
            required = {
                "fact_order_item.price",
                "fact_order_item.order_id",
                "fact_order.order_id",
                "fact_order.status",
            }
            if not required.issubset(columns) or not self._has_gmv_status_filter(statement):
                raise SQLValidationError(
                    "DWD GMV must sum order-item price and exclude canceled/unavailable orders"
                )
            if {"fact_order_item.freight_value", "fact_payment.payment_value"} & columns:
                raise SQLValidationError("freight or payment value cannot replace or inflate GMV")
        if "aov" in metric_ids:
            required = {
                "dws_sales_region_daily.gmv",
                "dws_sales_region_daily.order_count",
            }
            if not required.issubset(columns):
                raise SQLValidationError(
                    "AOV must be recomputed from region-DWS GMV and order count"
                )
        if "category_order_count" in metric_ids and not self._has_category_scope(statement):
            raise SQLValidationError(
                "category_order_count requires category grouping or a category filter"
            )

    def _has_gmv_status_filter(self, statement: exp.Expression) -> bool:
        for negation in statement.find_all(exp.Not):
            predicate = negation.this
            if not isinstance(predicate, exp.In) or not isinstance(predicate.this, exp.Column):
                continue
            if predicate.this.name != "status":
                continue
            values = {
                str(item.this).casefold()
                for item in predicate.expressions
                if isinstance(item, exp.Literal) and item.is_string
            }
            if {"canceled", "unavailable"}.issubset(values):
                return True
        return False

    def _has_category_scope(self, statement: exp.Expression) -> bool:
        for group in statement.find_all(exp.Group):
            if any(
                isinstance(item, exp.Column) and item.name == "category_id"
                for item in group.expressions
            ):
                return True
        for predicate_type in (exp.EQ, exp.In):
            for predicate in statement.find_all(predicate_type):
                if any(column.name == "category_id" for column in predicate.find_all(exp.Column)):
                    return True
        return False

    def _enforce_limit(self, statement: exp.Expression) -> exp.Expression:
        current_limit = statement.args.get("limit")
        if current_limit is None:
            return statement.limit(self.policy.max_rows, copy=False)
        expression = current_limit.expression
        if not isinstance(expression, exp.Literal) or not expression.is_int:
            raise SQLValidationError("LIMIT must be a fixed integer")
        if int(expression.this) > self.policy.max_rows:
            current_limit.set("expression", exp.Literal.number(self.policy.max_rows))
        return statement
