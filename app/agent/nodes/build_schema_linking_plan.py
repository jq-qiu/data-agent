"""SQL-004 节点：在 SQL 生成前构建并校验 SchemaLinkingPlan。

该节点只做确定性方案生成，不调用 LLM、不执行 SQL、不写入任何数据。
Plan 生成失败时通过异常使请求明确失败，避免模型自行补出未登记 JOIN。
"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.nl2sql.schema_linking import (
    MetaRelationshipPathProvider,
    SchemaLinkingPlanBuilder,
)


async def build_schema_linking_plan(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict:
    """根据过滤后的 Schema/指标/关系生成结构化 SQL 生成方案。"""

    write = runtime.stream_writer
    write({"type": "progress", "step": "构建Schema方案", "status": "running"})
    try:
        catalog = runtime.context["sql_validator"].catalog
        meta_repository = runtime.context["meta_mysql_repository"]
        builder = SchemaLinkingPlanBuilder(
            catalog,
            MetaRelationshipPathProvider(meta_repository),
        )
        plan = await builder.build(
            query=str(state["query"]),
            table_infos=state["table_infos"],
            metric_infos=state["metric_infos"],
            join_relations=state["join_relations"],
            grain_warnings=state.get("grain_warnings", []),
        )
        write({"type": "progress", "step": "构建Schema方案", "status": "success"})
        logger.info(
            "SchemaLinkingPlan tables=%s relations=%s group_by=%s",
            list(plan.tables),
            [item.relation_id for item in plan.join_relations],
            list(plan.group_by_columns),
        )
        return {"schema_linking_plan": plan.model_dump(mode="json")}
    except Exception as error:
        logger.error("构建Schema方案发生异常：%s", type(error).__name__)
        write({"type": "progress", "step": "构建Schema方案", "status": "error"})
        raise
