from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from elasticsearch import AsyncElasticsearch
from langchain_core.embeddings import Embeddings
from qdrant_client import AsyncQdrantClient

from app.metadata.catalog import MetadataCatalog
from app.metadata.retrieval import query_metadata_by_vector, retrieve_value

TABLE_LIMIT = 5
COLUMN_LIMIT = 10
RELATIONSHIP_LIMIT = 5


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    question: str
    expected_metric_ids: tuple[str, ...]
    expected_tables: tuple[str, ...]
    expected_columns: tuple[str, ...]
    expected_join_relations: tuple[str, ...]
    expected_values: tuple[tuple[str, str], ...]
    required_grain_warning: bool


def load_golden_cases(path: Path) -> tuple[GoldenCase, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        GoldenCase(
            case_id=item["case_id"],
            question=item["question"],
            expected_metric_ids=tuple(item.get("expected_metric_ids", [])),
            expected_tables=tuple(item.get("expected_tables", [])),
            expected_columns=tuple(item.get("expected_columns", [])),
            expected_join_relations=tuple(item.get("expected_join_relations", [])),
            expected_values=tuple(
                (value["column_id"], value["canonical_value"])
                for value in item.get("expected_values", [])
            ),
            required_grain_warning=bool(item.get("required_grain_warning", False)),
        )
        for item in raw
    )


def _recall(expected: set[str], actual: set[str]) -> float | None:
    if not expected:
        return None
    return len(expected & actual) / len(expected)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 1.0


def _lexical_metrics(catalog: MetadataCatalog, question: str) -> list[str]:
    normalized = question.casefold()
    matches: list[tuple[int, str]] = []
    for metric in catalog.metrics:
        terms = (metric.metric_id, metric.display_name, *metric.aliases)
        longest = max(
            (len(term) for term in terms if term.casefold() in normalized),
            default=0,
        )
        if longest:
            matches.append((longest, metric.metric_id))
    return [metric_id for _, metric_id in sorted(matches, reverse=True)]


def _append_unique(target: list[str], values: list[str] | tuple[str, ...]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _shortest_relation_path(
    catalog: MetadataCatalog,
    start: str,
    end: str,
) -> list[str]:
    if start == end:
        return []
    queue: list[tuple[str, list[str]]] = [(start, [])]
    visited = {start}
    while queue:
        table, path = queue.pop(0)
        for relation in catalog.relationships:
            if not relation.allowed:
                continue
            if relation.left_table == table:
                neighbor = relation.right_table
            elif relation.right_table == table:
                neighbor = relation.left_table
            else:
                continue
            if neighbor == end:
                return [*path, relation.relation_id]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, [*path, relation.relation_id]))
    return []


async def evaluate_metadata(
    catalog: MetadataCatalog,
    cases: tuple[GoldenCase, ...],
    qdrant: AsyncQdrantClient,
    elasticsearch: AsyncElasticsearch,
    embeddings: Embeddings,
) -> dict[str, Any]:
    vectors = await embeddings.aembed_documents([case.question for case in cases])
    catalog_metrics = {item.metric_id: item for item in catalog.metrics}
    catalog_relations = {item.relation_id: item for item in catalog.relationships}
    case_results: list[dict[str, Any]] = []
    metric_hits: list[float] = []
    reciprocal_ranks: list[float] = []
    table_recalls: list[float] = []
    column_recalls: list[float] = []
    join_recalls: list[float] = []
    value_hits: list[float] = []
    context_precisions: list[float] = []
    context_recalls: list[float] = []
    token_counts: list[int] = []
    warning_results: list[bool] = []

    for case, vector in zip(cases, vectors, strict=True):
        metrics = await query_metadata_by_vector(qdrant, vector, "metric", 5)
        tables = await query_metadata_by_vector(qdrant, vector, "table", 5)
        columns = await query_metadata_by_vector(qdrant, vector, "column", 10)
        relations = await query_metadata_by_vector(qdrant, vector, "relationship", 5)
        values = await retrieve_value(elasticsearch, case.question, limit=5)

        semantic_metric_ids = [item.object_id for item in metrics]
        lexical_metric_ids = _lexical_metrics(catalog, case.question)
        metric_ids = [*lexical_metric_ids]
        _append_unique(metric_ids, semantic_metric_ids)
        semantic_table_ids = [item.object_id for item in tables]
        semantic_column_ids = [item.object_id for item in columns]
        table_ids: list[str] = []
        column_ids: list[str] = []
        relation_ids = [item.object_id for item in relations]

        for metric_id in lexical_metric_ids:
            metric = catalog_metrics[metric_id]
            _append_unique(column_ids, metric.relevant_columns)
            _append_unique(
                table_ids,
                [column_id.split(".", 1)[0] for column_id in metric.relevant_columns],
            )
        for value in values:
            column_id = value["column_id"]
            table_id = column_id.split(".", 1)[0]
            _append_unique(column_ids, [column_id])
            _append_unique(table_ids, [table_id])

        anchor_tables = [*table_ids]
        _append_unique(anchor_tables, semantic_table_ids[:2])
        if any(token in case.question for token in ("年", "月", "日", "周", "季度", "趋势")):
            _append_unique(anchor_tables, ["dim_date"])
        path_relations: list[str] = []
        for index, left_table in enumerate(anchor_tables):
            for right_table in anchor_tables[index + 1 :]:
                _append_unique(
                    path_relations,
                    _shortest_relation_path(catalog, left_table, right_table),
                )
        relation_ids = [*path_relations, *relation_ids]
        relation_ids = list(dict.fromkeys(relation_ids))
        for relation_id in path_relations:
            relation = catalog_relations[relation_id]
            _append_unique(table_ids, [relation.left_table, relation.right_table])
            _append_unique(
                column_ids,
                [
                    f"{relation.left_table}.{relation.left_column}",
                    f"{relation.right_table}.{relation.right_column}",
                ],
            )
        _append_unique(table_ids, semantic_table_ids)
        _append_unique(column_ids, semantic_column_ids)

        table_set = set(table_ids[:TABLE_LIMIT])
        for relation_id, relation in catalog_relations.items():
            if (
                relation.left_table in table_set
                and relation.right_table in table_set
                and relation_id not in relation_ids
            ):
                relation_ids.append(relation_id)

        expected_metric_set = set(case.expected_metric_ids)
        expected_table_set = set(case.expected_tables)
        expected_column_set = set(case.expected_columns)
        expected_relation_set = set(case.expected_join_relations)
        actual_value_set = {(value["column_id"], value["canonical_value"]) for value in values}
        expected_value_set = set(case.expected_values)

        if expected_metric_set:
            hit = float(bool(metric_ids and metric_ids[0] in expected_metric_set))
            metric_hits.append(hit)
            rank = next(
                (index + 1 for index, item in enumerate(metric_ids) if item in expected_metric_set),
                None,
            )
            reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        table_recall = _recall(expected_table_set, set(table_ids[:TABLE_LIMIT]))
        column_recall = _recall(expected_column_set, set(column_ids[:COLUMN_LIMIT]))
        join_recall = _recall(expected_relation_set, set(relation_ids[:RELATIONSHIP_LIMIT]))
        if table_recall is not None:
            table_recalls.append(table_recall)
        if column_recall is not None:
            column_recalls.append(column_recall)
        if join_recall is not None:
            join_recalls.append(join_recall)
        if expected_value_set:
            value_hits.append(len(expected_value_set & actual_value_set) / len(expected_value_set))

        actual_context = (
            {f"metric:{item}" for item in metric_ids[:1]}
            | {f"table:{item}" for item in table_ids[:TABLE_LIMIT]}
            | {f"column:{item}" for item in column_ids[:COLUMN_LIMIT]}
            | {f"relationship:{item}" for item in relation_ids[:RELATIONSHIP_LIMIT]}
            | {f"value:{column}:{value}" for column, value in actual_value_set}
        )
        expected_context = (
            {f"metric:{item}" for item in expected_metric_set}
            | {f"table:{item}" for item in expected_table_set}
            | {f"column:{item}" for item in expected_column_set}
            | {f"relationship:{item}" for item in expected_relation_set}
            | {f"value:{column}:{value}" for column, value in expected_value_set}
        )
        context_precisions.append(
            len(actual_context & expected_context) / len(actual_context) if actual_context else 1.0
        )
        context_recalls.append(
            len(actual_context & expected_context) / len(expected_context)
            if expected_context
            else 1.0
        )
        context_text = " ".join(sorted(actual_context))
        token_count = len(context_text.encode("utf-8")) // 4 + 1
        token_counts.append(token_count)
        warnings = [
            catalog_relations[item].grain_warning
            for item in relation_ids[:RELATIONSHIP_LIMIT]
            if catalog_relations[item].grain_warning
        ]
        warning_ok = not case.required_grain_warning or bool(warnings)
        warning_results.append(warning_ok)

        case_results.append(
            {
                "case_id": case.case_id,
                "metric_top1": metric_ids[:1],
                "tables": table_ids[:TABLE_LIMIT],
                "columns": column_ids[:COLUMN_LIMIT],
                "join_relations": relation_ids[:RELATIONSHIP_LIMIT],
                "values": values,
                "grain_warnings": warnings,
                "table_recall": table_recall,
                "column_recall": column_recall,
                "join_key_recall": join_recall,
                "warning_ok": warning_ok,
                "context_token_count": token_count,
            }
        )

    metrics_summary = {
        "metric_hit_at_1": _mean(metric_hits),
        "mrr": _mean(reciprocal_ranks),
        "table_recall_at_5": _mean(table_recalls),
        "column_recall_at_10": _mean(column_recalls),
        "join_key_recall_at_5": _mean(join_recalls),
        "value_grounding_accuracy": _mean(value_hits),
        "context_precision": _mean(context_precisions),
        "context_recall": _mean(context_recalls),
        "average_context_token_count": _mean([float(value) for value in token_counts]),
        "max_context_token_count": max(token_counts, default=0),
        "grain_warning_accuracy": _mean([float(value) for value in warning_results]),
    }
    thresholds = {
        "metric_hit_at_1": 0.8,
        "table_recall_at_5": 0.85,
        "column_recall_at_10": 0.8,
        "join_key_recall_at_5": 0.8,
        "value_grounding_accuracy": 0.8,
        "grain_warning_accuracy": 1.0,
    }
    gate_checks = {
        name: metrics_summary[name] >= threshold for name, threshold in thresholds.items()
    }
    return {
        "dataset_version": "metadata-golden-v1",
        "metadata_version": catalog.version,
        "case_count": len(cases),
        "retrieval_limits": {
            "metric": 1,
            "table": TABLE_LIMIT,
            "column": COLUMN_LIMIT,
            "relationship": RELATIONSHIP_LIMIT,
            "value": 5,
        },
        "metrics": metrics_summary,
        "thresholds": thresholds,
        "gate_checks": gate_checks,
        "gate_2_passed": all(gate_checks.values()),
        "cases": case_results,
    }
