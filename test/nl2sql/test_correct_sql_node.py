"""SQL-024: correct_sql 节点使用 Stub LLM 的闭环测试。

测试不连接真实模型：错误 DWD SQL 进入 correct_sql 后，Stub 返回规范 DWS SQL，
结果必须能被同一个 SQLValidator 接受；Stub 返回仍错误的 SQL 时必须被拒绝。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import app.agent.nodes.correct_sql as correct_sql_module
from app.agent.nodes.correct_sql import correct_sql
from app.metadata.catalog import load_catalog
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.schema_linking import (
    SchemaLinkingOrder,
    SchemaLinkingPlan,
    SchemaLinkingProjection,
)
from app.nl2sql.validator import SQLValidationError, SQLValidator

ROOT = Path(__file__).parents[2]

DWD_WRONG_SQL = (
    "SELECT purchase_date, SUM(price) AS gmv FROM fact_order_item "
    "GROUP BY purchase_date"
)
CORRECT_DWS_SQL = (
    "SELECT r.date_id AS 日期, SUM(r.gmv) AS 每日GMV "
    "FROM dws_sales_region_daily r "
    "WHERE r.date_id BETWEEN 20180501 AND 20180531 "
    "GROUP BY r.date_id ORDER BY r.date_id"
)


@pytest.fixture(scope="module")
def validator() -> SQLValidator:
    return SQLValidator(
        load_catalog(ROOT / "conf" / "meta_config.yaml"),
        load_sql_policy(ROOT / "conf" / "sql_policy.yaml"),
    )


def _plan() -> SchemaLinkingPlan:
    return SchemaLinkingPlan(
        metric_ids=("gmv",),
        tables=("dws_sales_region_daily",),
        columns=(
            "dws_sales_region_daily.date_id",
            "dws_sales_region_daily.gmv",
        ),
        join_relations=(),
        source_table="dws_sales_region_daily",
        result_projections=(
            SchemaLinkingProjection(
                kind="column",
                column="dws_sales_region_daily.date_id",
            ),
            SchemaLinkingProjection(
                kind="sum",
                column="dws_sales_region_daily.gmv",
            ),
        ),
        group_by_columns=("dws_sales_region_daily.date_id",),
        order_by=(SchemaLinkingOrder(column="dws_sales_region_daily.date_id"),),
    )


def _state(sql: str, plan: SchemaLinkingPlan) -> dict[str, Any]:
    return {
        "query": "列出2018年5月每日GMV，按日期排序",
        "table_infos": [],
        "metric_infos": [],
        "join_relations": [],
        "grain_warnings": [],
        "schema_linking_plan": plan.model_dump(mode="json"),
        "db_info": {"version": "8.0", "dialect": "mysql"},
        "date_info": {"date": "2026-09-08", "weekday": "Tuesday", "quarter": "Q3"},
        "sql": sql,
        "error": "SQL uses a table outside SchemaLinkingPlan",
        "repair_attempts": 0,
    }


def _runtime() -> SimpleNamespace:
    writes: list[dict[str, Any]] = []
    return SimpleNamespace(
        stream_writer=writes.append,
        context={},
        writes=writes,
    )


@pytest.mark.asyncio
async def test_correct_sql_stub_repairs_dwd_daily_gmv_to_dws_contract(
    validator: SQLValidator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_llm = FakeListChatModel(responses=[CORRECT_DWS_SQL])
    monkeypatch.setattr(correct_sql_module, "llm", fake_llm)
    plan = _plan()

    result = await correct_sql(_state(DWD_WRONG_SQL, plan), _runtime())

    assert result["repair_attempts"] == 1
    validated = validator.validate(
        result["sql"],
        ("gmv",),
        schema_linking_plan=plan,
    )
    assert "dws_sales_region_daily" in validated.tables


@pytest.mark.asyncio
async def test_correct_sql_stub_that_stays_on_dwd_is_rejected_by_validator(
    validator: SQLValidator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    still_wrong = (
        "SELECT o.purchase_date, SUM(i.price) FROM fact_order i "
        "JOIN fact_order_item i ON i.order_id = o.order_id "
        "GROUP BY o.purchase_date"
    )
    fake_llm = FakeListChatModel(responses=[still_wrong])
    monkeypatch.setattr(correct_sql_module, "llm", fake_llm)
    plan = _plan()

    result = await correct_sql(_state(DWD_WRONG_SQL, plan), _runtime())

    assert result["repair_attempts"] == 1
    with pytest.raises(SQLValidationError):
        validator.validate(result["sql"], ("gmv",), schema_linking_plan=plan)
