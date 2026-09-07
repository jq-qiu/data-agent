"""定义表元数据实体及其列、主键和允许关系。"""

from dataclasses import dataclass, field


@dataclass
class TableInfo:
    id: str
    name: str
    role: str
    description: str
    grain: str = ""
    time_column: str | None = None
    primary_key: list[str] = field(default_factory=list)
    allowed_join_relations: list[str] = field(default_factory=list)
    alias: list[str] = field(default_factory=list)
