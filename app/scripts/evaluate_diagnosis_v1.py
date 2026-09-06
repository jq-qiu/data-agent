from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

from app.clients.mysql_client_manager import dw_mysql_client_manager
from app.conf.app_config import app_config
from app.diagnosis.analyzer import DeterministicAnalyzer, ReconciliationStatus
from app.diagnosis.capability import (
    CapabilityAssessor,
    CapabilityDataSource,
    DataCapabilityProfile,
    DataQualityStatus,
)
from app.diagnosis.evidence import (
    EvidenceChecker,
    EvidenceSupportLevel,
    EvidenceType,
)
from app.diagnosis.intent import Intent, IntentRouter
from app.diagnosis.planner import AnalysisPlanner
from app.diagnosis.query import (
    AnalysisQueryBuilder,
    AnalysisQueryContext,
    AnalysisTaskExecutor,
    QueryDataSource,
)
from app.diagnosis.question import (
    AnalysisQuestionParser,
    CandidateFactor,
    DatePeriod,
)
from app.diagnosis.report import ReportGenerator, ReportStatementKind
from app.evaluation.diagnosis import (
    DiagnosisCaseObservation,
    DiagnosisErrorCategory,
    score_diagnosis,
)
from app.metadata.catalog import load_catalog
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.validator import SQLValidator
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "data" / "evaluation" / "diagnosis_golden_v1.json"
REPORT_PATH = ROOT / "data" / "reports" / "EVAL-001_diagnosis_regression.json"
RUN_DIR = ROOT / "eval_runs" / "EVAL-001_v1"
_FORBIDDEN = ("导致", "造成", "证明", "唯一原因", "一定能够", "必然提升")
_STAGE_ERRORS = {
    "intent": DiagnosisErrorCategory.METRIC_RECOGNITION,
    "parser": DiagnosisErrorCategory.METRIC_RECOGNITION,
    "capability": DiagnosisErrorCategory.SCHEMA_LINKING,
    "planner": DiagnosisErrorCategory.ANALYSIS_PLANNING,
    "query": DiagnosisErrorCategory.QUERY_BUILDER,
    "execution": DiagnosisErrorCategory.SQL_EXECUTION,
    "analyzer": DiagnosisErrorCategory.NUMERIC_ANALYSIS,
    "evidence": DiagnosisErrorCategory.EVIDENCE_VALIDATION,
    "report": DiagnosisErrorCategory.UNSUPPORTED_CLAIM,
}


def _profile(catalog: Any, case_id: str) -> DataCapabilityProfile:
    columns = tuple(
        sorted(
            f"{table.table_name}.{column.name}"
            for table in catalog.tables
            for column in table.columns
        )
    )
    non_empty = tuple(
        column
        for column in columns
        if not (
            case_id == "D10"
            and column == "analysis_sales_region_daily.visitors"
        )
    )
    return DataCapabilityProfile(
        source=CapabilityDataSource.SYNTHETIC_CASE,
        available_period=DatePeriod(
            start=date(2018, 4, 1), end=date(2018, 5, 31)
        ),
        available_columns=columns,
        non_empty_columns=non_empty,
        data_quality_status=DataQualityStatus.PASS,
    )


def _unsupported_claims(report: Any, bundle: Any) -> int:
    evidence = {item.evidence_id: item for item in bundle.evidence}
    return sum(
        statement.kind is ReportStatementKind.CONCLUSION
        and any(
            evidence[evidence_id].support_level is EvidenceSupportLevel.UNSUPPORTED
            for evidence_id in statement.evidence_ids
        )
        for section in report.sections
        for statement in section.statements
    )


async def _evaluate() -> tuple[dict[str, Any], tuple[DiagnosisCaseObservation, ...]]:
    if app_config.db_dw.database != "data_agent_v1_dw":
        raise RuntimeError("EVAL-001 requires the isolated V1 database")
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    catalog = load_catalog(ROOT / "conf" / "meta_config.yaml")
    validator = SQLValidator(
        catalog, load_sql_policy(ROOT / "conf" / "sql_policy.yaml")
    )
    parser = AnalysisQuestionParser.from_catalog(catalog)
    assessor = CapabilityAssessor(catalog)
    observations: list[DiagnosisCaseObservation] = []

    dw_mysql_client_manager.init()
    if dw_mysql_client_manager.session_factory is None:
        raise RuntimeError("isolated DW session factory did not initialize")
    try:
        async with dw_mysql_client_manager.session_factory() as session:
            repository = DWMySQLRepository(session)
            for case in golden["cases"]:
                stage = "intent"
                started = perf_counter()
                query_count = 0
                try:
                    intent = IntentRouter().route(case["question"])
                    if intent.intent is not Intent.DIAGNOSIS:
                        raise ValueError("diagnosis_intent_not_selected")
                    stage = "parser"
                    parsed = parser.parse(case["question"], intent.intent)
                    if parsed.parsed_question is None:
                        raise ValueError("diagnosis_question_parse_failed")
                    stage = "capability"
                    if parsed.parsed_question.scope.model_dump(
                        mode="json", exclude_none=True
                    ) != case["scope"]:
                        raise ValueError("diagnosis_scope_mismatch")
                    capability = assessor.assess(
                        parsed.parsed_question, _profile(catalog, case["case_id"])
                    )
                    stage = "planner"
                    plan = AnalysisPlanner().plan(parsed.parsed_question, capability)
                    stage = "query"
                    builder = AnalysisQueryBuilder(
                        catalog,
                        AnalysisQueryContext(
                            source=QueryDataSource.SYNTHETIC_CASE,
                            case_id=case["case_id"],
                        ),
                    )
                    stage = "execution"
                    captured = io.StringIO()
                    with redirect_stdout(captured), redirect_stderr(captured):
                        query_results = await AnalysisTaskExecutor(
                            builder, validator, repository
                        ).execute(plan)
                    query_count = len(query_results)
                    stage = "analyzer"
                    analysis_results = DeterministicAnalyzer().analyze(
                        plan, query_results
                    )
                    stage = "evidence"
                    bundle = EvidenceChecker().check(plan, analysis_results)
                    stage = "report"
                    report = ReportGenerator().generate(bundle)
                    ReportGenerator.validate(report, bundle)

                    candidate_by_id = {
                        item.evidence_id: item
                        for item in bundle.evidence
                        if item.evidence_type is EvidenceType.CANDIDATE_FACTOR
                    }
                    predicted = tuple(
                        factor
                        for evidence_id in report.candidate_ranking
                        for factor in [candidate_by_id[evidence_id].factor]
                        if factor is not None
                    )
                    supported = tuple(
                        factor
                        for item in candidate_by_id.values()
                        if item.support_level is not EvidenceSupportLevel.UNSUPPORTED
                        for factor in [item.factor]
                        if factor is not None
                    )
                    differences = [
                        abs(result.reconciliation.difference)
                        for result in analysis_results
                        if result.reconciliation is not None
                    ]
                    reconciled = all(
                        result.reconciliation is None
                        or result.reconciliation.status is ReconciliationStatus.PASS
                        for result in analysis_results
                    )
                    elapsed = Decimal(str((perf_counter() - started) * 1000)).quantize(
                        Decimal("0.001")
                    )
                    observations.append(
                        DiagnosisCaseObservation(
                            case_id=case["case_id"],
                            expected_factors=tuple(
                                CandidateFactor(value)
                                for value in case["expected_factors"]
                            ),
                            predicted_factors=predicted,
                            supported_evidence_factors=supported,
                            expected_degradation=case["expected_degradation"],
                            expected_no_decline=case["expected_no_decline"],
                            anomaly_status=bundle.anomaly_status,
                            report_status=report.status,
                            missing_evidence=bundle.missing_evidence,
                            numeric_consistent=reconciled,
                            max_reconciliation_error=max(
                                differences, default=Decimal(0)
                            ),
                            unsupported_claim_count=_unsupported_claims(
                                report, bundle
                            ),
                            causal_language_violation_count=sum(
                                term in report.markdown for term in _FORBIDDEN
                            ),
                            elapsed_ms=elapsed,
                            query_count=query_count,
                            successful=True,
                        )
                    )
                except Exception as error:  # noqa: BLE001 - classify every case failure
                    elapsed = Decimal(str((perf_counter() - started) * 1000)).quantize(
                        Decimal("0.001")
                    )
                    observations.append(
                        DiagnosisCaseObservation(
                            case_id=case["case_id"],
                            expected_factors=tuple(
                                CandidateFactor(value)
                                for value in case["expected_factors"]
                            ),
                            predicted_factors=(),
                            supported_evidence_factors=(),
                            expected_degradation=case["expected_degradation"],
                            expected_no_decline=case["expected_no_decline"],
                            numeric_consistent=False,
                            max_reconciliation_error=Decimal(0),
                            unsupported_claim_count=0,
                            causal_language_violation_count=0,
                            elapsed_ms=elapsed,
                            query_count=query_count,
                            successful=False,
                            primary_error=_STAGE_ERRORS[stage],
                            error_type=type(error).__name__,
                        )
                    )
    finally:
        await dw_mysql_client_manager.close()

    observation_tuple = tuple(observations)
    summary = score_diagnosis(
        observation_tuple, evaluation_version=golden["version"]
    )
    report_payload = {
        "feature": "EVAL-001",
        "evaluation_scope": "D01-D10 functional regression; not production generalization",
        "database": "data_agent_v1_dw",
        "dataset_version": golden["dataset_version"],
        "generator_version": golden["generator_version"],
        "metric_registry_version": golden["metric_registry_version"],
        "model": "none",
        "summary": summary.model_dump(mode="json"),
        "cases": [item.model_dump(mode="json") for item in observation_tuple],
    }
    return report_payload, observation_tuple


def _write_artifacts(
    report: dict[str, Any],
    observations: tuple[DiagnosisCaseObservation, ...],
    *,
    report_path: Path = REPORT_PATH,
    run_dir: Path = RUN_DIR,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    report_path.write_text(encoded, encoding="utf-8")
    summary_payload = {key: value for key, value in report.items() if key != "cases"}
    (run_dir / "summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (run_dir / "diagnosis_results.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "case_id",
                "expected_factors",
                "predicted_factors",
                "anomaly_status",
                "report_status",
                "numeric_consistent",
                "max_reconciliation_error",
                "unsupported_claim_count",
                "causal_language_violation_count",
                "query_count",
                "elapsed_ms",
                "successful",
                "primary_error",
                "error_type",
            ),
        )
        writer.writeheader()
        for item in observations:
            writer.writerow(
                {
                    "case_id": item.case_id,
                    "expected_factors": "|".join(item.expected_factors),
                    "predicted_factors": "|".join(item.predicted_factors),
                    "anomaly_status": item.anomaly_status or "",
                    "report_status": item.report_status or "",
                    "numeric_consistent": item.numeric_consistent,
                    "max_reconciliation_error": item.max_reconciliation_error,
                    "unsupported_claim_count": item.unsupported_claim_count,
                    "causal_language_violation_count": item.causal_language_violation_count,
                    "query_count": item.query_count,
                    "elapsed_ms": item.elapsed_ms,
                    "successful": item.successful,
                    "primary_error": item.primary_error or "",
                    "error_type": item.error_type or "",
                }
            )
    failures = [item for item in observations if not item.successful]
    lines = [
        "# EVAL-001 Error Analysis",
        "",
        "D01-D10 is a functional regression set, not a production accuracy sample.",
        "",
        f"Failed cases: {len(failures)}",
        "",
    ]
    if failures:
        lines.extend(
            f"- {item.case_id}: {item.primary_error.value} ({item.error_type})"
            for item in failures
            if item.primary_error is not None
        )
    else:
        lines.append("No failed cases; every frozen error-category count is zero.")
    (run_dir / "error_analysis.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the D01-D10 V1 diagnosis regression"
    )
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--run-dir", type=Path, default=RUN_DIR)
    args = parser.parse_args(argv)
    report, observations = asyncio.run(_evaluate())
    _write_artifacts(
        report,
        observations,
        report_path=args.report,
        run_dir=args.run_dir,
    )
    summary = report["summary"]
    print(
        json.dumps(
            {
                "feature": report["feature"],
                "case_count": summary["case_count"],
                "successful_cases": summary["successful_cases"],
                "single_cause_hit_at_1": summary["single_cause_hit_at_1"],
                "root_cause_recall_at_3": summary["root_cause_recall_at_3"],
                "evidence_precision": summary["evidence_precision"],
                "numeric_consistency": summary["numeric_consistency"],
                "unsupported_claim_count": summary["unsupported_claim_count"],
                "causal_language_violation_count": summary[
                    "causal_language_violation_count"
                ],
                "gate_5_passed": summary["gate_5_passed"],
            }
        )
    )
    return 0 if summary["gate_5_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
