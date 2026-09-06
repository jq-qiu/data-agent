import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from langchain_core.embeddings import Embeddings
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import dw_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.conf.app_config import app_config
from app.diagnosis.grounding import (
    QdrantElasticsearchCandidateRetriever,
    SemanticGrounder,
)
from app.diagnosis.intent import IntentRouter
from app.diagnosis.intent_classifier import LangChainIntentClassifier
from app.diagnosis.semantics import AnalysisSemanticRegistry
from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.metadata.catalog import load_catalog
from app.nl2sql.policy import load_sql_policy
from app.nl2sql.validator import SQLValidator
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.query_service import QueryService

ROOT = Path(__file__).parents[2]


class _SerializedMetaMySQLRepository(MetaMySQLRepository):
    """Serialize parallel metadata reads that share one request-scoped session."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._read_lock = asyncio.Lock()

    async def get_v1_column_info_by_id(self, column_id: str) -> ColumnInfo:
        async with self._read_lock:
            return await super().get_v1_column_info_by_id(column_id)

    async def get_v1_metric_info_by_id(self, metric_id: str) -> MetricInfo:
        async with self._read_lock:
            return await super().get_v1_metric_info_by_id(metric_id)

    async def get_v1_metrics_matching_text(self, value: str) -> list[MetricInfo]:
        async with self._read_lock:
            return await super().get_v1_metrics_matching_text(value)


@lru_cache(maxsize=1)
def get_sql_validator() -> SQLValidator:
    return SQLValidator(
        load_catalog(ROOT / "conf" / "meta_config.yaml"),
        load_sql_policy(ROOT / "conf" / "sql_policy.yaml"),
    )


@lru_cache(maxsize=1)
def get_intent_router() -> IntentRouter:
    from app.agent.llm import llm

    return IntentRouter.from_catalog(
        get_sql_validator().catalog,
        classifier=LangChainIntentClassifier(llm),
    )


async def get_embedding_client():
    return embedding_client_manager.client


async def get_column_qdrant_repository():
    return ColumnQdrantRepository(qdrant_client_manager.client)


async def get_metric_qdrant_repository():
    return MetricQdrantRepository(qdrant_client_manager.client)


async def get_value_es_repository():
    return ValueESRepository(es_client_manager.client)


async def get_meta_session():
    """每次查询数据库Session每次都应该是新的Session，数据库操作完成关闭"""
    async with meta_mysql_client_manager.session_factory() as meta_session:
        yield meta_session  # 查询前会获取到session,执行DB操作，完成DB操作后 自定关闭Session


async def get_meta_mysql_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
):
    return _SerializedMetaMySQLRepository(session)


async def get_dw_session():
    """每次查询数据库Session每次都应该是新的Session，数据库操作完成关闭"""
    async with dw_mysql_client_manager.session_factory() as dw_session:
        yield dw_session  # 查询前会获取到session,执行DB操作，完成DB操作后 自定关闭Session


async def get_dw_mysql_repository(
    session: Annotated[AsyncSession, Depends(get_dw_session)],
):
    return DWMySQLRepository(session)


async def get_query_service(
    embedding_client: Annotated[Embeddings, Depends(get_embedding_client)],
    column_qdrant_repository: Annotated[
        ColumnQdrantRepository,
        Depends(get_column_qdrant_repository),
    ],
    metric_qdrant_repository: Annotated[
        MetricQdrantRepository,
        Depends(get_metric_qdrant_repository),
    ],
    value_es_repository: Annotated[ValueESRepository, Depends(get_value_es_repository)],
    meta_mysql_repository: Annotated[
        MetaMySQLRepository,
        Depends(get_meta_mysql_repository),
    ],
    dw_mysql_repository: Annotated[
        DWMySQLRepository,
        Depends(get_dw_mysql_repository),
    ],
    sql_validator: Annotated[SQLValidator, Depends(get_sql_validator)],
    intent_router: Annotated[IntentRouter, Depends(get_intent_router)],
) -> QueryService:
    if (
        app_config.db_dw.database != "data_agent_v1_dw"
        or sql_validator.policy.allowed_database != "data_agent_v1_dw"
    ):
        raise RuntimeError("API-001 requires the isolated V1 database")
    registry = AnalysisSemanticRegistry.from_catalog(sql_validator.catalog)
    semantic_grounder = SemanticGrounder(
        sql_validator.catalog,
        registry,
        QdrantElasticsearchCandidateRetriever(
            metric_qdrant_repository.client,
            value_es_repository.client,
            embedding_client,
            sql_validator.catalog,
            registry,
        ),
    )
    return QueryService(
        embedding_client=embedding_client,
        column_qdrant_repository=column_qdrant_repository,
        metric_qdrant_repository=metric_qdrant_repository,
        value_es_repository=value_es_repository,
        meta_mysql_repository=meta_mysql_repository,
        dw_mysql_repository=dw_mysql_repository,
        sql_validator=sql_validator,
        intent_router=intent_router,
        semantic_grounder=semantic_grounder,
    )
