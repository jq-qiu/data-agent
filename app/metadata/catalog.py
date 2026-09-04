from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class MetadataValidationError(ValueError):
    """Raised when configured metadata is inconsistent with the warehouse."""


@dataclass(frozen=True)
class ColumnDefinition:
    name: str
    role: str
    description: str
    aliases: tuple[str, ...] = ()
    is_sensitive: bool = False
    value_index_enabled: bool = False
    value_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class TableDefinition:
    table_name: str
    role: str
    grain: str
    description: str
    time_column: str | None
    primary_key: tuple[str, ...]
    allowed_join_relations: tuple[str, ...]
    aliases: tuple[str, ...]
    columns: tuple[ColumnDefinition, ...]


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    display_name: str
    description: str
    formula: str
    base_grain: str
    time_column: str
    status_filters: dict[str, tuple[str, ...]]
    allowed_dimensions: tuple[str, ...]
    component_metrics: tuple[str, ...]
    relevant_columns: tuple[str, ...]
    aliases: tuple[str, ...]
    version: str


@dataclass(frozen=True)
class RelationshipDefinition:
    relation_id: str
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    cardinality: str
    allowed: bool
    grain_warning: str


@dataclass(frozen=True)
class MetadataCatalog:
    version: str
    tables: tuple[TableDefinition, ...]
    metrics: tuple[MetricDefinition, ...]
    relationships: tuple[RelationshipDefinition, ...]

    @property
    def table_map(self) -> dict[str, TableDefinition]:
        return {table.table_name: table for table in self.tables}

    @property
    def column_ids(self) -> set[str]:
        return {
            f"{table.table_name}.{column.name}" for table in self.tables for column in table.columns
        }


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or []))


def load_catalog(path: Path) -> MetadataCatalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MetadataValidationError("metadata config must be a mapping")

    version = str(raw.get("version", "")).strip()
    if not version:
        raise MetadataValidationError("metadata version is required")

    tables: list[TableDefinition] = []
    for table_raw in raw.get("tables", []):
        columns: list[ColumnDefinition] = []
        for column_raw in table_raw.get("columns", []):
            aliases = {
                str(canonical): _strings(values)
                for canonical, values in (column_raw.get("value_aliases") or {}).items()
            }
            columns.append(
                ColumnDefinition(
                    name=str(column_raw["name"]),
                    role=str(column_raw["role"]),
                    description=str(column_raw["description"]),
                    aliases=_strings(column_raw.get("aliases")),
                    is_sensitive=bool(column_raw.get("is_sensitive", False)),
                    value_index_enabled=bool(column_raw.get("value_index_enabled", False)),
                    value_aliases=aliases,
                )
            )
        tables.append(
            TableDefinition(
                table_name=str(table_raw["table_name"]),
                role=str(table_raw["role"]),
                grain=str(table_raw["grain"]),
                description=str(table_raw["description"]),
                time_column=table_raw.get("time_column"),
                primary_key=_strings(table_raw.get("primary_key")),
                allowed_join_relations=_strings(table_raw.get("allowed_join_relations")),
                aliases=_strings(table_raw.get("aliases")),
                columns=tuple(columns),
            )
        )

    metrics = tuple(
        MetricDefinition(
            metric_id=str(item["metric_id"]),
            display_name=str(item["display_name"]),
            description=str(item["description"]),
            formula=str(item["formula"]),
            base_grain=str(item["base_grain"]),
            time_column=str(item["time_column"]),
            status_filters={
                str(key): _strings(values)
                for key, values in (item.get("status_filters") or {}).items()
            },
            allowed_dimensions=_strings(item.get("allowed_dimensions")),
            component_metrics=_strings(item.get("component_metrics")),
            relevant_columns=_strings(item.get("relevant_columns")),
            aliases=_strings(item.get("aliases")),
            version=str(item.get("version", version)),
        )
        for item in raw.get("metrics", [])
    )
    relationships = tuple(
        RelationshipDefinition(
            relation_id=str(item["relation_id"]),
            left_table=str(item["left_table"]),
            left_column=str(item["left_column"]),
            right_table=str(item["right_table"]),
            right_column=str(item["right_column"]),
            cardinality=str(item["cardinality"]),
            allowed=bool(item["allowed"]),
            grain_warning=str(item.get("grain_warning", "")),
        )
        for item in raw.get("relationships", [])
    )
    catalog = MetadataCatalog(version, tuple(tables), metrics, relationships)
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: MetadataCatalog) -> None:
    table_names = [table.table_name for table in catalog.tables]
    if len(table_names) != len(set(table_names)):
        raise MetadataValidationError("duplicate table metadata")
    relation_ids = [relation.relation_id for relation in catalog.relationships]
    if len(relation_ids) != len(set(relation_ids)):
        raise MetadataValidationError("duplicate relationship metadata")
    metric_ids = [metric.metric_id for metric in catalog.metrics]
    if len(metric_ids) != len(set(metric_ids)):
        raise MetadataValidationError("duplicate metric metadata")

    table_map = catalog.table_map
    column_ids = catalog.column_ids
    relation_id_set = set(relation_ids)
    for table in catalog.tables:
        column_names = [column.name for column in table.columns]
        if len(column_names) != len(set(column_names)):
            raise MetadataValidationError(f"duplicate columns in {table.table_name}")
        missing_keys = set(table.primary_key) - set(column_names)
        if missing_keys:
            raise MetadataValidationError(
                f"unknown primary key columns in {table.table_name}: {sorted(missing_keys)}"
            )
        if table.time_column and table.time_column not in column_names:
            raise MetadataValidationError(f"unknown time column in {table.table_name}")
        missing_relations = set(table.allowed_join_relations) - relation_id_set
        if missing_relations:
            raise MetadataValidationError(
                f"unknown relations in {table.table_name}: {sorted(missing_relations)}"
            )

    for relationship in catalog.relationships:
        left_id = f"{relationship.left_table}.{relationship.left_column}"
        right_id = f"{relationship.right_table}.{relationship.right_column}"
        if relationship.left_table not in table_map or relationship.right_table not in table_map:
            raise MetadataValidationError(f"unknown relationship table: {relationship.relation_id}")
        if left_id not in column_ids or right_id not in column_ids:
            raise MetadataValidationError(
                f"unknown relationship column: {relationship.relation_id}"
            )
        if (
            relationship.cardinality in {"one_to_many", "many_to_many"}
            and not relationship.grain_warning
        ):
            raise MetadataValidationError(f"missing grain warning for {relationship.relation_id}")

    for metric in catalog.metrics:
        missing = set(metric.relevant_columns) - column_ids
        if missing:
            raise MetadataValidationError(
                f"unknown metric columns for {metric.metric_id}: {sorted(missing)}"
            )
        if metric.time_column not in column_ids:
            raise MetadataValidationError(f"unknown time column for metric {metric.metric_id}")

    _validate_metric_invariants(catalog)


def _validate_metric_invariants(catalog: MetadataCatalog) -> None:
    metrics = {metric.metric_id: metric for metric in catalog.metrics}
    gmv = metrics.get("gmv")
    if gmv is None or gmv.formula != "SUM(fact_order_item.price)":
        raise MetadataValidationError("GMV must equal SUM(fact_order_item.price)")
    if "fact_order_item.freight_value" in gmv.relevant_columns:
        raise MetadataValidationError("freight_value must not be part of V1 GMV")
    aov = metrics.get("aov")
    expected_aov = (
        "SUM(dws_sales_region_daily.gmv) / NULLIF(SUM(dws_sales_region_daily.order_count), 0)"
    )
    if aov is None or aov.formula != expected_aov:
        raise MetadataValidationError("AOV must use region DWS GMV and overall order count")
