"""封装字段值索引的写入与检索，不承担语义判断或业务计算。"""

from dataclasses import asdict

from elastic_transport import ObjectApiResponse
from elasticsearch import AsyncElasticsearch

from app.conf.app_config import app_config
from app.entities.value_info import ValueInfo


class ValueESRepository:
    """操作字段取值ES持久层类"""

    def __init__(
        self,
        client: AsyncElasticsearch,
        index_name: str | None = None,
        analyzer: str | None = None,
        number_of_shards: int | None = None,
        number_of_replicas: int | None = None,
    ):
        self.client = client
        self.idx_name = index_name or app_config.es.index_name
        self.analyzer = analyzer or app_config.es.analyzer
        self.number_of_shards = number_of_shards or app_config.es.number_of_shards
        if number_of_replicas is None:
            number_of_replicas = app_config.es.number_of_replicas
        self.number_of_replicas = number_of_replicas
        self.es_index_settings = {
            "number_of_shards": self.number_of_shards,
            "number_of_replicas": self.number_of_replicas,
        }
        self.es_index_mappings = {
            "dynamic": False,
            "properties": {
                "id": {"type": "keyword"},
                "value": {
                    "type": "text",
                    "analyzer": self.analyzer,
                    "search_analyzer": self.analyzer,
                },
                "column_id": {"type": "keyword"},
            },
        }

    async def ensure_index(self):
        # 判断索引库是否存在
        if await self.client.indices.exists(index=self.idx_name):
            # 副本数是动态设置，确保已有索引也符合当前单节点配置。
            await self.client.indices.put_settings(
                index=self.idx_name,
                settings={"number_of_replicas": self.number_of_replicas},
            )
            await self.ensure_ready()
            return

        # 创建索引库
        await self.client.indices.create(
            index=self.idx_name, settings=self.es_index_settings, mappings=self.es_index_mappings
        )

        await self.ensure_ready()

    async def ensure_ready(self):
        """确保索引主分片已分配，避免构建到写入阶段才失败。"""
        health = await self.client.cluster.health(
            index=self.idx_name,
            wait_for_status="yellow",
            timeout="10s",
        )
        if health.get("status") == "red":
            raise RuntimeError(
                f"ES索引 {self.idx_name} 主分片未分配，"
                "请检查ES节点磁盘空间和 _cluster/allocation/explain"
            )

    async def upsert(self, value_infos: list[ValueInfo], batch_size=10):
        if not value_infos:
            return

        for i in range(0, len(value_infos), batch_size):
            batch = value_infos[i : i + batch_size]
            operations: list = []
            for value_info in batch:
                # 指定操作的索引库以及文档ID
                operations.append({"index": {"_index": self.idx_name, "_id": value_info.id}})
                # 指定文档内容
                operations.append(asdict(value_info))
            # 将本批次数据批量写入ES
            response = await self.client.bulk(operations=operations)
            if response.get("errors"):
                failed_items = [
                    item["index"] for item in response["items"] if item["index"].get("error")
                ]
                first_error = failed_items[0] if failed_items else "unknown bulk error"
                raise RuntimeError(f"ES批量写入失败: {first_error}")

        # 构建脚本返回前保证新文档可以立即被检索。
        await self.client.indices.refresh(index=self.idx_name)

    """
    #条件检索 采用全文查询match 特点：先对文本进行分词，根据分词后词条进行检索
        POST data_agent/_search
        {
          "from":0,
          "size": 10,
          "query": {
            "match": {
              "value": "广东地区"
            }
          },
          "min_score": 0.6
        }
    """

    async def search(
        self, keyword: str, score_threshold: float = 0.6, limit: int = 10
    ) -> list[ValueInfo]:
        # 1.执行全文检索
        result: ObjectApiResponse = await self.client.search(
            # 索引库名称 不指定会查询所有索引库
            index=self.idx_name,
            # 查询条件，采用match全文查询
            query={"match": {"value": keyword}},
            # 相关性得分
            min_score=score_threshold,
            # 返回记录数
            size=limit,
        )
        # 2.解析ES结果
        return [ValueInfo(**hit["_source"]) for hit in result["hits"]["hits"]]

    async def search_v1_grounded(self, keyword: str, limit: int = 5) -> list[ValueInfo]:
        """返回带规范列 ID 的有限候选，最终绑定仍由 SemanticGrounder 判断。"""

        result = await self.client.search(
            index="data-agent-value-v1",
            query={
                "bool": {
                    "should": [
                        {"term": {"canonical_value": {"value": keyword, "boost": 8}}},
                        {"term": {"aliases": {"value": keyword, "boost": 10}}},
                        {"match_phrase": {"matched_value": keyword}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            size=limit,
        )
        hits = result["hits"]["hits"]
        exact_hits = [
            hit
            for hit in hits
            if keyword == str(hit["_source"]["canonical_value"])
            or keyword in hit["_source"].get("aliases", [])
        ]
        selected_hits = exact_hits or hits
        return [
            ValueInfo(
                id=str(hit["_source"]["id"]),
                value=str(hit["_source"]["canonical_value"]),
                column_id=str(hit["_source"]["column_id"]),
                matched_value=keyword,
            )
            for hit in selected_hits
        ]
