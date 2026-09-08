"""以 AST 和 Registry 规则校验 SQL 的只读性、Schema、JOIN、粒度与结果规模。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.metadata.catalog import MetadataCatalog
from app.nl2sql.policy import SQLPolicy
from app.nl2sql.schema_linking import SchemaLinkingFilter, SchemaLinkingPlan

_METRIC_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "order_count": frozenset({"dws_sales_region_daily.order_count"}),
    "item_count": frozenset({"dws_sales_category_daily.item_count"}),
    "visitors": frozenset({"dws_sales_region_daily.visitors"}),
    "category_order_count": frozenset(
        {"dws_sales_category_daily.category_order_count"}
    ),
    "promotion_coverage": frozenset(
        {
            "dws_sales_region_daily.promoted_sku_count",
            "dws_sales_region_daily.active_sku_count",
        }
    ),
    "inventory_fill_rate": frozenset(
        {
            "dws_sales_region_daily.available_sku_count",
            "dws_sales_region_daily.required_sku_count",
        }
    ),
}
_CALENDAR_LITERAL_PATTERNS = {
    "dim_date.month": re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$"),
    "dim_date.date": re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$"),
}


class SQLValidationError(ValueError):
    """Raised when SQL violates the frozen V1 query policy."""


@dataclass(frozen=True)
class ValidatedSQL:
    """通过全部策略检查后的不可变 SQL 及其安全、Schema 和粒度审计信息。"""

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
    """SQL 执行前的强制边界；只接受 Registry 可解释的单条只读查询。"""

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

    def validate(
        self,
        sql: str,
        metric_ids: tuple[str, ...] = (),
        *,
        schema_linking_plan: SchemaLinkingPlan | Mapping[str, Any] | None = None,
    ) -> ValidatedSQL:
        """解析并逐层校验候选 SQL，成功时返回规范化且带行数上限的语句。"""

        # 先检查原始文本再建 AST，可提前阻断注释绕过、文件访问和会话变量等语法技巧。
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
        subquery_outputs = {
            subquery.alias_or_name: set(subquery.this.named_selects)
            for subquery in statement.find_all(exp.Subquery)
            if subquery.alias_or_name
        }
        virtual_outputs = {**subquery_outputs, **cte_outputs}
        tables, alias_map = self._resolve_tables(statement, set(virtual_outputs))
        columns = self._validate_columns(statement, tables, alias_map, virtual_outputs)
        join_relations, grain_warnings = self._validate_joins(statement, alias_map, virtual_outputs)
        self._validate_window_functions(statement)
        self._validate_functions(statement)
        self._validate_calendar_literals(statement, tables, alias_map)
        self._validate_sensitive_projection(statement, tables, alias_map)
        self._validate_grain_rules(
            statement,
            tables,
            columns,
            metric_ids,
            alias_map,
        )
        if schema_linking_plan is not None:
            plan = (
                schema_linking_plan
                if isinstance(schema_linking_plan, SchemaLinkingPlan)
                else SchemaLinkingPlan.model_validate(schema_linking_plan)
            )
            self._validate_schema_linking_constraints(
                statement,
                tables,
                columns,
                join_relations,
                alias_map,
                plan,
            )

        # LIMIT 在 Validator 内统一收紧，不能依赖生成模型主动遵守返回规模约束。
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
        for subquery in statement.find_all(exp.Subquery):
            alias = subquery.alias_or_name
            if alias and alias in cte_names:
                aliases[alias] = alias
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
        """要求每个 JOIN 使用 Registry 白名单等值关系，并返回对应粒度警告。"""

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
            if isinstance(function, exp.TsOrDsToDate) and isinstance(
                function.parent, (exp.Year, exp.Month, exp.Day, exp.Quarter)
            ):
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

    def _validate_calendar_literals(
        self,
        statement: exp.Expression,
        tables: set[str],
        aliases: dict[str, str],
    ) -> None:
        for predicate in statement.find_all(exp.In):
            if not isinstance(predicate.this, exp.Column):
                continue
            column_id = self._source_column_id(predicate.this, tables, aliases)
            for value in predicate.expressions:
                self._validate_calendar_literal(column_id, value)

        for predicate in statement.find_all(exp.Between):
            if not isinstance(predicate.this, exp.Column):
                continue
            column_id = self._source_column_id(predicate.this, tables, aliases)
            self._validate_calendar_literal(column_id, predicate.args.get("low"))
            self._validate_calendar_literal(column_id, predicate.args.get("high"))

        comparison_types = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)
        for predicate in statement.find_all(*comparison_types):
            left = predicate.this
            right = predicate.expression
            if isinstance(left, exp.Column):
                self._validate_calendar_literal(
                    self._source_column_id(left, tables, aliases),
                    right,
                )
            if isinstance(right, exp.Column):
                self._validate_calendar_literal(
                    self._source_column_id(right, tables, aliases),
                    left,
                )

    def _source_column_id(
        self,
        column: exp.Column,
        tables: set[str],
        aliases: dict[str, str],
    ) -> str | None:
        if column.table:
            source_name = aliases.get(column.table)
            if source_name in tables:
                return f"{source_name}.{column.name}"
            return None
        candidates = [table for table in tables if column.name in self.table_columns[table]]
        if len(candidates) == 1:
            return f"{candidates[0]}.{column.name}"
        return None

    @staticmethod
    def _validate_calendar_literal(
        column_id: str | None,
        value: exp.Expression | None,
    ) -> None:
        if column_id not in {
            "dim_date.month",
            "dim_date.date",
            "dim_date.year",
            "dim_date.quarter",
            "dim_date.date_id",
        }:
            return
        if column_id == "dim_date.date" and isinstance(value, exp.Cast):
            value = value.this
        if not isinstance(value, exp.Literal):
            return
        if column_id in _CALENDAR_LITERAL_PATTERNS:
            pattern = _CALENDAR_LITERAL_PATTERNS[column_id]
            if not value.is_string or pattern.fullmatch(str(value.this)) is None:
                raise SQLValidationError(
                    f"{column_id} requires its canonical string literal format"
                )
            return
        if not value.is_int:
            raise SQLValidationError(f"{column_id} requires an integer literal")
        number = int(value.this)
        if column_id == "dim_date.year" and len(str(value.this)) != 4:
            raise SQLValidationError("dim_date.year requires a four-digit integer")
        if column_id == "dim_date.quarter" and number not in {1, 2, 3, 4}:
            raise SQLValidationError("dim_date.quarter literal is out of range")
        if column_id == "dim_date.date_id" and len(str(value.this)) != 8:
            raise SQLValidationError("dim_date.date_id requires YYYYMMDD integer format")

    def _validate_window_functions(self, statement: exp.Expression) -> None:
        for row_number in statement.find_all(exp.RowNumber):
            window = row_number.parent
            if not isinstance(window, exp.Window) or window.args.get("order") is None:
                raise SQLValidationError("ROW_NUMBER requires OVER with ORDER BY")
            partitions = window.args.get("partition_by") or ()
            if any(
                isinstance(item, exp.Literal) and item.is_int for item in partitions
            ):
                raise SQLValidationError(
                    "ROW_NUMBER PARTITION BY must be an expression, not a position"
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
        aliases: dict[str, str],
    ) -> None:
        """检查无法仅靠 SQL 语法发现的指标口径与一对多聚合风险。"""

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
        for metric_id in metric_ids:
            metric_required = _METRIC_REQUIRED_COLUMNS.get(metric_id)
            used = self._statement_source_columns(statement, tables, aliases)
            if metric_required is not None and not metric_required.issubset(used):
                raise SQLValidationError(
                    f"{metric_id} must use its registered Metric Registry source columns"
                )
        if "category_order_count" in metric_ids and not self._has_category_scope(statement):
            raise SQLValidationError(
                "category_order_count requires category grouping or a category filter"
            )

    def _validate_schema_linking_constraints(
        self,
        statement: exp.Expression,
        tables: set[str],
        columns: set[str],
        join_relations: list[str],
        aliases: dict[str, str],
        plan: SchemaLinkingPlan,
    ) -> None:
        if not tables.issubset(plan.tables):
            raise SQLValidationError("SQL uses a table outside SchemaLinkingPlan")
        if not columns.issubset(plan.columns):
            raise SQLValidationError("SQL uses a column outside SchemaLinkingPlan")
        if not set(join_relations).issubset(
            {relation.relation_id for relation in plan.join_relations}
        ):
            raise SQLValidationError("SQL uses a JOIN outside SchemaLinkingPlan")
        if not set(plan.required_metric_columns).issubset(columns):
            raise SQLValidationError("SQL omits required Metric Registry columns")
        if plan.calendar_table is not None and plan.calendar_table not in tables:
            raise SQLValidationError("SQL omits the planned calendar table")

        select_aliases = self._select_alias_source_columns(
            statement,
            tables,
            aliases,
        )
        expected_groups = {*plan.group_by_columns, *plan.display_columns}
        if expected_groups:
            actual_groups: set[str] = set()
            for group in statement.find_all(exp.Group):
                for column in group.find_all(exp.Column):
                    column_id = self._source_column_id(column, tables, aliases)
                    if column_id is None and not column.table:
                        column_id = select_aliases.get(column.name)
                    if column_id is not None:
                        actual_groups.add(column_id)
            if actual_groups != expected_groups:
                raise SQLValidationError("SQL GROUP BY differs from SchemaLinkingPlan")

        if plan.order_by and next(statement.find_all(exp.RowNumber), None) is None:
            actual_order: list[tuple[str, str]] = []
            for order in statement.find_all(exp.Order):
                for ordered in order.expressions:
                    expression = ordered.this
                    if not isinstance(expression, exp.Column):
                        continue
                    column_id = self._source_column_id(expression, tables, aliases)
                    if column_id is None and not expression.table:
                        column_id = select_aliases.get(expression.name)
                    if column_id is not None:
                        direction = "desc" if bool(ordered.args.get("desc")) else "asc"
                        actual_order.append((column_id, direction))
            expected_order = [
                (item.column, item.direction) for item in plan.order_by
            ]
            if actual_order != expected_order:
                raise SQLValidationError("SQL ORDER BY differs from SchemaLinkingPlan")

        for required_filter in plan.filters:
            if not self._has_planned_filter(
                statement,
                tables,
                aliases,
                required_filter,
            ):
                raise SQLValidationError(
                    f"SQL omits planned filter: {required_filter.column_id}"
                )

    def _has_planned_filter(
        self,
        statement: exp.Expression,
        tables: set[str],
        aliases: dict[str, str],
        required_filter: SchemaLinkingFilter,
    ) -> bool:
        for predicate in statement.find_all(exp.In):
            if not isinstance(predicate.this, exp.Column):
                continue
            column_id = self._source_column_id(predicate.this, tables, aliases)
            if column_id != required_filter.column_id:
                continue
            values = {
                str(item.this)
                for item in predicate.expressions
                if isinstance(item, exp.Literal) and item.is_string
            }
            excluded = isinstance(predicate.parent, exp.Not)
            if excluded == required_filter.exclude and set(required_filter.values) == values:
                return True
        return False

    def _select_alias_source_columns(
        self,
        statement: exp.Expression,
        tables: set[str],
        aliases: dict[str, str],
    ) -> dict[str, str]:
        sources: dict[str, str] = {}
        for select in statement.find_all(exp.Select):
            for projection in select.expressions:
                if not isinstance(projection, exp.Alias):
                    continue
                expression = projection.this
                if not isinstance(expression, exp.Column):
                    continue
                column_id = self._source_column_id(expression, tables, aliases)
                if column_id is not None:
                    sources[projection.alias] = column_id
        return sources

    def _statement_source_columns(
        self,
        statement: exp.Expression,
        tables: set[str],
        aliases: dict[str, str],
    ) -> set[str]:
        resolved: set[str] = set()
        for column in statement.find_all(exp.Column):
            name = column.name
            qualifier = column.table
            if qualifier:
                source_name = aliases.get(qualifier)
                if source_name in tables and name in self.table_columns[source_name]:
                    resolved.add(f"{source_name}.{name}")
                continue
            candidates = [
                table for table in tables if name in self.table_columns[table]
            ]
            if len(candidates) == 1:
                resolved.add(f"{candidates[0]}.{name}")
        return resolved

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
