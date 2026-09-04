import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def generate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    write = runtime.stream_writer
    write({"type": "progress", "step": "生成SQL", "status": "running"})

    try:
        # 1.从state获取生成SQL上下文信息 包含：表信息、指标信息、日期、数仓信息、用户用户
        query = state["query"]
        table_infos = state["table_infos"]
        metric_infos = state["metric_infos"]
        db_info = state["db_info"]
        date_info = state["date_info"]
        # 2.调用大模型生成纯文本SQL
        # 2.1 创建提示词运行单元
        prompt = PromptTemplate(template=load_prompt("generate_sql"),
                                input_variables=["query", "table_infos", "metric_infos", "db_info", "date_info"])
        # 2.2 llm结果解析采用字符串结果解析器
        str_output_parse = StrOutputParser()
        # 2.3 调用Langchain链，获取生成SQL
        chain = prompt | llm | str_output_parse
        sql = await chain.ainvoke({"query": query,
                                   "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False),
                                   "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False),
                                   "db_info": yaml.dump(db_info, allow_unicode=True, sort_keys=False),
                                   "date_info": yaml.dump(date_info, allow_unicode=True, sort_keys=False)
                                   })
        write({"type": "progress", "step": "生成SQL", "status": "success"})
        logger.info(f"生成SQL成功：{sql}")
        # 3.更新state
        return {"sql": sql}
    except Exception as e:
        logger.error(f"生成SQL发生异常：{e}")
        write({"type": "progress", "step": "生成SQL", "status": "error"})
        raise
