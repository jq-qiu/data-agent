import json
from time import perf_counter

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


def normalize_keywords(values) -> list[str]:
    """清理大模型返回的关键词并保留原始顺序去重。"""
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(
        str(value).strip()
        for value in values
        if value is not None and str(value).strip()
    ))


async def expand_recall_keywords(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """一次调用大模型，同时生成字段、指标和字段取值召回关键词。"""
    writer = runtime.stream_writer
    writer({"type": "progress", "step": "扩展召回关键词", "status": "running"})
    started_at = perf_counter()

    try:
        prompt = PromptTemplate(
            template=load_prompt("expand_recall_keywords"),
            input_variables=["query", "keywords"],
        )
        chain = prompt | llm | JsonOutputParser()
        result = await chain.ainvoke({
            "query": state["query"],
            "keywords": json.dumps(state["keywords"], ensure_ascii=False),
        })

        if not isinstance(result, dict):
            raise ValueError("统一关键词扩展结果必须是JSON对象")

        column_keywords = normalize_keywords(result.get("column_keywords"))
        metric_keywords = normalize_keywords(result.get("metric_keywords"))
        value_keywords = normalize_keywords(result.get("value_keywords"))

        logger.info(
            f"统一关键词扩展耗时：{perf_counter() - started_at:.3f}秒，"
            f"字段：{column_keywords}，指标：{metric_keywords}，取值：{value_keywords}"
        )
        writer({"type": "progress", "step": "扩展召回关键词", "status": "success"})
        return {
            "column_keywords": column_keywords,
            "metric_keywords": metric_keywords,
            "value_keywords": value_keywords,
        }
    except Exception as error:
        logger.error(
            f"统一关键词扩展失败，耗时：{perf_counter() - started_at:.3f}秒：{error}"
        )
        writer({"type": "progress", "step": "扩展召回关键词", "status": "error"})
        raise
