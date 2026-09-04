from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from app.clients.mysql_client_manager import dw_mysql_client_manager
from app.data_import.olist import OlistImporter, OlistManifest

PROJECT_ROOT = Path(__file__).parents[2]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import the verified Olist V2 source into ODS")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "olist" / "v2",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "data" / "manifests" / "olist_v2.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "data" / "reports" / "DATA-001_olist_import.json",
    )
    parser.add_argument("--chunk-size", type=int, default=2_000)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict[str, object]:
    manifest = OlistManifest.from_path(args.manifest)
    importer = OlistImporter(manifest, chunk_size=args.chunk_size)
    dw_mysql_client_manager.init()
    if dw_mysql_client_manager.engine is None:
        raise RuntimeError("DW database engine was not initialized")
    try:
        async with dw_mysql_client_manager.engine.connect() as async_connection:
            result = await async_connection.run_sync(
                lambda connection: importer.import_into(connection, args.source_dir)
            )
    finally:
        await dw_mysql_client_manager.close()
    return asdict(result)


def main() -> None:
    args = _parse_args()
    try:
        report = asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001 - CLI must persist a sanitized failure report.
        report = {"status": "failed", "error_type": type(exc).__name__}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False))
        raise SystemExit(1) from None

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
