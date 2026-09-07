"""从版本化 Ground Truth 事件沿指标链确定性生成合成 Evidence 与 DWS 结果。"""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
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
    Text,
    and_,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection

EVENT_TYPES = frozenset({"traffic_drop", "promotion_end", "stockout"})
DIRECT_METRICS = {
    "traffic_drop": "visitors",
    "promotion_end": "promotion_coverage",
    "stockout": "inventory_fill_rate",
}
EXPECTED_CASE_BUCKETS = {
    "D01": ("traffic_drop",),
    "D02": ("traffic_drop",),
    "D03": ("promotion_end",),
    "D04": ("promotion_end",),
    "D05": ("stockout",),
    "D06": ("stockout",),
    "D07": ("traffic_drop", "promotion_end"),
    "D08": ("traffic_drop", "stockout"),
    "D09": (),
    "D10": (),
}
_SUCCESS = "success"
_RUNNING = "running"
_FAILED = "failed"
_CENT = Decimal("0.01")


class SyntheticConfigError(ValueError):
    """Raised when the versioned generator configuration is invalid."""


class SyntheticGenerationError(RuntimeError):
    """Raised when Synthetic Evidence cannot be generated or reconciled."""


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @property
    def dates(self) -> tuple[date, ...]:
        return tuple(
            self.start + timedelta(days=offset)
            for offset in range((self.end - self.start).days + 1)
        )


@dataclass(frozen=True)
class EventConfig:
    event_type: str
    effect_strength: Decimal
    ground_truth_rank: int


@dataclass(frozen=True)
class CaseConfig:
    case_id: str
    region_id: str
    category_id: str | None
    causes: tuple[EventConfig, ...]
    missing_evidence: tuple[str, ...]
    unobserved_order_factor: Decimal


@dataclass(frozen=True)
class SyntheticConfig:
    generator_version: str
    random_seed: int
    dataset_version: str
    baseline_period: Period
    current_period: Period
    base_conversion_rate: Decimal
    active_sku_count: int
    required_sku_count: int
    baseline_promotion_coverage: Decimal
    baseline_inventory_fill_rate: Decimal
    promotion_order_elasticity: Decimal
    inventory_order_elasticity: Decimal
    cases: tuple[CaseConfig, ...]
    config_sha256: str

    @classmethod
    def from_path(cls, path: Path) -> SyntheticConfig:
        raw_bytes = path.read_bytes()
        raw: dict[str, Any] = json.loads(raw_bytes)
        config = cls(
            generator_version=str(raw["generator_version"]),
            random_seed=int(raw["random_seed"]),
            dataset_version=str(raw["dataset_version"]),
            baseline_period=_period(raw["baseline_period"]),
            current_period=_period(raw["current_period"]),
            base_conversion_rate=Decimal(str(raw["base_conversion_rate"])),
            active_sku_count=int(raw["active_sku_count"]),
            required_sku_count=int(raw["required_sku_count"]),
            baseline_promotion_coverage=Decimal(
                str(raw["baseline_promotion_coverage"])
            ),
            baseline_inventory_fill_rate=Decimal(
                str(raw["baseline_inventory_fill_rate"])
            ),
            promotion_order_elasticity=Decimal(
                str(raw["promotion_order_elasticity"])
            ),
            inventory_order_elasticity=Decimal(
                str(raw["inventory_order_elasticity"])
            ),
            cases=tuple(_case(item) for item in raw["cases"]),
            config_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.generator_version != "synthetic-v1":
            raise SyntheticConfigError("Unexpected generator version")
        if self.dataset_version != "2":
            raise SyntheticConfigError("Unexpected source dataset version")
        if not 0 < self.base_conversion_rate <= 1:
            raise SyntheticConfigError("Base conversion rate must be in (0, 1]")
        if self.active_sku_count <= 0 or self.required_sku_count <= 0:
            raise SyntheticConfigError("SKU denominators must be positive")
        if self.baseline_period.end >= self.current_period.start:
            raise SyntheticConfigError("Baseline and current periods must not overlap")
        actual_buckets = {
            case.case_id: tuple(event.event_type for event in case.causes)
            for case in self.cases
        }
        if actual_buckets != EXPECTED_CASE_BUCKETS:
            raise SyntheticConfigError("D01-D10 case buckets do not match the frozen design")
        for case in self.cases:
            if not case.region_id or len(case.region_id) != 2:
                raise SyntheticConfigError(f"Invalid region for {case.case_id}")
            if not 0 < case.unobserved_order_factor <= 1:
                raise SyntheticConfigError(f"Invalid unobserved factor for {case.case_id}")
            ranks = [event.ground_truth_rank for event in case.causes]
            if ranks != list(range(1, len(ranks) + 1)):
                raise SyntheticConfigError(f"Invalid Ground Truth ranks for {case.case_id}")
            for event in case.causes:
                if event.event_type not in EVENT_TYPES:
                    raise SyntheticConfigError(f"Invalid event type for {case.case_id}")
                if not 0 < event.effect_strength < 1:
                    raise SyntheticConfigError(f"Invalid event strength for {case.case_id}")
        d10 = next(case for case in self.cases if case.case_id == "D10")
        if d10.missing_evidence != ("visitors",):
            raise SyntheticConfigError("D10 must be the frozen missing-Visitors case")


@dataclass(frozen=True)
class SyntheticPayload:
    case_rows: tuple[dict[str, Any], ...]
    event_rows: tuple[dict[str, Any], ...]
    region_rows: tuple[dict[str, Any], ...]
    category_rows: tuple[dict[str, Any], ...]
    content_sha256: str


@dataclass(frozen=True)
class SyntheticReconciliation:
    passed: bool
    case_count: int
    event_count: int
    event_types: tuple[str, ...]
    region_row_count: int
    category_row_count: int
    content_sha256: str
    source_summary_sha256: str
    source_unchanged: bool
    source_gate_passed: bool
    single_factor_cases: int
    dual_factor_cases: int
    no_clear_evidence_cases: int
    missing_evidence_cases: int
    evidence_chain_failures: int
    stable_case_failures: int
    degradation_case_failures: int
    zero_denominator_returns_none: bool


@dataclass(frozen=True)
class SyntheticGenerationResult:
    batch_id: str
    status: str
    reused: bool
    reconciliation: SyntheticReconciliation


def build_synthetic_tables() -> tuple[MetaData, dict[str, Table]]:
    metadata = MetaData()
    tables: dict[str, Table] = {}
    tables["synthetic_generation_batch"] = Table(
        "synthetic_generation_batch",
        metadata,
        Column("batch_id", String(36), primary_key=True),
        Column("generator_version", String(32), nullable=False),
        Column("random_seed", BigInteger, nullable=False),
        Column("dataset_version", String(32), nullable=False),
        Column("config_sha256", String(64), nullable=False),
        Column("content_sha256", String(64), nullable=True),
        Column("source_summary_sha256", String(64), nullable=False),
        Column("started_at", DateTime, nullable=False),
        Column("completed_at", DateTime, nullable=True),
        Column("status", String(16), nullable=False),
        Column("error_type", String(128), nullable=True),
    )
    tables["fact_ground_truth_case"] = Table(
        "fact_ground_truth_case",
        metadata,
        Column("case_id", String(8), primary_key=True),
        Column("baseline_start_date", Date, nullable=False),
        Column("baseline_end_date", Date, nullable=False),
        Column("current_start_date", Date, nullable=False),
        Column("current_end_date", Date, nullable=False),
        Column("region_id", String(2), nullable=False),
        Column("category_id", String(128), nullable=True),
        Column("expected_causes_json", Text, nullable=False),
        Column("missing_evidence_json", Text, nullable=False),
        Column("expected_outcome", String(16), nullable=False),
        Column("random_seed", BigInteger, nullable=False),
        Column("generator_version", String(32), nullable=False),
        Column("dataset_version", String(32), nullable=False),
    )
    tables["fact_business_event"] = Table(
        "fact_business_event",
        metadata,
        Column("event_id", String(64), primary_key=True),
        Column("case_id", String(8), nullable=False),
        Column("event_type", String(32), nullable=False),
        Column("start_date", Date, nullable=False),
        Column("end_date", Date, nullable=False),
        Column("region_id", String(2), nullable=False),
        Column("category_id", String(128), nullable=True),
        Column("effect_strength", Numeric(8, 4), nullable=False),
        Column("direct_metric", String(64), nullable=False),
        Column("expected_metric", String(64), nullable=False),
        Column("expected_direction", String(16), nullable=False),
        Column("ground_truth_rank", SmallInteger, nullable=False),
        Column("random_seed", BigInteger, nullable=False),
        Column("generator_version", String(32), nullable=False),
    )
    common_columns = lambda: (
        Column("case_id", String(8), primary_key=True),
        Column("date_id", Integer, primary_key=True),
        Column("region_id", String(2), primary_key=True),
        Column("period_role", String(16), nullable=False),
        Column("visitors", BigInteger, nullable=True),
        Column("promoted_sku_count", BigInteger, nullable=False),
        Column("active_sku_count", BigInteger, nullable=False),
        Column("available_sku_count", BigInteger, nullable=False),
        Column("required_sku_count", BigInteger, nullable=False),
        Column("analysis_order_count", BigInteger, nullable=False),
        Column("analysis_gmv", Numeric(18, 2), nullable=False),
        Column("dataset_version", String(32), nullable=False),
        Column("generator_version", String(32), nullable=False),
    )
    tables["analysis_sales_region_daily"] = Table(
        "analysis_sales_region_daily",
        metadata,
        *common_columns(),
    )
    tables["analysis_sales_category_daily"] = Table(
        "analysis_sales_category_daily",
        metadata,
        *common_columns(),
        Column("category_id", String(128), primary_key=True),
    )
    return metadata, tables


class SyntheticEvidenceGenerator:
    """从事件定义出发生成证据，再沿 Visitors→Orders→GMV 链路推导结果变化。"""

    def __init__(self, config: SyntheticConfig):
        self.config = config

    def generate(self, connection: Connection) -> SyntheticGenerationResult:
        """使用固定 Seed/版本生成隔离案例，并在持久化前后校验指标链一致性。"""

        source_tables = self._reflect_source_tables(connection)
        self._assert_data_foundation(source_tables, connection)
        source_before = _source_summary(connection, source_tables)
        if not _source_gate_passed(source_before):
            raise SyntheticGenerationError("Accepted DATA-002 source no longer reconciles")
        source_summary_sha256 = _digest(source_before)
        payload = self._build_payload(connection, source_tables)
        connection.commit()

        metadata, tables = build_synthetic_tables()
        metadata.create_all(connection)
        connection.commit()
        batch = tables["synthetic_generation_batch"]
        previous = connection.execute(
            select(batch.c.batch_id, batch.c.content_sha256).where(
                and_(
                    batch.c.generator_version == self.config.generator_version,
                    batch.c.random_seed == self.config.random_seed,
                    batch.c.dataset_version == self.config.dataset_version,
                    batch.c.config_sha256 == self.config.config_sha256,
                    batch.c.status == _SUCCESS,
                )
            )
        ).one_or_none()
        connection.commit()
        if previous is not None:
            reconciliation = reconcile_synthetic_evidence(
                connection,
                tables,
                source_tables,
                self.config,
                payload,
                source_summary_sha256,
            )
            connection.commit()
            if previous.content_sha256 != payload.content_sha256 or not reconciliation.passed:
                raise SyntheticGenerationError(
                    "Existing successful Synthetic Evidence no longer reconciles"
                )
            return SyntheticGenerationResult(
                batch_id=str(previous.batch_id),
                status=_SUCCESS,
                reused=True,
                reconciliation=reconciliation,
            )

        self._assert_targets_empty(connection, tables)
        connection.commit()
        batch_id = str(uuid.uuid4())
        started_at = _utc_now()
        with connection.begin():
            connection.execute(
                insert(batch),
                {
                    "batch_id": batch_id,
                    "generator_version": self.config.generator_version,
                    "random_seed": self.config.random_seed,
                    "dataset_version": self.config.dataset_version,
                    "config_sha256": self.config.config_sha256,
                    "content_sha256": None,
                    "source_summary_sha256": source_summary_sha256,
                    "started_at": started_at,
                    "completed_at": None,
                    "status": _RUNNING,
                    "error_type": None,
                },
            )
        try:
            with connection.begin():
                _insert_rows(connection, tables["fact_ground_truth_case"], payload.case_rows)
                _insert_rows(connection, tables["fact_business_event"], payload.event_rows)
                _insert_rows(connection, tables["analysis_sales_region_daily"], payload.region_rows)
                _insert_rows(
                    connection,
                    tables["analysis_sales_category_daily"],
                    payload.category_rows,
                )
                reconciliation = reconcile_synthetic_evidence(
                    connection,
                    tables,
                    source_tables,
                    self.config,
                    payload,
                    source_summary_sha256,
                )
                if not reconciliation.passed:
                    raise SyntheticGenerationError("DATA-003 reconciliation failed")
                connection.execute(
                    update(batch)
                    .where(batch.c.batch_id == batch_id)
                    .values(
                        content_sha256=payload.content_sha256,
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
                    update(batch)
                    .where(batch.c.batch_id == batch_id)
                    .values(
                        status=_FAILED,
                        completed_at=_utc_now(),
                        error_type=type(exc).__name__[:128],
                    )
                )
            raise
        return SyntheticGenerationResult(
            batch_id=batch_id,
            status=_SUCCESS,
            reused=False,
            reconciliation=reconciliation,
        )

    def _reflect_source_tables(self, connection: Connection) -> dict[str, Table]:
        metadata = MetaData()
        required = (
            "data_foundation_build_batch",
            "fact_order",
            "fact_order_item",
            "dws_sales_region_daily",
            "dws_sales_category_daily",
        )
        try:
            return {
                name: Table(name, metadata, autoload_with=connection)
                for name in required
            }
        except Exception as exc:
            raise SyntheticGenerationError("Required DATA-002 tables are unavailable") from exc

    def _assert_data_foundation(
        self,
        source_tables: dict[str, Table],
        connection: Connection,
    ) -> None:
        batch = source_tables["data_foundation_build_batch"]
        count = connection.execute(
            select(func.count())
            .select_from(batch)
            .where(
                and_(
                    batch.c.dataset_version == self.config.dataset_version,
                    batch.c.status == _SUCCESS,
                )
            )
        ).scalar_one()
        connection.commit()
        if int(count) != 1:
            raise SyntheticGenerationError("Exactly one accepted DATA-002 batch is required")

    def _assert_targets_empty(
        self,
        connection: Connection,
        tables: dict[str, Table],
    ) -> None:
        nonempty = [
            name
            for name in (
                "fact_ground_truth_case",
                "fact_business_event",
                "analysis_sales_region_daily",
                "analysis_sales_category_daily",
            )
            if _count(connection, tables[name]) > 0
        ]
        if nonempty:
            raise SyntheticGenerationError(
                "Unaccepted Synthetic Evidence exists; automatic overwrite is disabled"
            )

    def _build_payload(
        self,
        connection: Connection,
        source_tables: dict[str, Table],
    ) -> SyntheticPayload:
        case_rows: list[dict[str, Any]] = []
        event_rows: list[dict[str, Any]] = []
        region_rows: list[dict[str, Any]] = []
        category_rows: list[dict[str, Any]] = []
        for case in self.config.cases:
            baseline_orders, baseline_gmv = self._baseline_values(
                connection,
                source_tables,
                case,
            )
            if baseline_orders <= 0 or baseline_gmv <= 0:
                raise SyntheticGenerationError(f"Empty baseline scope for {case.case_id}")
            case_rows.append(self._case_row(case))
            event_rows.extend(self._event_rows(case))
            generated = self._analysis_rows(case, baseline_orders, baseline_gmv)
            if case.category_id is None:
                region_rows.extend(generated)
            else:
                category_rows.extend(generated)

        case_rows.sort(key=lambda row: row["case_id"])
        event_rows.sort(key=lambda row: row["event_id"])
        region_rows.sort(key=lambda row: (row["case_id"], row["date_id"], row["region_id"]))
        category_rows.sort(
            key=lambda row: (
                row["case_id"],
                row["date_id"],
                row["region_id"],
                row["category_id"],
            )
        )

        digest_payload = {
            "cases": case_rows,
            "events": event_rows,
            "region": region_rows,
            "category": category_rows,
        }
        return SyntheticPayload(
            case_rows=tuple(case_rows),
            event_rows=tuple(event_rows),
            region_rows=tuple(region_rows),
            category_rows=tuple(category_rows),
            content_sha256=_digest(digest_payload),
        )

    def _baseline_values(
        self,
        connection: Connection,
        source_tables: dict[str, Table],
        case: CaseConfig,
    ) -> tuple[int, Decimal]:
        start_id = _date_id(self.config.baseline_period.start)
        end_id = _date_id(self.config.baseline_period.end)
        if case.category_id is None:
            table = source_tables["dws_sales_region_daily"]
            order_column = table.c.order_count
            condition = table.c.region_id == case.region_id
        else:
            table = source_tables["dws_sales_category_daily"]
            order_column = table.c.category_order_count
            condition = and_(
                table.c.region_id == case.region_id,
                table.c.category_id == case.category_id,
            )
        row = connection.execute(
            select(
                func.coalesce(func.sum(order_column), 0).label("orders"),
                func.coalesce(func.sum(table.c.gmv), 0).label("gmv"),
            ).where(
                and_(
                    table.c.date_id.between(start_id, end_id),
                    condition,
                )
            )
        ).one()
        return int(row.orders), _money(row.gmv)

    def _case_row(self, case: CaseConfig) -> dict[str, Any]:
        outcome = "decrease" if self._result_factor(case) < 1 else "stable"
        return {
            "case_id": case.case_id,
            "baseline_start_date": self.config.baseline_period.start,
            "baseline_end_date": self.config.baseline_period.end,
            "current_start_date": self.config.current_period.start,
            "current_end_date": self.config.current_period.end,
            "region_id": case.region_id,
            "category_id": case.category_id,
            "expected_causes_json": json.dumps(
                [event.event_type for event in case.causes],
                separators=(",", ":"),
            ),
            "missing_evidence_json": json.dumps(
                list(case.missing_evidence),
                separators=(",", ":"),
            ),
            "expected_outcome": outcome,
            "random_seed": self.config.random_seed,
            "generator_version": self.config.generator_version,
            "dataset_version": self.config.dataset_version,
        }

    def _event_rows(self, case: CaseConfig) -> list[dict[str, Any]]:
        return [
            {
                "event_id": f"{case.case_id}-{event.event_type}",
                "case_id": case.case_id,
                "event_type": event.event_type,
                "start_date": self.config.current_period.start,
                "end_date": self.config.current_period.end,
                "region_id": case.region_id,
                "category_id": case.category_id,
                "effect_strength": event.effect_strength,
                "direct_metric": DIRECT_METRICS[event.event_type],
                "expected_metric": "gmv",
                "expected_direction": "decrease",
                "ground_truth_rank": event.ground_truth_rank,
                "random_seed": self.config.random_seed,
                "generator_version": self.config.generator_version,
            }
            for event in case.causes
        ]

    def _analysis_rows(
        self,
        case: CaseConfig,
        baseline_orders: int,
        baseline_gmv: Decimal,
    ) -> list[dict[str, Any]]:
        base_rate = self.config.base_conversion_rate
        baseline_visitors = _round_int(Decimal(baseline_orders) / base_rate)
        traffic_factor, promotion_factor, inventory_factor = self._evidence_factors(case)
        hidden_current_visitors = _round_int(Decimal(baseline_visitors) * traffic_factor)
        current_orders = _round_int(
            Decimal(hidden_current_visitors)
            * base_rate
            * promotion_factor
            * inventory_factor
            * case.unobserved_order_factor
        )
        baseline_aov = baseline_gmv / Decimal(baseline_orders)
        current_gmv = _money(baseline_aov * Decimal(current_orders))

        promoted_baseline = _round_int(
            Decimal(self.config.active_sku_count)
            * self.config.baseline_promotion_coverage
        )
        promoted_current = _round_int(Decimal(promoted_baseline) * _promotion_direct(case))
        available_baseline = _round_int(
            Decimal(self.config.required_sku_count)
            * self.config.baseline_inventory_fill_rate
        )
        available_current = _round_int(Decimal(available_baseline) * _inventory_direct(case))

        rows: list[dict[str, Any]] = []
        for role, period, visitors, orders, gmv, promoted, available in (
            (
                "baseline",
                self.config.baseline_period,
                baseline_visitors,
                baseline_orders,
                baseline_gmv,
                promoted_baseline,
                available_baseline,
            ),
            (
                "current",
                self.config.current_period,
                hidden_current_visitors,
                current_orders,
                current_gmv,
                promoted_current,
                available_current,
            ),
        ):
            dates = period.dates
            visitor_values = _allocate_int(
                visitors,
                len(dates),
                _seed(self.config.random_seed, case.case_id, role, "visitors"),
            )
            order_values = _allocate_int(
                orders,
                len(dates),
                _seed(self.config.random_seed, case.case_id, role, "orders"),
            )
            gmv_values = _allocate_money(gmv, order_values)
            for index, day in enumerate(dates):
                row = {
                    "case_id": case.case_id,
                    "date_id": _date_id(day),
                    "region_id": case.region_id,
                    "period_role": role,
                    "visitors": (
                        None if "visitors" in case.missing_evidence else visitor_values[index]
                    ),
                    "promoted_sku_count": promoted,
                    "active_sku_count": self.config.active_sku_count,
                    "available_sku_count": available,
                    "required_sku_count": self.config.required_sku_count,
                    "analysis_order_count": order_values[index],
                    "analysis_gmv": gmv_values[index],
                    "dataset_version": self.config.dataset_version,
                    "generator_version": self.config.generator_version,
                }
                if case.category_id is not None:
                    row["category_id"] = case.category_id
                rows.append(row)
        return rows

    def _evidence_factors(self, case: CaseConfig) -> tuple[Decimal, Decimal, Decimal]:
        traffic = Decimal(1)
        promotion = Decimal(1)
        inventory = Decimal(1)
        for event in case.causes:
            if event.event_type == "traffic_drop":
                traffic *= 1 - event.effect_strength
            elif event.event_type == "promotion_end":
                promotion *= 1 - (
                    event.effect_strength * self.config.promotion_order_elasticity
                )
            elif event.event_type == "stockout":
                inventory *= 1 - (
                    event.effect_strength * self.config.inventory_order_elasticity
                )
        return traffic, promotion, inventory

    def _result_factor(self, case: CaseConfig) -> Decimal:
        traffic, promotion, inventory = self._evidence_factors(case)
        return traffic * promotion * inventory * case.unobserved_order_factor


def reconcile_synthetic_evidence(
    connection: Connection,
    tables: dict[str, Table],
    source_tables: dict[str, Table],
    config: SyntheticConfig,
    expected_payload: SyntheticPayload,
    source_summary_sha256: str,
) -> SyntheticReconciliation:
    persisted_payload = _read_persisted_payload(connection, tables)
    content_sha256 = _digest(persisted_payload)
    source_after_sha256 = _digest(_source_summary(connection, source_tables))
    case_count = _count(connection, tables["fact_ground_truth_case"])
    event_count = _count(connection, tables["fact_business_event"])
    event_types = tuple(
        sorted(
            str(value)
            for value in connection.execute(
                select(tables["fact_business_event"].c.event_type).distinct()
            ).scalars()
        )
    )
    failures = _validate_case_chains(connection, tables, config)
    single_factor_cases = sum(len(case.causes) == 1 for case in config.cases)
    dual_factor_cases = sum(len(case.causes) == 2 for case in config.cases)
    no_clear_evidence_cases = sum(case.case_id == "D09" for case in config.cases)
    missing_evidence_cases = sum(bool(case.missing_evidence) for case in config.cases)
    source_unchanged = source_summary_sha256 == source_after_sha256
    source_gate_passed = _source_gate_passed(_source_summary(connection, source_tables))
    passed = all(
        (
            case_count == 10,
            event_count == len(expected_payload.event_rows),
            event_types == tuple(sorted(EVENT_TYPES)),
            _count(connection, tables["analysis_sales_region_daily"])
            == len(expected_payload.region_rows),
            _count(connection, tables["analysis_sales_category_daily"])
            == len(expected_payload.category_rows),
            content_sha256 == expected_payload.content_sha256,
            source_unchanged,
            source_gate_passed,
            failures["evidence_chain"] == 0,
            failures["stable_case"] == 0,
            failures["degradation_case"] == 0,
            safe_ratio(1, 0) is None,
        )
    )
    return SyntheticReconciliation(
        passed=passed,
        case_count=case_count,
        event_count=event_count,
        event_types=event_types,
        region_row_count=_count(connection, tables["analysis_sales_region_daily"]),
        category_row_count=_count(connection, tables["analysis_sales_category_daily"]),
        content_sha256=content_sha256,
        source_summary_sha256=source_after_sha256,
        source_unchanged=source_unchanged,
        source_gate_passed=source_gate_passed,
        single_factor_cases=single_factor_cases,
        dual_factor_cases=dual_factor_cases,
        no_clear_evidence_cases=no_clear_evidence_cases,
        missing_evidence_cases=missing_evidence_cases,
        evidence_chain_failures=failures["evidence_chain"],
        stable_case_failures=failures["stable_case"],
        degradation_case_failures=failures["degradation_case"],
        zero_denominator_returns_none=safe_ratio(1, 0) is None,
    )


def safe_ratio(numerator: int | Decimal, denominator: int | Decimal) -> Decimal | None:
    """运行时由可加分子分母重算比率；分母为零时显式返回空值。"""

    denominator_decimal = Decimal(denominator)
    if denominator_decimal == 0:
        return None
    return Decimal(numerator) / denominator_decimal


def _validate_case_chains(
    connection: Connection,
    tables: dict[str, Table],
    config: SyntheticConfig,
) -> dict[str, int]:
    failures = {"evidence_chain": 0, "stable_case": 0, "degradation_case": 0}
    for case in config.cases:
        table = (
            tables["analysis_sales_region_daily"]
            if case.category_id is None
            else tables["analysis_sales_category_daily"]
        )
        rows = {
            str(row.period_role): row
            for row in connection.execute(
                select(
                    table.c.period_role,
                    func.sum(table.c.visitors).label("visitors"),
                    func.sum(table.c.promoted_sku_count).label("promoted"),
                    func.sum(table.c.active_sku_count).label("active"),
                    func.sum(table.c.available_sku_count).label("available"),
                    func.sum(table.c.required_sku_count).label("required"),
                    func.sum(table.c.analysis_order_count).label("orders"),
                    func.sum(table.c.analysis_gmv).label("gmv"),
                )
                .where(table.c.case_id == case.case_id)
                .group_by(table.c.period_role)
            ).mappings()
        }
        baseline = rows["baseline"]
        current = rows["current"]
        causes = {event.event_type for event in case.causes}
        if case.case_id == "D09":
            if baseline.orders != current.orders or _money(baseline.gmv) != _money(current.gmv):
                failures["stable_case"] += 1
            continue
        if case.case_id == "D10":
            if (
                baseline.visitors is not None
                or current.visitors is not None
                or int(current.orders) >= int(baseline.orders)
                or _money(current.gmv) >= _money(baseline.gmv)
            ):
                failures["degradation_case"] += 1
            continue
        evidence_ok = int(current.orders) < int(baseline.orders) and _money(
            current.gmv
        ) < _money(baseline.gmv)
        if "traffic_drop" in causes:
            evidence_ok = evidence_ok and int(current.visitors) < int(baseline.visitors)
        if "promotion_end" in causes:
            evidence_ok = evidence_ok and _required_ratio(
                current.promoted,
                current.active,
            ) < _required_ratio(baseline.promoted, baseline.active)
        if "stockout" in causes:
            evidence_ok = evidence_ok and _required_ratio(
                current.available,
                current.required,
            ) < _required_ratio(baseline.available, baseline.required)
        baseline_aov = _required_ratio(baseline.gmv, baseline.orders)
        current_aov = _required_ratio(current.gmv, current.orders)
        if abs(baseline_aov - current_aov) > _CENT:
            evidence_ok = False
        if not evidence_ok:
            failures["evidence_chain"] += 1
    return failures


def _read_persisted_payload(
    connection: Connection,
    tables: dict[str, Table],
) -> dict[str, list[dict[str, Any]]]:
    definitions = (
        ("cases", "fact_ground_truth_case", ("case_id",)),
        ("events", "fact_business_event", ("event_id",)),
        ("region", "analysis_sales_region_daily", ("case_id", "date_id", "region_id")),
        (
            "category",
            "analysis_sales_category_daily",
            ("case_id", "date_id", "region_id", "category_id"),
        ),
    )
    payload: dict[str, list[dict[str, Any]]] = {}
    for label, table_name, order_columns in definitions:
        table = tables[table_name]
        rows = connection.execute(
            select(table).order_by(*(table.c[column] for column in order_columns))
        ).mappings()
        payload[label] = [dict(row) for row in rows]
    return payload


def _source_summary(
    connection: Connection,
    source_tables: dict[str, Table],
) -> dict[str, int | str]:
    fact_order = source_tables["fact_order"]
    fact_item = source_tables["fact_order_item"]
    region = source_tables["dws_sales_region_daily"]
    category = source_tables["dws_sales_category_daily"]
    valid = fact_order.c.status.not_in(("canceled", "unavailable"))
    dwd_gmv = connection.execute(
        select(func.coalesce(func.sum(fact_item.c.price), 0))
        .select_from(
            fact_order.join(fact_item, fact_item.c.order_id == fact_order.c.order_id)
        )
        .where(valid)
    ).scalar_one()
    return {
        "fact_order_count": _count(connection, fact_order),
        "fact_item_count": _count(connection, fact_item),
        "region_row_count": _count(connection, region),
        "category_row_count": _count(connection, category),
        "valid_order_count": int(
            connection.execute(
                select(func.count()).select_from(fact_order).where(valid)
            ).scalar_one()
        ),
        "region_order_count": int(
            connection.execute(
                select(func.coalesce(func.sum(region.c.order_count), 0))
            ).scalar_one()
        ),
        "dwd_gmv": _money_text(_money(dwd_gmv)),
        "region_gmv": _money_text(
            _money(connection.execute(select(func.sum(region.c.gmv))).scalar_one())
        ),
        "category_gmv": _money_text(
            _money(connection.execute(select(func.sum(category.c.gmv))).scalar_one())
        ),
    }


def _source_gate_passed(summary: dict[str, int | str]) -> bool:
    return bool(
        summary["dwd_gmv"] == summary["region_gmv"] == summary["category_gmv"]
        and summary["valid_order_count"] == summary["region_order_count"]
    )


def _case(raw: dict[str, Any]) -> CaseConfig:
    return CaseConfig(
        case_id=str(raw["case_id"]),
        region_id=str(raw["region_id"]),
        category_id=(str(raw["category_id"]) if raw.get("category_id") else None),
        causes=tuple(
            EventConfig(
                event_type=str(item["event_type"]),
                effect_strength=Decimal(str(item["effect_strength"])),
                ground_truth_rank=int(item["ground_truth_rank"]),
            )
            for item in raw["causes"]
        ),
        missing_evidence=tuple(str(value) for value in raw["missing_evidence"]),
        unobserved_order_factor=Decimal(str(raw["unobserved_order_factor"])),
    )


def _period(raw: dict[str, Any]) -> Period:
    return Period(start=date.fromisoformat(raw["start"]), end=date.fromisoformat(raw["end"]))


def _promotion_direct(case: CaseConfig) -> Decimal:
    factor = Decimal(1)
    for event in case.causes:
        if event.event_type == "promotion_end":
            factor *= 1 - event.effect_strength
    return factor


def _inventory_direct(case: CaseConfig) -> Decimal:
    factor = Decimal(1)
    for event in case.causes:
        if event.event_type == "stockout":
            factor *= 1 - event.effect_strength
    return factor


def _allocate_int(total: int, size: int, seed: int) -> list[int]:
    quotient, remainder = divmod(total, size)
    values = [quotient] * size
    indexes = list(range(size))
    random.Random(seed).shuffle(indexes)
    for index in indexes[:remainder]:
        values[index] += 1
    return values


def _allocate_money(total: Decimal, weights: list[int]) -> list[Decimal]:
    total_cents = int((_money(total) * 100).to_integral_value())
    weight_sum = sum(weights)
    if weight_sum <= 0:
        raise SyntheticGenerationError("Cannot allocate GMV without positive orders")
    raw_cents = [Decimal(total_cents) * weight / weight_sum for weight in weights]
    cents = [int(value) for value in raw_cents]
    remainder = total_cents - sum(cents)
    order = sorted(
        range(len(weights)),
        key=lambda index: raw_cents[index] - cents[index],
        reverse=True,
    )
    for index in order[:remainder]:
        cents[index] += 1
    return [Decimal(value) / 100 for value in cents]


def _seed(base_seed: int, *parts: str) -> int:
    value = ":".join((str(base_seed), *parts)).encode()
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big")


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    raise TypeError(f"Unsupported digest value type: {type(value).__name__}")


def _insert_rows(connection: Connection, table: Table, rows: tuple[dict[str, Any], ...]) -> None:
    if rows:
        connection.execute(insert(table), rows)


def _count(connection: Connection, table: Table) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def _required_ratio(numerator: object, denominator: object) -> Decimal:
    result = safe_ratio(Decimal(str(numerator)), Decimal(str(denominator)))
    if result is None:
        raise SyntheticGenerationError("Unexpected zero denominator")
    return result


def _round_int(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(_CENT, rounding=ROUND_HALF_UP)


def _money_text(value: Decimal) -> str:
    return format(value, ".2f")


def _date_id(value: date) -> int:
    return value.year * 10_000 + value.month * 100 + value.day


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
