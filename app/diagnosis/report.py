from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.diagnosis.evidence import (
    AnomalyStatus,
    EvidenceFact,
    EvidenceSupportLevel,
    EvidenceType,
    EvidenceValidationError,
    ValidatedEvidence,
    ValidatedEvidenceBundle,
    evidence_limitation_label,
)

_FORBIDDEN_CLAIMS = ("导致", "造成", "证明", "唯一原因", "一定能够", "必然提升")
_SUPPORT_ORDER = {
    EvidenceSupportLevel.HIGH: 0,
    EvidenceSupportLevel.MEDIUM: 1,
    EvidenceSupportLevel.LOW: 2,
    EvidenceSupportLevel.UNSUPPORTED: 3,
}
_FACTOR_ORDER = {"traffic": 0, "promotion": 1, "inventory": 2}


class ReportStatus(StrEnum):
    COMPLETE = "COMPLETE"
    DEGRADED = "DEGRADED"
    NO_DECLINE = "NO_DECLINE"


class ReportSectionId(StrEnum):
    PROBLEM = "problem_definition"
    ANOMALY = "anomaly_confirmation"
    DECOMPOSITION = "metric_decomposition"
    DIMENSION = "dimension_contribution"
    CANDIDATE = "candidate_evidence"
    LIMITATIONS = "limitations_and_recommendations"


class ReportStatementKind(StrEnum):
    FACT = "fact"
    CONCLUSION = "conclusion"
    LIMITATION = "limitation"
    RECOMMENDATION = "recommendation"


class ReportStatement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ReportStatementKind
    text: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    analysis_result_ids: tuple[str, ...] = Field(min_length=1)
    query_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_statement(self) -> ReportStatement:
        if any(term in self.text for term in _FORBIDDEN_CLAIMS):
            raise ValueError("report statement contains forbidden causal language")
        for values in (
            self.evidence_ids,
            self.analysis_result_ids,
            self.query_ids,
        ):
            if len(values) != len(set(values)):
                raise ValueError("report statement lineage must be unique")
        return self


class ReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_id: ReportSectionId
    title: str = Field(min_length=1)
    statements: tuple[ReportStatement, ...] = Field(min_length=1)


class DiagnosisReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_version: Literal["diagnosis-report-v1"] = "diagnosis-report-v1"
    evidence_version: Literal["validated-evidence-v1"] = "validated-evidence-v1"
    status: ReportStatus
    candidate_ranking: tuple[str, ...]
    sections: tuple[ReportSection, ...] = Field(min_length=6, max_length=6)
    markdown: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_report_shape(self) -> DiagnosisReport:
        if tuple(section.section_id for section in self.sections) != tuple(
            ReportSectionId
        ):
            raise ValueError("report sections must use the frozen order")
        if len(self.candidate_ranking) != len(set(self.candidate_ranking)):
            raise ValueError("candidate ranking must contain unique Evidence IDs")
        if any(term in self.markdown for term in _FORBIDDEN_CLAIMS):
            raise ValueError("report contains forbidden causal language")
        return self


class ReportGenerator:
    """Renders only Validated Evidence; it cannot inspect Analysis or Query results."""

    def generate(self, bundle: ValidatedEvidenceBundle) -> DiagnosisReport:
        anomaly = bundle.evidence[0]
        supported_candidates = sorted(
            (
                item
                for item in bundle.evidence
                if item.evidence_type is EvidenceType.CANDIDATE_FACTOR
                and item.support_level is not EvidenceSupportLevel.UNSUPPORTED
            ),
            key=_candidate_sort_key,
        )
        if bundle.anomaly_status is AnomalyStatus.DECLINE_NOT_CONFIRMED:
            status = ReportStatus.NO_DECLINE
        elif (
            bundle.anomaly_status is AnomalyStatus.DECLINE_CONFIRMED
            and supported_candidates
        ):
            status = ReportStatus.COMPLETE
        else:
            status = ReportStatus.DEGRADED

        sections = (
            self._problem_section(bundle, anomaly),
            self._anomaly_section(bundle, anomaly),
            self._decomposition_section(bundle, anomaly),
            self._dimension_section(bundle, anomaly),
            self._candidate_section(bundle, anomaly, supported_candidates),
            self._limitations_section(bundle, anomaly, supported_candidates),
        )
        markdown = _render_markdown(sections)
        try:
            report = DiagnosisReport(
                status=status,
                candidate_ranking=tuple(
                    item.evidence_id for item in supported_candidates
                ),
                sections=sections,
                markdown=markdown,
            )
        except ValidationError as error:
            raise EvidenceValidationError("diagnosis_report_contract_invalid") from error
        self.validate(report, bundle)
        return report

    @staticmethod
    def validate(
        report: DiagnosisReport, bundle: ValidatedEvidenceBundle
    ) -> None:
        evidence_by_id = {item.evidence_id: item for item in bundle.evidence}
        if report.evidence_version != bundle.evidence_version:
            raise EvidenceValidationError("report_evidence_version_mismatch")
        supported_candidates = sorted(
            (
                item
                for item in bundle.evidence
                if item.evidence_type is EvidenceType.CANDIDATE_FACTOR
                and item.support_level is not EvidenceSupportLevel.UNSUPPORTED
            ),
            key=_candidate_sort_key,
        )
        expected_ranking = tuple(item.evidence_id for item in supported_candidates)
        if report.candidate_ranking != expected_ranking:
            raise EvidenceValidationError("report_candidate_ranking_invalid")
        if bundle.anomaly_status is AnomalyStatus.DECLINE_NOT_CONFIRMED:
            expected_status = ReportStatus.NO_DECLINE
        elif (
            bundle.anomaly_status is AnomalyStatus.DECLINE_CONFIRMED
            and supported_candidates
        ):
            expected_status = ReportStatus.COMPLETE
        else:
            expected_status = ReportStatus.DEGRADED
        if report.status is not expected_status:
            raise EvidenceValidationError("report_status_invalid")
        for evidence_id in report.candidate_ranking:
            evidence = evidence_by_id.get(evidence_id)
            if (
                evidence is None
                or evidence.evidence_type is not EvidenceType.CANDIDATE_FACTOR
                or evidence.support_level is EvidenceSupportLevel.UNSUPPORTED
            ):
                raise EvidenceValidationError("unsupported_candidate_in_ranking")
        for section in report.sections:
            for statement in section.statements:
                referenced: list[ValidatedEvidence] = []
                for evidence_id in statement.evidence_ids:
                    evidence = evidence_by_id.get(evidence_id)
                    if evidence is None:
                        raise EvidenceValidationError("report_references_unknown_evidence")
                    referenced.append(evidence)
                allowed_analysis = {
                    value for item in referenced for value in item.analysis_result_ids
                }
                allowed_queries = {value for item in referenced for value in item.query_ids}
                if not set(statement.analysis_result_ids) <= allowed_analysis:
                    raise EvidenceValidationError("report_analysis_lineage_invalid")
                if not set(statement.query_ids) <= allowed_queries:
                    raise EvidenceValidationError("report_query_lineage_invalid")
                if statement.kind is ReportStatementKind.CONCLUSION and any(
                    item.support_level is EvidenceSupportLevel.UNSUPPORTED
                    for item in referenced
                ):
                    raise EvidenceValidationError(
                        "unsupported_evidence_used_for_conclusion"
                    )
        if report.markdown != _render_markdown(report.sections):
            raise EvidenceValidationError("report_markdown_not_derived_from_sections")

    @staticmethod
    def _problem_section(
        bundle: ValidatedEvidenceBundle, anomaly: ValidatedEvidence
    ) -> ReportSection:
        scope_parts = []
        if bundle.scope.region is not None:
            scope_parts.append(f"region={bundle.scope.region}")
        if bundle.scope.category is not None:
            scope_parts.append(f"category={bundle.scope.category}")
        scope_text = ", ".join(scope_parts) if scope_parts else "overall"
        text = (
            f"目标指标=gmv；当前期={bundle.current_period.start.isoformat()}~"
            f"{bundle.current_period.end.isoformat()}；基期="
            f"{bundle.baseline_period.start.isoformat()}~"
            f"{bundle.baseline_period.end.isoformat()}；范围={scope_text}。"
        )
        return _section(
            ReportSectionId.PROBLEM,
            "1. 问题定义",
            (_statement(ReportStatementKind.FACT, text, (anomaly,)),),
        )

    @staticmethod
    def _anomaly_section(
        bundle: ValidatedEvidenceBundle, anomaly: ValidatedEvidence
    ) -> ReportSection:
        fact = anomaly.facts[0]
        values = (
            f"baseline={_number(fact.baseline_value)}, current={_number(fact.current_value)}, "
            f"delta={_number(fact.absolute_delta)}, change_rate={_number(fact.change_rate)}"
        )
        if bundle.anomaly_status is AnomalyStatus.DECLINE_CONFIRMED:
            text = f"GMV 下降已确认：{values}。"
        elif bundle.anomaly_status is AnomalyStatus.DECLINE_NOT_CONFIRMED:
            text = f"未确认 GMV 下降，不进入候选因素结论：{values}。"
        else:
            text = f"GMV 变化不可用，诊断降级：{values}。"
        return _section(
            ReportSectionId.ANOMALY,
            "2. 异常确认",
            (_statement(ReportStatementKind.FACT, text, (anomaly,)),),
        )

    @staticmethod
    def _decomposition_section(
        bundle: ValidatedEvidenceBundle, anomaly: ValidatedEvidence
    ) -> ReportSection:
        items = [
            item
            for item in bundle.evidence
            if item.evidence_type is EvidenceType.METRIC_DECOMPOSITION
        ]
        if not items:
            statements = (
                _statement(
                    ReportStatementKind.LIMITATION,
                    "当前计划未提供 GMV 两因素拆解 Evidence。",
                    (anomaly,),
                ),
            )
        else:
            item = items[0]
            gmv = _fact(item, "gmv")
            order = _fact(item, "order_count_contribution")
            aov = _fact(item, "aov_contribution")
            if item.support_level is EvidenceSupportLevel.HIGH:
                text = (
                    f"GMV 总变化={_number(gmv.absolute_delta)}；订单量贡献="
                    f"{_number(order.absolute_delta)}；AOV 贡献="
                    f"{_number(aov.absolute_delta)}；数值已对账。"
                )
                kind = ReportStatementKind.FACT
            else:
                text = (
                    f"GMV 总变化={_number(gmv.absolute_delta)}；订单量与 AOV 贡献"
                    "不可完整计算，仅保留降级结果。"
                )
                kind = ReportStatementKind.LIMITATION
            statements = (_statement(kind, text, (item,)),)
        return _section(
            ReportSectionId.DECOMPOSITION,
            "3. 指标拆解",
            statements,
        )

    @staticmethod
    def _dimension_section(
        bundle: ValidatedEvidenceBundle, anomaly: ValidatedEvidence
    ) -> ReportSection:
        dimensions = [
            item
            for item in bundle.evidence
            if item.evidence_type is EvidenceType.DIMENSION_CONTRIBUTION
        ]
        statements: list[ReportStatement] = []
        for item in dimensions:
            if item.dimension is None:
                raise EvidenceValidationError("dimension_evidence_identity_missing")
            for fact in item.facts:
                identity = f"{item.dimension.value}={fact.dimension_value}"
                if item.support_level is EvidenceSupportLevel.HIGH:
                    text = (
                        f"{identity}：GMV delta={_number(fact.absolute_delta)}，"
                        f"contribution={_number(fact.contribution)}。"
                    )
                    kind = ReportStatementKind.FACT
                else:
                    text = (
                        f"{identity}：GMV delta={_number(fact.absolute_delta)}；"
                        "完整贡献率不可用。"
                    )
                    kind = ReportStatementKind.LIMITATION
                statements.append(_statement(kind, text, (item,)))
        if not statements:
            statements.append(
                _statement(
                    ReportStatementKind.LIMITATION,
                    "当前计划未提供地区或品类贡献 Evidence。",
                    (anomaly,),
                )
            )
        return _section(
            ReportSectionId.DIMENSION,
            "4. 维度贡献",
            tuple(statements),
        )

    @staticmethod
    def _candidate_section(
        bundle: ValidatedEvidenceBundle,
        anomaly: ValidatedEvidence,
        supported: Sequence[ValidatedEvidence],
    ) -> ReportSection:
        statements: list[ReportStatement] = []
        for item in supported:
            primary = item.facts[0]
            orders = _fact(
                item,
                "category_order_count"
                if bundle.scope.category is not None
                else "order_count",
            )
            conversion = _fact(item, "conversion_rate")
            text = (
                f"{_factor_label(item)} 为 {item.support_level.value} 级关联候选："
                f"{primary.metric_id} delta={_number(primary.absolute_delta)}, "
                f"change_rate={_number(primary.change_rate)}；conversion_rate delta="
                f"{_number(conversion.absolute_delta)}；order_count delta="
                f"{_number(orders.absolute_delta)}。"
            )
            statements.append(
                _statement(ReportStatementKind.CONCLUSION, text, (item,))
            )
        unsupported = tuple(
            item
            for item in bundle.evidence
            if item.evidence_type is EvidenceType.CANDIDATE_FACTOR
            and item.support_level is EvidenceSupportLevel.UNSUPPORTED
        )
        for item in unsupported:
            labels = "，".join(evidence_limitation_label(l) for l in item.limitations)
            statements.append(
                _statement(
                    ReportStatementKind.LIMITATION,
                    f"{_factor_label(item)} 未支持：{labels}。",
                    (item,),
                )
            )
        if not statements:
            candidates = tuple(
                item
                for item in bundle.evidence
                if item.evidence_type is EvidenceType.CANDIDATE_FACTOR
            )
            references = candidates or (anomaly,)
            statements.append(
                _statement(
                    ReportStatementKind.LIMITATION,
                    "现有 Evidence 不足以形成受支持的候选因素结论。",
                    references,
                )
            )
        return _section(
            ReportSectionId.CANDIDATE,
            "5. 候选因素证据",
            tuple(statements),
        )

    @staticmethod
    def _limitations_section(
        bundle: ValidatedEvidenceBundle,
        anomaly: ValidatedEvidence,
        supported: Sequence[ValidatedEvidence],
    ) -> ReportSection:
        statements: list[ReportStatement] = []
        candidates = [
            item
            for item in bundle.evidence
            if item.evidence_type is EvidenceType.CANDIDATE_FACTOR
        ]
        if bundle.missing_evidence:
            statements.append(
                _statement(
                    ReportStatementKind.LIMITATION,
                    "上游声明缺失 Evidence："
                    + ", ".join(bundle.missing_evidence)
                    + "。",
                    (anomaly,),
                )
            )
        recommendation_refs = tuple(supported) or tuple(candidates) or (anomaly,)
        statements.append(
            _statement(
                ReportStatementKind.RECOMMENDATION,
                "建议结合数据补全、替代解释排查以及实验或准实验设计进一步验证。",
                recommendation_refs,
            )
        )
        if supported:
            top = supported[0]
            statements.append(
                _statement(
                    ReportStatementKind.RECOMMENDATION,
                    f"综合现有证据，本次 GMV 下降更可能主要与{_factor_label_cn(top)}变化相关。",
                    (top,),
                )
            )
        else:
            statements.append(
                _statement(
                    ReportStatementKind.RECOMMENDATION,
                    "当前证据不足以判断本次 GMV 下降主要与哪个因素相关。",
                    tuple(candidates) or (anomaly,),
                )
            )
        return _section(
            ReportSectionId.LIMITATIONS,
            "6. 数据限制和建议",
            tuple(statements),
        )


class ReportGeneratorNode:
    def __init__(self, generator: ReportGenerator | None = None) -> None:
        self._generator = generator or ReportGenerator()

    def __call__(self, state: Mapping[str, Any]) -> dict[str, object]:
        try:
            bundle = ValidatedEvidenceBundle.model_validate(
                state.get("validated_evidence")
            )
        except ValidationError as error:
            raise EvidenceValidationError("report_generator_input_invalid") from error
        report = self._generator.generate(bundle)
        return {
            "final_report": report.model_dump(mode="json"),
            "final_answer": report.markdown,
        }


def _candidate_sort_key(item: ValidatedEvidence) -> tuple[int, Decimal, int]:
    rate = item.facts[0].change_rate
    magnitude = abs(rate) if rate is not None else Decimal(0)
    factor = item.factor.value if item.factor is not None else ""
    return (_SUPPORT_ORDER[item.support_level], -magnitude, _FACTOR_ORDER[factor])


def _factor_label(item: ValidatedEvidence) -> str:
    labels = {"traffic": "Traffic", "promotion": "Promotion", "inventory": "Inventory"}
    if item.factor is None:
        raise EvidenceValidationError("candidate_factor_identity_missing")
    return labels[item.factor.value]


def _factor_label_cn(item: ValidatedEvidence) -> str:
    labels = {"traffic": "流量", "promotion": "促销", "inventory": "库存"}
    if item.factor is None:
        raise EvidenceValidationError("candidate_factor_identity_missing")
    return labels[item.factor.value]


def _fact(item: ValidatedEvidence, metric_id: str) -> EvidenceFact:
    matches = [fact for fact in item.facts if fact.metric_id == metric_id]
    if len(matches) != 1:
        raise EvidenceValidationError(f"report_fact_missing_or_duplicate:{metric_id}")
    return matches[0]


def _statement(
    kind: ReportStatementKind,
    text: str,
    evidence: Sequence[ValidatedEvidence],
) -> ReportStatement:
    evidence_ids: list[str] = []
    analysis_ids: list[str] = []
    query_ids: list[str] = []
    for item in evidence:
        evidence_ids.append(item.evidence_id)
        analysis_ids.extend(item.analysis_result_ids)
        query_ids.extend(item.query_ids)
    return ReportStatement(
        kind=kind,
        text=text,
        evidence_ids=tuple(dict.fromkeys(evidence_ids)),
        analysis_result_ids=tuple(dict.fromkeys(analysis_ids)),
        query_ids=tuple(dict.fromkeys(query_ids)),
    )


def _section(
    section_id: ReportSectionId,
    title: str,
    statements: tuple[ReportStatement, ...],
) -> ReportSection:
    return ReportSection(section_id=section_id, title=title, statements=statements)


def _number(value: Decimal | None) -> str:
    return "null" if value is None else format(value, "f")


def _render_markdown(sections: Sequence[ReportSection]) -> str:
    blocks: list[str] = []
    for section in sections:
        blocks.append(f"## {section.title}")
        for statement in section.statements:
            evidence = ",".join(statement.evidence_ids)
            analyses = ",".join(statement.analysis_result_ids)
            queries = ",".join(statement.query_ids)
            blocks.append(
                f"- {statement.text} [Evidence: {evidence}; Analysis: {analyses}; "
                f"Query: {queries}]"
            )
    return "\n\n".join(blocks)
