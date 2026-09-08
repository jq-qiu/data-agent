"""SQL-004: NL2SQL SchemaLinkingPlan and deterministic plan builder.

模块职责
--------
开放式 NL2SQL 在召回/过滤之后、LLM 生成 SQL 之前，需要一个可审计的
结构化查询方案。本模块用 Metadata Catalog 和 Relationship Registry 决定：
用哪些指标、哪些表、哪些列、走哪条 JOIN 路径、按什么规范维度分组，
从而避免让模型在最后一步自行猜测 JOIN 与业务维度。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.metadata.catalog import MetadataCatalog
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository


class SchemaLinkingPlanError(ValueError):
    """Plan 构建或校验失败时抛出，原因使用稳定机器可读文本。"""


class SchemaLinkingJoin(BaseModel):
    """Plan 中一条已登记 JOIN 关系；左右端必须是 Catalog 中的真实键。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relation_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    left_table: str
    left_column: str
    right_table: str
    right_column: str


class SchemaLinkingOrder(BaseModel):
    """稳定排序声明；列必须是 qualified column id。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    direction: Literal["asc", "desc"] = "asc"


class SchemaLinkingFilter(BaseModel):
    """从 Metric Registry status_filters 投影出的值过滤，不接收自由文本。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    column_id: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    values: tuple[str, ...]
    exclude: bool = True


class SchemaLinkingTopN(BaseModel):
    """TopN 声明；分组为空表示全局 TopN，否则为受约束的分组 TopN。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(ge=1, le=100)
    partition_by: tuple[str, ...] = ()
    order_by: tuple[SchemaLinkingOrder, ...] = Field(min_length=1)


class SchemaLinkingPlan(BaseModel):
    """SQL 生成前冻结的查询方案；只包含 Registry 可回查的逻辑/物理对象。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_version: Literal["schema-linking-plan-v1"] = "schema-linking-plan-v1"
    metric_ids: tuple[str, ...] = ()
    tables: tuple[str, ...]
    columns: tuple[str, ...]
    required_metric_columns: tuple[str, ...] = ()
    calendar_table: str | None = None
    join_relations: tuple[SchemaLinkingJoin, ...]
    group_by_columns: tuple[str, ...] = ()
    display_columns: tuple[str, ...] = ()
    filters: tuple[SchemaLinkingFilter, ...] = ()
    order_by: tuple[SchemaLinkingOrder, ...] = ()
    topn: SchemaLinkingTopN | None = None
    grain_warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_and_qualified(self) -> SchemaLinkingPlan:
        for label, values in (
            ("tables", self.tables),
            ("columns", self.columns),
            ("group_by_columns", self.group_by_columns),
            ("display_columns", self.display_columns),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        for label, values in (
            ("columns", self.columns),
            ("required_metric_columns", self.required_metric_columns),
            ("group_by_columns", self.group_by_columns),
            ("display_columns", self.display_columns),
        ):
            for value in values:
                if not _QUALIFIED_COLUMN.fullmatch(value):
                    raise ValueError(f"{label} must be qualified table.column")
        if not set(self.group_by_columns).issubset(self.columns):
            raise ValueError("group_by_columns must be in columns")
        if not set(self.required_metric_columns).issubset(self.columns):
            raise ValueError("required_metric_columns must be in columns")
        if self.calendar_table is not None and self.calendar_table not in self.tables:
            raise ValueError("calendar_table must be in tables")
        if not set(self.display_columns).issubset(self.columns):
            raise ValueError("display_columns must be in columns")
        if not {item.column_id for item in self.filters}.issubset(self.columns):
            raise ValueError("filter columns must be in columns")
        for order in self.order_by:
            if order.column not in self.columns:
                raise ValueError("order_by columns must be in columns")
        return self


_QUALIFIED_COLUMN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_TABLE_COLUMN = re.compile(
    r"^(?P<table>[a-z][a-z0-9_]*)\.(?P<column>[a-z][a-z0-9_]*)$"
)

_REGION_TERMS = ("州", "地区", "region", "state")
_CATEGORY_TERMS = ("品类", "分类", "category")
_DISPLAY_TERMS = ("名称", "名字", "显示名", "英文", "葡萄牙语", "name")
_LIST_TERMS = ("列出", "有哪些", "各", "按", "排名", "排行", "分别")
_GROUP_CUES = (
    "按",
    "各",
    "每",
    "哪些",
    "分别",
    "贡献",
    "分布",
    "排名",
    "排行",
    "最高",
    "最低",
    "最多",
    "最少",
    "top",
    "bottom",
)
_AGGREGATE_TERMS = (
    "统计",
    "平均",
    "合计",
    "汇总",
    "数量",
    "总数",
    "计数",
    "分布",
    "记录",
    "最高",
    "最低",
    "最多",
    "最少",
    "avg",
    "sum",
    "count",
    "rank",
)
_DWS_ONLY_METRIC_COLUMNS: dict[str, tuple[str, ...]] = {
    "order_count": ("dws_sales_region_daily.order_count",),
    "item_count": ("dws_sales_category_daily.item_count",),
    "visitors": ("dws_sales_region_daily.visitors",),
    "category_order_count": ("dws_sales_category_daily.category_order_count",),
}
_CALENDAR_QUERY_TERMS = (
    "按月",
    "月份",
    "季度",
    "对比",
    "相比",
    "同比",
    "环比",
)
_CALENDAR_DATE_COLUMNS = ("date_id", "date", "month", "quarter", "year")
_CALENDAR_MONTH_GROUP_TERMS = ("按月", "月份")
_CALENDAR_QUARTER_GROUP_TERMS = ("按季度", "各季度", "季度对比")
_CALENDAR_DATE_GROUP_TERMS = ("每日", "按日", "按日期")
_COMPARISON_TERMS = ("对比", "相比", "同比", "环比")
_VALID_ORDER_TERMS = ("有效订单",)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _contains_any(value: str, terms: Sequence[str]) -> bool:
    normalized = _normalize(value)
    return any(term in normalized for term in terms)


def _qualified(table: str, column: str) -> str:
    return f"{table}.{column}"


def _table_of(qualified_column: str) -> str:
    match = _TABLE_COLUMN.fullmatch(qualified_column)
    if match is None:
        raise SchemaLinkingPlanError(f"invalid qualified column: {qualified_column}")
    return match.group("table")


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


class RelationshipPathProvider(Protocol):
    """返回 Registry 中 start 到 end 的最短合法 JOIN 路径。"""

    async def relationship_path(
        self,
        start_table: str,
        end_table: str,
    ) -> tuple[SchemaLinkingJoin, ...]: ...


class MetaRelationshipPathProvider:
    """Production provider：直接复用 MySQL Metadata 的 BFS 关系路径查询。"""

    def __init__(self, repository: MetaMySQLRepository) -> None:
        self._repository = repository

    async def relationship_path(
        self,
        start_table: str,
        end_table: str,
    ) -> tuple[SchemaLinkingJoin, ...]:
        rows = await self._repository.get_v1_relationship_path(start_table, end_table)
        return tuple(
            SchemaLinkingJoin(
                relation_id=str(row["relation_id"]),
                left_table=str(row["left_table"]),
                left_column=str(row["left_column"]),
                right_table=str(row["right_table"]),
                right_column=str(row["right_column"]),
            )
            for row in rows
        )


class SchemaLinkingPlanBuilder:
    """从过滤后的 NL2SQL 上下文确定性生成 SchemaLinkingPlan。

    本类不调用 LLM、不访问原始行、不把连接对象写入 State。
    当用户问题需要地区/品类维度而对应规范维度表尚未进入候选时，
    通过 Relationship Registry 反查路径并把中间表/键加入方案。
    """

    def __init__(
        self,
        catalog: MetadataCatalog,
        path_provider: RelationshipPathProvider,
    ) -> None:
        self._catalog = catalog
        self._path_provider = path_provider
        self._metric_map = {item.metric_id: item for item in catalog.metrics}
        self._column_roles = {
            f"{table.table_name}.{column.name}": column.role
            for table in catalog.tables
            for column in table.columns
        }
        self._column_terms = {
            f"{table.table_name}.{column.name}": tuple(
                dict.fromkeys((column.name, *column.aliases))
            )
            for table in catalog.tables
            for column in table.columns
        }
        self._status_value_terms = tuple(
            tuple(dict.fromkeys((canonical, *aliases)))
            for table in catalog.tables
            if table.table_name == "fact_order"
            for column in table.columns
            if column.name == "status"
            for canonical, aliases in column.value_aliases.items()
        )

    async def build(
        self,
        *,
        query: str,
        table_infos: Sequence[Mapping[str, Any]],
        metric_infos: Sequence[Mapping[str, Any]],
        join_relations: Sequence[Mapping[str, Any]],
        grain_warnings: Sequence[str] = (),
    ) -> SchemaLinkingPlan:
        selected_tables = [str(item["name"]) for item in table_infos]
        selected_table_map = {
            name: item for item in table_infos if (name := str(item["name"]))
        }
        metric_ids = tuple(
            dict.fromkeys(str(item["id"]) for item in metric_infos if item.get("id"))
        )
        missing_metrics = [
            metric_id
            for metric_id in metric_ids
            if metric_id not in self._metric_map
        ]
        if missing_metrics:
            raise SchemaLinkingPlanError(
                f"unknown_metric_in_schema_plan:{','.join(sorted(missing_metrics))}"
            )

        plan_tables: dict[str, Mapping[str, Any]] = {
            table: selected_table_map[table]
            for table in selected_tables
            if table in selected_table_map
        }

        required_metric_columns = self._dws_metric_columns(metric_ids)
        self._restore_dws_metric_tables(plan_tables, required_metric_columns)

        planned_joins = {
            str(row["relation_id"]): SchemaLinkingJoin(
                relation_id=str(row["relation_id"]),
                left_table=str(row["left_table"]),
                left_column=str(row["left_column"]),
                right_table=str(row["right_table"]),
                right_column=str(row["right_column"]),
            )
            for row in join_relations
            if all(
                str(row.get(key))
                for key in (
                    "relation_id",
                    "left_table",
                    "left_column",
                    "right_table",
                    "right_column",
                )
            )
        }

        requested = self._requested_dimensions(query, bool(metric_ids))
        dimension_paths: list[SchemaLinkingJoin] = []
        group_columns: list[str] = []
        display_columns: list[str] = []

        # 地区语义：优先使用已选择汇总表的 region_id；否则通过 Registry 反查 dim_region。
        if requested.get("region"):
            direct = self._direct_dimension_column(
                plan_tables,
                "region_id",
            )
            if direct is not None:
                group_columns.append(direct)
            else:
                await self._ensure_dimension_table(
                    plan_tables,
                    "dim_region",
                    dimension_paths,
                    start_table=self._semantic_start_table(
                        query,
                        plan_tables,
                        "dim_region",
                    ),
                )
                if "dim_region" not in plan_tables:
                    raise SchemaLinkingPlanError(
                        "requested_region_dimension_unresolved"
                    )
                group_columns.append("dim_region.state_code")
                if requested.get("display"):
                    display_columns.append("dim_region.display_name")

        # 品类语义：DWS 已含 category_id 时优先直接分组，不额外引入 JOIN。
        if requested.get("category"):
            direct = self._direct_dimension_column(
                plan_tables,
                "category_id",
            )
            if direct is not None:
                group_columns.append(direct)
            elif "dim_product" in plan_tables:
                group_columns.append("dim_product.category_id")
            else:
                await self._ensure_dimension_table(
                    plan_tables,
                    "dim_category",
                    dimension_paths,
                    start_table=self._semantic_start_table(
                        query,
                        plan_tables,
                        "dim_category",
                    ),
                )
                if "dim_category" not in plan_tables:
                    raise SchemaLinkingPlanError(
                        "requested_category_dimension_unresolved"
                    )
                group_columns.append("dim_category.category_id")
                if requested.get("display"):
                    display_columns.append("dim_category.category_name_en")

        # 显示名称只在用户明确要求时补入；不能用名称列替代规范分组列。
        if (
            requested.get("display")
            and requested.get("region")
            and "dim_region" in plan_tables
            and "dim_region.display_name" not in display_columns
            and "dim_region.display_name" in self._catalog.column_ids
        ):
            display_columns.append("dim_region.display_name")
        if (
            requested.get("display")
            and requested.get("category")
            and "dim_category" in plan_tables
            and "dim_category.category_name_en" not in display_columns
            and "dim_category.category_name_en" in self._catalog.column_ids
        ):
            display_columns.append("dim_category.category_name_en")

        if (
            "fact_order" in plan_tables
            and "fact_order.status" in self._catalog.column_ids
            and self._status_dimension_requested(query)
        ):
            group_columns.append("fact_order.status")

        mentioned_dimensions = self._mentioned_dimension_columns(
            query,
            plan_tables,
        )
        if not group_columns and _contains_any(query, _AGGREGATE_TERMS) and _contains_any(
            query,
            _GROUP_CUES,
        ):
            group_columns.extend(mentioned_dimensions)

        calendar_table = self._calendar_table(
            query,
            plan_tables,
            dimension_paths,
        )
        calendar_groups = self._calendar_group_columns(query, calendar_table)
        group_columns = [
            *calendar_groups,
            *(column for column in group_columns if column not in calendar_groups),
        ]

        table_names = tuple(sorted(plan_tables))
        filters = tuple(
            dict.fromkeys(
                (
                    *self._metric_filters(metric_ids, table_names),
                    *self._query_filters(query, table_names),
                )
            )
        )
        selected_columns = {
            _qualified(str(ti["name"]), str(column["name"]))
            for ti in table_infos
            for column in ti.get("columns", [])
        }
        metric_columns = {
            column
            for column in self._metric_columns(metric_ids)
            if _table_of(column) in table_names
        }
        columns = (
            set(selected_columns)
            | metric_columns
            | set(required_metric_columns)
            | set(self._calendar_columns(calendar_table))
        )
        for column in (*group_columns, *display_columns):
            columns.add(column)
        for query_filter in filters:
            columns.add(query_filter.column_id)
        for join in dimension_paths:
            columns.add(_qualified(join.left_table, join.left_column))
            columns.add(_qualified(join.right_table, join.right_column))

        columns = {
            column
            for column in columns
            if column in self._catalog.column_ids and _table_of(column) in table_names
        }

        join_list = (*planned_joins.values(), *dimension_paths)
        connected = self._connect_plan_tables(table_names, join_list)
        if connected is None:
            # 失败关闭：宁可让本次请求明确失败，也不让模型补出未登记 JOIN。
            raise SchemaLinkingPlanError(
                "schema_linking_tables_not_connected:"
                + ",".join(sorted(table_names))
                + ":edges="
                + ",".join(
                    sorted(
                        f"{join.left_table}->{join.right_table}"
                        for join in join_list
                        if join.left_table in table_names
                        and join.right_table in table_names
                    )
                )
            )

        order_by = self._infer_order(
            query,
            group_columns,
            display_columns,
            columns,
        )
        plan = SchemaLinkingPlan(
            metric_ids=metric_ids,
            tables=table_names,
            columns=_unique(sorted(columns)),
            required_metric_columns=_unique(required_metric_columns),
            calendar_table=calendar_table,
            join_relations=connected,
            group_by_columns=_unique(group_columns),
            display_columns=_unique(display_columns),
            filters=filters,
            order_by=order_by,
            grain_warnings=tuple(grain_warnings),
        )
        validate_schema_linking_plan(plan, self._catalog)
        return plan

    def _metric_columns(self, metric_ids: Sequence[str]) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                column
                for metric_id in metric_ids
                if (metric := self._metric_map.get(metric_id))
                for column in metric.relevant_columns
            )
        )

    @staticmethod
    def _direct_dimension_column(
        plan_tables: Mapping[str, Mapping[str, Any]],
        column_name: str,
    ) -> str | None:
        candidates: list[tuple[int, str]] = []
        role_order = ("aggregate", "dimension", "fact", "synthetic_evidence")
        for table_name, table in plan_tables.items():
            columns = table.get("columns", [])
            if any(str(column.get("name")) == column_name for column in columns):
                role = str(table.get("role", ""))
                rank = role_order.index(role) if role in role_order else len(role_order)
                candidates.append((rank, table_name))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]))
        return _qualified(candidates[0][1], column_name)

    def _dws_metric_columns(
        self,
        metric_ids: Sequence[str],
    ) -> tuple[str, ...]:
        columns: list[str] = []
        for metric_id in metric_ids:
            for column_id in _DWS_ONLY_METRIC_COLUMNS.get(metric_id, ()):
                if column_id in self._catalog.column_ids:
                    columns.append(column_id)
        return tuple(dict.fromkeys(columns))

    def _restore_dws_metric_tables(
        self,
        plan_tables: dict[str, Mapping[str, Any]],
        required_metric_columns: Sequence[str],
    ) -> None:
        required_tables = tuple(
            dict.fromkeys(_table_of(column) for column in required_metric_columns)
        )
        if not required_tables:
            return

        restored: dict[str, Mapping[str, Any]] = {}
        for table_name in required_tables:
            definition = self._catalog.table_map.get(table_name)
            if definition is None:
                raise SchemaLinkingPlanError(
                    f"metric_source_table_missing_from_catalog:{table_name}"
                )
            restored[table_name] = self.table_state_from_catalog(definition)
        plan_tables.clear()
        plan_tables.update(restored)

    def _calendar_table(
        self,
        query: str,
        plan_tables: dict[str, Mapping[str, Any]],
        calendar_paths: list[SchemaLinkingJoin],
    ) -> str | None:
        if not _contains_any(query, _CALENDAR_QUERY_TERMS):
            return None
        if "dim_date" in plan_tables:
            return "dim_date"
        owners = sorted(
            table_name
            for table_name, table in plan_tables.items()
            if any(str(column.get("name")) == "date_id" for column in table.get("columns", []))
        )
        for owner in owners:
            for relation in self._catalog.relationships:
                if relation.left_table != "dim_date" and relation.right_table != "dim_date":
                    continue
                if relation.left_table != owner and relation.right_table != owner:
                    continue
                join = SchemaLinkingJoin(
                    relation_id=relation.relation_id,
                    left_table=relation.left_table,
                    left_column=relation.left_column,
                    right_table=relation.right_table,
                    right_column=relation.right_column,
                )
                if join.relation_id not in {
                    item.relation_id for item in calendar_paths
                }:
                    calendar_paths.append(join)
                for table_name in (owner, "dim_date"):
                    if table_name in plan_tables:
                        continue
                    definition = self._catalog.table_map.get(table_name)
                    if definition is None:
                        raise SchemaLinkingPlanError(
                            f"calendar_table_missing_from_catalog:{table_name}"
                        )
                    plan_tables[table_name] = self.table_state_from_catalog(
                        definition
                    )
                return "dim_date"
        return None

    def _calendar_columns(
        self,
        calendar_table: str | None,
    ) -> tuple[str, ...]:
        if calendar_table is None:
            return ()
        return tuple(
            dict.fromkeys(
                _qualified(calendar_table, column_name)
                for column_name in _CALENDAR_DATE_COLUMNS
                if _qualified(calendar_table, column_name) in self._catalog.column_ids
            )
        )

    @staticmethod
    def _calendar_group_columns(
        query: str,
        calendar_table: str | None,
    ) -> tuple[str, ...]:
        if calendar_table is None:
            return ()
        if _contains_any(query, _CALENDAR_DATE_GROUP_TERMS):
            return (f"{calendar_table}.date",)
        if _contains_any(query, _CALENDAR_QUARTER_GROUP_TERMS):
            return (f"{calendar_table}.quarter",)
        month_mentions = re.findall(r"(?<!\d)(?:1[0-2]|[1-9])月", query)
        if _contains_any(query, _CALENDAR_MONTH_GROUP_TERMS) or (
            len(month_mentions) >= 2 and _contains_any(query, _COMPARISON_TERMS)
        ):
            return (f"{calendar_table}.month",)
        year_mentions = re.findall(r"(?<!\d)\d{4}年", query)
        if len(year_mentions) >= 2 and _contains_any(query, _COMPARISON_TERMS):
            return (f"{calendar_table}.year",)
        return ()

    def _status_dimension_requested(self, query: str) -> bool:
        if _contains_any(query, ("按订单状态", "各订单状态", "订单状态分布")):
            return True
        return sum(_contains_any(query, terms) for terms in self._status_value_terms) >= 2

    def _mentioned_dimension_columns(
        self,
        query: str,
        plan_tables: Mapping[str, Mapping[str, Any]],
    ) -> tuple[str, ...]:
        normalized = _normalize(query)
        matches: list[str] = []
        for column_id, terms in self._column_terms.items():
            if _table_of(column_id) not in plan_tables:
                continue
            if self._column_roles.get(column_id) != "dimension":
                continue
            if any(
                len(normalized_term := _normalize(term)) >= 2
                and normalized_term in normalized
                for term in terms
            ):
                matches.append(column_id)
        return tuple(matches)

    async def _ensure_dimension_table(
        self,
        plan_tables: dict[str, Mapping[str, Any]],
        dimension_table: str,
        dimension_paths: list[SchemaLinkingJoin],
        start_table: str | None = None,
    ) -> None:
        if dimension_table in plan_tables:
            return
        dimension_definition = self._catalog.table_map.get(dimension_table)
        if dimension_definition is None:
            raise SchemaLinkingPlanError(
                f"dimension_table_missing_from_catalog:{dimension_table}"
            )
        start = start_table or self._best_path_start(plan_tables)
        path = await self._path_provider.relationship_path(start, dimension_table)
        if not path:
            return
        for join in path:
            if join.relation_id not in {item.relation_id for item in dimension_paths}:
                dimension_paths.append(join)
            for table_name in (join.left_table, join.right_table):
                definition = self._catalog.table_map.get(table_name)
                if definition is None:
                    raise SchemaLinkingPlanError(
                        f"path_table_missing_from_catalog:{table_name}"
                    )
                if table_name not in plan_tables:
                    plan_tables[table_name] = self.table_state_from_catalog(
                        definition
                    )
        if dimension_table not in plan_tables:
            plan_tables[dimension_table] = self.table_state_from_catalog(
                dimension_definition
            )

    @staticmethod
    def _best_path_start(
        plan_tables: Mapping[str, Mapping[str, Any]],
    ) -> str:
        preferred = ("fact_order_item", "fact_order", "dim_customer", "dim_product")
        for table in preferred:
            if table in plan_tables:
                return table
        return next(iter(sorted(plan_tables)))

    @staticmethod
    def _semantic_start_table(
        query: str,
        plan_tables: Mapping[str, Mapping[str, Any]],
        dimension_table: str,
    ) -> str | None:
        if dimension_table == "dim_region":
            prefers_customer = _contains_any(
                query,
                ("客户", "买家", "customer", "州", "地区"),
            ) and not _contains_any(query, ("卖家", "商家", "seller"))
            if prefers_customer and "dim_customer" in plan_tables:
                return "dim_customer"
            if not prefers_customer and "dim_seller" in plan_tables:
                return "dim_seller"
            if "dim_customer" in plan_tables:
                return "dim_customer"
        if dimension_table == "dim_category" and "dim_product" in plan_tables:
            return "dim_product"
        return None

    def _connect_plan_tables(
        self,
        table_names: Sequence[str],
        extra_joins: Sequence[SchemaLinkingJoin],
    ) -> tuple[SchemaLinkingJoin, ...] | None:
        table_set = set(table_names)
        catalog_joins = [
            SchemaLinkingJoin(
                relation_id=item.relation_id,
                left_table=item.left_table,
                left_column=item.left_column,
                right_table=item.right_table,
                right_column=item.right_column,
            )
            for item in self._catalog.relationships
            if item.left_table in table_set and item.right_table in table_set
        ]
        all_joins = {
            join.relation_id: join
            for join in (*extra_joins, *catalog_joins)
            if join.left_table in table_set and join.right_table in table_set
        }
        neighbors: dict[str, list[SchemaLinkingJoin]] = {}
        for join in all_joins.values():
            neighbors.setdefault(join.left_table, []).append(join)
            neighbors.setdefault(join.right_table, []).append(join)

        root = next(iter(sorted(table_set)))
        queue = [root]
        visited = {root}
        selected: list[SchemaLinkingJoin] = []
        index = 0
        while index < len(queue):
            current = queue[index]
            index += 1
            for join in neighbors.get(current, []):
                neighbor = (
                    join.right_table
                    if join.left_table == current
                    else join.left_table
                )
                if neighbor not in table_set or neighbor in visited:
                    continue
                visited.add(neighbor)
                selected.append(join)
                queue.append(neighbor)
        if visited != table_set:
            return None
        return tuple(selected)

    def _infer_order(
        self,
        query: str,
        group_columns: Sequence[str],
        display_columns: Sequence[str],
        columns: Collection[str],
    ) -> tuple[SchemaLinkingOrder, ...]:
        calendar_groups = tuple(
            column for column in group_columns if column.startswith("dim_date.")
        )
        if calendar_groups:
            return tuple(
                SchemaLinkingOrder(column=column)
                for column in group_columns
            )
        if display_columns and _contains_any(query, _LIST_TERMS):
            return tuple(
                SchemaLinkingOrder(column=column) for column in display_columns
            )
        if group_columns and _contains_any(query, _LIST_TERMS):
            return tuple(
                SchemaLinkingOrder(column=column) for column in group_columns
            )
        if _contains_any(query, _LIST_TERMS):
            mentioned = self._mentioned_dimension_columns(
                query,
                {
                    _table_of(column): {}
                    for column in columns
                },
            )
            mentioned = tuple(column for column in mentioned if column in columns)
            if len(mentioned) == 1:
                return (SchemaLinkingOrder(column=mentioned[0]),)
        return ()

    def _metric_filters(
        self,
        metric_ids: Sequence[str],
        table_names: Sequence[str],
    ) -> tuple[SchemaLinkingFilter, ...]:
        filters: list[SchemaLinkingFilter] = []
        for metric_id in metric_ids:
            metric = self._metric_map.get(metric_id)
            if metric is None or not metric.status_filters:
                continue
            for key, values in metric.status_filters.items():
                column_id = key.partition(":")[2] if key.startswith("exclude:") else key
                if (
                    column_id in self._catalog.column_ids
                    and _table_of(column_id) in table_names
                ):
                    filters.append(
                        SchemaLinkingFilter(
                            column_id=column_id,
                            values=tuple(values),
                            exclude=key.startswith("exclude:"),
                        )
                    )
        return tuple(filters)

    @staticmethod
    def _query_filters(
        query: str,
        table_names: Sequence[str],
    ) -> tuple[SchemaLinkingFilter, ...]:
        if "fact_order" not in table_names or not _contains_any(query, _VALID_ORDER_TERMS):
            return ()
        return (
            SchemaLinkingFilter(
                column_id="fact_order.status",
                values=("canceled", "unavailable"),
                exclude=True,
            ),
        )

    @staticmethod
    @staticmethod
    def _requested_dimensions(
        query: str,
        has_metric: bool,
    ) -> dict[str, bool]:
        grouped = (
            has_metric or _contains_any(query, _AGGREGATE_TERMS)
        ) and _contains_any(query, _GROUP_CUES)
        return {
            "region": grouped and _contains_any(query, _REGION_TERMS),
            "category": grouped and _contains_any(query, _CATEGORY_TERMS),
            "display": _contains_any(query, _DISPLAY_TERMS),
        }

    @staticmethod
    def table_state_from_catalog(definition: Any) -> dict[str, Any]:
        return {
            "name": definition.table_name,
            "role": definition.role,
            "grain": definition.grain,
            "description": definition.description,
            "time_column": definition.time_column,
            "primary_key": list(definition.primary_key),
            "allowed_join_relations": list(definition.allowed_join_relations),
            "columns": [
                {
                    "name": column.name,
                    "type": "text",
                    "role": column.role,
                    "examples": [],
                    "description": column.description,
                    "alias": list(column.aliases),
                }
                for column in definition.columns
            ],
        }


def validate_schema_linking_plan(
    plan: SchemaLinkingPlan,
    catalog: MetadataCatalog,
) -> None:
    """校验 Plan 的所有对象都可回溯到 Catalog；失败时抛出 SchemaLinkingPlanError。"""

    issues: list[str] = []
    table_set = set(plan.tables)
    for table_name in plan.tables:
        if table_name not in catalog.table_map:
            issues.append(f"unknown_table:{table_name}")
    for column in (*plan.columns, *plan.group_by_columns, *plan.display_columns):
        if column not in catalog.column_ids:
            issues.append(f"unknown_column:{column}")
        table_name = _table_of(column)
        if table_name not in table_set:
            issues.append(f"column_without_table:{column}")
    for column in plan.required_metric_columns:
        if column not in catalog.column_ids:
            issues.append(f"unknown_metric_column:{column}")
    known_relations = {item.relation_id: item for item in catalog.relationships}
    for join in plan.join_relations:
        relation = known_relations.get(join.relation_id)
        if relation is None:
            issues.append(f"unknown_relation:{join.relation_id}")
        else:
            if (
                relation.left_table != join.left_table
                or relation.left_column != join.left_column
                or relation.right_table != join.right_table
                or relation.right_column != join.right_column
            ):
                issues.append(f"relation_mismatch:{join.relation_id}")
            if relation.left_table not in table_set or relation.right_table not in table_set:
                issues.append(f"relation_outside_plan:{join.relation_id}")
    metric_map = {item.metric_id for item in catalog.metrics}
    for metric_id in plan.metric_ids:
        if metric_id not in metric_map:
            issues.append(f"unknown_metric:{metric_id}")
    if issues:
        raise SchemaLinkingPlanError(
            "schema_linking_plan_invalid:" + ",".join(sorted(set(issues)))
        )
