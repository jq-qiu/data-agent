"""定义指标元数据实体，包括公式、粒度、维度和版本信息。"""

from dataclasses import dataclass, field


@dataclass
class MetricInfo:
    id: str
    name: str
    description: str
    relevant_columns: list[str]
    alias: list[str]
    formula: str = ""
    base_grain: str = ""
    time_column: str = ""
    status_filters: dict[str, list[str]] = field(default_factory=dict)
    allowed_dimensions: list[str] = field(default_factory=list)
    component_metrics: list[str] = field(default_factory=list)
    version: str = ""
