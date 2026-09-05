# ANA-002 Completion Report

## Feature

ANA-002 Analysis Question Parser. The repository now has strict, serializable schemas and a deterministic, Metadata Catalog-backed parser for the frozen V1 GMV diagnosis structure. It extracts adjacent calendar-month periods, canonical Region/Category Scope, requested dimensions, and Traffic/Promotion/Inventory factors, or returns a fixed structured error. Capability assessment and all later diagnosis stages remain unimplemented.

## Changed Files

- `specs/ANA-002_analysis_question_parser.md`: frozen scope, output contract, allowed files, plan, and acceptance criteria;
- `app/diagnosis/question.py`: schemas, Catalog vocabulary adapter, deterministic parser, and injected async node;
- `app/diagnosis/__init__.py`: public exports for the accepted parser contract;
- `data/evaluation/analysis_question_parser_golden_v1.json`: 18 fixed parsed/error cases;
- `app/scripts/evaluate_analysis_question_parser_v1.py`: deterministic evaluation and report entry point;
- `data/reports/ANA-002_analysis_question_parser_evaluation.json`: real per-case parsing evidence;
- `test/diagnosis/test_analysis_question_parser.py`: schema, time, metric, Scope, semantic-boundary, error, node, and evaluation tests;
- `IMPLEMENTATION_STATUS.md`, `ANA-002_COMPLETION.md`: completion and next-Feature status.

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_analysis_question_parser.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_analysis_question_parser_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check app/diagnosis app/scripts/evaluate_analysis_question_parser_v1.py test/diagnosis/test_analysis_question_parser.py
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app/diagnosis app/scripts/evaluate_analysis_question_parser_v1.py
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## Test Results

- ANA-002 targeted tests: 19 passed;
- full pytest regression: 109 passed;
- schema invariants, month boundaries, cross-year baseline, Catalog aliases, Scope normalization, semantic request boundaries, structured errors, JSON node output, and fixed evaluation all passed;
- no external model, database, vector store, or search service was used.

## Lint Results

Ruff executed against the full repository and reported 31 existing diagnostics, unchanged from ANA-001 and below the ENG-001 baseline of 51. All ANA-002 Python and test files pass Ruff.

## Type Check Results

mypy executed against `app` and reported 36 existing errors in 11 files, unchanged from ANA-001 and below the ENG-001 baseline of 40 errors in 14 files. A targeted mypy run for all ANA-002 modules passed with no issues.

## Evaluation Results

Dataset `analysis-question-parser-golden-v1` contains 18 fixed functional cases: 10 successful parses and 8 required error paths.

| Metric | Result |
|---|---:|
| Exact Outcome Match | 18/18 |
| Successful Parse Match | 10/10 |
| Structured Error Match | 8/8 |
| Target Metric Match | 10/10 |
| Current Period Match | 10/10 |
| Baseline Period Match | 10/10 |
| Comparison Type Match | 10/10 |
| Scope Match | 10/10 |
| Requested Dimensions Match | 10/10 |
| Requested Factors Match | 10/10 |
| Failed Cases | 0 |

This is a deterministic V1 functional set, not a production-language generalization benchmark.

## Acceptance Criteria

- PASS: schemas reject unknown fields, invalid values, reverse periods, duplicates, and mixed success/error outcomes;
- PASS: target Metric and canonical Scope values come from the injected `metadata-v1` Catalog vocabulary;
- PASS: only `gmv` diagnosis succeeds, except the frozen all-factor question safely resolves to the V1 GMV target after DIAGNOSIS routing;
- PASS: `YYYY年M月` and `YYYY-MM` normalize to exact calendar boundaries, including December-to-January rollover;
- PASS: one current month safely derives its previous month, two adjacent months sort correctly, and incomplete/non-adjacent periods fail structurally;
- PASS: general reason requests default to unscoped V1 dimensions and all three candidate factors;
- PASS: decomposition, contribution, and explicit factor requests do not add unrelated requested semantics;
- PASS: registered region/category aliases canonicalize correctly; multiple and unregistered Scope values fail structurally;
- PASS: non-DIAGNOSIS input, non-GMV target, missing/invalid time, missing baseline, and invalid Scope use frozen workflow error codes;
- PASS: the injected async node emits JSON-only state and holds Catalog-derived vocabulary outside Agent State;
- PASS: all 18 fixed cases match exactly with no failed case;
- PASS: full pytest passes and Ruff/mypy remain at the accepted baseline;
- PASS: Query Graph, NL2SQL, SQL policy, Metadata configuration, databases, data, and API are unchanged.

## Known Issues

- The parser intentionally accepts only adjacent calendar-month comparisons in the two documented month formats. Quarter, week, arbitrary date range, and non-adjacent comparison requests degrade for later scope decisions.
- Natural-language handling is deliberately deterministic and high precision. Unregistered Region/Category values and novel phrasing fail rather than being guessed or sent to an LLM.
- The Catalog currently contains explicit aliases for six Brazilian states and five categories; the parser can only canonicalize values registered there.
- The parser node is not wired into the production Graph because ANA-003 and later diagnosis nodes do not exist yet.
- The repository retains 31 Ruff diagnostics and 36 mypy errors in 11 files from the accepted baseline.

## Diff Review Summary

- scope review: only ANA-002 schemas/parser, fixed evaluation, tests, Spec, report, and status files changed;
- architecture review: Catalog-derived vocabulary is injected into the parser/node and no Client, Repository, LLM, Registry, or connection object enters Agent State;
- semantic review: Metric, periods, Scope, dimensions, and factors are separated; the parser does not decide data capability or analysis methods;
- safety review: unknown metrics, missing/invalid time, incomplete baseline, multiple Scope values, unregistered Scope, and wrong intent stop with structured errors;
- isolation review: no database command ran and neither `data_agent_v1_dw` nor original `dw` was accessed or modified;
- security review: the diff contains no API Key, database password, Token, Cookie, or full connection string;
- downstream review: capability, planning, query execution, analysis, Evidence, report generation, Graph wiring, and API were not implemented;
- whitespace review: `git diff --check` passed.
