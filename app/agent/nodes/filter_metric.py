import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, MetricInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    write = runtime.stream_writer
    write({"type": "progress", "step": "过滤指标", "status": "running"})

    try:
        # 1.获取state中指标信息,用户问题
        metric_infos: list[MetricInfoState] = state["metric_infos"]
        query = state["query"]
        # 2.调用llm获取回答用户问题需要指标
        # 2.1 构建提示词运行单元
        prompt = PromptTemplate(template=load_prompt("filter_metric_info"), input_variables=["query", "metric_infos"])
        # 2.2 llm结果解析 JSON格式
        out_put = JsonOutputParser()
        # 2.3 构建链，执行异步调用 得到所需指标列表（只包含指标名称）
        # [
        #     "指标1名称",
        #     "指标2名称"
        # ]
        chain = prompt | llm | out_put
        # 2.4 处理传入的列表对象，将列表转为Yaml
        result = await chain.ainvoke(
            {"query": query, "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False)}
        )
        logger.info(f"调用llm获取所需指标：{result}")

        # 3.遍历已有指标信息列表，将不需要的指标信息移除
        #  遍历中删除列表元素 可能存在漏删 解决方法采用切片表达式 对原列表进行复制得到列表副本 遍历列表副本 删除操作原列表
        for metric_info in metric_infos[:]:
            metric_name = metric_info["name"]
            if metric_name not in result:
                metric_infos.remove(metric_info)
        # 4.更新state中指标信息列表 “metric_infos”
        write({"type": "progress", "step": "过滤指标", "status": "success"})
        logger.info(f"过滤指标成功，指标：{[metric_info["name"] for metric_info in metric_infos]}")
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
