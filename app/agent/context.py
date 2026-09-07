"""定义开放式 NL2SQL Graph 的只读运行时依赖，避免把客户端和仓储对象写入请求 State。"""

from langchain_core.embeddings import Embeddings
from typing_extensions import TypedDict

from app.nl2sql.validator import SQLValidator
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


class DataAgentContext(TypedDict):
    """runtime中context数据结构定义,存放静态依赖：操作不同库持久层对象 对于节点而言只读"""

    # 这些对象具有连接或生命周期状态，只能由依赖容器注入，不能进入可序列化 State。
    meta_mysql_repository: MetaMySQLRepository
    dw_mysql_repository: DWMySQLRepository
    embedding_client: Embeddings
    column_qdrant_repository: ColumnQdrantRepository
    metric_qdrant_repository: MetricQdrantRepository
    value_es_repository: ValueESRepository
    sql_validator: SQLValidator
