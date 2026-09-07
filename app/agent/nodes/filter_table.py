"""结合问题与召回字段筛选相关表，避免向模型暴露无关 Schema。"""

import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, TableInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_table(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """过滤表格信息 将不需要的表跟表中字段删除"""
    write = runtime.stream_writer
    write({"type": "progress", "step": "过滤表格", "status": "running"})

    try:
        # 1. 从state获取表信息列表，用户问题
        table_infos: list[TableInfoState] = state["table_infos"]
        query = state["query"]
        # 2. 调用llm获取回答用户问题所需要表跟字段
        prompt = PromptTemplate(
            template=load_prompt("filter_table_info"), input_variables=["query", "table_infos"]
        )
        chain = prompt | llm | JsonOutputParser()
        # {
        #     "表名1": ["字段1名称", "字段2名称", "..."],
        #     "表名2": ["字段1", "字段2", "..."]
        # }
        # 输出只描述“表名 -> 所需列名”；真正的列详情继续来自召回后的元数据对象。
        result = await chain.ainvoke(
            {
                "query": query,
                "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False),
            }
        )

        # 3.遍历表信息列表，将不需要的表信息以及表中字段删除
        # 3.1 将不需要表删除
        # 先移除无关表，再在保留表内裁剪列，降低下一步 SQL Prompt 的无关 Schema 噪声。
        for table_info in table_infos[:]:
            table_name = table_info["name"]
            if table_name not in result:
                table_infos.remove(table_info)
            else:
                # 3.2 将表下包含不需要字段信息删除
                columns = table_info["columns"]
                # 3.2.1 遍历表下字段列表
                for column in columns[:]:
                    column_name = column["name"]
                    # 3.2.2 只有字段没有出现在llm结果 字典的Value中
                    if column_name not in result[table_name]:
                        table_info["columns"].remove(column)
        write({"type": "progress", "step": "过滤表格", "status": "success"})
        logger.info(f"过滤表格成功，表信息：{[table_info['name'] for table_info in table_infos]}")
        logger.info(
            f"过滤表格成功，字段信息：{[column['name'] for ti in table_infos for column in ti['columns']]}"
        )
        # 4. 更新state中“table_infos”
        return {"table_infos": table_infos}
    except Exception as e:
        logger.error(f"过滤表格发生异常：{e}")
        write({"type": "progress", "step": "过滤表格", "status": "error"})
        raise
