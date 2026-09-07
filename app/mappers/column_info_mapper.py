"""在列 ORM 模型、领域实体与检索文档之间进行显式转换。"""

from dataclasses import asdict
from typing import Any

from app.entities.column_info import ColumnInfo
from app.models.column_info_mysql import ColumnInfoMySQL


def _required_text(value: str | None, field: str) -> str:
    if value is None:
        raise ValueError(f"{field} must not be null")
    return value


def _any_list(value: dict | list | None, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"{field} must be a list")
    return value


def _string_list(value: dict | list | None, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"{field} must be a list")
    return [str(item) for item in value]


class ColumnInfoMapper:
    @staticmethod
    def to_entity(column_info_mysql: ColumnInfoMySQL) -> ColumnInfo:
        # 将持久层对象 转为 业务层对象 只能手动赋值
        return ColumnInfo(
            id=column_info_mysql.id,
            name=_required_text(column_info_mysql.name, "column_info.name"),
            type=_required_text(column_info_mysql.type, "column_info.type"),
            role=_required_text(column_info_mysql.role, "column_info.role"),
            examples=_any_list(column_info_mysql.examples, "column_info.examples"),
            description=_required_text(
                column_info_mysql.description, "column_info.description"
            ),
            alias=_string_list(column_info_mysql.alias, "column_info.alias"),
            table_id=_required_text(column_info_mysql.table_id, "column_info.table_id"),
        )

    @staticmethod
    def to_model(column_info: ColumnInfo) -> ColumnInfoMySQL:
        # 将业务层对象转为持久层对象
        data = asdict(column_info)
        legacy_fields = (
            "id",
            "name",
            "type",
            "role",
            "examples",
            "description",
            "alias",
            "table_id",
        )
        return ColumnInfoMySQL(**{key: data[key] for key in legacy_fields})
