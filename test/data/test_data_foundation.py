from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine, event, select
from sqlalchemy.engine import Connection, Engine

from app.data_foundation.olist import (
    LOGICAL_FOREIGN_KEYS,
    DataFoundationError,
    OlistDataFoundationBuilder,
    build_foundation_tables,
)
from app.data_import.olist import OlistManifest


@pytest.fixture
def engine() -> Iterator[Engine]:
    sqlite_engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(sqlite_engine, "connect")
    def _enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield sqlite_engine
    sqlite_engine.dispose()


def _manifest() -> OlistManifest:
    return OlistManifest(
        dataset_name="olist_fixture",
        dataset_version="2",
        source_url="https://example.invalid/olist-fixture",
        license="test-only",
        archive_filename="fixture.zip",
        archive_size_bytes=1,
        archive_sha256="a" * 64,
        files=(),
    )


def _create_ods(connection: Connection) -> None:
    metadata = MetaData()
    tables = {
        "ods_olist_import_batch": Table(
            "ods_olist_import_batch",
            metadata,
            Column("batch_id", String, primary_key=True),
            Column("dataset_version", String, nullable=False),
            Column("archive_sha256", String, nullable=False),
            Column("status", String, nullable=False),
        ),
        "ods_olist_customers": Table(
            "ods_olist_customers",
            metadata,
            Column("customer_id", String),
            Column("customer_unique_id", String),
            Column("customer_state", String),
        ),
        "ods_olist_sellers": Table(
            "ods_olist_sellers",
            metadata,
            Column("seller_id", String),
            Column("seller_state", String),
        ),
        "ods_olist_product_category_name_translation": Table(
            "ods_olist_product_category_name_translation",
            metadata,
            Column("product_category_name", String),
            Column("product_category_name_english", String),
        ),
        "ods_olist_products": Table(
            "ods_olist_products",
            metadata,
            Column("product_id", String),
            Column("product_category_name", String),
            Column("product_weight_g", String),
            Column("product_length_cm", String),
            Column("product_height_cm", String),
            Column("product_width_cm", String),
        ),
        "ods_olist_orders": Table(
            "ods_olist_orders",
            metadata,
            Column("order_id", String),
            Column("customer_id", String),
            Column("order_status", String),
            Column("order_purchase_timestamp", String),
            Column("order_approved_at", String),
            Column("order_delivered_carrier_date", String),
            Column("order_delivered_customer_date", String),
            Column("order_estimated_delivery_date", String),
        ),
        "ods_olist_order_items": Table(
            "ods_olist_order_items",
            metadata,
            Column("order_id", String),
            Column("order_item_id", String),
            Column("product_id", String),
            Column("seller_id", String),
            Column("shipping_limit_date", String),
            Column("price", String),
            Column("freight_value", String),
        ),
        "ods_olist_order_payments": Table(
            "ods_olist_order_payments",
            metadata,
            Column("order_id", String),
            Column("payment_sequential", String),
            Column("payment_type", String),
            Column("payment_installments", String),
            Column("payment_value", String),
        ),
        "ods_olist_order_reviews": Table(
            "ods_olist_order_reviews",
            metadata,
            Column("review_id", String),
            Column("order_id", String),
            Column("review_score", String),
            Column("review_creation_date", String),
        ),
    }
    metadata.create_all(connection)
    connection.execute(
        tables["ods_olist_import_batch"].insert(),
        {
            "batch_id": "source-batch",
            "dataset_version": "2",
            "archive_sha256": "a" * 64,
            "status": "success",
        },
    )
    connection.execute(
        tables["ods_olist_customers"].insert(),
        [
            {"customer_id": "c1", "customer_unique_id": "u1", "customer_state": "SP"},
            {"customer_id": "c2", "customer_unique_id": "u2", "customer_state": "SP"},
            {"customer_id": "c3", "customer_unique_id": "u3", "customer_state": "RJ"},
        ],
    )
    connection.execute(
        tables["ods_olist_sellers"].insert(),
        {"seller_id": "s1", "seller_state": "SP"},
    )
    connection.execute(
        tables["ods_olist_product_category_name_translation"].insert(),
        [
            {"product_category_name": "cat_a", "product_category_name_english": "A"},
            {"product_category_name": "cat_b", "product_category_name_english": "B"},
        ],
    )
    connection.execute(
        tables["ods_olist_products"].insert(),
        [
            _product("p1", "cat_a"),
            _product("p2", "cat_b"),
        ],
    )
    connection.execute(
        tables["ods_olist_orders"].insert(),
        [
            _order("o1", "c1", "delivered", "2018-05-01 10:00:00"),
            _order("o2", "c2", "delivered", "2018-05-02 10:00:00"),
            _order("o3", "c3", "canceled", "2018-05-03 10:00:00"),
        ],
    )
    connection.execute(
        tables["ods_olist_order_items"].insert(),
        [
            _item("o1", "1", "p1", "10.00"),
            _item("o1", "2", "p2", "20.00"),
            _item("o3", "1", "p1", "100.00"),
        ],
    )
    connection.execute(
        tables["ods_olist_order_payments"].insert(),
        [
            _payment("o1", "1", "15.00"),
            _payment("o1", "2", "15.00"),
            _payment("o2", "1", "0.00"),
            _payment("o3", "1", "100.00"),
        ],
    )
    connection.execute(
        tables["ods_olist_order_reviews"].insert(),
        [
            _review("r1", "o1", "5"),
            _review("r1", "o2", "4"),
        ],
    )
    connection.commit()


def _product(product_id: str, category: str) -> dict[str, str]:
    return {
        "product_id": product_id,
        "product_category_name": category,
        "product_weight_g": "100",
        "product_length_cm": "10",
        "product_height_cm": "20",
        "product_width_cm": "30",
    }


def _order(order_id: str, customer_id: str, status: str, purchased_at: str) -> dict[str, str]:
    return {
        "order_id": order_id,
        "customer_id": customer_id,
        "order_status": status,
        "order_purchase_timestamp": purchased_at,
        "order_approved_at": purchased_at,
        "order_delivered_carrier_date": purchased_at,
        "order_delivered_customer_date": "2018-05-05 10:00:00",
        "order_estimated_delivery_date": "2018-05-06 00:00:00",
    }


def _item(order_id: str, item_no: str, product_id: str, price: str) -> dict[str, str]:
    return {
        "order_id": order_id,
        "order_item_id": item_no,
        "product_id": product_id,
        "seller_id": "s1",
        "shipping_limit_date": "2018-05-04 00:00:00",
        "price": price,
        "freight_value": "5.00",
    }


def _payment(order_id: str, sequence: str, value: str) -> dict[str, str]:
    return {
        "order_id": order_id,
        "payment_sequential": sequence,
        "payment_type": "credit_card",
        "payment_installments": "1",
        "payment_value": value,
    }


def _review(review_id: str, order_id: str, score: str) -> dict[str, str]:
    return {
        "review_id": review_id,
        "order_id": order_id,
        "review_score": score,
        "review_creation_date": "2018-05-07 00:00:00",
    }


def test_schema_freezes_dwd_and_dws_grains_without_ratio_columns() -> None:
    _metadata, tables = build_foundation_tables()

    assert len([name for name in tables if name.startswith(("dim_", "fact_"))]) == 11
    assert [column.name for column in tables["dws_sales_region_daily"].primary_key] == [
        "date_id",
        "region_id",
    ]
    assert [column.name for column in tables["dws_sales_category_daily"].primary_key] == [
        "date_id",
        "region_id",
        "category_id",
    ]
    assert "aov" not in tables["dws_sales_region_daily"].c
    assert "conversion_rate" not in tables["dws_sales_region_daily"].c
    assert len(LOGICAL_FOREIGN_KEYS) == 7


def test_build_reconciles_grains_money_orders_and_is_idempotent(engine: Engine) -> None:
    with engine.connect() as connection:
        _create_ods(connection)
        builder = OlistDataFoundationBuilder(_manifest(), chunk_size=2)

        first = builder.build(connection)
        second = builder.build(connection)
        _metadata, tables = build_foundation_tables()
        region_rows = connection.execute(
            select(tables["dws_sales_region_daily"]).order_by(
                tables["dws_sales_region_daily"].c.date_id
            )
        ).mappings().all()

    assert first.status == "success"
    assert first.reused is False
    assert second.reused is True
    assert second.batch_id == first.batch_id
    assert first.reconciliation.passed is True
    assert first.reconciliation.base_gmv == "30.00"
    assert first.reconciliation.region_dws_gmv == "30.00"
    assert first.reconciliation.category_dws_gmv == "30.00"
    assert first.reconciliation.valid_order_count == 2
    assert first.reconciliation.region_dws_order_count == 2
    assert first.reconciliation.category_order_count_sum == 2
    assert first.reconciliation.naive_payment_item_join_gmv == "60.00"
    assert first.reconciliation.join_inflation_detected is True
    assert not any(first.reconciliation.orphan_counts.values())
    assert first.reconciliation.synthetic_non_null_count == 0
    assert first.reconciliation.table_counts["dim_date"] == 3
    assert [row.order_count for row in region_rows] == [1, 1]
    assert [str(row.gmv) for row in region_rows] == ["30.00", "0.00"]


def test_reuse_rejects_a_corrupted_successful_build(engine: Engine) -> None:
    with engine.connect() as connection:
        _create_ods(connection)
        builder = OlistDataFoundationBuilder(_manifest())
        builder.build(connection)
        _metadata, tables = build_foundation_tables()
        connection.execute(tables["dws_sales_region_daily"].delete())
        connection.commit()

        with pytest.raises(DataFoundationError, match="no longer reconciles"):
            builder.build(connection)
