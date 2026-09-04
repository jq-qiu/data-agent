from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    and_,
    func,
    insert,
    literal,
    or_,
    select,
    update,
)
from sqlalchemy.engine import Connection, RowMapping

from app.data_import.olist import OlistManifest

EXCLUDED_ORDER_STATUSES = ("canceled", "unavailable")
UNKNOWN_CATEGORY_ID = "__unknown__"
LOGICAL_FOREIGN_KEYS = (
    ("order_customer", "fact_order", "customer_id", "dim_customer", "customer_id"),
    ("item_order", "fact_order_item", "order_id", "fact_order", "order_id"),
    ("item_product", "fact_order_item", "product_id", "dim_product", "product_id"),
    ("item_seller", "fact_order_item", "seller_id", "dim_seller", "seller_id"),
    ("payment_order", "fact_payment", "order_id", "fact_order", "order_id"),
    ("delivery_order", "fact_delivery", "order_id", "fact_order", "order_id"),
    ("review_order", "fact_review", "order_id", "fact_order", "order_id"),
)
_SUCCESS = "success"
_RUNNING = "running"
_FAILED = "failed"


class DataFoundationError(RuntimeError):
    """Raised when the deterministic DWD/DWS build cannot be accepted."""


@dataclass(frozen=True)
class ReconciliationResult:
    passed: bool
    table_counts: dict[str, int]
    expected_fact_counts: dict[str, int]
    orphan_counts: dict[str, int]
    date_dimension_contiguous: bool
    base_gmv: str
    region_dws_gmv: str
    category_dws_gmv: str
    valid_order_count: int
    region_dws_order_count: int
    category_order_count_sum: int
    naive_payment_item_join_gmv: str
    join_inflation_detected: bool
    synthetic_non_null_count: int


@dataclass(frozen=True)
class DataFoundationResult:
    batch_id: str
    status: str
    reused: bool
    reconciliation: ReconciliationResult


def build_foundation_tables() -> tuple[MetaData, dict[str, Table]]:
    metadata = MetaData()
    tables: dict[str, Table] = {}

    tables["data_foundation_build_batch"] = Table(
        "data_foundation_build_batch",
        metadata,
        Column("batch_id", String(36), primary_key=True),
        Column("dataset_version", String(32), nullable=False),
        Column("source_archive_sha256", String(64), nullable=False),
        Column("started_at", DateTime, nullable=False),
        Column("completed_at", DateTime, nullable=True),
        Column("status", String(16), nullable=False),
        Column("error_type", String(128), nullable=True),
    )
    tables["dim_date"] = Table(
        "dim_date",
        metadata,
        Column("date_id", Integer, primary_key=True),
        Column("date", Date, nullable=False, unique=True),
        Column("year", SmallInteger, nullable=False),
        Column("quarter", SmallInteger, nullable=False),
        Column("month", String(7), nullable=False),
        Column("week", String(8), nullable=False),
    )
    tables["dim_region"] = Table(
        "dim_region",
        metadata,
        Column("state_code", String(2), primary_key=True),
        Column("display_name", String(64), nullable=False),
    )
    tables["dim_category"] = Table(
        "dim_category",
        metadata,
        Column("category_id", String(128), primary_key=True),
        Column("category_name_pt", String(128), nullable=True),
        Column("category_name_en", String(128), nullable=True),
    )
    tables["dim_customer"] = Table(
        "dim_customer",
        metadata,
        Column("customer_id", String(64), primary_key=True),
        Column("customer_unique_id", String(64), nullable=False),
        Column("state", String(2), nullable=False),
    )
    tables["dim_product"] = Table(
        "dim_product",
        metadata,
        Column("product_id", String(64), primary_key=True),
        Column(
            "category_id",
            String(128),
            nullable=False,
        ),
        Column("weight_g", Integer, nullable=True),
        Column("length_cm", Integer, nullable=True),
        Column("height_cm", Integer, nullable=True),
        Column("width_cm", Integer, nullable=True),
    )
    tables["dim_seller"] = Table(
        "dim_seller",
        metadata,
        Column("seller_id", String(64), primary_key=True),
        Column("state", String(2), nullable=False),
    )
    tables["fact_order"] = Table(
        "fact_order",
        metadata,
        Column("order_id", String(64), primary_key=True),
        Column(
            "customer_id",
            String(64),
            nullable=False,
        ),
        Column("status", String(32), nullable=False),
        Column("purchase_timestamp", DateTime, nullable=False),
        Column("purchase_date", Date, nullable=False),
        Column("date_id", Integer, nullable=False),
        Column("approved_at", DateTime, nullable=True),
        Column("delivered_carrier_at", DateTime, nullable=True),
        Column("delivered_customer_at", DateTime, nullable=True),
        Column("estimated_delivery_date", Date, nullable=False),
    )
    tables["fact_order_item"] = Table(
        "fact_order_item",
        metadata,
        Column("order_id", String(64), primary_key=True),
        Column("item_no", Integer, primary_key=True),
        Column(
            "product_id",
            String(64),
            nullable=False,
        ),
        Column("seller_id", String(64), nullable=False),
        Column("shipping_limit_at", DateTime, nullable=False),
        Column("price", Numeric(18, 2), nullable=False),
        Column("freight_value", Numeric(18, 2), nullable=False),
    )
    tables["fact_payment"] = Table(
        "fact_payment",
        metadata,
        Column("order_id", String(64), primary_key=True),
        Column("payment_sequential", Integer, primary_key=True),
        Column("payment_type", String(32), nullable=False),
        Column("payment_installments", Integer, nullable=False),
        Column("payment_value", Numeric(18, 2), nullable=False),
    )
    tables["fact_delivery"] = Table(
        "fact_delivery",
        metadata,
        Column("order_id", String(64), primary_key=True),
        Column("estimated_date", Date, nullable=False),
        Column("delivered_date", Date, nullable=True),
        Column("delay_days", Integer, nullable=True),
    )
    tables["fact_review"] = Table(
        "fact_review",
        metadata,
        Column("review_id", String(64), primary_key=True),
        Column("order_id", String(64), primary_key=True),
        Column("score", SmallInteger, nullable=False),
        Column("created_at", DateTime, nullable=False),
    )
    tables["dws_sales_region_daily"] = Table(
        "dws_sales_region_daily",
        metadata,
        Column("date_id", Integer, primary_key=True),
        Column(
            "region_id",
            String(2),
            primary_key=True,
        ),
        Column("gmv", Numeric(18, 2), nullable=False),
        Column("order_count", BigInteger, nullable=False),
        Column("visitors", BigInteger, nullable=True),
        Column("promoted_sku_count", BigInteger, nullable=True),
        Column("active_sku_count", BigInteger, nullable=True),
        Column("available_sku_count", BigInteger, nullable=True),
        Column("required_sku_count", BigInteger, nullable=True),
        Column("dataset_version", String(32), nullable=False),
        Column("synthetic_version", String(32), nullable=True),
    )
    tables["dws_sales_category_daily"] = Table(
        "dws_sales_category_daily",
        metadata,
        Column("date_id", Integer, primary_key=True),
        Column(
            "region_id",
            String(2),
            primary_key=True,
        ),
        Column(
            "category_id",
            String(128),
            primary_key=True,
        ),
        Column("gmv", Numeric(18, 2), nullable=False),
        Column("item_count", BigInteger, nullable=False),
        Column("category_order_count", BigInteger, nullable=False),
        Column("category_visitors", BigInteger, nullable=True),
        Column("promoted_sku_count", BigInteger, nullable=True),
        Column("active_sku_count", BigInteger, nullable=True),
        Column("available_sku_count", BigInteger, nullable=True),
        Column("required_sku_count", BigInteger, nullable=True),
        Column("dataset_version", String(32), nullable=False),
        Column("synthetic_version", String(32), nullable=True),
    )
    return metadata, tables


class OlistDataFoundationBuilder:
    def __init__(self, manifest: OlistManifest, chunk_size: int = 2_000):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self.manifest = manifest
        self.chunk_size = chunk_size

    def build(self, connection: Connection) -> DataFoundationResult:
        metadata, tables = build_foundation_tables()
        ods = self._reflect_ods(connection)
        self._assert_source_batch(connection, ods)
        metadata.create_all(connection)
        connection.commit()

        batch = tables["data_foundation_build_batch"]
        previous_batch_id = connection.execute(
            select(batch.c.batch_id).where(
                and_(
                    batch.c.dataset_version == self.manifest.dataset_version,
                    batch.c.source_archive_sha256 == self.manifest.archive_sha256,
                    batch.c.status == _SUCCESS,
                )
            )
        ).scalar_one_or_none()
        connection.commit()
        if previous_batch_id is not None:
            reconciliation = reconcile_data_foundation(connection, tables, ods, self.manifest)
            connection.commit()
            if not reconciliation.passed:
                raise DataFoundationError(
                    "Existing successful data foundation no longer reconciles"
                )
            return DataFoundationResult(
                batch_id=str(previous_batch_id),
                status=_SUCCESS,
                reused=True,
                reconciliation=reconciliation,
            )

        batch_id = str(uuid.uuid4())
        started_at = _utc_now()
        with connection.begin():
            connection.execute(
                insert(batch),
                {
                    "batch_id": batch_id,
                    "dataset_version": self.manifest.dataset_version,
                    "source_archive_sha256": self.manifest.archive_sha256,
                    "started_at": started_at,
                    "completed_at": None,
                    "status": _RUNNING,
                    "error_type": None,
                },
            )

        try:
            with connection.begin():
                self._assert_target_tables_empty(connection, tables)
                self._load_dimensions(connection, tables, ods)
                self._load_facts(connection, tables, ods)
                self._load_dws(connection, tables)
                reconciliation = reconcile_data_foundation(
                    connection,
                    tables,
                    ods,
                    self.manifest,
                )
                if not reconciliation.passed:
                    raise DataFoundationError("DATA-002 reconciliation failed")
                connection.execute(
                    update(batch)
                    .where(batch.c.batch_id == batch_id)
                    .values(status=_SUCCESS, completed_at=_utc_now(), error_type=None)
                )
        except Exception as exc:
            if connection.in_transaction():
                connection.rollback()
            with connection.begin():
                connection.execute(
                    update(batch)
                    .where(batch.c.batch_id == batch_id)
                    .values(
                        status=_FAILED,
                        completed_at=_utc_now(),
                        error_type=type(exc).__name__[:128],
                    )
                )
            raise

        return DataFoundationResult(
            batch_id=batch_id,
            status=_SUCCESS,
            reused=False,
            reconciliation=reconciliation,
        )

    def _reflect_ods(self, connection: Connection) -> dict[str, Table]:
        metadata = MetaData()
        required = {
            "ods_olist_customers",
            "ods_olist_import_batch",
            "ods_olist_order_items",
            "ods_olist_order_payments",
            "ods_olist_order_reviews",
            "ods_olist_orders",
            "ods_olist_product_category_name_translation",
            "ods_olist_products",
            "ods_olist_sellers",
        }
        try:
            return {
                name: Table(name, metadata, autoload_with=connection)
                for name in sorted(required)
            }
        except Exception as exc:
            raise DataFoundationError("Required DATA-001 ODS tables are unavailable") from exc

    def _assert_source_batch(self, connection: Connection, ods: dict[str, Table]) -> None:
        batch = ods["ods_olist_import_batch"]
        count = connection.execute(
            select(func.count())
            .select_from(batch)
            .where(
                and_(
                    batch.c.dataset_version == self.manifest.dataset_version,
                    batch.c.archive_sha256 == self.manifest.archive_sha256,
                    batch.c.status == _SUCCESS,
                )
            )
        ).scalar_one()
        connection.commit()
        if count != 1:
            raise DataFoundationError("Exactly one successful DATA-001 source batch is required")

    def _assert_target_tables_empty(
        self,
        connection: Connection,
        tables: dict[str, Table],
    ) -> None:
        nonempty = [
            name
            for name, table in tables.items()
            if name != "data_foundation_build_batch" and _count(connection, table) > 0
        ]
        if nonempty:
            raise DataFoundationError(
                "Unaccepted DWD/DWS data exists; automatic overwrite is disabled"
            )

    def _load_dimensions(
        self,
        connection: Connection,
        tables: dict[str, Table],
        ods: dict[str, Table],
    ) -> None:
        orders = ods["ods_olist_orders"]
        min_ts, max_ts = connection.execute(
            select(
                func.min(orders.c.order_purchase_timestamp),
                func.max(orders.c.order_purchase_timestamp),
            )
        ).one()
        min_date = _parse_datetime(min_ts).date()
        max_date = _parse_datetime(max_ts).date()
        date_rows = []
        current = min_date
        while current <= max_date:
            iso_year, iso_week, _ = current.isocalendar()
            date_rows.append(
                {
                    "date_id": _date_id(current),
                    "date": current,
                    "year": current.year,
                    "quarter": (current.month - 1) // 3 + 1,
                    "month": current.strftime("%Y-%m"),
                    "week": f"{iso_year}-W{iso_week:02d}",
                }
            )
            current += timedelta(days=1)
        connection.execute(insert(tables["dim_date"]), date_rows)

        customers = ods["ods_olist_customers"]
        sellers = ods["ods_olist_sellers"]
        states = {
            str(value)
            for value in connection.execute(select(customers.c.customer_state).distinct()).scalars()
            if value
        }
        states.update(
            str(value)
            for value in connection.execute(select(sellers.c.seller_state).distinct()).scalars()
            if value
        )
        connection.execute(
            insert(tables["dim_region"]),
            [{"state_code": state, "display_name": state} for state in sorted(states)],
        )

        translations_table = ods["ods_olist_product_category_name_translation"]
        translations = {
            str(row.product_category_name): str(row.product_category_name_english)
            for row in connection.execute(select(translations_table)).mappings()
        }
        products = ods["ods_olist_products"]
        categories = {
            str(value)
            for value in connection.execute(select(products.c.product_category_name).distinct()).scalars()
            if value
        }
        connection.execute(
            insert(tables["dim_category"]),
            [
                {
                    "category_id": UNKNOWN_CATEGORY_ID,
                    "category_name_pt": None,
                    "category_name_en": None,
                },
                *(
                    {
                        "category_id": category,
                        "category_name_pt": category,
                        "category_name_en": translations.get(category),
                    }
                    for category in sorted(categories | set(translations))
                ),
            ],
        )

        customer_rows = (
            {
                "customer_id": str(row.customer_id),
                "customer_unique_id": str(row.customer_unique_id),
                "state": str(row.customer_state),
            }
            for row in connection.execute(select(customers)).mappings()
        )
        _insert_chunks(connection, tables["dim_customer"], customer_rows, self.chunk_size)

        product_rows = (
            {
                "product_id": str(row.product_id),
                "category_id": str(row.product_category_name or UNKNOWN_CATEGORY_ID),
                "weight_g": _parse_int(row.product_weight_g),
                "length_cm": _parse_int(row.product_length_cm),
                "height_cm": _parse_int(row.product_height_cm),
                "width_cm": _parse_int(row.product_width_cm),
            }
            for row in connection.execute(select(products)).mappings()
        )
        _insert_chunks(connection, tables["dim_product"], product_rows, self.chunk_size)

        seller_rows = (
            {
                "seller_id": str(row.seller_id),
                "state": str(row.seller_state),
            }
            for row in connection.execute(select(sellers)).mappings()
        )
        _insert_chunks(connection, tables["dim_seller"], seller_rows, self.chunk_size)

    def _load_facts(
        self,
        connection: Connection,
        tables: dict[str, Table],
        ods: dict[str, Table],
    ) -> None:
        orders = ods["ods_olist_orders"]
        order_rows = (
            _order_row(row)
            for row in connection.execute(select(orders)).mappings()
        )
        _insert_chunks(connection, tables["fact_order"], order_rows, self.chunk_size)

        items = ods["ods_olist_order_items"]
        item_rows = (
            {
                "order_id": str(row.order_id),
                "item_no": _required_int(row.order_item_id),
                "product_id": str(row.product_id),
                "seller_id": str(row.seller_id),
                "shipping_limit_at": _parse_datetime(row.shipping_limit_date),
                "price": _required_decimal(row.price),
                "freight_value": _required_decimal(row.freight_value),
            }
            for row in connection.execute(select(items)).mappings()
        )
        _insert_chunks(connection, tables["fact_order_item"], item_rows, self.chunk_size)

        payments = ods["ods_olist_order_payments"]
        payment_rows = (
            {
                "order_id": str(row.order_id),
                "payment_sequential": _required_int(row.payment_sequential),
                "payment_type": str(row.payment_type),
                "payment_installments": _required_int(row.payment_installments),
                "payment_value": _required_decimal(row.payment_value),
            }
            for row in connection.execute(select(payments)).mappings()
        )
        _insert_chunks(connection, tables["fact_payment"], payment_rows, self.chunk_size)

        delivery_rows = (_delivery_row(row) for row in connection.execute(select(orders)).mappings())
        _insert_chunks(connection, tables["fact_delivery"], delivery_rows, self.chunk_size)

        reviews = ods["ods_olist_order_reviews"]
        review_rows = (
            {
                "review_id": str(row.review_id),
                "order_id": str(row.order_id),
                "score": _required_int(row.review_score),
                "created_at": _parse_datetime(row.review_creation_date),
            }
            for row in connection.execute(select(reviews)).mappings()
        )
        _insert_chunks(connection, tables["fact_review"], review_rows, self.chunk_size)

    def _load_dws(self, connection: Connection, tables: dict[str, Table]) -> None:
        fact_order = tables["fact_order"]
        fact_item = tables["fact_order_item"]
        customer = tables["dim_customer"]
        product = tables["dim_product"]

        valid_order = fact_order.c.status.not_in(EXCLUDED_ORDER_STATUSES)
        order_counts = {
            (_date_id(row.purchase_date), str(row.region_id)): int(row.order_count)
            for row in connection.execute(
                select(
                    fact_order.c.purchase_date,
                    customer.c.state.label("region_id"),
                    func.count(fact_order.c.order_id).label("order_count"),
                )
                .join(customer, customer.c.customer_id == fact_order.c.customer_id)
                .where(valid_order)
                .group_by(fact_order.c.purchase_date, customer.c.state)
            ).mappings()
        }
        region_gmv = {
            (_date_id(row.purchase_date), str(row.region_id)): _money(row.gmv)
            for row in connection.execute(
                select(
                    fact_order.c.purchase_date,
                    customer.c.state.label("region_id"),
                    func.sum(fact_item.c.price).label("gmv"),
                )
                .join(customer, customer.c.customer_id == fact_order.c.customer_id)
                .join(fact_item, fact_item.c.order_id == fact_order.c.order_id)
                .where(valid_order)
                .group_by(fact_order.c.purchase_date, customer.c.state)
            ).mappings()
        }
        region_rows = [
            {
                "date_id": key[0],
                "region_id": key[1],
                "gmv": region_gmv.get(key, Decimal("0.00")),
                "order_count": order_counts.get(key, 0),
                "visitors": None,
                "promoted_sku_count": None,
                "active_sku_count": None,
                "available_sku_count": None,
                "required_sku_count": None,
                "dataset_version": self.manifest.dataset_version,
                "synthetic_version": None,
            }
            for key in sorted(order_counts.keys() | region_gmv.keys())
        ]
        _insert_chunks(
            connection,
            tables["dws_sales_region_daily"],
            region_rows,
            self.chunk_size,
        )

        category_rows = (
            {
                "date_id": _date_id(row.purchase_date),
                "region_id": str(row.region_id),
                "category_id": str(row.category_id),
                "gmv": _money(row.gmv),
                "item_count": int(row.item_count),
                "category_order_count": int(row.category_order_count),
                "category_visitors": None,
                "promoted_sku_count": None,
                "active_sku_count": None,
                "available_sku_count": None,
                "required_sku_count": None,
                "dataset_version": self.manifest.dataset_version,
                "synthetic_version": None,
            }
            for row in connection.execute(
                select(
                    fact_order.c.purchase_date,
                    customer.c.state.label("region_id"),
                    product.c.category_id,
                    func.sum(fact_item.c.price).label("gmv"),
                    func.count().label("item_count"),
                    func.count(func.distinct(fact_order.c.order_id)).label(
                        "category_order_count"
                    ),
                )
                .join(customer, customer.c.customer_id == fact_order.c.customer_id)
                .join(fact_item, fact_item.c.order_id == fact_order.c.order_id)
                .join(product, product.c.product_id == fact_item.c.product_id)
                .where(valid_order)
                .group_by(
                    fact_order.c.purchase_date,
                    customer.c.state,
                    product.c.category_id,
                )
            ).mappings()
        )
        _insert_chunks(
            connection,
            tables["dws_sales_category_daily"],
            category_rows,
            self.chunk_size,
        )


def reconcile_data_foundation(
    connection: Connection,
    tables: dict[str, Table],
    ods: dict[str, Table],
    manifest: OlistManifest,
) -> ReconciliationResult:
    target_names = tuple(
        name for name in tables if name != "data_foundation_build_batch"
    )
    table_counts = {
        name: int(connection.execute(select(func.count()).select_from(tables[name])).scalar_one())
        for name in target_names
    }
    expected_fact_counts = {
        "fact_order": _count(connection, ods["ods_olist_orders"]),
        "fact_order_item": _count(connection, ods["ods_olist_order_items"]),
        "fact_payment": _count(connection, ods["ods_olist_order_payments"]),
        "fact_delivery": _count(connection, ods["ods_olist_orders"]),
        "fact_review": _count(connection, ods["ods_olist_order_reviews"]),
    }
    orphan_counts = _orphan_counts(connection, tables)
    fact_order = tables["fact_order"]
    fact_item = tables["fact_order_item"]
    fact_payment = tables["fact_payment"]
    valid_order = fact_order.c.status.not_in(EXCLUDED_ORDER_STATUSES)

    base_gmv = _money(
        connection.execute(
            select(func.coalesce(func.sum(fact_item.c.price), 0))
            .select_from(
                fact_order.join(
                    fact_item,
                    fact_item.c.order_id == fact_order.c.order_id,
                )
            )
            .where(valid_order)
        ).scalar_one()
    )
    region_gmv = _money(
        connection.execute(
            select(func.coalesce(func.sum(tables["dws_sales_region_daily"].c.gmv), 0))
        ).scalar_one()
    )
    category_gmv = _money(
        connection.execute(
            select(func.coalesce(func.sum(tables["dws_sales_category_daily"].c.gmv), 0))
        ).scalar_one()
    )
    valid_order_count = int(
        connection.execute(
            select(func.count()).select_from(fact_order).where(valid_order)
        ).scalar_one()
    )
    region_order_count = int(
        connection.execute(
            select(func.coalesce(func.sum(tables["dws_sales_region_daily"].c.order_count), 0))
        ).scalar_one()
    )
    category_order_count_sum = int(
        connection.execute(
            select(
                func.coalesce(
                    func.sum(tables["dws_sales_category_daily"].c.category_order_count),
                    0,
                )
            )
        ).scalar_one()
    )
    naive_join_gmv = _money(
        connection.execute(
            select(func.coalesce(func.sum(fact_item.c.price), 0))
            .select_from(
                fact_order.join(
                    fact_item,
                    fact_item.c.order_id == fact_order.c.order_id,
                ).join(
                    fact_payment,
                    fact_payment.c.order_id == fact_order.c.order_id,
                )
            )
            .where(valid_order)
        ).scalar_one()
    )
    synthetic_non_null_count = _synthetic_non_null_count(connection, tables)

    dates = tables["dim_date"]
    min_date, max_date, date_count = connection.execute(
        select(func.min(dates.c.date), func.max(dates.c.date), func.count()).select_from(dates)
    ).one()
    date_dimension_contiguous = bool(
        min_date
        and max_date
        and int(date_count) == (max_date - min_date).days + 1
    )
    fact_counts_match = all(
        table_counts[name] == expected for name, expected in expected_fact_counts.items()
    )
    passed = all(
        (
            fact_counts_match,
            not any(orphan_counts.values()),
            date_dimension_contiguous,
            base_gmv == region_gmv == category_gmv,
            valid_order_count == region_order_count,
            synthetic_non_null_count == 0,
            _dws_grains_unique(connection, tables),
            _dws_versions_match(connection, tables, manifest.dataset_version),
        )
    )
    return ReconciliationResult(
        passed=passed,
        table_counts=table_counts,
        expected_fact_counts=expected_fact_counts,
        orphan_counts=orphan_counts,
        date_dimension_contiguous=date_dimension_contiguous,
        base_gmv=_money_text(base_gmv),
        region_dws_gmv=_money_text(region_gmv),
        category_dws_gmv=_money_text(category_gmv),
        valid_order_count=valid_order_count,
        region_dws_order_count=region_order_count,
        category_order_count_sum=category_order_count_sum,
        naive_payment_item_join_gmv=_money_text(naive_join_gmv),
        join_inflation_detected=naive_join_gmv != base_gmv,
        synthetic_non_null_count=synthetic_non_null_count,
    )


def _orphan_counts(connection: Connection, tables: dict[str, Table]) -> dict[str, int]:
    counts = {}
    for label, child_name, child_key, parent_name, parent_key in LOGICAL_FOREIGN_KEYS:
        child = tables[child_name]
        parent = tables[parent_name]
        counts[label] = int(
            connection.execute(
                select(func.count())
                .select_from(
                    child.outerjoin(parent, child.c[child_key] == parent.c[parent_key])
                )
                .where(parent.c[parent_key].is_(None))
            ).scalar_one()
        )
    return counts


def _synthetic_non_null_count(connection: Connection, tables: dict[str, Table]) -> int:
    region = tables["dws_sales_region_daily"]
    category = tables["dws_sales_category_daily"]
    region_columns = (
        region.c.visitors,
        region.c.promoted_sku_count,
        region.c.active_sku_count,
        region.c.available_sku_count,
        region.c.required_sku_count,
        region.c.synthetic_version,
    )
    category_columns = (
        category.c.category_visitors,
        category.c.promoted_sku_count,
        category.c.active_sku_count,
        category.c.available_sku_count,
        category.c.required_sku_count,
        category.c.synthetic_version,
    )
    region_count = connection.execute(
        select(func.count()).select_from(region).where(or_(*(col.is_not(None) for col in region_columns)))
    ).scalar_one()
    category_count = connection.execute(
        select(func.count())
        .select_from(category)
        .where(or_(*(col.is_not(None) for col in category_columns)))
    ).scalar_one()
    return int(region_count) + int(category_count)


def _dws_grains_unique(connection: Connection, tables: dict[str, Table]) -> bool:
    region = tables["dws_sales_region_daily"]
    category = tables["dws_sales_category_daily"]
    region_duplicates = connection.execute(
        select(func.count())
        .select_from(
            select(literal(1))
            .select_from(region)
            .group_by(region.c.date_id, region.c.region_id)
            .having(func.count() > 1)
            .subquery()
        )
    ).scalar_one()
    category_duplicates = connection.execute(
        select(func.count())
        .select_from(
            select(literal(1))
            .select_from(category)
            .group_by(category.c.date_id, category.c.region_id, category.c.category_id)
            .having(func.count() > 1)
            .subquery()
        )
    ).scalar_one()
    return int(region_duplicates) == 0 and int(category_duplicates) == 0


def _dws_versions_match(
    connection: Connection,
    tables: dict[str, Table],
    dataset_version: str,
) -> bool:
    for name in ("dws_sales_region_daily", "dws_sales_category_daily"):
        table = tables[name]
        mismatches = connection.execute(
            select(func.count())
            .select_from(table)
            .where(table.c.dataset_version != dataset_version)
        ).scalar_one()
        if int(mismatches):
            return False
    return True


def _order_row(row: RowMapping) -> dict[str, Any]:
    purchase_timestamp = _parse_datetime(row.order_purchase_timestamp)
    return {
        "order_id": str(row.order_id),
        "customer_id": str(row.customer_id),
        "status": str(row.order_status),
        "purchase_timestamp": purchase_timestamp,
        "purchase_date": purchase_timestamp.date(),
        "date_id": _date_id(purchase_timestamp.date()),
        "approved_at": _optional_datetime(row.order_approved_at),
        "delivered_carrier_at": _optional_datetime(row.order_delivered_carrier_date),
        "delivered_customer_at": _optional_datetime(row.order_delivered_customer_date),
        "estimated_delivery_date": _parse_datetime(row.order_estimated_delivery_date).date(),
    }


def _delivery_row(row: RowMapping) -> dict[str, Any]:
    estimated = _parse_datetime(row.order_estimated_delivery_date).date()
    delivered_at = _optional_datetime(row.order_delivered_customer_date)
    delivered = delivered_at.date() if delivered_at else None
    return {
        "order_id": str(row.order_id),
        "estimated_date": estimated,
        "delivered_date": delivered,
        "delay_days": (delivered - estimated).days if delivered else None,
    }


def _insert_chunks(
    connection: Connection,
    table: Table,
    rows: Iterable[dict[str, Any]],
    chunk_size: int,
) -> None:
    chunk: list[dict[str, Any]] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= chunk_size:
            connection.execute(insert(table), chunk)
            chunk = []
    if chunk:
        connection.execute(insert(table), chunk)


def _count(connection: Connection, table: Table) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def _date_id(value: date) -> int:
    return value.year * 10_000 + value.month * 100 + value.day


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if not value:
        raise DataFoundationError("Required source datetime is blank")
    return datetime.fromisoformat(str(value))


def _optional_datetime(value: object) -> datetime | None:
    if not value:
        return None
    return _parse_datetime(value)


def _parse_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(Decimal(str(value)))


def _required_int(value: object) -> int:
    parsed = _parse_int(value)
    if parsed is None:
        raise DataFoundationError("Required source integer is blank")
    return parsed


def _required_decimal(value: object) -> Decimal:
    if value in (None, ""):
        raise DataFoundationError("Required source amount is blank")
    return _money(Decimal(str(value)))


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _money_text(value: Decimal) -> str:
    return format(value, ".2f")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
