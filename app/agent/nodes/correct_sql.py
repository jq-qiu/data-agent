"""在首次 SQL 校验失败后调用模型进行一次受限修复，并把结果送回同一校验链路。"""

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def correct_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """根据校验错误修复候选 SQL；输出仍是未受信任文本，必须重新进入 Validator。"""

    write = runtime.stream_writer
    write({"type": "progress", "step": "校正SQL", "status": "running"})

    try:
        # 修复 Prompt 同时接收原问题、受控元数据、原 SQL 和校验错误，避免模型脱离失败上下文重写。
        # 1.获取state中信息 包含：表信息、指标信息、日期、数仓信息、用户用户、SQL、SQL错误信息
        query = state["query"]
        table_infos = state["table_infos"]
        metric_infos = state["metric_infos"]
        join_relations = state["join_relations"]
        grain_warnings = state["grain_warnings"]
        schema_linking_plan = state.get("schema_linking_plan")
        db_info = state["db_info"]
        date_info = state["date_info"]
        sql = state["sql"]
        error = state["error"]
        # 2.调用大模型修复SQL
        prompt = PromptTemplate(
            template=load_prompt("correct_sql"),
            input_variables=[
                "query",
                "table_infos",
                "metric_infos",
                "join_relations",
                "grain_warnings",
                "schema_linking_plan",
                "db_info",
                "date_info",
                "sql",
                "error",
            ],
        )
        # 2.2 llm结果解析采用字符串结果解析器
        str_output_parse = StrOutputParser()
        # 2.3 调用Langchain链，获取生成SQL
        chain = prompt | llm | str_output_parse
        # TypedDict 等结构先序列化为 YAML，让 Prompt 看到明确字段层级而不是 Python 对象表示。
        sql = await chain.ainvoke(
            {
                "query": query,
                "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False),
                "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False),
                "join_relations": yaml.dump(join_relations, allow_unicode=True, sort_keys=False),
                "grain_warnings": yaml.dump(grain_warnings, allow_unicode=True, sort_keys=False),
                "schema_linking_plan": yaml.dump(
                    schema_linking_plan,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                "db_info": yaml.dump(db_info, allow_unicode=True, sort_keys=False),
                "date_info": yaml.dump(date_info, allow_unicode=True, sort_keys=False),
                "sql": sql,
                "error": error,
            }
        )

        logger.info(f"修正SQL成功：{sql}")
        write({"type": "progress", "step": "校正SQL", "status": "success"})
        # 这里只替换候选 SQL 并增加修复计数；Graph 会把它重新送回 validate_sql。
        return {"sql": sql, "repair_attempts": state.get("repair_attempts", 0) + 1}
    except Exception as e:
        logger.error(f"校正SQL发生异常：{e}")
        write({"type": "progress", "step": "校正SQL", "status": "error"})
        raise
