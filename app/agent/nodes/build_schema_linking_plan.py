"""SQL-004 节点：在 SQL 生成前构建并校验 SchemaLinkingPlan。

该节点只做确定性方案生成，不调用 LLM、不执行 SQL、不写入任何数据。
Plan 生成失败时通过异常使请求明确失败，避免模型自行补出未登记 JOIN。
"""

from typing import cast

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState, TableInfoState
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
        existing_tables = {str(item["name"]) for item in state["table_infos"]}
        updated_table_infos: list[TableInfoState] = list(state["table_infos"])
        for table_name in plan.tables:
            if table_name in existing_tables:
                continue
            definition = catalog.table_map[table_name]
            table_state = SchemaLinkingPlanBuilder.table_state_from_catalog(
                definition
            )
            planned_columns = {
                str(column).partition(".")[2]
                for column in plan.columns
                if str(column).startswith(f"{table_name}.")
            }
            if planned_columns:
                table_state["columns"] = [
                    column
                    for column in table_state["columns"]
                    if column["name"] in planned_columns
                ]
            updated_table_infos.append(cast(TableInfoState, table_state))
        write({"type": "progress", "step": "构建Schema方案", "status": "success"})
        logger.info(
            "SchemaLinkingPlan tables={} relations={} group_by={}",
            list(plan.tables),
            [item.relation_id for item in plan.join_relations],
            list(plan.group_by_columns),
        )
        return {
            "schema_linking_plan": plan.model_dump(mode="json"),
            "table_infos": updated_table_infos,
        }
    except Exception as error:
        logger.error("构建Schema方案发生异常：{}", error)
        write({"type": "progress", "step": "构建Schema方案", "status": "error"})
        raise
