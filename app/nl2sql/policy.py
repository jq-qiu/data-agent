"""加载 SQL 安全策略，包括只读限制、白名单和修复预算。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SQLPolicy:
    version: str
    allowed_database: str
    max_rows: int
    timeout_seconds: float
    max_repair_attempts: int
    forbidden_schemas: frozenset[str]
    forbidden_functions: frozenset[str]
    allowed_functions: frozenset[str]


def load_sql_policy(path: Path) -> SQLPolicy:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SQLPolicy(
        version=str(raw["version"]),
        allowed_database=str(raw["allowed_database"]),
        max_rows=int(raw["max_rows"]),
        timeout_seconds=float(raw["timeout_seconds"]),
        max_repair_attempts=int(raw["max_repair_attempts"]),
        forbidden_schemas=frozenset(str(item).casefold() for item in raw["forbidden_schemas"]),
        forbidden_functions=frozenset(str(item).casefold() for item in raw["forbidden_functions"]),
        allowed_functions=frozenset(str(item).casefold() for item in raw["allowed_functions"]),
    )
