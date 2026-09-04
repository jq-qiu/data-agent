from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import dw_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.conf.app_config import app_config
from app.metadata.catalog import MetadataCatalog, load_catalog
from app.metadata.evaluation import evaluate_metadata, load_golden_cases
from app.metadata.retrieval import rebuild_value_index, rebuild_vector_index
from app.metadata.storage import sync_mysql_registry
from app.metadata.warehouse import inspect_warehouse, validate_warehouse_schema

ROOT = Path(__file__).parents[2]
DEFAULT_CONFIG = ROOT / "conf" / "meta_config.yaml"
DEFAULT_GOLDEN = ROOT / "data" / "evaluation" / "metadata_golden_v1.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "META-001_metadata_evaluation.json"


async def _collect_warehouse_values(
    catalog: MetadataCatalog,
    session: Any,
) -> tuple[dict[str, list[Any]], dict[str, list[str]]]:
    examples: dict[str, list[Any]] = {}
    values: dict[str, list[str]] = {}
    for table in catalog.tables:
        for column in table.columns:
            column_id = f"{table.table_name}.{column.name}"
            result = await session.execute(
                text(f"SELECT DISTINCT `{column.name}` FROM `{table.table_name}` LIMIT 10")
            )
            examples[column_id] = [
                str(value) for value in result.scalars().all() if value is not None
            ]
            if column.value_index_enabled:
                result = await session.execute(
                    text(f"SELECT DISTINCT `{column.name}` FROM `{table.table_name}` LIMIT 100000")
                )
                values[column_id] = [
                    str(value) for value in result.scalars().all() if value is not None
                ]
    return examples, values


def _catalog_digest(config_path: Path, golden_path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(config_path.read_bytes())
    digest.update(golden_path.read_bytes())
    return digest.hexdigest()


async def build(
    config_path: Path, golden_path: Path, report_path: Path, evaluate: bool
) -> dict[str, Any]:
    if app_config.db_dw.database != "data_agent_v1_dw":
        raise RuntimeError("META-001 may only read the isolated data_agent_v1_dw database")
    catalog = load_catalog(config_path)
    dw_mysql_client_manager.init()
    meta_mysql_client_manager.init()
    qdrant_client_manager.init()
    es_client_manager.init()
    embedding_client_manager.init()
    assert dw_mysql_client_manager.engine is not None
    assert meta_mysql_client_manager.engine is not None
    assert qdrant_client_manager.client is not None
    assert es_client_manager.client is not None
    assert embedding_client_manager.client is not None
    qdrant = qdrant_client_manager.client
    elasticsearch = es_client_manager.client
    embeddings = embedding_client_manager.client
    dw_session_factory = async_sessionmaker(
        dw_mysql_client_manager.engine,
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        async with dw_session_factory() as dw_session:
            warehouse_schema = await inspect_warehouse(dw_session, catalog)
            validate_warehouse_schema(catalog, warehouse_schema)
            examples, values = await _collect_warehouse_values(catalog, dw_session)

        mysql_counts = await sync_mysql_registry(
            meta_mysql_client_manager.engine,
            catalog,
            warehouse_schema,
            examples,
        )
        vector_count = await rebuild_vector_index(
            qdrant,
            embeddings,
            catalog,
            app_config.qdrant.embedding_size,
        )
        value_count = await rebuild_value_index(elasticsearch, catalog, values)
        result: dict[str, Any] = {
            "metadata_version": catalog.version,
            "catalog_sha256": _catalog_digest(config_path, golden_path),
            "warehouse_schema_valid": True,
            "mysql_counts": mysql_counts,
            "qdrant_point_count": vector_count,
            "elasticsearch_value_count": value_count,
        }
        if evaluate:
            cases = load_golden_cases(golden_path)
            evaluation = await evaluate_metadata(
                catalog,
                cases,
                qdrant,
                elasticsearch,
                embeddings,
            )
            result["evaluation"] = evaluation
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            if not evaluation["gate_2_passed"]:
                raise RuntimeError("META-001 Gate 2 evaluation did not meet frozen thresholds")
        return result
    finally:
        await dw_mysql_client_manager.close()
        await meta_mysql_client_manager.close()
        await qdrant_client_manager.close()
        await es_client_manager.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the isolated Olist V1 metadata registry")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(build(args.config, args.golden, args.report, args.evaluate))
    summary = {
        "metadata_version": result["metadata_version"],
        "warehouse_schema_valid": result["warehouse_schema_valid"],
        "mysql_counts": result["mysql_counts"],
        "qdrant_point_count": result["qdrant_point_count"],
        "elasticsearch_value_count": result["elasticsearch_value_count"],
        "gate_2_passed": result.get("evaluation", {}).get("gate_2_passed"),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
