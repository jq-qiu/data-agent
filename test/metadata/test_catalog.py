from dataclasses import replace
from pathlib import Path

import pytest

from app.metadata.catalog import MetadataValidationError, load_catalog, validate_catalog
from app.metadata.evaluation import load_golden_cases
from app.metadata.retrieval import metadata_documents, value_documents
from app.metadata.warehouse import validate_warehouse_schema

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "conf" / "meta_config.yaml"
GOLDEN = ROOT / "data" / "evaluation" / "metadata_golden_v1.json"


def test_catalog_covers_accepted_olist_schema_and_metric_invariants() -> None:
    catalog = load_catalog(CONFIG)
    tables = catalog.table_map
    metrics = {metric.metric_id: metric for metric in catalog.metrics}

    assert catalog.version == "metadata-v1"
    assert len(tables) == 15
    assert len(catalog.column_ids) == 103
    assert len(catalog.relationships) == 21
    assert metrics["gmv"].formula == "SUM(fact_order_item.price)"
    assert metrics["gmv"].status_filters == {
        "exclude:fact_order.status": ("canceled", "unavailable")
    }
    assert "fact_order_item.freight_value" not in metrics["gmv"].relevant_columns
    assert "dws_sales_region_daily.order_count" in metrics["aov"].relevant_columns
    assert "禁止跨品类" in tables["dws_sales_category_daily"].description
    assert tables["dim_region"].grain == "one row per Brazilian federative unit"


def test_catalog_contains_no_stale_domestic_demo_schema() -> None:
    content = CONFIG.read_text(encoding="utf-8")

    for stale_name in ("province", "region_name", "customer_name", "member_level", "brand"):
        assert stale_name not in content
    assert "巴西州" in content


def test_metric_invariant_rejects_freight_in_gmv() -> None:
    catalog = load_catalog(CONFIG)
    metrics = list(catalog.metrics)
    metrics[0] = replace(
        metrics[0],
        relevant_columns=(*metrics[0].relevant_columns, "fact_order_item.freight_value"),
    )

    with pytest.raises(MetadataValidationError, match="freight_value"):
        validate_catalog(replace(catalog, metrics=tuple(metrics)))


def test_warehouse_validation_rejects_missing_configured_column() -> None:
    catalog = load_catalog(CONFIG)
    schema = {
        table.table_name: {column.name: "varchar(32)" for column in table.columns}
        for table in catalog.tables
    }
    del schema["fact_order_item"]["price"]

    with pytest.raises(MetadataValidationError, match="price"):
        validate_warehouse_schema(catalog, schema)


def test_metadata_documents_are_unique_and_cover_every_object() -> None:
    catalog = load_catalog(CONFIG)
    documents = metadata_documents(catalog)
    ids = {(item["object_type"], item["object_id"]) for item in documents}

    assert len(ids) == len(documents)
    assert len(documents) == 15 + 103 + 9 + 21
    assert ("table", "dim_region") in ids
    assert ("column", "fact_order_item.price") in ids
    assert ("metric", "gmv") in ids
    assert ("relationship", "payment_to_order") in ids


def test_value_aliases_map_to_real_canonical_values() -> None:
    catalog = load_catalog(CONFIG)
    values = {
        "dim_region.state_code": ["SP", "RJ", "MG", "RS", "PR", "BA"],
        "dim_category.category_id": [
            "cama_mesa_banho",
            "beleza_saude",
            "esporte_lazer",
            "moveis_decoracao",
            "informatica_acessorios",
        ],
        "dim_category.category_name_pt": [],
        "dim_category.category_name_en": [],
        "fact_order.status": [
            "approved",
            "canceled",
            "created",
            "delivered",
            "invoiced",
            "processing",
            "shipped",
            "unavailable",
        ],
        "fact_payment.payment_type": [
            "boleto",
            "credit_card",
            "debit_card",
            "not_defined",
            "voucher",
        ],
    }

    documents = value_documents(catalog, values)
    sao_paulo = next(
        item
        for item in documents
        if item["column_id"] == "dim_region.state_code" and item["canonical_value"] == "SP"
    )

    assert "圣保罗州" in sao_paulo["aliases"]
    assert sao_paulo["canonical_value"] == "SP"


def test_golden_dataset_is_fixed_and_covers_gate_two_categories() -> None:
    cases = load_golden_cases(GOLDEN)

    assert len(cases) == 12
    assert len({case.case_id for case in cases}) == 12
    assert any(case.expected_metric_ids for case in cases)
    assert any(case.expected_join_relations for case in cases)
    assert any(case.expected_values for case in cases)
    assert any(case.required_grain_warning for case in cases)
