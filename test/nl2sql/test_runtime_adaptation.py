from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.mappers.column_info_mapper import ColumnInfoMapper
from app.mappers.metric_info_mapper import MetricInfoMapper
from app.mappers.table_info_mapper import TableInfoMapper
from app.nl2sql.validator import ValidatedSQL
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository

ROOT = Path(__file__).parents[2]


@pytest.mark.asyncio
async def test_dw_repository_only_executes_validated_sql_with_timeout_and_row_cap() -> None:
    mappings = SimpleNamespace(fetchmany=lambda limit: [{"gmv": 1}] if limit == 500 else [])
    result = SimpleNamespace(mappings=lambda: mappings)
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    repository = DWMySQLRepository(session)
    validated = ValidatedSQL(
        sql="SELECT SUM(gmv) AS gmv FROM dws_sales_region_daily LIMIT 500",
        tables=("dws_sales_region_daily",),
        columns=("dws_sales_region_daily.gmv",),
        join_relations=(),
        grain_warnings=(),
        policy_version="sql-policy-v1",
        max_rows=500,
        timeout_seconds=10.0,
    )

    await repository.validate_sql(validated)
    rows = await repository.execute_sql(validated)

    assert rows == [{"gmv": 1}]
    assert session.execute.await_count == 2
    assert str(session.execute.await_args_list[0].args[0]).startswith("EXPLAIN SELECT")
    assert str(session.execute.await_args_list[1].args[0]).startswith("SELECT SUM")


@pytest.mark.asyncio
async def test_v1_vector_repositories_filter_the_shared_metadata_collection() -> None:
    response = SimpleNamespace(
        points=[SimpleNamespace(payload={"object_id": "fact_order.purchase_date"})]
    )
    client = SimpleNamespace(query_points=AsyncMock(return_value=response))

    column_ids = await ColumnQdrantRepository(client).search_v1_ids([0.1, 0.2])
    metric_ids = await MetricQdrantRepository(client).search_v1_ids([0.1, 0.2])

    assert column_ids == ["fact_order.purchase_date"]
    assert metric_ids == ["fact_order.purchase_date"]
    assert all(
        call.kwargs["collection_name"] == "data-agent-metadata-v1"
        for call in client.query_points.await_args_list
    )


@pytest.mark.asyncio
async def test_v1_value_repository_returns_canonical_value() -> None:
    client = SimpleNamespace(
        search=AsyncMock(
            return_value={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "id": "value-id",
                                "column_id": "dim_region.state_code",
                                "canonical_value": "SP",
                                "aliases": ["圣保罗州"],
                            }
                        },
                        {
                            "_source": {
                                "id": "noise-id",
                                "column_id": "dim_region.state_code",
                                "canonical_value": "RJ",
                                "aliases": ["里约热内卢州"],
                            }
                        },
                    ]
                }
            }
        )
    )

    values = await ValueESRepository(client).search_v1_grounded("圣保罗州")

    assert values[0].value == "SP"
    assert values[0].column_id == "dim_region.state_code"
    assert values[0].matched_value == "圣保罗州"
    assert len(values) == 1
    assert client.search.await_args.kwargs["index"] == "data-agent-value-v1"


def test_extended_entities_keep_legacy_mapper_writes_compatible() -> None:
    table_model = TableInfoMapper.to_model(
        TableInfo(
            id="fact_order",
            name="fact_order",
            role="fact",
            description="orders",
            grain="one row per order",
            primary_key=["order_id"],
        )
    )
    column_model = ColumnInfoMapper.to_model(
        ColumnInfo(
            id="fact_order.order_id",
            name="order_id",
            type="varchar(64)",
            role="primary_key",
            examples=[],
            description="order id",
            alias=[],
            table_id="fact_order",
            is_sensitive=True,
        )
    )
    metric_model = MetricInfoMapper.to_model(
        MetricInfo(
            id="gmv",
            name="GMV",
            description="gmv",
            relevant_columns=["fact_order_item.price"],
            alias=["成交总额"],
            formula="SUM(fact_order_item.price)",
        )
    )

    assert table_model.name == "fact_order"
    assert column_model.name == "order_id"
    assert metric_model.name == "GMV"


def test_v1_metric_mapping_decodes_mysql_json_strings() -> None:
    metric = MetaMySQLRepository._v1_metric_from_row(
        {
            "metric_id": "gmv",
            "display_name": "GMV",
            "description": "gmv",
            "relevant_columns": '["fact_order_item.price"]',
            "aliases": '["成交总额"]',
            "formula": "SUM(fact_order_item.price)",
            "base_grain": "order item",
            "time_column": "fact_order.purchase_date",
            "status_filters": '{"exclude:fact_order.status":["canceled","unavailable"]}',
            "allowed_dimensions": '["date","region"]',
            "component_metrics": "[]",
            "version": "metadata-v1",
        }
    )

    assert metric.relevant_columns == ["fact_order_item.price"]
    assert metric.status_filters == {"exclude:fact_order.status": ["canceled", "unavailable"]}


def test_prompts_require_registry_join_and_contain_no_domestic_demo_examples() -> None:
    prompt_names = (
        "expand_recall_keywords.prompt",
        "generate_sql.prompt",
        "correct_sql.prompt",
    )
    content = "\n".join(
        (ROOT / "prompts" / name).read_text(encoding="utf-8") for name in prompt_names
    )

    assert "{join_relations}" in content
    assert "{schema_linking_plan}" in content
    assert "{repair_constraints}" in content
    assert "则基于用户问题语义与通用业务常识进行" not in content
    assert "不得使用通用业务常识自创公式" in content
    for stale_term in ("华南", "广东省", "华为"):
        assert stale_term not in content
