"""结合问题与召回候选筛选相关指标，缩小 SQL 生成上下文。"""

from collections.abc import Collection, Sequence

import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, MetricInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


def apply_metric_selection_policy(
    query: str,
    metric_infos: Sequence[MetricInfoState],
    selected_names: Collection[str],
    grounded_columns: Collection[str] = (),
) -> list[MetricInfoState]:
    """对 LLM 选择结果施加 Registry 粒度无法表达的确定性收紧。"""

    normalized = query.casefold()
    physical_detail_count = "明细" in normalized and any(
        term in normalized
        for term in ("记录数", "多少条", "一共有多少", "一共多少")
    )
    status_sliced_order_count = "fact_order.status" in grounded_columns

    selected: list[MetricInfoState] = []
    for metric_info in metric_infos:
        if metric_info["name"] not in selected_names:
            continue
        metric_id = metric_info["id"]
        if metric_id == "item_count" and physical_detail_count:
            continue
        if metric_id == "order_count" and status_sliced_order_count:
            continue
        selected.append(metric_info)
    return selected


async def filter_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """从召回候选中筛出问题所需指标，并保留 Registry 提供的公式与口径信息。"""

    write = runtime.stream_writer
    write({"type": "progress", "step": "过滤指标", "status": "running"})

    try:
        # 1.获取state中指标信息,用户问题
        metric_infos: list[MetricInfoState] = state["metric_infos"]
        query = state["query"]
        # 2.调用llm获取回答用户问题需要指标
        # 2.1 构建提示词运行单元
        prompt = PromptTemplate(
            template=load_prompt("filter_metric_info"), input_variables=["query", "metric_infos"]
        )
        # 2.2 llm结果解析 JSON格式
        out_put = JsonOutputParser()
        # 2.3 构建链，执行异步调用 得到所需指标列表（只包含指标名称）
        # [
        #     "指标1名称",
        #     "指标2名称"
        # ]
        chain = prompt | llm | out_put
        # 2.4 处理传入的列表对象，将列表转为Yaml
        # 模型只返回需要的指标名称；公式、粒度和版本仍保留自 Registry 召回的完整对象。
        result = await chain.ainvoke(
            {
                "query": query,
                "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False),
            }
        )
        logger.info(f"调用llm获取所需指标：{result}")

        grounded_columns = {
            value.column_id for value in state.get("retrieved_values", [])
        }
        metric_infos = apply_metric_selection_policy(
            query,
            metric_infos,
            result,
            grounded_columns,
        )
        # 4.更新state中指标信息列表 “metric_infos”
        write({"type": "progress", "step": "过滤指标", "status": "success"})
        logger.info(f"过滤指标成功，指标：{[metric_info['name'] for metric_info in metric_infos]}")
        return {"metric_infos": metric_infos}
    except Exception as e:
        logger.error(f"过滤指标发生异常：{e}")
        write({"type": "progress", "step": "过滤指标", "status": "error"})
        raise


# if __name__ == '__main__':
#     metric_state = MetricInfoState(
#         name="AOV",
#         description="销售平均值",
#         relevant_columns=["order_amount"],
#         alias=["销售额平均值"]
#     )
#     print(yaml.dump(metric_state, allow_unicode=True, sort_keys=False))
