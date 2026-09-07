# ANA-007 Evidence Report

## 1. Feature

Implement two separate deterministic stages after ANA-006:

1. `EvidenceChecker`, which converts accepted Analysis Results into validated,
   traceable Evidence with explicit support levels and limitations;
2. `ReportGenerator`, which consumes only the validated Evidence bundle and
   produces structured JSON plus a Markdown diagnosis report.

## 2. Source of Truth

This Feature follows, in order:

1. the current user request;
2. this specification;
3. `IMPLEMENTATION_PLAN.md`;
4. `docs/01_product_scope.md`;
5. `docs/02_data_and_metric_design.md`;
6. `docs/04_analysis_methodology.md`;
7. `docs/05_agent_workflow.md`;
8. `docs/06_evaluation.md`;
9. `specs/ANA-006_deterministic_analyzer.md` and its accepted output contract;
10. `AGENTS.md` and existing code behavior.

## 3. In Scope

- Strict, frozen, JSON-serializable Validated Evidence schemas.
- Evidence lineage to exact Analysis Result IDs, Query IDs, and Metric versions.
- Deterministic anomaly, decomposition, dimension, and candidate-factor
  Evidence validation.
- Stable `high`, `medium`, `low`, and `unsupported` support levels.
- Explicit conflicting/missing Evidence and causal-design limitations.
- Candidate ordering by support level, then absolute primary-metric change rate,
  then frozen factor order.
- A deterministic JSON/Markdown report with the six frozen sections.
- Report statements whose key facts and conclusions cite Validated Evidence.
- Separate Evidence Checker and Report Generator node adapters.
- Fixed offline contract evaluation and unit tests.

## 4. Out of Scope

- Reading Ground Truth events at runtime, tuning against D01-D10 labels, or
  claiming production/statistical generalization.
- LLM-generated business reasoning, strict causal inference, experimental
  effect estimates, or action execution.
- Changes to Analyzer mathematics, Metric Registry, query execution, NL2SQL,
  LangGraph wiring, State definitions outside node adapters, API, data, or
  database schemas.
- EVAL-001, API-001, and every later Feature.

## 5. Allowed Files

- `specs/ANA-007_evidence_report.md`
- `app/diagnosis/__init__.py`
- `app/diagnosis/evidence.py`
- `app/diagnosis/report.py`
- `app/scripts/evaluate_evidence_report_v1.py`
- `data/evaluation/evidence_report_golden_v1.json`
- `data/reports/ANA-007_evidence_report_evaluation.json`
- `test/diagnosis/test_evidence_report.py`
- `docs/reports/ANA-007_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

## 6. Evidence Contract

Every `ValidatedEvidence` item contains:

- stable `evidence_id` (`E001`, `E002`, ...);
- a controlled Evidence type and claim code;
- `support_level`;
- exact `analysis_result_ids`, `query_ids`, and Metric versions;
- typed numeric facts copied from Analysis Results;
- stable limitations;
- optional Factor or Dimension identity.

Evidence output must not contain raw SQL, parameters, SQL fingerprints,
validation traces, credentials, free-form model content, or Ground Truth labels.

The Evidence bundle also freezes the target Metric, current/baseline periods,
Scope, anomaly status, accepted Evidence items, and upstream missing-evidence
identifiers. It is the only Report Generator input.

## 7. Deterministic Validation Rules

### 7.1 Structural and Lineage Validation

- Analysis Result IDs must be consecutive and unique.
- Result methods and count must exactly match the Analysis Plan, including one
  Dimension result per requested Dimension.
- Every result must contain Query and Metric lineage.
- Duplicate Evidence lineage or inconsistent versions fail closed with
  `EVIDENCE_VALIDATION_FAILED`.

### 7.2 Anomaly Gate

- GMV absolute delta below zero: `DECLINE_CONFIRMED`.
- GMV absolute delta at or above zero: `DECLINE_NOT_CONFIRMED`; no downstream
  candidate is admitted into report conclusions.
- Missing GMV comparison values: `UNAVAILABLE`; report degrades.

The anomaly Evidence itself remains traceable in every case.

### 7.3 Decomposition and Dimension Evidence

- Reconciled Shapley values with non-null contributions are `high` Evidence.
- Zero-AOV-denominator decomposition is `low`, marked incomplete, and cannot be
  presented as a complete decomposition.
- A reconciled Dimension result with contribution ratios is `high`.
- A degraded or near-zero Dimension result is `low`; only member deltas may be
  reported, and complete-contribution language is forbidden.

### 7.4 Candidate Evidence

Directional validation uses no invented magnitude cutoff:

- the GMV decline must first be confirmed;
- the candidate primary metric and Order Count must both decrease;
- Promotion and Inventory require Conversion Rate to decrease for `high`;
- Traffic is `high` when Visitors, Conversion Rate, and Order Count do not
  conflict and Visitors/Order Count decrease;
- when the primary metric and Order Count decrease but Conversion Rate is
  missing or moves oppositely, Traffic is `medium` and the limitation is shown;
- for Promotion/Inventory, a missing Conversion Rate yields `medium`, while a
  non-decreasing Conversion Rate is direct conflict and therefore
  `unsupported`;
- a missing primary metric, non-decreasing primary metric, or non-decreasing
  Order Count is `unsupported` and cannot enter candidate conclusions.

All candidate Evidence includes `SYNTHETIC_CANDIDATE_DATA` and
`NO_CAUSAL_DESIGN`. Directional association is not a causal estimate.

## 8. Report Contract

The deterministic Report contains:

1. 问题定义;
2. 异常确认;
3. 指标拆解;
4. 维度贡献;
5. 候选因素证据;
6. 数据限制和建议.

Each report statement contains Evidence IDs, Analysis Result IDs, and Query IDs.
Any candidate conclusion references Evidence with support `high`, `medium`, or
`low`; `unsupported` Evidence can appear only as a limitation/conflict. Numeric
facts are rendered from Evidence facts, never recomputed or read from Query
Results.

The Report Generator rejects output containing deterministic causal claims,
including “导致”, “造成”, “证明”, “唯一原因”, or guaranteed-outcome language.
Allowed wording is limited to change contribution, directional consistency,
association Evidence, candidate factors, limitations, and next investigation.

Report status is:

- `COMPLETE` when a decline and at least one supported candidate are present;
- `DEGRADED` when comparison/candidate Evidence is unavailable or insufficient;
- `NO_DECLINE` when the requested decline is not confirmed.

## 9. Failure Contract

Invalid structure, lineage, metric version, numeric reference, or report claim
raises a typed `EvidenceValidationError` with code
`EVIDENCE_VALIDATION_FAILED`. Missing or conflicting business Evidence uses the
explicit `unsupported`/degraded contract rather than fabricated values.

## 10. Acceptance Criteria

1. Every Evidence fact and report statement traces to exact upstream IDs and
   Metric versions.
2. No-decline cases stop candidate conclusions.
3. Missing/conflicting factor data is visible and never promoted to a supported
   conclusion.
4. Supported candidate ordering is deterministic and independent of Ground
   Truth labels.
5. Degraded Shapley/Dimension cases do not use complete-reconciliation claims.
6. Report Generator consumes only a validated Evidence bundle and preserves all
   numbers exactly.
7. Forbidden causal language and unsupported Evidence in conclusions fail
   closed.
8. Fixed evaluation passes all Evidence/report contract cases.
9. Full pytest is green and Ruff/mypy do not regress their accepted baselines.
10. Diff is limited to the allowed ANA-007 files and contains no secrets.

## 11. Validation Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_evidence_report.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_evidence_report_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
```
