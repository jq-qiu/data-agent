from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.entities.column_info import ColumnInfo


async def recall_column(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = get_stream_writer()
    writer({"type": "progress", "step": "召回字段", "status": "running"})

    try:
        # 使用统一扩展节点产生的字段关键词，保留顺序去重。
        keywords = list(dict.fromkeys(state["keywords"] + state["column_keywords"]))
        # 3.遍历关键词列表，根据每个关键词进行向量检索 将得分大于0.6的向量点
        # 3.1 创建字段信息字典 key:字段ID value：字段信息
        retrieved_columns_map: dict[str, ColumnInfo] = {}
        # 3.2 从runtime获取embeding客户端
        embedding_client = runtime.context["embedding_client"]
        column_qdrant_repository = runtime.context["column_qdrant_repository"]
        meta_mysql_repository = runtime.context["meta_mysql_repository"]

        for keyword in keywords:
            # 3.1 对关键词转为向量
            embedding = await embedding_client.aembed_query(keyword)
            # 3.2 检索字段信息向量集合
            column_ids = await column_qdrant_repository.search_v1_ids(embedding)
            colunm_infos: list[ColumnInfo] = [
                await meta_mysql_repository.get_v1_column_info_by_id(column_id)
                for column_id in column_ids
            ]
            # 3.3 获取检索结果
            for colunm_info in colunm_infos:
                colunm_id = colunm_info.id
                if colunm_id not in retrieved_columns_map:
                    retrieved_columns_map[colunm_id] = colunm_info
        # 4.获取可能需要字段信息
        writer({"type": "progress", "step": "召回字段", "status": "success"})
        logger.info(f"召回字段成功，字段信息：{list(retrieved_columns_map.keys())}")
        return {"retrieved_columns": list(retrieved_columns_map.values())}
    except Exception as e:
        logger.error(f"召回字段节点执行异常:{e}")
        writer({"type": "progress", "step": "召回字段", "status": "error"})
        raise
