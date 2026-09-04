from __future__ import annotations

import csv
import hashlib
import json
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    and_,
    func,
    select,
    update,
)
from sqlalchemy.engine import Connection

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SUCCESS = "success"
_RUNNING = "running"
_FAILED = "failed"


class OlistValidationError(ValueError):
    """Raised when local source files do not match the versioned manifest."""


class OlistImportError(RuntimeError):
    """Raised when validated source data cannot be safely imported."""


@dataclass(frozen=True)
class OlistFileSpec:
    filename: str
    table_name: str
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    size_bytes: int
    sha256: str
    row_count: int


@dataclass(frozen=True)
class OlistManifest:
    dataset_name: str
    dataset_version: str
    source_url: str
    license: str
    archive_filename: str
    archive_size_bytes: int
    archive_sha256: str
    files: tuple[OlistFileSpec, ...]

    @classmethod
    def from_path(cls, path: Path) -> OlistManifest:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        archive = raw["archive"]
        files = tuple(
            OlistFileSpec(
                filename=item["filename"],
                table_name=item["table_name"],
                columns=tuple(item["columns"]),
                key_columns=tuple(item["key_columns"]),
                size_bytes=item["size_bytes"],
                sha256=item["sha256"],
                row_count=item["row_count"],
            )
            for item in raw["files"]
        )
        manifest = cls(
            dataset_name=raw["dataset_name"],
            dataset_version=raw["dataset_version"],
            source_url=raw["source_url"],
            license=raw["license"],
            archive_filename=archive["filename"],
            archive_size_bytes=archive["size_bytes"],
            archive_sha256=archive["sha256"],
            files=files,
        )
        manifest.validate_structure()
        return manifest

    def validate_structure(self) -> None:
        if len(self.files) != 9:
            raise OlistValidationError("Olist manifest must declare exactly 9 CSV files")
        filenames = {item.filename for item in self.files}
        table_names = {item.table_name for item in self.files}
        if len(filenames) != 9 or len(table_names) != 9:
            raise OlistValidationError("Olist filenames and table names must be unique")
        for item in self.files:
            if Path(item.filename).name != item.filename or not item.filename.endswith(".csv"):
                raise OlistValidationError(f"Unsafe source filename: {item.filename}")
            if not _SAFE_IDENTIFIER.fullmatch(item.table_name):
                raise OlistValidationError(f"Unsafe ODS table name: {item.table_name}")
            if not item.columns or len(set(item.columns)) != len(item.columns):
                raise OlistValidationError(f"Invalid columns for {item.filename}")
            if any(not _SAFE_IDENTIFIER.fullmatch(column) for column in item.columns):
                raise OlistValidationError(f"Unsafe column in {item.filename}")
            if not set(item.key_columns).issubset(item.columns):
                raise OlistValidationError(f"Unknown key column in {item.filename}")


@dataclass(frozen=True)
class OlistFileValidation:
    spec: OlistFileSpec
    duplicate_key_count: int
    blank_key_count: int


@dataclass(frozen=True)
class OlistImportFileResult:
    filename: str
    table_name: str
    source_row_count: int
    imported_row_count: int


@dataclass(frozen=True)
class OlistImportResult:
    batch_id: str
    status: str
    reused: bool
    files: tuple[OlistImportFileResult, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_dataset(
    source_dir: Path,
    manifest: OlistManifest,
) -> tuple[OlistFileValidation, ...]:
    archive_path = source_dir / manifest.archive_filename
    _validate_file_identity(
        archive_path,
        manifest.archive_size_bytes,
        manifest.archive_sha256,
    )

    actual_csv_files = {path.name for path in source_dir.glob("*.csv")}
    expected_csv_files = {item.filename for item in manifest.files}
    if actual_csv_files != expected_csv_files:
        missing = sorted(expected_csv_files - actual_csv_files)
        unexpected = sorted(actual_csv_files - expected_csv_files)
        raise OlistValidationError(
            f"CSV file set mismatch; missing={missing}, unexpected={unexpected}"
        )

    validations = []
    for spec in manifest.files:
        path = source_dir / spec.filename
        _validate_file_identity(path, spec.size_bytes, spec.sha256)
        validations.append(_validate_csv(path, spec))
    return tuple(validations)


def _validate_file_identity(path: Path, expected_size: int, expected_sha256: str) -> None:
    if not path.is_file():
        raise OlistValidationError(f"Missing source file: {path.name}")
    if path.stat().st_size != expected_size:
        raise OlistValidationError(f"File size mismatch: {path.name}")
    if sha256_file(path) != expected_sha256:
        raise OlistValidationError(f"SHA-256 mismatch: {path.name}")


def _validate_csv(path: Path, spec: OlistFileSpec) -> OlistFileValidation:
    row_count = 0
    duplicate_key_count = 0
    blank_key_count = 0
    seen_keys: set[tuple[str, ...]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != spec.columns:
            raise OlistValidationError(f"CSV header mismatch: {path.name}")
        for row in reader:
            if None in row:
                raise OlistValidationError(f"Malformed CSV row: {path.name}")
            row_count += 1
            if spec.key_columns:
                key = tuple(row[column] for column in spec.key_columns)
                if any(value == "" for value in key):
                    blank_key_count += 1
                if key in seen_keys:
                    duplicate_key_count += 1
                else:
                    seen_keys.add(key)

    if row_count != spec.row_count:
        raise OlistValidationError(f"CSV row count mismatch: {path.name}")
    if blank_key_count:
        raise OlistValidationError(f"Blank declared key in {path.name}")
    if duplicate_key_count:
        raise OlistValidationError(f"Duplicate declared key in {path.name}")
    return OlistFileValidation(
        spec=spec,
        duplicate_key_count=duplicate_key_count,
        blank_key_count=blank_key_count,
    )


def _build_tables(manifest: OlistManifest) -> tuple[MetaData, Table, Table, dict[str, Table]]:
    metadata = MetaData()
    batch_table = Table(
        "ods_olist_import_batch",
        metadata,
        Column("batch_id", String(36), primary_key=True),
        Column("dataset_name", String(128), nullable=False),
        Column("dataset_version", String(32), nullable=False),
        Column("archive_sha256", String(64), nullable=False),
        Column("source_url", Text, nullable=False),
        Column("license", String(64), nullable=False),
        Column("started_at", DateTime, nullable=False),
        Column("completed_at", DateTime, nullable=True),
        Column("status", String(16), nullable=False),
        Column("error_type", String(128), nullable=True),
    )
    file_table = Table(
        "ods_olist_import_file",
        metadata,
        Column("batch_id", String(36), primary_key=True),
        Column("source_file", String(128), primary_key=True),
        Column("ods_table", String(128), nullable=False),
        Column("file_size_bytes", BigInteger, nullable=False),
        Column("file_sha256", String(64), nullable=False),
        Column("source_row_count", BigInteger, nullable=False),
        Column("imported_row_count", BigInteger, nullable=False),
        Column("header_json", Text, nullable=False),
        Column("key_columns_json", Text, nullable=False),
        Column("duplicate_key_count", BigInteger, nullable=False),
        Column("blank_key_count", BigInteger, nullable=False),
        Column("status", String(16), nullable=False),
    )
    data_tables = {
        spec.filename: Table(
            spec.table_name,
            metadata,
            *(Column(column, Text, nullable=True) for column in spec.columns),
        )
        for spec in manifest.files
    }
    return metadata, batch_table, file_table, data_tables


class OlistImporter:
    def __init__(self, manifest: OlistManifest, chunk_size: int = 2_000):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self.manifest = manifest
        self.chunk_size = chunk_size

    def import_into(self, connection: Connection, source_dir: Path) -> OlistImportResult:
        validations = validate_dataset(source_dir, self.manifest)
        metadata, batch_table, file_table, data_tables = _build_tables(self.manifest)
        metadata.create_all(connection)
        connection.commit()

        with connection.begin():
            previous_batch_id = connection.execute(
                select(batch_table.c.batch_id).where(
                    and_(
                        batch_table.c.dataset_name == self.manifest.dataset_name,
                        batch_table.c.dataset_version == self.manifest.dataset_version,
                        batch_table.c.archive_sha256 == self.manifest.archive_sha256,
                        batch_table.c.status == _SUCCESS,
                    )
                )
            ).scalar_one_or_none()
            if previous_batch_id is not None:
                return self._load_existing_result(
                    connection,
                    file_table,
                    str(previous_batch_id),
                )
            nonempty_tables = [
                table.name
                for table in data_tables.values()
                if connection.execute(select(func.count()).select_from(table)).scalar_one() > 0
            ]

        batch_id = str(uuid.uuid4())
        started_at = _utc_now()
        if nonempty_tables:
            self._record_batch(
                connection,
                batch_table,
                batch_id,
                started_at,
                _FAILED,
                "ExistingOdsDataError",
            )
            raise OlistImportError(
                "ODS tables contain data from a different or unaudited dataset version"
            )

        self._record_batch(connection, batch_table, batch_id, started_at, _RUNNING, None)
        try:
            with connection.begin():
                results = tuple(
                    self._import_file(
                        connection,
                        source_dir,
                        validation,
                        file_table,
                        data_tables[validation.spec.filename],
                        batch_id,
                    )
                    for validation in validations
                )
                connection.execute(
                    update(batch_table)
                    .where(batch_table.c.batch_id == batch_id)
                    .values(
                        status=_SUCCESS,
                        completed_at=_utc_now(),
                        error_type=None,
                    )
                )
        except Exception as exc:
            if connection.in_transaction():
                connection.rollback()
            with connection.begin():
                connection.execute(
                    update(batch_table)
                    .where(batch_table.c.batch_id == batch_id)
                    .values(
                        status=_FAILED,
                        completed_at=_utc_now(),
                        error_type=type(exc).__name__[:128],
                    )
                )
            raise

        return OlistImportResult(
            batch_id=batch_id,
            status=_SUCCESS,
            reused=False,
            files=results,
        )

    def _record_batch(
        self,
        connection: Connection,
        batch_table: Table,
        batch_id: str,
        started_at: datetime,
        status: str,
        error_type: str | None,
    ) -> None:
        with connection.begin():
            connection.execute(
                batch_table.insert(),
                {
                    "batch_id": batch_id,
                    "dataset_name": self.manifest.dataset_name,
                    "dataset_version": self.manifest.dataset_version,
                    "archive_sha256": self.manifest.archive_sha256,
                    "source_url": self.manifest.source_url,
                    "license": self.manifest.license,
                    "started_at": started_at,
                    "completed_at": started_at if status == _FAILED else None,
                    "status": status,
                    "error_type": error_type,
                },
            )

    def _import_file(
        self,
        connection: Connection,
        source_dir: Path,
        validation: OlistFileValidation,
        file_table: Table,
        data_table: Table,
        batch_id: str,
    ) -> OlistImportFileResult:
        spec = validation.spec
        inserted_count = 0
        for rows in _read_chunks(source_dir / spec.filename, spec, self.chunk_size):
            connection.execute(data_table.insert(), rows)
            inserted_count += len(rows)
        database_count = connection.execute(
            select(func.count()).select_from(data_table)
        ).scalar_one()
        if inserted_count != spec.row_count or database_count != spec.row_count:
            raise OlistImportError(f"Imported row count mismatch: {spec.filename}")

        connection.execute(
            file_table.insert(),
            {
                "batch_id": batch_id,
                "source_file": spec.filename,
                "ods_table": spec.table_name,
                "file_size_bytes": spec.size_bytes,
                "file_sha256": spec.sha256,
                "source_row_count": spec.row_count,
                "imported_row_count": database_count,
                "header_json": json.dumps(spec.columns, ensure_ascii=False),
                "key_columns_json": json.dumps(spec.key_columns, ensure_ascii=False),
                "duplicate_key_count": validation.duplicate_key_count,
                "blank_key_count": validation.blank_key_count,
                "status": _SUCCESS,
            },
        )
        return OlistImportFileResult(
            filename=spec.filename,
            table_name=spec.table_name,
            source_row_count=spec.row_count,
            imported_row_count=database_count,
        )

    def _load_existing_result(
        self,
        connection: Connection,
        file_table: Table,
        batch_id: str,
    ) -> OlistImportResult:
        rows = connection.execute(
            select(
                file_table.c.source_file,
                file_table.c.ods_table,
                file_table.c.source_row_count,
                file_table.c.imported_row_count,
            )
            .where(file_table.c.batch_id == batch_id)
            .order_by(file_table.c.source_file)
        ).all()
        if len(rows) != len(self.manifest.files):
            raise OlistImportError("Successful batch has incomplete file audit records")
        return OlistImportResult(
            batch_id=batch_id,
            status=_SUCCESS,
            reused=True,
            files=tuple(
                OlistImportFileResult(
                    filename=str(row.source_file),
                    table_name=str(row.ods_table),
                    source_row_count=int(row.source_row_count),
                    imported_row_count=int(row.imported_row_count),
                )
                for row in rows
            ),
        )


def _read_chunks(
    path: Path,
    spec: OlistFileSpec,
    chunk_size: int,
) -> Iterator[list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != spec.columns:
            raise OlistValidationError(f"CSV header changed during import: {path.name}")
        chunk: list[dict[str, str]] = []
        for row in reader:
            chunk.append({column: row[column] for column in spec.columns})
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
