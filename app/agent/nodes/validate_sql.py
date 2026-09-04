from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.nl2sql.validator import SQLValidationError


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    write = runtime.stream_writer
    write({"type": "progress", "step": "验证SQL", "status": "running"})

    try:
        # 1.获取state中生成SQL
        sql = state["sql"]
        metric_ids = tuple(item["id"] for item in state.get("metric_infos", []))
        sql_validator = runtime.context["sql_validator"]
        validated_sql = sql_validator.validate(sql, metric_ids)
        # 2.调用数仓持久层通过执行计划关键字验证SQL
        dw_mysql_repository = runtime.context["dw_mysql_repository"]
        await dw_mysql_repository.validate_sql(validated_sql)
        write({"type": "progress", "step": "验证SQL", "status": "success"})
        return {
            "sql": validated_sql.sql,
            "validated_sql": validated_sql.sql,
            "validation_trace": validated_sql.as_trace(),
            "error": None,
        }
    except (SQLValidationError, SQLAlchemyError, TimeoutError) as e:
        logger.error(f"验证SQL发生异常：{e}")
        write({"type": "progress", "step": "验证SQL", "status": "error"})
        return {"validated_sql": "", "validation_trace": {}, "error": f"{e}"}
