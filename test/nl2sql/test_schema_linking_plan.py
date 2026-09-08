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
            relation_id="order_item_to_order",
            left_table="fact_order_item",
            left_column="order_id",
            right_table="fact_order",
            right_column="order_id",
        ),
        SchemaLinkingJoin(
            relation_id="order_to_customer",
            left_table="fact_order",
            left_column="customer_id",
            right_table="dim_customer",
            right_column="customer_id",
        ),
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
                "relation_id": "order_item_to_order",
                "left_table": "fact_order_item",
                "left_column": "order_id",
                "right_table": "fact_order",
                "right_column": "order_id",
                "cardinality": "many_to_one",
                "grain_warning": "",
            },
            {
                "relation_id": "order_to_customer",
                "left_table": "fact_order",
                "left_column": "customer_id",
                "right_table": "dim_customer",
                "right_column": "customer_id",
                "cardinality": "many_to_one",
                "grain_warning": "",
            },
        ],
    )

    assert "dim_region" in plan.tables
    assert "dim_region.state_code" in plan.group_by_columns
    assert {"order_item_to_order", "order_to_customer", "customer_to_region"}.issubset(
        {join.relation_id for join in plan.join_relations}
    )
    assert provider.calls == [("fact_order_item", "dim_region")]


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
