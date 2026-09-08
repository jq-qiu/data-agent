"""SQL-004: SchemaLinkingPlan Builder/Validator 单元测试。

测试不使用真实 MySQL/Qdrant/ES，只验证 Registry 驱动的维度补全、
DWS 优先和失败关闭行为。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.metadata.catalog import load_catalog
from app.nl2sql.schema_linking import (
    SchemaLinkingJoin,
    SchemaLinkingPlan,
    SchemaLinkingPlanBuilder,
    SchemaLinkingPlanError,
    validate_schema_linking_plan,
)

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(ROOT / "conf" / "meta_config.yaml")


def _column(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "type": "text",
        "role": "column",
        "examples": [],
        "description": name,
        "alias": [],
    }


def _table(
    name: str,
    columns: tuple[str, ...],
    *,
    role: str = "fact",
) -> dict[str, Any]:
    return {
        "name": name,
        "role": role,
        "grain": "row",
        "description": name,
        "time_column": None,
        "primary_key": [],
        "allowed_join_relations": [],
        "columns": [_column(column) for column in columns],
    }


def _metric(metric_id: str) -> dict[str, Any]:
    return {
        "id": metric_id,
        "name": metric_id,
        "description": metric_id,
        "formula": "",
        "base_grain": "",
        "time_column": "",
        "status_filters": {},
        "allowed_dimensions": [],
        "component_metrics": [],
        "relevant_columns": [],
        "alias": [],
    }


class StubPathProvider:
    def __init__(self, path: tuple[SchemaLinkingJoin, ...] = ()) -> None:
        self._path = path
        self.calls: list[tuple[str, str]] = []

    async def relationship_path(
        self,
        start_table: str,
        end_table: str,
    ) -> tuple[SchemaLinkingJoin, ...]:
        self.calls.append((start_table, end_table))
        return self._path


@pytest.mark.asyncio
async def test_region_question_completes_dim_region_join_path(
    catalog,
) -> None:
    path = (
        SchemaLinkingJoin(
            relation_id="customer_to_region",
            left_table="dim_customer",
            left_column="state",
            right_table="dim_region",
            right_column="state_code",
        ),
    )
    provider = StubPathProvider(path)
    builder = SchemaLinkingPlanBuilder(catalog, provider)
    plan = await builder.build(
        query="按客户所在巴西州统计有效订单GMV",
        table_infos=[
            _table(
                "fact_order_item",
                ("order_id", "product_id", "price"),
            ),
            _table(
                "fact_order",
                ("order_id", "customer_id", "status", "purchase_date"),
            ),
            _table(
                "dim_customer",
                ("customer_id", "state"),
                role="dimension",
            ),
        ],
        metric_infos=[_metric("gmv")],
        join_relations=[
            {
                "relation_id": relation.relation_id,
                "left_table": relation.left_table,
                "left_column": relation.left_column,
                "right_table": relation.right_table,
                "right_column": relation.right_column,
                "cardinality": relation.cardinality,
                "grain_warning": relation.grain_warning,
            }
            for relation in catalog.relationships
        ],
    )

    assert "dim_region" in plan.tables
    assert "dim_region.state_code" in plan.group_by_columns
    assert {"order_item_to_order", "order_to_customer", "customer_to_region"}.issubset(
        {join.relation_id for join in plan.join_relations}
    )
    assert provider.calls == [("dim_customer", "dim_region")]


@pytest.mark.asyncio
async def test_dws_category_dimension_does_not_join_dim_category_for_display(
    catalog,
) -> None:
    provider = StubPathProvider()
    builder = SchemaLinkingPlanBuilder(catalog, provider)
    plan = await builder.build(
        query="2018年5月商品项数最多的5个品类",
        table_infos=[
            _table(
                "dws_sales_category_daily",
                ("date_id", "region_id", "category_id", "item_count"),
                role="aggregate",
            )
        ],
        metric_infos=[_metric("item_count")],
        join_relations=[],
    )

    assert plan.group_by_columns == ("dws_sales_category_daily.category_id",)
    assert "dim_category" not in plan.tables
    assert plan.join_relations == ()
    assert provider.calls == []


def test_plan_validator_rejects_unknown_column(catalog) -> None:
    plan = SchemaLinkingPlan(
        tables=("fact_order",),
        columns=("fact_order.status", "fact_order.not_a_column"),
        join_relations=(),
    )
    with pytest.raises(SchemaLinkingPlanError, match="unknown_column"):
        validate_schema_linking_plan(plan, catalog)


def test_plan_model_requires_metric_columns_in_allowed_columns() -> None:
    with pytest.raises(ValueError, match="required_metric_columns"):
        SchemaLinkingPlan(
            tables=("dws_sales_region_daily",),
            columns=("dws_sales_region_daily.date_id",),
            required_metric_columns=("dws_sales_region_daily.order_count",),
            join_relations=(),
        )


@pytest.mark.asyncio
async def test_disconnected_tables_fail_closed(catalog) -> None:
    builder = SchemaLinkingPlanBuilder(catalog, StubPathProvider())
    with pytest.raises(SchemaLinkingPlanError, match="not_connected"):
        await builder.build(
            query="列出所有订单状态",
            table_infos=[
                _table("fact_review", ("review_id", "order_id")),
                _table("dim_region", ("state_code", "display_name"), role="dimension"),
            ],
            metric_infos=[],
            join_relations=[],
        )


@pytest.mark.asyncio
async def test_region_filter_without_group_cue_does_not_force_grouping(
    catalog,
) -> None:
    builder = SchemaLinkingPlanBuilder(catalog, StubPathProvider())
    plan = await builder.build(
        query="2018年5月SP州GMV是多少",
        table_infos=[
            _table(
                "dws_sales_region_daily",
                ("date_id", "region_id", "gmv", "order_count"),
                role="aggregate",
            )
        ],
        metric_infos=[_metric("gmv")],
        join_relations=[],
    )

    assert plan.group_by_columns == ()
    assert plan.metric_ids == ("gmv",)


@pytest.mark.asyncio
async def test_aggregate_dimension_groups_without_registered_metric(
    catalog,
) -> None:
    path = (
        SchemaLinkingJoin(
            relation_id="customer_to_region",
            left_table="dim_customer",
            left_column="state",
            right_table="dim_region",
            right_column="state_code",
        ),
    )
    provider = StubPathProvider(path)
    builder = SchemaLinkingPlanBuilder(catalog, provider)
    plan = await builder.build(
        query="按客户所在巴西州统计平均配送延迟天数",
        table_infos=[
            _table("fact_delivery", ("order_id", "delay_days")),
            _table("fact_order", ("order_id", "customer_id", "status")),
            _table("dim_customer", ("customer_id", "state"), role="dimension"),
        ],
        metric_infos=[],
        join_relations=[
            {
                "relation_id": relation.relation_id,
                "left_table": relation.left_table,
                "left_column": relation.left_column,
                "right_table": relation.right_table,
                "right_column": relation.right_column,
                "cardinality": relation.cardinality,
                "grain_warning": relation.grain_warning,
            }
            for relation in catalog.relationships
        ],
    )

    assert "dim_region.state_code" in plan.group_by_columns
    assert plan.metric_ids == ()


@pytest.mark.asyncio
async def test_dws_metric_columns_restore_registered_source_table(
    catalog,
) -> None:
    builder = SchemaLinkingPlanBuilder(catalog, StubPathProvider())
    plan = await builder.build(
        query="2018年5月整体订单数是多少",
        table_infos=[_table("fact_order", ("order_id", "customer_id", "status"))],
        metric_infos=[_metric("order_count")],
        join_relations=[],
    )

    assert "dws_sales_region_daily.order_count" in plan.required_metric_columns
    assert "dws_sales_region_daily.order_count" in plan.columns
    assert plan.tables == ("dws_sales_region_daily",)
    assert "fact_order" not in plan.tables


@pytest.mark.asyncio
async def test_comparison_question_adds_dim_date_calendar_table(catalog) -> None:
    builder = SchemaLinkingPlanBuilder(catalog, StubPathProvider())
    plan = await builder.build(
        query="对比2018年4月和5月的GMV",
        table_infos=[
            _table(
                "dws_sales_region_daily",
                ("date_id", "region_id", "gmv", "order_count"),
                role="aggregate",
            )
        ],
        metric_infos=[_metric("gmv")],
        join_relations=[],
    )

    assert plan.calendar_table == "dim_date"
    assert "dim_date" in plan.tables
    assert any(join.relation_id == "region_daily_to_date" for join in plan.join_relations)
