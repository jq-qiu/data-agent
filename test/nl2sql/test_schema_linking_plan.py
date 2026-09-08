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


def _relationships(catalog) -> list[dict[str, str]]:
    return [
        {
            "relation_id": relation.relation_id,
            "left_table": relation.left_table,
            "left_column": relation.left_column,
            "right_table": relation.right_table,
            "right_column": relation.right_column,
        }
        for relation in catalog.relationships
    ]


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "table_name", "column_name"),
    [
        ("Olist订单有哪些订单状态", "fact_order", "status"),
        ("支付记录中有哪些付款方式", "fact_payment", "payment_type"),
    ],
)
async def test_canonical_value_lists_receive_stable_dimension_order(
    catalog,
    query: str,
    table_name: str,
    column_name: str,
) -> None:
    plan = await SchemaLinkingPlanBuilder(catalog, StubPathProvider()).build(
        query=query,
        table_infos=[_table(table_name, (column_name,))],
        metric_infos=[],
        join_relations=[],
    )

    assert tuple(item.column for item in plan.order_by) == (
        f"{table_name}.{column_name}",
    )


@pytest.mark.asyncio
async def test_valid_order_payment_group_adds_filter_group_and_order(catalog) -> None:
    plan = await SchemaLinkingPlanBuilder(catalog, StubPathProvider()).build(
        query="按付款方式统计有效订单的支付明细记录数",
        table_infos=[
            _table("fact_payment", ("payment_type", "order_id")),
            _table("fact_order", ("order_id",)),
        ],
        metric_infos=[],
        join_relations=_relationships(catalog),
    )

    assert plan.group_by_columns == ("fact_payment.payment_type",)
    assert tuple(item.column for item in plan.order_by) == (
        "fact_payment.payment_type",
    )
    assert len(plan.filters) == 1
    assert plan.filters[0].column_id == "fact_order.status"
    assert plan.filters[0].values == ("canceled", "unavailable")
    assert "fact_order.status" in plan.columns


@pytest.mark.asyncio
async def test_month_comparison_uses_canonical_calendar_group_and_order(catalog) -> None:
    plan = await SchemaLinkingPlanBuilder(catalog, StubPathProvider()).build(
        query="对比2018年4月和5月的整体订单数",
        table_infos=[_table("fact_order", ("order_id", "date_id"))],
        metric_infos=[_metric("order_count")],
        join_relations=_relationships(catalog),
    )

    assert plan.group_by_columns == ("dim_date.month",)
    assert tuple(item.column for item in plan.order_by) == ("dim_date.month",)
    assert plan.calendar_table == "dim_date"


@pytest.mark.asyncio
async def test_status_comparison_keeps_fact_grain_and_groups_month_status(catalog) -> None:
    plan = await SchemaLinkingPlanBuilder(catalog, StubPathProvider()).build(
        query="对比2018年4月和5月已送达与已取消订单的数量",
        table_infos=[
            _table("fact_order", ("order_id", "status", "date_id")),
            _table("dim_date", ("date_id", "month"), role="dimension"),
        ],
        metric_infos=[],
        join_relations=_relationships(catalog),
    )

    assert plan.tables == ("dim_date", "fact_order")
    assert plan.metric_ids == ()
    assert plan.group_by_columns == ("dim_date.month", "fact_order.status")
    assert tuple(item.column for item in plan.order_by) == plan.group_by_columns


@pytest.mark.asyncio
async def test_single_status_filter_does_not_force_status_group(catalog) -> None:
    plan = await SchemaLinkingPlanBuilder(catalog, StubPathProvider()).build(
        query="已取消订单的数量",
        table_infos=[_table("fact_order", ("order_id", "status"))],
        metric_infos=[],
        join_relations=[],
    )

    assert plan.group_by_columns == ()


@pytest.mark.asyncio
async def test_display_name_grouping_orders_by_requested_display(catalog) -> None:
    plan = await SchemaLinkingPlanBuilder(catalog, StubPathProvider()).build(
        query="按商品英文品类统计有效订单GMV",
        table_infos=[
            _table("fact_order_item", ("order_id", "product_id", "price")),
            _table("fact_order", ("order_id", "status")),
            _table("dim_product", ("product_id", "category_id"), role="dimension"),
            _table(
                "dim_category",
                ("category_id", "category_name_en"),
                role="dimension",
            ),
        ],
        metric_infos=[_metric("gmv")],
        join_relations=_relationships(catalog),
    )

    assert plan.group_by_columns == ("dim_category.category_id",)
    assert plan.display_columns == ("dim_category.category_name_en",)
    assert tuple(item.column for item in plan.order_by) == plan.display_columns
    assert len(plan.filters) == 1



@pytest.mark.asyncio
async def test_overall_order_count_plan_does_not_force_grain_columns(catalog) -> None:
    builder = SchemaLinkingPlanBuilder(catalog, StubPathProvider())
    plan = await builder.build(
        query="2018年5月整体订单数是多少",
        table_infos=[_table("fact_order", ("order_id", "customer_id", "status"))],
        metric_infos=[_metric("order_count")],
        join_relations=[],
    )

    assert set(plan.required_metric_columns) == {
        "dws_sales_region_daily.order_count"
    }
    assert "dws_sales_region_daily.date_id" in plan.columns
    assert "dws_sales_region_daily.region_id" in plan.columns


@pytest.mark.asyncio
async def test_region_grouping_keeps_region_id_outside_required_metric_columns(
    catalog,
) -> None:
    builder = SchemaLinkingPlanBuilder(catalog, StubPathProvider())
    plan = await builder.build(
        query="按巴西州统计2018年5月整体订单数",
        table_infos=[
            _table(
                "dws_sales_region_daily",
                ("date_id", "region_id", "order_count"),
                role="aggregate",
            )
        ],
        metric_infos=[_metric("order_count")],
        join_relations=[],
    )

    assert "dws_sales_region_daily.region_id" in plan.group_by_columns
    assert set(plan.required_metric_columns) == {
        "dws_sales_region_daily.order_count"
    }
