"""管理 Elasticsearch 异步客户端的初始化、访问与关闭。"""

import asyncio

from elasticsearch import AsyncElasticsearch

from app.conf.app_config import ESConfig, app_config


class ESClientManager:
    """持有单个异步 ES 客户端；未初始化访问会立即失败，避免传播 None。"""

    def __init__(self, config: ESConfig):
        self.config = config
        self._client: AsyncElasticsearch | None = None

    @property
    def client(self) -> AsyncElasticsearch:
        # 未启动时直接报错，避免下游拿到 Optional 客户端后在更深层才失败。
        if self._client is None:
            raise RuntimeError("Elasticsearch client is not initialized; call init() first")
        return self._client

    def _get_url(self):
        return f"http://{self.config.host}:{self.config.port}"

    def init(self):
        """依据配置创建连接；索引名称和检索策略仍由 Repository 管理。"""

        self._client = AsyncElasticsearch(
            hosts=self._get_url(),
            request_timeout=600
        )

    async def close(self):
        """释放底层连接；生命周期由 FastAPI lifespan 或命令行入口负责。"""

        if self._client:
            await self._client.close()


es_client_manager = ESClientManager(app_config.es)

if __name__ == '__main__':
    es_client_manager.init()
    client = es_client_manager.client

    idx_name = "test"


    async def test_index():
        """采用显示映射创建索引库"""
        if not await client.indices.exists(index=idx_name):
            resp = await client.indices.create(
                index=idx_name,
                mappings={
                    "dynamic": False,
                    "properties": {
                        "id": {
                            "type": "long"
                        },
                        "name": {
                            "type": "text",
                            "analyzer": app_config.es.analyzer
                        },
                        "brand": {
                            "type": "keyword"
                        },
                        "image": {
                            "type": "keyword",
                            "index": False
                        },
                        "price": {
                            "type": "float"
                        }
                    }
                }
            )
            print(resp)
        await es_client_manager.close()


    # asyncio.run(test_index())

    async def test_doc():
        await client.index(
            index=idx_name,
            document={
                "id": 3,
                "name": "小米su7 ultra长续航版本",
                "brand": "小米汽车",
                "image": "www.xxx.xxx/xm.png",
                "price": 406000
            }
        )

        await client.bulk(operations=[
            {
                "index": {
                    "_index": idx_name
                }
            },
            {
                "id": 1,
                "name": "小米17ProMax 1T 雪花白 8GB+16GB",
                "brand": "小米",
                "image": "www.xxx.xxx/xm.png",
                "price": 5000
            },
            {
                "index": {
                    "_index": idx_name
                }
            },
            {
                "id": 2,
                "name": "小米17ProMax 1T 冰晶蓝 8GB+16GB",
                "brand": "小米",
                "image": "www.xxx.xxx/xm.png",
                "price": 6000
            }
        ])
        await es_client_manager.close()
    asyncio.run(test_doc())

