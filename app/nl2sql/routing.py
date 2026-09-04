from collections.abc import Mapping
from typing import Any


def route_after_validation(state: Mapping[str, Any]) -> str:
    if state.get("error") is None:
        return "execute_sql"
    if state.get("repair_attempts", 0) < 1:
        return "correct_sql"
    return "end"
