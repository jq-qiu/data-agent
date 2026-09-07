"""在表 ORM 模型与领域实体之间进行显式转换。"""

from dataclasses import asdict

from app.entities.table_info import TableInfo
from app.models.table_info_mysql import TableInfoMySQL


def _required_text(value: str | None, field: str) -> str:
    if value is None:
        raise ValueError(f"{field} must not be null")
    return value


class TableInfoMapper:
    @staticmethod
    def to_entity(table_info_mysql: TableInfoMySQL) -> TableInfo:
        return TableInfo(
            id=table_info_mysql.id,
            name=_required_text(table_info_mysql.name, "table_info.name"),
            role=_required_text(table_info_mysql.role, "table_info.role"),
            description=_required_text(
                table_info_mysql.description, "table_info.description"
            ),
        )

    @staticmethod
    def to_model(table_info: TableInfo) -> TableInfoMySQL:
        data = asdict(table_info)
        return TableInfoMySQL(**{key: data[key] for key in ("id", "name", "role", "description")})
