from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    write = runtime.stream_writer
    write({"type": "progress", "step": "验证SQL", "status": "running"})

    try:
        #1.获取state中生成SQL
        sql = state["sql"]
        #2.调用数仓持久层通过执行计划关键字验证SQL
        dw_mysql_repository = runtime.context["dw_mysql_repository"]
        await dw_mysql_repository.validate_sql(sql)
        write({"type": "progress", "step": "验证SQL", "status": "success"})
        return {"error": None}
    except Exception as e:
        logger.error(f"验证SQL发生异常：{e}")
        write({"type": "progress", "step": "验证SQL", "status": "error"})
        return {"error": f"{e}"}
