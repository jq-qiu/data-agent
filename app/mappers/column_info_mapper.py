from dataclasses import asdict

from app.entities.column_info import ColumnInfo
from app.models.column_info_mysql import ColumnInfoMySQL


class ColumnInfoMapper:
    @staticmethod
    def to_entity(column_info_mysql: ColumnInfoMySQL) -> ColumnInfo:
        # 将持久层对象 转为 业务层对象 只能手动赋值
        return ColumnInfo(
            id=column_info_mysql.id,
            name=column_info_mysql.name,
            type=column_info_mysql.type,
            role=column_info_mysql.role,
            examples=column_info_mysql.examples,
            description=column_info_mysql.description,
            alias=column_info_mysql.alias,
            table_id=column_info_mysql.table_id,
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
