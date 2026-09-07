"""封装列向量索引的写入与相似度检索。"""

from dataclasses import asdict
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    QueryResponse,
    VectorParams,
)

from app.conf.app_config import app_config
from app.entities.column_info import ColumnInfo


def _payload(point: Any) -> dict[str, Any]:
    payload = point.payload
    if not isinstance(payload, dict):
        raise TypeError("Qdrant point returned no valid payload")
    return payload


class ColumnQdrantRepository:
    """列向量持久层；只返回检索候选，不决定哪些列可以进入 SQL。"""

    coll_name = "data-agent-column"

    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def _create_collection(self):
        await self.client.create_collection(
            collection_name=self.coll_name,
            vectors_config=VectorParams(
                size=app_config.qdrant.embedding_size, distance=Distance.COSINE
            ),
        )

    async def ensure_collection(self):
        if not await self.client.collection_exists(collection_name=self.coll_name):
            await self._create_collection()

    async def reset_collection(self):
        """完整重建索引时清理旧向量，避免重复构建产生重复数据。"""
        if await self.client.collection_exists(collection_name=self.coll_name):
            await self.client.delete_collection(collection_name=self.coll_name)
        await self._create_collection()

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        payloads: list[ColumnInfo],
        batch_size: int = 10,
    ):
        # 1.采用zip函数，按照"索引下标"打包为元组迭代器 [(id,vector,payload),(id,vector,payload),(id,vector,payload)]
        zipped = list(zip(ids, embeddings, payloads))

        # 2.采用分批次保存向量数据点到qdrant
        for i in range(0, len(zipped), batch_size):
            batch = zipped[i : i + batch_size]
            points = [
                PointStruct(
                    id=id,
                    vector=embeding,
                    # 注意：向量点元信息必须是字典结构
                    payload=asdict(payload),
                )
                for id, embeding, payload in batch
            ]
            await self.client.upsert(collection_name=self.coll_name, points=points)

    async def search(
        self, embedding: list[float], score_threshold: float = 0.6, limit: int = 10
    ) -> list[ColumnInfo]:
        result: QueryResponse = await self.client.query_points(
            collection_name=self.coll_name,
            query=embedding,
            score_threshold=score_threshold,
            limit=limit,
        )
        # **point.payload  解构表达式 将Qdrant中payload字典{id:"abc"}转为id="abc"
        return [ColumnInfo(**_payload(point)) for point in result.points]

    async def search_v1_ids(self, embedding: list[float], limit: int = 10) -> list[str]:
        result = await self.client.query_points(
            collection_name="data-agent-metadata-v1",
            query=embedding,
            query_filter=Filter(
                must=[FieldCondition(key="object_type", match=MatchValue(value="column"))]
            ),
            limit=limit,
            with_payload=True,
        )
        return [
            str(point.payload["object_id"]) for point in result.points if point.payload is not None
        ]
