"""把版本化 Catalog 投影为元数据库、向量库和值索引的存储记录。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Column, MetaData, String, Table, Text, delete, insert
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.ext.asyncio import AsyncEngine

from app.metadata.catalog import MetadataCatalog


def registry_tables() -> tuple[MetaData, dict[str, Table]]:
    metadata = MetaData()
    tables: dict[str, Table] = {}
    tables["table"] = Table(
        "meta_v1_table",
        metadata,
        Column("table_name", String(128), primary_key=True),
        Column("role", String(32), nullable=False),
        Column("grain", String(255), nullable=False),
        Column("description", Text, nullable=False),
        Column("time_column", String(128), nullable=True),
        Column("primary_key", JSON, nullable=False),
        Column("allowed_join_relations", JSON, nullable=False),
        Column("aliases", JSON, nullable=False),
        Column("version", String(32), nullable=False),
    )
    tables["column"] = Table(
        "meta_v1_column",
        metadata,
        Column("column_id", String(257), primary_key=True),
        Column("table_name", String(128), nullable=False),
        Column("column_name", String(128), nullable=False),
        Column("data_type", String(128), nullable=False),
        Column("role", String(32), nullable=False),
        Column("description", Text, nullable=False),
        Column("aliases", JSON, nullable=False),
        Column("examples", JSON, nullable=False),
        Column("is_sensitive", Boolean, nullable=False),
        Column("value_index_enabled", Boolean, nullable=False),
        Column("version", String(32), nullable=False),
    )
    tables["metric"] = Table(
        "meta_v1_metric",
        metadata,
        Column("metric_id", String(128), primary_key=True),
        Column("display_name", String(128), nullable=False),
        Column("description", Text, nullable=False),
        Column("formula", Text, nullable=False),
        Column("base_grain", String(255), nullable=False),
        Column("time_column", String(257), nullable=False),
        Column("status_filters", JSON, nullable=False),
        Column("allowed_dimensions", JSON, nullable=False),
        Column("component_metrics", JSON, nullable=False),
        Column("relevant_columns", JSON, nullable=False),
        Column("aliases", JSON, nullable=False),
        Column("version", String(32), nullable=False),
    )
    tables["relationship"] = Table(
        "meta_v1_relationship",
        metadata,
        Column("relation_id", String(128), primary_key=True),
        Column("left_table", String(128), nullable=False),
        Column("left_column", String(128), nullable=False),
        Column("right_table", String(128), nullable=False),
        Column("right_column", String(128), nullable=False),
        Column("cardinality", String(32), nullable=False),
        Column("allowed", Boolean, nullable=False),
        Column("grain_warning", Text, nullable=False),
        Column("version", String(32), nullable=False),
    )
    return metadata, tables


async def sync_mysql_registry(
    engine: AsyncEngine,
    catalog: MetadataCatalog,
    warehouse_schema: dict[str, dict[str, str]],
    examples: dict[str, list[Any]],
) -> dict[str, int]:
    metadata, tables = registry_tables()
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
        for table in tables.values():
            await connection.execute(delete(table))

        table_rows = [
            {
                "table_name": item.table_name,
                "role": item.role,
                "grain": item.grain,
                "description": item.description,
                "time_column": item.time_column,
                "primary_key": list(item.primary_key),
                "allowed_join_relations": list(item.allowed_join_relations),
                "aliases": list(item.aliases),
                "version": catalog.version,
            }
            for item in catalog.tables
        ]
        column_rows = [
            {
                "column_id": f"{table.table_name}.{column.name}",
                "table_name": table.table_name,
                "column_name": column.name,
                "data_type": warehouse_schema[table.table_name][column.name],
                "role": column.role,
                "description": column.description,
                "aliases": list(column.aliases),
                "examples": examples.get(f"{table.table_name}.{column.name}", []),
                "is_sensitive": column.is_sensitive,
                "value_index_enabled": column.value_index_enabled,
                "version": catalog.version,
            }
            for table in catalog.tables
            for column in table.columns
        ]
        metric_rows = [
            {
                "metric_id": item.metric_id,
                "display_name": item.display_name,
                "description": item.description,
                "formula": item.formula,
                "base_grain": item.base_grain,
                "time_column": item.time_column,
                "status_filters": {
                    key: list(values) for key, values in item.status_filters.items()
                },
                "allowed_dimensions": list(item.allowed_dimensions),
                "component_metrics": list(item.component_metrics),
                "relevant_columns": list(item.relevant_columns),
                "aliases": list(item.aliases),
                "version": item.version,
            }
            for item in catalog.metrics
        ]
        relationship_rows = [
            {
                "relation_id": item.relation_id,
                "left_table": item.left_table,
                "left_column": item.left_column,
                "right_table": item.right_table,
                "right_column": item.right_column,
                "cardinality": item.cardinality,
                "allowed": item.allowed,
                "grain_warning": item.grain_warning,
                "version": catalog.version,
            }
            for item in catalog.relationships
        ]
        for table, rows in (
            (tables["table"], table_rows),
            (tables["column"], column_rows),
            (tables["metric"], metric_rows),
            (tables["relationship"], relationship_rows),
        ):
            if rows:
                await connection.execute(insert(table), rows)
    return {
        "tables": len(table_rows),
        "columns": len(column_rows),
        "metrics": len(metric_rows),
        "relationships": len(relationship_rows),
    }
