from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from elasticsearch import AsyncElasticsearch
from langchain_core.embeddings import Embeddings
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.metadata.catalog import MetadataCatalog

COLLECTION_NAME = "data-agent-metadata-v1"
VALUE_INDEX_NAME = "data-agent-value-v1"
POINT_NAMESPACE = uuid.UUID("67467ea9-f413-5be7-9cee-bd57b58d58c8")


@dataclass(frozen=True)
class RetrievedItem:
    object_type: str
    object_id: str
    score: float
    grain_warning: str = ""


def metadata_documents(catalog: MetadataCatalog) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for table in catalog.tables:
        documents.append(
            {
                "object_type": "table",
                "object_id": table.table_name,
                "text": " ".join(
                    (table.table_name, *table.aliases, table.description, table.grain)
                ),
                "grain_warning": "",
            }
        )
        for column in table.columns:
            documents.append(
                {
                    "object_type": "column",
                    "object_id": f"{table.table_name}.{column.name}",
                    "text": " ".join(
                        (
                            table.table_name,
                            column.name,
                            *table.aliases,
                            *column.aliases,
                            column.description,
                        )
                    ),
                    "grain_warning": "",
                }
            )
    for metric in catalog.metrics:
        documents.append(
            {
                "object_type": "metric",
                "object_id": metric.metric_id,
                "text": " ".join(
                    (
                        metric.metric_id,
                        metric.display_name,
                        *metric.aliases,
                        metric.description,
                        metric.formula,
                    )
                ),
                "grain_warning": "",
            }
        )
    for relation in catalog.relationships:
        documents.append(
            {
                "object_type": "relationship",
                "object_id": relation.relation_id,
                "text": (
                    f"{relation.relation_id} {relation.left_table} {relation.left_column} "
                    f"{relation.right_table} {relation.right_column} {relation.cardinality} "
                    f"{relation.grain_warning}"
                ),
                "grain_warning": relation.grain_warning,
            }
        )
    return documents


async def rebuild_vector_index(
    client: AsyncQdrantClient,
    embedding_client: Embeddings,
    catalog: MetadataCatalog,
    embedding_size: int,
) -> int:
    documents = metadata_documents(catalog)
    embeddings = await embedding_client.aembed_documents([item["text"] for item in documents])
    if embeddings and len(embeddings[0]) != embedding_size:
        raise ValueError(
            f"embedding dimension {len(embeddings[0])} does not match configured {embedding_size}"
        )
    if await client.collection_exists(COLLECTION_NAME):
        await client.delete_collection(COLLECTION_NAME)
    await client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=embedding_size, distance=Distance.COSINE),
    )
    points = [
        PointStruct(
            id=str(uuid.uuid5(POINT_NAMESPACE, f"{item['object_type']}:{item['object_id']}")),
            vector=vector,
            payload={key: value for key, value in item.items() if key != "text"},
        )
        for item, vector in zip(documents, embeddings, strict=True)
    ]
    await client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)
    return len(points)


async def retrieve_metadata(
    client: AsyncQdrantClient,
    embedding_client: Embeddings,
    question: str,
    object_type: str,
    limit: int,
) -> list[RetrievedItem]:
    embedding = await embedding_client.aembed_query(question)
    return await query_metadata_by_vector(client, embedding, object_type, limit)


async def query_metadata_by_vector(
    client: AsyncQdrantClient,
    embedding: list[float],
    object_type: str,
    limit: int,
) -> list[RetrievedItem]:
    response = await client.query_points(
        collection_name=COLLECTION_NAME,
        query=embedding,
        query_filter=Filter(
            must=[FieldCondition(key="object_type", match=MatchValue(value=object_type))]
        ),
        limit=limit,
        with_payload=True,
    )
    return [
        RetrievedItem(
            object_type=str(point.payload["object_type"]),
            object_id=str(point.payload["object_id"]),
            score=float(point.score),
            grain_warning=str(point.payload.get("grain_warning", "")),
        )
        for point in response.points
        if point.payload is not None
    ]


def value_documents(catalog: MetadataCatalog, values: dict[str, list[str]]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for table in catalog.tables:
        for column in table.columns:
            if not column.value_index_enabled:
                continue
            column_id = f"{table.table_name}.{column.name}"
            actual_values = set(values.get(column_id, []))
            for canonical in sorted(actual_values):
                aliases = column.value_aliases.get(canonical, ())
                documents.append(
                    {
                        "id": str(uuid.uuid5(POINT_NAMESPACE, f"value:{column_id}:{canonical}")),
                        "column_id": column_id,
                        "canonical_value": canonical,
                        "matched_value": " ".join((canonical, *aliases)),
                        "aliases": list(aliases),
                    }
                )
            missing_alias_targets = set(column.value_aliases) - actual_values
            if missing_alias_targets:
                raise ValueError(
                    f"configured canonical values missing from {column_id}: "
                    f"{sorted(missing_alias_targets)}"
                )
    return documents


async def rebuild_value_index(
    client: AsyncElasticsearch,
    catalog: MetadataCatalog,
    values: dict[str, list[str]],
) -> int:
    documents = value_documents(catalog, values)
    if await client.indices.exists(index=VALUE_INDEX_NAME):
        await client.indices.delete(index=VALUE_INDEX_NAME)
    await client.indices.create(
        index=VALUE_INDEX_NAME,
        settings={"number_of_shards": 1, "number_of_replicas": 0},
        mappings={
            "dynamic": False,
            "properties": {
                "id": {"type": "keyword"},
                "column_id": {"type": "keyword"},
                "canonical_value": {"type": "keyword"},
                "matched_value": {"type": "text", "analyzer": "standard"},
                "aliases": {"type": "keyword"},
            },
        },
    )
    operations: list[dict[str, Any]] = []
    for document in documents:
        operations.append({"index": {"_index": VALUE_INDEX_NAME, "_id": document["id"]}})
        operations.append(document)
    if operations:
        response = await client.bulk(operations=operations)
        if response.get("errors"):
            raise RuntimeError("Elasticsearch value index bulk write failed")
    await client.indices.refresh(index=VALUE_INDEX_NAME)
    return len(documents)


async def retrieve_value(
    client: AsyncElasticsearch,
    question: str,
    limit: int = 5,
) -> list[dict[str, str]]:
    response = await client.search(
        index=VALUE_INDEX_NAME,
        query={"match": {"matched_value": question}},
        size=limit,
    )
    return [
        {
            "column_id": str(hit["_source"]["column_id"]),
            "canonical_value": str(hit["_source"]["canonical_value"]),
        }
        for hit in response["hits"]["hits"]
    ]
