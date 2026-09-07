"""定义 Elasticsearch 字段值文档的数据实体。"""

from dataclasses import dataclass

"""保存到ES中字段枚举文档对象"""


@dataclass
class ValueInfo:
    id: str
    value: str
    column_id: str
    matched_value: str | None = None
