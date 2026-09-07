"""把元数据配置解析为表、列、指标和关系的结构化对象。"""

from dataclasses import dataclass

"""用于接受元信息转为对象"""

@dataclass
class ColumnConfig:
    name: str
    role: str
    description: str
    alias: list[str]
    sync: bool


@dataclass
class TableConfig:
    name: str
    role: str
    description: str
    columns: list[ColumnConfig]


@dataclass
class MetricConfig:
    name: str
    description: str
    relevant_columns: list[str]
    alias: list[str]


@dataclass
class MetaConfig:
    tables: list[TableConfig] | None = None
    metrics: list[MetricConfig] | None = None
