"""通过向量检索召回与指标关键词相关的指标定义。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.entities.metric_info import MetricInfo


async def recall_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """召回 Registry 中已有的指标候选，指标公式仍以 Registry 记录为准。"""

    # 1.获取流写入器对象
    write = runtime.stream_writer
    write({"type": "progress", "step": "召回指标", "status": "running"})
    # 2.具体逻辑
    try:
        # 使用统一扩展节点产生的指标关键词，保留顺序去重。
        keywords = list(dict.fromkeys(state["keywords"] + state["metric_keywords"]))

        # 2.4 声明指标信息字典，字典Key=指标ID  Value=指标信息（MetricInfo） 方便去重
        retrieved_metrics_dict: dict[str, MetricInfo] = {}

        # 2.5 从runtime中获取Embedding客户端、指标向量持久层
        embedding_client = runtime.context["embedding_client"]
        metric_qdrant_repository = runtime.context["metric_qdrant_repository"]
        meta_mysql_repository = runtime.context["meta_mysql_repository"]

        # 精确文本匹配优先加入候选，可直接识别规范名称和受控别名。
        for metric_info in await meta_mysql_repository.get_v1_metrics_matching_text(state["query"]):
            retrieved_metrics_dict[metric_info.id] = metric_info

        # 2.6 遍历关键词列表，执行向量检索
        for keyword in keywords:
            # 2.6.1 将关键词转为向量
            embedding = await embedding_client.aembed_query(keyword)
            # 2.6.2 执行向量索引库检索
            # 指标候选较少且误召回会引入错误计算公式，因此每个关键词只取Top5
            metric_ids = await metric_qdrant_repository.search_v1_ids(embedding, limit=5)
            # 与列召回相同，向量命中只提供 ID，完整公式和版本必须回元数据库读取。
            metric_infos: list[MetricInfo] = [
                await meta_mysql_repository.get_v1_metric_info_by_id(metric_id)
                for metric_id in metric_ids
            ]
            # 2.6.3 去重
            for metric_info in metric_infos:
                metric_id = metric_info.id
                if metric_id not in retrieved_metrics_dict:
                    retrieved_metrics_dict[metric_id] = metric_info

        # 2.7 更新State中召回指标列表
        write({"type": "progress", "step": "召回指标", "status": "success"})
        logger.info(f"召回指标信息成功：{list(retrieved_metrics_dict.keys())}")
        return {"retrieved_metrics": list(retrieved_metrics_dict.values())}
    except Exception as e:
        logger.error(f"召回指标发生异常：{e}")
        write({"type": "progress", "step": "召回指标", "status": "error"})
        raise
