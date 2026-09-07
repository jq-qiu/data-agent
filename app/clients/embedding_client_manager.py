"""管理 Embedding 客户端的初始化与访问生命周期。"""

import asyncio

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from app.conf.api_key import resolve_api_key
from app.conf.app_config import EmbeddingConfig, app_config


class EmbeddingClientManager:
    """
    用于操作embedding客户端管理器
    """

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._client: Embeddings | None = None

    @property
    def client(self) -> Embeddings:
        # 属性不隐式初始化网络客户端，生命周期错误会在调用点立即暴露。
        if self._client is None:
            raise RuntimeError("embedding client is not initialized; call init() first")
        return self._client

    def init(self):
        """显式创建客户端；调用方必须先初始化，再通过只读属性访问。"""

        api_key = resolve_api_key(self.config.api_key_env, "硅基流动")

        # Manager 只负责连接配置与生命周期；向量召回策略由 Repository/Service 决定。
        self._client = OpenAIEmbeddings(
            model=self.config.model,
            base_url=self.config.base_url,
            api_key=api_key,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
            check_embedding_ctx_length=False,
            model_kwargs={"encoding_format": "float"},
        )


embedding_client_manager = EmbeddingClientManager(app_config.embedding)

if __name__ == '__main__':
    embedding_client_manager.init()
    client = embedding_client_manager.client


    def test_sync_embedding():
        # embed_query = client.embed_query("你好")
        embed_query = client.embed_documents(["你好", "世界"])
        print(embed_query)  # [[],[]]
        print(len(embed_query))


    # test_sync_embedding()

    async def test_async_embedding():
        # query = await client.aembed_query("苹果")
        # print(query)
        aembed_documents_ = await client.aembed_documents(["苹果", "香蕉"])
        print(aembed_documents_)


    asyncio.run(test_async_embedding())


    async def test_async_batch_embedding(batch_size: int = 5):
        keywords = ["苹果", "香蕉", "橘子", "芒果", "开发工程师", "机器学习", "深度学习", "数据科学", "数据处理",
                    "数据可视化", "数据可视化", "数据可视化", "数据可视化", "数据可视化", "数据可视化", "数据可视化",
                    "数据可视化", "数据可视化", "数据可视化", "汽车", "小米", "大米"]
        for i in range(0, len(keywords), batch_size):
            print("处理批次", i, batch_size)
            batch = keywords[i:i + batch_size]
            batch_embed = await client.aembed_documents(batch)
            print(batch_embed)

    asyncio.run(test_async_batch_embedding())
