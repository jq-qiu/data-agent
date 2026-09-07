"""从真实或合成数据源读取覆盖与质量信息，形成请求级运行时能力画像。"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.diagnosis.capability import (
    CapabilityDataSource,
    DataCapabilityProfile,
    DataQualityStatus,
)
from app.diagnosis.query import AnalysisQueryRepository
from app.diagnosis.question import DatePeriod
from app.metadata.catalog import MetadataCatalog
from app.nl2sql.validator import SQLValidator

_ISOLATED_DATABASE = "data_agent_v1_dw"
_SYNTHETIC_CASE_PATTERN = re.compile(r"^D(?:0[1-9]|10)$")
_PROFILE_COLUMNS = {
    "dws_sales_region_daily": (
        "date_id",
        "region_id",
        "gmv",
        "order_count",
        "visitors",
        "promoted_sku_count",
        "active_sku_count",
        "available_sku_count",
        "required_sku_count",
    ),
    "dws_sales_category_daily": (
        "date_id",
        "region_id",
        "category_id",
        "gmv",
        "category_order_count",
        "category_visitors",
        "promoted_sku_count",
        "active_sku_count",
        "available_sku_count",
        "required_sku_count",
    ),
}


class RuntimeCapabilityError(RuntimeError):
    """Raised when the live warehouse cannot produce a safe capability profile."""


class WarehouseCapabilityProfileProvider:
    """Builds a truthful profile from validated, aggregate-only DWS probes."""

    def __init__(
        self,
        catalog: MetadataCatalog,
        validator: SQLValidator,
        repository: AnalysisQueryRepository,
    ) -> None:
        if validator.policy.allowed_database != _ISOLATED_DATABASE:
            raise RuntimeCapabilityError("isolated_database_required")
        self._catalog = catalog
        self._validator = validator
        self._repository = repository
        self._validate_catalog()

    async def load(self) -> DataCapabilityProfile:
        """通过统一 Validator 执行聚合探测，返回真实数仓当前可用的诊断能力。"""

        bounds: list[tuple[date, date]] = []
        non_empty: list[str] = []
        for table, columns in _PROFILE_COLUMNS.items():
            row = await self._probe(table, columns)
            start = _date_id(row.get("min_date"))
            end = _date_id(row.get("max_date"))
            bounds.append((start, end))
            for column in columns:
                count = row.get(f"{column}_non_null_count")
                if _positive_count(count):
                    non_empty.append(f"{table}.{column}")

        available_start = max(start for start, _ in bounds)
        available_end = min(end for _, end in bounds)
        if available_end < available_start:
            raise RuntimeCapabilityError("warehouse_periods_do_not_overlap")
        return DataCapabilityProfile(
            source=CapabilityDataSource.WAREHOUSE,
            available_period=DatePeriod(
                start=available_start,
                end=available_end,
            ),
            available_columns=tuple(sorted(self._catalog.column_ids)),
            non_empty_columns=tuple(sorted(non_empty)),
            data_quality_status=DataQualityStatus.PASS,
        )

    async def _probe(
        self,
        table: str,
        columns: tuple[str, ...],
    ) -> dict[str, Any]:
        projections = [
            "MIN(date_id) AS min_date",
            "MAX(date_id) AS max_date",
            *(
                f"COUNT({column}) AS {column}_non_null_count"
                for column in columns
            ),
        ]
        sql = f"SELECT {', '.join(projections)} FROM {table}"
        validated = self._validator.validate(sql)
        await self._repository.validate_sql(validated)
        rows = await self._repository.execute_sql(validated)
        if len(rows) != 1:
            raise RuntimeCapabilityError("warehouse_profile_shape_invalid")
        return rows[0]

    def _validate_catalog(self) -> None:
        required = {
            f"{table}.{column}"
            for table, columns in _PROFILE_COLUMNS.items()
            for column in columns
        }
        if missing := required - self._catalog.column_ids:
            raise RuntimeCapabilityError(
                f"warehouse_profile_catalog_missing:{','.join(sorted(missing))}"
            )




_SYNTHETIC_PROFILE_COLUMNS = {
    "analysis_sales_region_daily": (
        "case_id",
        "date_id",
        "region_id",
        "period_role",
        "analysis_gmv",
        "analysis_order_count",
        "visitors",
        "promoted_sku_count",
        "active_sku_count",
        "available_sku_count",
        "required_sku_count",
    ),
    "analysis_sales_category_daily": (
        "case_id",
        "date_id",
        "region_id",
        "category_id",
        "period_role",
        "analysis_gmv",
        "analysis_order_count",
        "visitors",
        "promoted_sku_count",
        "active_sku_count",
        "available_sku_count",
        "required_sku_count",
    ),
}


class SyntheticCapabilityProfileProvider:
    """Builds a case-bound profile from validated analysis_* table probes."""

    def __init__(
        self,
        catalog: MetadataCatalog,
        validator: SQLValidator,
        repository: AnalysisQueryRepository,
        case_id: str,
    ) -> None:
        if validator.policy.allowed_database != _ISOLATED_DATABASE:
            raise RuntimeCapabilityError("isolated_database_required")
        if not _SYNTHETIC_CASE_PATTERN.fullmatch(case_id):
            raise RuntimeCapabilityError("invalid_synthetic_case")
        self._catalog = catalog
        self._validator = validator
        self._repository = repository
        self._case_id = case_id
        self._validate_catalog()

    async def load(self) -> DataCapabilityProfile:
        """仅在指定 case_id 范围探测合成数据，防止案例之间的 Evidence 混用。"""

        bounds: list[tuple[date, date]] = []
        non_empty: list[str] = []
        for table, columns in _SYNTHETIC_PROFILE_COLUMNS.items():
            row = await self._probe(table, columns)
            start_raw = row.get("min_date")
            end_raw = row.get("max_date")
            if start_raw is None or end_raw is None:
                continue
            bounds.append((_date_id(start_raw), _date_id(end_raw)))
            for column in columns:
                count = row.get(f"{column}_non_null_count")
                if _positive_count(count):
                    non_empty.append(f"{table}.{column}")

        if not bounds:
            raise RuntimeCapabilityError("synthetic_case_empty")
        available_start = max(start for start, _ in bounds)
        available_end = min(end for _, end in bounds)
        if available_end < available_start:
            raise RuntimeCapabilityError("synthetic_periods_do_not_overlap")
        return DataCapabilityProfile(
            source=CapabilityDataSource.SYNTHETIC_CASE,
            available_period=DatePeriod(start=available_start, end=available_end),
            available_columns=tuple(sorted(self._catalog.column_ids)),
            non_empty_columns=tuple(sorted(non_empty)),
            data_quality_status=DataQualityStatus.PASS,
        )

    async def _probe(
        self,
        table: str,
        columns: tuple[str, ...],
    ) -> dict[str, Any]:
        projections = [
            "MIN(date_id) AS min_date",
            "MAX(date_id) AS max_date",
            *(
                f"COUNT({column}) AS {column}_non_null_count"
                for column in columns
            ),
        ]
        sql = (
            f"SELECT {', '.join(projections)} FROM {table} "
            f"WHERE case_id = '{self._case_id}'"
        )
        validated = self._validator.validate(sql)
        await self._repository.validate_sql(validated)
        rows = await self._repository.execute_sql(validated)
        if len(rows) != 1:
            raise RuntimeCapabilityError("synthetic_profile_shape_invalid")
        return rows[0]

    def _validate_catalog(self) -> None:
        required = {
            f"{table}.{column}"
            for table, columns in _SYNTHETIC_PROFILE_COLUMNS.items()
            for column in columns
        }
        if missing := required - self._catalog.column_ids:
            raise RuntimeCapabilityError(
                f"synthetic_profile_catalog_missing:{','.join(sorted(missing))}"
            )
def _positive_count(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _date_id(value: Any) -> date:
    try:
        text = str(int(value))
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except (TypeError, ValueError, OverflowError) as error:
        raise RuntimeCapabilityError("warehouse_date_bounds_invalid") from error
