import json

from langchain_core.embeddings import Embeddings

from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.state import DataAgentState
from app.nl2sql.validator import SQLValidator
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


class QueryService:
    def __init__(
        self,
        embedding_client: Embeddings,
        column_qdrant_repository: ColumnQdrantRepository,
        metric_qdrant_repository: MetricQdrantRepository,
        value_es_repository: ValueESRepository,
        meta_mysql_repository: MetaMySQLRepository,
        dw_mysql_repository: DWMySQLRepository,
        sql_validator: SQLValidator,
    ):
        self.embedding_client = embedding_client
        self.column_qdrant_repository = column_qdrant_repository
        self.metric_qdrant_repository = metric_qdrant_repository
        self.value_es_repository = value_es_repository
        self.meta_mysql_repository = meta_mysql_repository
        self.dw_mysql_repository = dw_mysql_repository
        self.sql_validator = sql_validator

    async def query_answer(self, query: str):
        state = DataAgentState(query=query, repair_attempts=0)
        context = DataAgentContext(
            meta_mysql_repository=self.meta_mysql_repository,
            dw_mysql_repository=self.dw_mysql_repository,
            embedding_client=self.embedding_client,
            column_qdrant_repository=self.column_qdrant_repository,
            metric_qdrant_repository=self.metric_qdrant_repository,
            value_es_repository=self.value_es_repository,
            sql_validator=self.sql_validator,
        )
        async for chunk in graph.astream(input=state, context=context, stream_mode="custom"):
            yield f"data: {json.dumps(chunk, ensure_ascii=False, default=str)}\n\n"
