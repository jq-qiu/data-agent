from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def execute_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    write = runtime.stream_writer
    write({"type": "progress", "step": "执行SQL", "status": "running"})

    try:
        # 1.获取业务SQL
        sql = state["validated_sql"]
        metric_ids = tuple(item["id"] for item in state.get("metric_infos", []))
        validated_sql = runtime.context["sql_validator"].validate(sql, metric_ids)
        # 2.调用数仓持久层执行SQL
        dw_mysql_repository = runtime.context["dw_mysql_repository"]
        data = await dw_mysql_repository.execute_sql(validated_sql)
        # 3.将结果通过流写入器返回给用户
        # 3.1 节点运行状态
        write({"type": "progress", "step": "执行SQL", "status": "success"})
        # 3.2 SQL执行结果
        write({"type": "result", "data": data, "validation": validated_sql.as_trace()})
    except Exception as e:
        logger.error(f"执行SQL发生异常：{e}")
        write({"type": "progress", "step": "执行SQL", "status": "error"})
        raise
