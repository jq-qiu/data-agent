"""通过 Elasticsearch 召回真实字段值，把自然语言取值绑定到受控列。"""

from time import perf_counter

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.entities.value_info import ValueInfo


async def recall_value(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """召回字段取值，获取真实有效字段取值，用于解决llm生成SQL where 部分字段的取值"""
    node_started_at = perf_counter()
    # 1.获取流写入器对象
    write = runtime.stream_writer
    write({"type": "progress", "step": "召回字段取值", "status": "running"})
    try:
        # 只检索统一扩展节点识别出的真实字段取值，避免完整问句和操作词造成误召回。
        keywords = list(dict.fromkeys(state["value_keywords"]))

        # 2.4 初始化字段取值字典 字典key=“字段取值”ID vlaue=字段取值对象
        retrieved_metrics_dict: dict[str, ValueInfo] = {}

        # 2.5 从runtime中获取操作ES持久层对象
        value_es_repository = runtime.context["value_es_repository"]

        # 2.6 遍历关键词列表，执行全文检索 ，处理结果
        if keywords:
            for keyword in keywords:
                es_started_at = perf_counter()
                # ES 返回“规范列 ID + 真实规范值”，后续 WHERE 不直接使用用户的自由文本。
                value_infos: list[ValueInfo] = await value_es_repository.search_v1_grounded(keyword)
                logger.info(
                    f"ES字段取值检索耗时：{perf_counter() - es_started_at:.3f}秒，"
                    f"关键词：{keyword!r}，命中数：{len(value_infos)}"
                )
                for value_info in value_infos:
                    value_id = value_info.id
                    if value_id not in retrieved_metrics_dict:
                        retrieved_metrics_dict[value_id] = value_info
        write({"type": "progress", "step": "召回字段取值", "status": "success"})
        logger.info(f"字段取值召回成功：{list(retrieved_metrics_dict.keys())}")
        logger.info(
            f"字段取值召回总耗时：{perf_counter() - node_started_at:.3f}秒，"
            f"最终关键词数：{len(keywords)}，去重命中数：{len(retrieved_metrics_dict)}"
        )
        # 2.7 更新state中"retrieved_values"
        return {"retrieved_values": list(retrieved_metrics_dict.values())}
    except Exception as e:
        logger.error(f"召回字段取值发生异常，耗时：{perf_counter() - node_started_at:.3f}秒：{e}")
        write({"type": "progress", "step": "召回字段取值", "status": "error"})
        raise
