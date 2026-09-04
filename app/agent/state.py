from typing import TypedDict

from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.value_info import ValueInfo


class ColumnInfoState(TypedDict):
    name: str
    type: str
    role: str
    examples: list
    description: str
    alias: list[str]


class TableInfoState(TypedDict):
    name: str
    role: str
    grain: str
    description: str
    time_column: str | None
    primary_key: list[str]
    allowed_join_relations: list[str]
    columns: list[ColumnInfoState]


class MetricInfoState(TypedDict):
    id: str
    name: str
    description: str
    formula: str
    base_grain: str
    time_column: str
    status_filters: dict[str, list[str]]
    allowed_dimensions: list[str]
    component_metrics: list[str]
    relevant_columns: list[str]
    alias: list[str]


class RelationshipInfoState(TypedDict):
    relation_id: str
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    cardinality: str
    grain_warning: str


class DateInfoState(TypedDict):
    date: str
    weekday: str
    quarter: str


class DBInfoState(TypedDict):
    version: str
    dialect: str


class DataAgentState(TypedDict, total=False):
    # 提问问题
    query: str
    # 抽取关键字节点结果
    keywords: list[str]
    # 统一关键词扩展节点结果
    column_keywords: list[str]
    metric_keywords: list[str]
    value_keywords: list[str]
    # 召回字段节点结果
    retrieved_columns: list[ColumnInfo]
    # 召回指标节点结果
    retrieved_metrics: list[MetricInfo]
    # 召回字段取值结果
    retrieved_values: list[ValueInfo]
    # 合并节点结果
    table_infos: list[TableInfoState]  # 表信息
    metric_infos: list[MetricInfoState]  # 指标信息
    join_relations: list[RelationshipInfoState]
    grain_warnings: list[str]

    # 额外上下文结果
    date_info: DateInfoState
    db_info: DBInfoState

    # 生成SQL结果
    sql: str
    validated_sql: str
    validation_trace: dict
    repair_attempts: int

    # 校验SQL节点 SQL错误信息
    error: str | None
