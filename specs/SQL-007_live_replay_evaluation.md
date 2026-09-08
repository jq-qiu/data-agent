# SQL-007 NL2SQL Live/Replay Evaluation

Add a deterministic replay mode to the NL2SQL evaluator so one live external-service
run can be reproduced locally without invoking the model, retrieval services, or DW.

## In Scope

- Record every `NL2SQLRun` from live mode in a local replay cache.
- Preserve database scalar types required by result checksum normalization.
- Bind caches to dataset, prompt bundle, metadata, policy, model, and evaluator versions.
- Reject tampered, stale, incomplete, or extra-case caches.
- Add `--mode live|replay` and `--replay-cache` CLI options.
- Keep replay mode free of external client initialization and reference SQL execution.
- Unit tests and current documentation.

## Out of Scope

- No real-model 30-case rerun in this Feature.
- No SQL prompt, Validator, SchemaLinkingPlan, Golden Dataset, or historical artifact change.
- No production query result or credential may be committed; the default cache stays under
  the Git-ignored `.tmp/` directory.

## Allowed Files

- `app/nl2sql/evaluation.py`
- `app/scripts/evaluate_nl2sql_v1.py`
- `test/nl2sql/test_evaluation.py`
- `docs/06_evaluation.md`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- This Spec and its Completion Report

## Acceptance

- A recorded run replays to an identical evaluation result.
- Decimal, temporal, bytes, numeric, boolean, null, and text cells round-trip exactly.
- Cache identity and content-integrity mismatches fail closed.
- Replay mode does not initialize external clients or execute reference SQL.
- Full pytest, Ruff, and mypy pass.
