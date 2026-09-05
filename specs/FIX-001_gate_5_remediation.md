# FIX-001 Gate 5 Remediation

## 1. Feature

Remediate the two contract defects exposed by the first EVAL-001 run, then
rerun the unchanged D01-D10 diagnosis regression against the isolated
`data_agent_v1_dw` database. This Feature is limited to real Scope vocabulary
coverage and Scope-aware Order Count Evidence lineage.

## 2. Source of Truth

1. Current user authorization to continue.
2. This specification.
3. `IMPLEMENTATION_PLAN.md` and Gate 5.
4. `IMPLEMENTATION_STATUS.md` and `EVAL-001_COMPLETION.md`.
5. `docs/02_data_and_metric_design.md`.
6. `docs/03_metadata_and_nl2sql.md`.
7. `docs/04_analysis_methodology.md`.
8. `docs/05_agent_workflow.md`.
9. `docs/06_evaluation.md`.
10. `data/config/synthetic_v1.json` and the accepted DATA-003 tables.
11. Accepted META-001, ANA-002, ANA-005, ANA-006, ANA-007, and EVAL-001
    contracts.

## 3. Prerequisite Findings

- EVAL-001 attempted D01-D10 but only 4/10 chains completed.
- D03, D04, D06, D08, and D10 could not ground their exact Scope because the
  accepted Synthetic canonical values `SC`, `PA`, `ES`, `eletrodomesticos`, and
  `cool_stuff` were absent from the Metadata Catalog value vocabulary.
- D02 correctly used the Category table and `category_order_count` inside one
  Category Scope, but the Evidence model accepted only the overall/Region
  decomposition lineage `gmv + order_count + aov`.
- The accepted Query Builder must continue to use overall `order_count` only
  for overall/Region Scope and `category_order_count` only for a single Category
  Scope.

## 4. In Scope

- Register the five missing real canonical Scope values and useful aliases in
  `conf/meta_config.yaml`.
- Rebuild the existing isolated V1 MySQL Metadata registry, Qdrant collection,
  and Elasticsearch value index from the updated catalog without touching the
  original `dw` or Olist/Synthetic data tables.
- Preserve the overall/Region decomposition lineage contract:
  `gmv + order_count + aov`.
- Add the single-Category decomposition lineage contract:
  `gmv + category_order_count`.
- Make decomposition and candidate Evidence preserve the Scope-appropriate
  Order Count identity. Cross-grain or partial lineage must fail closed.
- Make Report fact lookup select the matching Category or overall Order Count
  identity from the already validated Evidence bundle without changing wording.
- Add focused metadata, parser, and Evidence regression tests.
- Add output-path options to the existing EVAL-001 runner solely to preserve
  the immutable first baseline while recording the FIX-001 rerun separately.
- Run the unchanged D01-D10 Golden questions, labels, scoring rules, and Gate 5
  thresholds and persist a new report/run directory.

## 5. Out of Scope

- No change to D01-D10 questions, expected Scope, Ground Truth causes, Synthetic
  data, Generator seed/version, evaluation scoring, or Gate thresholds.
- No change to GMV, AOV, overall Order Count, or Category Order Count formulas.
- No change to Query Builder table selection, SQL, Analyzer mathematics,
  candidate-factor rules, Evidence strength, ranking, or report wording.
- No ODS/DWD/DWS/Synthetic writes, DDL, data regeneration, or original `dw`
  access.
- No NL2SQL baseline work, LangGraph wiring, API, UI, or API-001 implementation.
- No unrelated Ruff/mypy cleanup.

## 6. Allowed Files

- `specs/FIX-001_gate_5_remediation.md`
- `conf/meta_config.yaml`
- `app/diagnosis/evidence.py`
- `app/diagnosis/report.py`
- `app/scripts/evaluate_diagnosis_v1.py`
- `test/metadata/test_catalog.py`
- `test/diagnosis/test_analysis_question_parser.py`
- `test/diagnosis/test_evidence_report.py`
- `data/reports/FIX-001_gate_5_regression.json`
- `eval_runs/FIX-001_v1/summary.json`
- `eval_runs/FIX-001_v1/diagnosis_results.csv`
- `eval_runs/FIX-001_v1/error_analysis.md`
- `FIX-001_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

## 7. Frozen Contract Decisions

### 7.1 Scope Vocabulary

Canonical values come from the accepted DATA-003 configuration and must also
exist in the isolated warehouse dimensions:

- Regions: `SC`, `PA`, `ES`.
- Categories: `eletrodomesticos`, `cool_stuff`.

The deterministic Parser still accepts only canonical values or aliases from
the injected Metadata Catalog. Unknown Scope text must continue to fail.

### 7.2 Decomposition Lineage

For a decomposition Analysis Task:

- when `scope.category` is absent, Evidence requires exactly the frozen
  components `gmv`, `order_count`, and `aov`;
- when `scope.category` is present, Evidence requires exactly `gmv` and
  `category_order_count` and must not require or reinterpret overall
  `order_count`;
- a Category lineage cannot satisfy an overall/Region task, and an overall
  lineage cannot satisfy a Category task;
- all lineage versions must remain unique and consistent.

The Analyzer's row field remains the generic local name `order_count`; Metric
lineage retains the Registry identity and grain semantics.

Candidate Evidence follows the same Scope rule: the numeric Analyzer field is
still locally named `order_count`, but the Evidence fact and lineage identity
must be `category_order_count` inside a Category Scope and `order_count`
otherwise. Report lookup uses the bundle Scope to select that validated fact;
it does not relabel Category Order Count as overall Order Count.

### 7.3 Evaluation History

The original `data/reports/EVAL-001_diagnosis_regression.json` and
`eval_runs/EVAL-001_v1/` remain unchanged as the failing baseline. The rerun is
written to `data/reports/FIX-001_gate_5_regression.json` and
`eval_runs/FIX-001_v1/`.

## 8. Local Plan

1. Add focused failing tests for all missing Scope values and both valid and
   invalid decomposition lineage/Scope combinations.
2. Implement the minimal catalog and Evidence contract corrections.
3. Add destination arguments without changing EVAL-001 evaluation behavior.
4. Run targeted tests and rebuild only the isolated V1 Metadata indexes.
5. Run the unchanged D01-D10 live read-only regression and record exact metrics.
6. Run full pytest, Ruff, mypy, secret/safe-artifact scans, and Diff Review.
7. Write the completion report, update status, create one commit, push, and stop.

## 9. Validation Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/metadata/test_catalog.py test/diagnosis/test_analysis_question_parser.py test/diagnosis/test_evidence_report.py test/evaluation/test_diagnosis_regression.py
.\.venv\Scripts\python.exe -m app.scripts.build_meta_knowledge_v1
.\.venv\Scripts\python.exe -m app.scripts.evaluate_diagnosis_v1 --report data/reports/FIX-001_gate_5_regression.json --run-dir eval_runs/FIX-001_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

## 10. Acceptance Criteria

1. The five missing canonical Scope values are proven present in the isolated
   warehouse and resolve exactly through the deterministic Parser.
2. Existing registered aliases and unknown-Scope rejection remain intact.
3. Overall/Region decomposition retains overall `order_count`/`aov` lineage.
4. A single Category Scope uses `category_order_count` for decomposition and
   candidate Evidence and passes validation without claiming it is overall
   Order Count.
5. Cross-grain, incomplete, duplicate, or version-conflicting lineage fails
   closed.
6. The Metadata rebuild succeeds only against the isolated V1 targets.
7. The immutable EVAL-001 first baseline artifacts remain byte-for-byte
   unchanged.
8. The unchanged D01-D10 regression completes all ten chains, records true
   metrics, and Gate 5 passes.
9. Persisted outputs contain no raw SQL, rows, parameters, credentials,
   connection details, or Ground Truth database payloads.
10. Full pytest passes and Ruff/mypy do not regress the accepted 31/36 baseline.
11. Diff is limited to the allowed FIX-001 files; API-001 is not started.

## 11. Completion Boundary

After the report, status, independent commit, and push are complete, stop
FIX-001. API-001 requires a separate next-Feature cycle even if Gate 5 passes.
