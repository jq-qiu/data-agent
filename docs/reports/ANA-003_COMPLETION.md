# ANA-003 Completion Report

## Feature

ANA-003 Capability Assessment. The repository now has strict Data Capability Profile and Assessment schemas plus a deterministic, Catalog-validated assessor for V1 GMV diagnosis. It gates each requested method on period coverage, scoped data grain, required non-empty columns, and data quality, while permanently excluding causal inference from V1.

## Changed Files

- `specs/ANA-003_capability_assessment.md`: frozen scope, capability contract, dependencies, plan, and acceptance criteria;
- `app/diagnosis/capability.py`: Profile/Method/Level/Assessment schemas, Catalog contract checks, capability rules, and injected node;
- `app/diagnosis/__init__.py`: public exports for the accepted capability contract;
- `data/evaluation/capability_assessment_golden_v1.json`: 13 fixed full, limited, blocked, Synthetic, category-scope, and causal-boundary cases;
- `app/scripts/evaluate_capability_assessment_v1.py`: deterministic evaluation and report entry point;
- `data/reports/ANA-003_capability_assessment_evaluation.json`: real per-case capability evidence;
- `test/diagnosis/test_capability_assessment.py`: schema, Catalog, time, grain, Evidence, quality, causal, node, and evaluation tests;
- `IMPLEMENTATION_STATUS.md`, `ANA-003_COMPLETION.md`: completion and next-Feature status.

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_capability_assessment.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_capability_assessment_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check app/diagnosis app/scripts/evaluate_capability_assessment_v1.py test/diagnosis/test_capability_assessment.py
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app/diagnosis app/scripts/evaluate_capability_assessment_v1.py
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## Test Results

- ANA-003 targeted tests: 15 passed;
- full pytest regression: 124 passed;
- schema, Catalog contract, period coverage, data-grain, missing Evidence, data quality, Synthetic degradation, causal boundary, serialization, and evaluation tests passed;
- no external model, database, vector store, or search service was used.

## Lint Results

Ruff executed against the full repository and reported 31 existing diagnostics, unchanged from ANA-002 and below the ENG-001 baseline of 51. All ANA-003 Python and test files pass Ruff.

## Type Check Results

mypy executed against `app` and reported 36 existing errors in 11 files, unchanged from ANA-002 and below the ENG-001 baseline of 40 errors in 14 files. A targeted mypy run for all ANA-003 modules passed with no issues.

## Evaluation Results

Dataset `capability-assessment-golden-v1` contains 13 fixed functional cases spanning full capability, requested subsets, partial Evidence, partial dimensions, missing periods/GMV, failed data quality, Synthetic missing Evidence, category Scope, and the causal boundary.

| Metric | Result |
|---|---:|
| Exact Assessment Match | 13/13 |
| Correct Degradation | 8/8 |
| Causal Method Allowed | 0/13 |
| Methods Allowed on Failed Data Quality | 0/1 |
| Failed Cases | 0 |

This is a deterministic V1 functional set, not a production capability or language-generalization benchmark.

## Acceptance Criteria

- PASS: Profile and Assessment schemas reject unknown fields, invalid periods, duplicate/unqualified columns, unstable issue references, duplicate/disordered methods, and invalid causal capability;
- PASS: every Data Profile column is validated against `metadata-v1`, including all table/column and required relationship contracts;
- PASS: a complete general GMV request opens six V1 methods and leaves only `causal_inference` unsupported;
- PASS: missing current/baseline coverage or scoped GMV closes every requested downstream method;
- PASS: missing overall Order Count preserves period comparison and independent dimension capability while closing decomposition and dependent factor validations;
- PASS: Region and Category contribution availability is evaluated from their own grain-specific fields;
- PASS: single Category Scope uses its category GMV and `category_order_count`; category order counts are never used across categories or for overall decomposition;
- PASS: a missing Promotion or Inventory field closes only that factor method when shared components remain available;
- PASS: Synthetic missing Visitors closes all candidate validations that require Conversion while preserving structural methods;
- PASS: data quality failure closes all requested methods and reports stable issue codes;
- PASS: an experimental-design flag cannot open causal inference because strict causality remains outside V1;
- PASS: the injected node emits only JSON capability State and does not expose Catalog or Profile objects;
- PASS: all 13 fixed cases match exactly, 8/8 degradation cases pass, and prohibited method counts remain zero;
- PASS: full pytest passes and Ruff/mypy remain at the accepted baseline;
- PASS: Parser, Query Graph, NL2SQL, SQL policy, Metadata configuration, data, databases, and API are unchanged.

## Known Issues

- ANA-003 consumes an injected request-scoped Data Profile; automatic construction from live repositories is intentionally deferred to the later runtime integration Feature. This Feature does not claim that static Catalog presence alone proves non-empty data.
- Period availability is represented as one contiguous request-scoped range. Slice-specific row counts and freshness must be resolved before constructing the Profile.
- When one requested dimension is available and another is missing, `dimension_contribution` remains supported and `available_dimensions` restricts the later Planner to the valid subset; ANA-004 must honor that intersection.
- Candidate-factor capability confirms only data availability, not direction, strength, or causal effect.
- The diagnosis branch remains unwired until the required downstream nodes exist.
- The repository retains 31 Ruff diagnostics and 36 mypy errors in 11 files from the accepted baseline.

## Diff Review Summary

- scope review: only ANA-003 capability schemas/rules, fixed evaluation, tests, Spec, report, and status files changed;
- architecture review: Catalog and request-scoped Profile are injected dependencies; Agent State receives only the serialized Assessment;
- grain review: overall/region decomposition uses region DWS Order Count, while category Order Count is accepted only within one Category Scope;
- degradation review: period, base metric, data quality, dimension, shared component, and factor-specific absence close only the methods permitted by the frozen rules;
- causal review: `causal_inference` is structurally prohibited regardless of the experimental flag;
- isolation review: no database command ran and neither `data_agent_v1_dw` nor original `dw` was accessed or modified;
- security review: Assessment outputs only stable method/dimension names, date roles, quality codes, and Catalog column IDs; no credential or raw data value is emitted;
- downstream review: planning, tasks, SQL, execution, numeric analysis, Evidence validation, reports, Graph wiring, and API were not implemented;
- whitespace review: `git diff --check` passed.
