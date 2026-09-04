from dataclasses import dataclass
from typing import Any


@dataclass
class ColumnInfo:
    id: str
    name: str
    type: str
    role: str
    examples: list[Any]
    description: str
    alias: list[str]
    table_id: str
    is_sensitive: bool = False
    value_index_enabled: bool = False
