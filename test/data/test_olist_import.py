import csv
import hashlib
import json
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import MetaData, Table, create_engine, func, select

from app.data_import.olist import (
    OlistImporter,
    OlistManifest,
    OlistValidationError,
    validate_dataset,
)

FILE_DEFINITIONS = (
    ("olist_customers_dataset.csv", "ods_olist_customers", ("customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"), ("customer_id",)),
    ("olist_geolocation_dataset.csv", "ods_olist_geolocation", ("geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"), ()),
    ("olist_order_items_dataset.csv", "ods_olist_order_items", ("order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"), ("order_id", "order_item_id")),
    ("olist_order_payments_dataset.csv", "ods_olist_order_payments", ("order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"), ("order_id", "payment_sequential")),
    ("olist_order_reviews_dataset.csv", "ods_olist_order_reviews", ("review_id", "order_id", "review_score", "review_comment_title", "review_comment_message", "review_creation_date", "review_answer_timestamp"), ("review_id", "order_id")),
    ("olist_orders_dataset.csv", "ods_olist_orders", ("order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"), ("order_id",)),
    ("olist_products_dataset.csv", "ods_olist_products", ("product_id", "product_category_name", "product_name_lenght", "product_description_lenght", "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"), ("product_id",)),
    ("olist_sellers_dataset.csv", "ods_olist_sellers", ("seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"), ("seller_id",)),
    ("product_category_name_translation.csv", "ods_olist_product_category_name_translation", ("product_category_name", "product_category_name_english"), ("product_category_name",)),
)


@pytest.fixture
def source_dir() -> Iterator[Path]:
    local_temp_root = Path(".tmp").resolve()
    local_temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="data001-", dir=local_temp_root) as directory:
        yield Path(directory)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture_dataset(root: Path, duplicate_customer_key: bool = False) -> Path:
    files = []
    for filename, table_name, columns, key_columns in FILE_DEFINITIONS:
        path = root / filename
        first_row = [f"{column}_value" for column in columns]
        if "zip_code_prefix" in " ".join(columns):
            first_row = ["00123" if "zip_code_prefix" in column else value for column, value in zip(columns, first_row)]
        rows = [first_row]
        if duplicate_customer_key and filename == "olist_customers_dataset.csv":
            rows.append(first_row)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(rows)
        files.append(
            {
                "filename": filename,
                "table_name": table_name,
                "columns": list(columns),
                "key_columns": list(key_columns),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "row_count": len(rows),
            }
        )

    archive_path = root / "olist_fixture.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, *_ in FILE_DEFINITIONS:
            archive.write(root / filename, filename)
    manifest = {
        "dataset_name": "olist_fixture",
        "dataset_version": "test-v1",
        "source_url": "https://example.invalid/olist-fixture",
        "license": "test-only",
        "archive": {
            "filename": archive_path.name,
            "size_bytes": archive_path.stat().st_size,
            "sha256": _sha256(archive_path),
        },
        "files": files,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_repository_manifest_declares_official_nine_files() -> None:
    manifest = OlistManifest.from_path(Path("data/manifests/olist_v2.json"))

    assert manifest.dataset_version == "2"
    assert len(manifest.files) == 9
    assert sum(item.row_count for item in manifest.files) == 1_550_922


def test_validate_dataset_checks_file_identity_header_and_keys(source_dir: Path) -> None:
    manifest = OlistManifest.from_path(_write_fixture_dataset(source_dir))

    validations = validate_dataset(source_dir, manifest)

    assert len(validations) == 9
    assert all(item.duplicate_key_count == 0 for item in validations)
    assert all(item.blank_key_count == 0 for item in validations)


def test_validate_dataset_rejects_missing_file(source_dir: Path) -> None:
    manifest = OlistManifest.from_path(_write_fixture_dataset(source_dir))
    (source_dir / "olist_orders_dataset.csv").unlink()

    with pytest.raises(OlistValidationError, match="CSV file set mismatch"):
        validate_dataset(source_dir, manifest)


def test_validate_dataset_rejects_duplicate_declared_key(source_dir: Path) -> None:
    manifest = OlistManifest.from_path(
        _write_fixture_dataset(source_dir, duplicate_customer_key=True)
    )

    with pytest.raises(OlistValidationError, match="Duplicate declared key"):
        validate_dataset(source_dir, manifest)


def test_import_preserves_source_columns_and_is_idempotent(source_dir: Path) -> None:
    manifest = OlistManifest.from_path(_write_fixture_dataset(source_dir))
    importer = OlistImporter(manifest, chunk_size=1)
    engine = create_engine("sqlite+pysqlite:///:memory:")

    with engine.connect() as connection:
        first = importer.import_into(connection, source_dir)
        second = importer.import_into(connection, source_dir)

        metadata = MetaData()
        customers = Table("ods_olist_customers", metadata, autoload_with=connection)
        count = connection.execute(select(func.count()).select_from(customers)).scalar_one()
        zip_code = connection.execute(
            select(customers.c.customer_zip_code_prefix)
        ).scalar_one()

    assert first.status == "success"
    assert first.reused is False
    assert second.reused is True
    assert second.batch_id == first.batch_id
    assert count == 1
    assert zip_code == "00123"
    assert set(customers.c.keys()) == set(manifest.files[0].columns)
