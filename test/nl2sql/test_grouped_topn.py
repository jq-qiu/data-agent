from pathlib import Path

from app.metadata.catalog import load_catalog
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.validator import SQLValidator
from app.scripts.evaluate_grouped_topn_v1 import (
    GroupedTopNCase,
    evaluate_rows,
    load_grouped_topn_golden,
)

ROOT = Path(__file__).parents[2]


def test_grouped_topn_golden_has_four_valid_reference_traces() -> None:
    dataset_version, cases = load_grouped_topn_golden()
    validator = SQLValidator(
        load_catalog(ROOT / "conf" / "meta_config.yaml"),
        load_sql_policy(ROOT / "conf" / "sql_policy.yaml"),
    )

    assert dataset_version == "grouped-topn-golden-v1"
    assert len(cases) == 4
    for case in cases:
        validated = validator.validate(case.reference_sql, case.expected_metric_ids)
        assert set(validated.tables) == set(case.expected_tables), case.case_id
        assert set(validated.columns) == set(case.expected_columns), case.case_id
        assert set(validated.join_relations) == set(
            case.expected_join_relations
        ), case.case_id


def test_grouped_topn_shape_evaluation_checks_rank_limit_and_order() -> None:
    case = GroupedTopNCase(
        case_id="unit",
        question="fixed test",
        n=2,
        group_column="group_id",
        rank_column="rank_position",
        expected_metric_ids=(),
        expected_tables=(),
        expected_columns=(),
        expected_join_relations=(),
        reference_sql="SELECT 1",
        expected_result_sha256=None,
    )
    valid = evaluate_rows(
        case,
        [
            {"group_id": "A", "item_id": "1", "rank_position": 1},
            {"group_id": "A", "item_id": "2", "rank_position": 2},
            {"group_id": "B", "item_id": "3", "rank_position": 1},
        ],
    )
    invalid = evaluate_rows(
        case,
        [
            {"group_id": "B", "item_id": "1", "rank_position": 1},
            {"group_id": "A", "item_id": "2", "rank_position": 2},
            {"group_id": "A", "item_id": "3", "rank_position": 3},
            {"group_id": "A", "item_id": "4", "rank_position": 4},
        ],
    )

    assert valid["rank_sequences_valid"] is True
    assert valid["per_group_limit_valid"] is True
    assert valid["deterministic_order_valid"] is True
    assert invalid["rank_sequences_valid"] is False
    assert invalid["per_group_limit_valid"] is False
    assert invalid["deterministic_order_valid"] is False
