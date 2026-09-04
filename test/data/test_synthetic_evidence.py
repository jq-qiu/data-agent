from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import Connection, Engine

from app.synthetic.generator import (
    EXPECTED_CASE_BUCKETS,
    SyntheticConfig,
    SyntheticEvidenceGenerator,
    SyntheticGenerationError,
    build_synthetic_tables,
    safe_ratio,
)

CONFIG_PATH = Path("data/config/synthetic_v1.json")


@pytest.fixture
def engine() -> Iterator[Engine]:
    sqlite_engine = create_engine("sqlite+pysqlite:///:memory:")
    yield sqlite_engine
    sqlite_engine.dispose()


def _prepare_source(connection: Connection) -> None:
    metadata = MetaData()
    batch = Table(
        "data_foundation_build_batch",
        metadata,
        Column("batch_id", String, primary_key=True),
        Column("dataset_version", String, nullable=False),
        Column("status", String, nullable=False),
    )
    fact_order = Table(
        "fact_order",
        metadata,
        Column("order_id", String, primary_key=True),
        Column("status", String, nullable=False),
    )
    fact_item = Table(
        "fact_order_item",
        metadata,
        Column("order_id", String, primary_key=True),
        Column("item_no", Integer, primary_key=True),
        Column("price", Numeric(18, 2), nullable=False),
    )
    region = Table(
        "dws_sales_region_daily",
        metadata,
        Column("date_id", Integer, primary_key=True),
        Column("region_id", String, primary_key=True),
        Column("gmv", Numeric(18, 2), nullable=False),
        Column("order_count", Integer, nullable=False),
    )
    category = Table(
        "dws_sales_category_daily",
        metadata,
        Column("date_id", Integer, primary_key=True),
        Column("region_id", String, primary_key=True),
        Column("category_id", String, primary_key=True),
        Column("gmv", Numeric(18, 2), nullable=False),
        Column("category_order_count", Integer, nullable=False),
    )
    metadata.create_all(connection)
    connection.execute(
        batch.insert(),
        {"batch_id": "foundation", "dataset_version": "2", "status": "success"},
    )
    orders = [
        {"order_id": f"o{index:03d}", "status": "delivered"}
        for index in range(1, 91)
    ]
    items = [
        {"order_id": row["order_id"], "item_no": 1, "price": "10.00"}
        for row in orders
    ]
    connection.execute(fact_order.insert(), orders)
    connection.execute(fact_item.insert(), items)

    region_rows = [
        {"date_id": 20180401, "region_id": region_id, "gmv": gmv, "order_count": orders}
        for region_id, gmv, orders in (
            ("PR", "100.00", 10),
            ("SP", "300.00", 30),
            ("SC", "100.00", 10),
            ("MG", "100.00", 10),
            ("PA", "100.00", 10),
            ("RJ", "100.00", 10),
            ("ES", "100.00", 10),
        )
    ]
    connection.execute(region.insert(), region_rows)
    category_rows = [
        _category_row("SP", "informatica_acessorios"),
        _category_row("SP", "eletrodomesticos"),
        _category_row("SP", "cool_stuff"),
        *(
            _category_row(region_id, "other")
            for region_id in ("PR", "SC", "MG", "PA", "RJ", "ES")
        ),
    ]
    connection.execute(category.insert(), category_rows)
    connection.commit()


def _category_row(region_id: str, category_id: str) -> dict[str, object]:
    return {
        "date_id": 20180401,
        "region_id": region_id,
        "category_id": category_id,
        "gmv": "100.00",
        "category_order_count": 10,
    }


def _generate(engine: Engine):
    with engine.connect() as connection:
        _prepare_source(connection)
        config = SyntheticConfig.from_path(CONFIG_PATH)
        result = SyntheticEvidenceGenerator(config).generate(connection)
    return result


def _period_totals(connection: Connection, table: Table, case_id: str):
    return {
        str(row.period_role): row
        for row in connection.execute(
            select(
                table.c.period_role,
                func.sum(table.c.visitors).label("visitors"),
                func.sum(table.c.promoted_sku_count).label("promoted"),
                func.sum(table.c.active_sku_count).label("active"),
                func.sum(table.c.available_sku_count).label("available"),
                func.sum(table.c.required_sku_count).label("required"),
                func.sum(table.c.analysis_order_count).label("orders"),
                func.sum(table.c.analysis_gmv).label("gmv"),
            )
            .where(table.c.case_id == case_id)
            .group_by(table.c.period_role)
        ).mappings()
    }


def test_config_freezes_ten_case_buckets_and_zero_ratio_behavior() -> None:
    config = SyntheticConfig.from_path(CONFIG_PATH)

    assert {case.case_id: tuple(event.event_type for event in case.causes) for case in config.cases} == EXPECTED_CASE_BUCKETS
    assert config.generator_version == "synthetic-v1"
    assert config.random_seed == 20260905
    assert safe_ratio(1, 0) is None


def test_two_independent_databases_generate_the_same_content_hash() -> None:
    first_engine = create_engine("sqlite+pysqlite:///:memory:")
    second_engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        first = _generate(first_engine)
        second = _generate(second_engine)
    finally:
        first_engine.dispose()
        second_engine.dispose()

    assert first.reconciliation.passed is True
    assert second.reconciliation.passed is True
    assert first.reconciliation.content_sha256 == second.reconciliation.content_sha256
    assert first.reconciliation.case_count == 10
    assert first.reconciliation.event_count == 10
    assert first.reconciliation.region_row_count == 427
    assert first.reconciliation.category_row_count == 183
    assert first.reconciliation.source_unchanged is True
    assert first.reconciliation.source_gate_passed is True


def test_evidence_chains_stable_case_degradation_and_idempotency(engine: Engine) -> None:
    with engine.connect() as connection:
        _prepare_source(connection)
        config = SyntheticConfig.from_path(CONFIG_PATH)
        generator = SyntheticEvidenceGenerator(config)

        first = generator.generate(connection)
        second = generator.generate(connection)
        _metadata, tables = build_synthetic_tables()
        d05 = _period_totals(connection, tables["analysis_sales_region_daily"], "D05")
        d07 = _period_totals(connection, tables["analysis_sales_region_daily"], "D07")
        d09 = _period_totals(connection, tables["analysis_sales_region_daily"], "D09")
        d10 = _period_totals(connection, tables["analysis_sales_region_daily"], "D10")

    assert first.status == "success"
    assert second.reused is True
    assert second.batch_id == first.batch_id
    assert int(d05["current"].available) < int(d05["baseline"].available)
    assert int(d05["current"].orders) < int(d05["baseline"].orders)
    assert d05["current"].gmv < d05["baseline"].gmv
    assert int(d07["current"].visitors) < int(d07["baseline"].visitors)
    assert safe_ratio(d07["current"].promoted, d07["current"].active) < safe_ratio(
        d07["baseline"].promoted,
        d07["baseline"].active,
    )
    assert d09["current"].orders == d09["baseline"].orders
    assert d09["current"].gmv == d09["baseline"].gmv
    assert d10["baseline"].visitors is None
    assert d10["current"].visitors is None
    assert int(d10["current"].orders) < int(d10["baseline"].orders)


def test_reuse_rejects_tampered_synthetic_evidence(engine: Engine) -> None:
    with engine.connect() as connection:
        _prepare_source(connection)
        config = SyntheticConfig.from_path(CONFIG_PATH)
        generator = SyntheticEvidenceGenerator(config)
        generator.generate(connection)
        _metadata, tables = build_synthetic_tables()
        connection.execute(
            tables["analysis_sales_region_daily"].update()
            .where(tables["analysis_sales_region_daily"].c.case_id == "D01")
            .values(analysis_order_count=0)
        )
        connection.commit()

        with pytest.raises(SyntheticGenerationError):
            generator.generate(connection)
