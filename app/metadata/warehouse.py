from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.metadata.catalog import MetadataCatalog, MetadataValidationError


async def inspect_warehouse(
    session: AsyncSession, catalog: MetadataCatalog
) -> dict[str, dict[str, str]]:
    schema: dict[str, dict[str, str]] = {}
    for table in catalog.tables:
        result = await session.execute(text(f"SHOW COLUMNS FROM `{table.table_name}`"))
        schema[table.table_name] = {str(row.Field): str(row.Type) for row in result.fetchall()}
    return schema


def validate_warehouse_schema(
    catalog: MetadataCatalog,
    schema: Mapping[str, Mapping[str, str]],
) -> None:
    for table in catalog.tables:
        actual_columns = schema.get(table.table_name)
        if actual_columns is None:
            raise MetadataValidationError(f"warehouse table is missing: {table.table_name}")
        configured = {column.name for column in table.columns}
        missing = configured - set(actual_columns)
        if missing:
            raise MetadataValidationError(
                f"warehouse columns are missing in {table.table_name}: {sorted(missing)}"
            )
