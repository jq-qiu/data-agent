"""定义列与指标关联关系的数据实体。"""

from dataclasses import dataclass


@dataclass
class ColumnMetric:
    column_id: str
    metric_id: str
