"""调用统一 SQL Validator 校验候选语句，并记录可审计的校验结果。"""

from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.nl2sql.validator import SQLValidationError


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """把候选 SQL 转换为 ValidatedSQL；失败时只返回受控错误和有限修复计数。"""

    write = runtime.stream_writer
    write({"type": "progress", "step": "验证SQL", "status": "running"})

    try:
        # 1.获取state中生成SQL
        sql = state["sql"]
        metric_ids = tuple(item["id"] for item in state.get("metric_infos", []))
        schema_linking_plan = state.get("schema_linking_plan")
        sql_validator = runtime.context["sql_validator"]
        # 第一层做 AST、白名单、JOIN、指标口径和粒度检查，得到不可变 ValidatedSQL。
        validated_sql = sql_validator.validate(
            sql,
            metric_ids,
            schema_linking_plan=schema_linking_plan,
        )
        # 2.调用数仓持久层通过执行计划关键字验证SQL
        dw_mysql_repository = runtime.context["dw_mysql_repository"]
        # 第二层用数据库 EXPLAIN 验证实际方言可执行性，但此时仍不运行真实业务查询。
        await dw_mysql_repository.validate_sql(validated_sql)
        write({"type": "progress", "step": "验证SQL", "status": "success"})
        return {
            "validated_sql": validated_sql.sql,
            "validation_trace": validated_sql.as_trace(),
            "error": None,
        }
    # 可预期的校验失败写回 State，路由器据 repair_attempts 决定修复一次或安全停止。
    except (SQLValidationError, SQLAlchemyError, TimeoutError) as e:
        logger.error(f"验证SQL发生异常：{e}")
        write({"type": "progress", "step": "验证SQL", "status": "error"})
        return {"validated_sql": "", "validation_trace": {}, "error": f"{e}"}
