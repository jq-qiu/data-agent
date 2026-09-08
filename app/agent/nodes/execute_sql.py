"""执行已经通过统一校验的只读 SQL，并将查询结果写入流式响应。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def execute_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """只执行 State 中的 validated_sql，并通过 SSE 输出结果或稳定错误事件。"""

    write = runtime.stream_writer
    write({"type": "progress", "step": "执行SQL", "status": "running"})

    try:
        # 1.获取业务SQL
        # 执行前再次校验原始候选，确保实际交给 Repository 的语句与通过策略检查的是同一来源。
        # Revalidate the exact source accepted by validate_sql. Re-parsing the
        # normalized rendering can change an allowlisted IF node into CASE.
        sql = state["sql"]
        metric_ids = tuple(item["id"] for item in state.get("metric_infos", []))
        validated_sql = runtime.context["sql_validator"].validate(
            sql,
            metric_ids,
            schema_linking_plan=state.get("schema_linking_plan"),
        )
        # 2.调用数仓持久层执行SQL
        dw_mysql_repository = runtime.context["dw_mysql_repository"]
        # Repository 只接受 ValidatedSQL，而不是任意字符串；查询结果由本节点转换为终态 SSE。
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
