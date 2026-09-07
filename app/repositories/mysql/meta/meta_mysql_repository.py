"""封装表、列、指标及其关系的元数据库访问。"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import select

from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.mappers.column_info_mapper import ColumnInfoMapper
from app.mappers.column_metric_mapper import ColumnMetricMapper
from app.mappers.metric_info_mapper import MetricInfoMapper
from app.mappers.table_info_mapper import TableInfoMapper
from app.models.column_info_mysql import ColumnInfoMySQL
from app.models.table_info_mysql import TableInfoMySQL


class MetaMySQLRepository:
    """跟MySQL数据库（元数据库）交互持久层 必须通过Session对象进行CURD"""

    # 本层只做持久化和查询；指标选择、语义绑定等判断由上层服务与 Registry 完成。

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_table_infos(self, table_infos: list[TableInfo]):
        """批量保存表信息"""
        # 将业务实体对象TableInfo 转为 数据库ORM实体TableInfoMySQL
        models = [TableInfoMapper.to_model(table_info) for table_info in table_infos]
        for model in models:
            await self.session.merge(model)

    async def save_column_infos(self, column_infos: list[ColumnInfo]):
        """批量保存字段信息"""
        models = [ColumnInfoMapper.to_model(column_info) for column_info in column_infos]
        for model in models:
            await self.session.merge(model)

    async def save_metric_info_to_meta_db(self, metric_infos: list[MetricInfo]):
        models = [MetricInfoMapper.to_model(metric_info) for metric_info in metric_infos]
        for model in models:
            await self.session.merge(model)

    async def save_column_metric_info_to_meta_db(self, column_metrics: list[ColumnMetric]):
        models = [ColumnMetricMapper.to_model(column_metric) for column_metric in column_metrics]
        for model in models:
            await self.session.merge(model)

    async def get_column_info_by_id(self, column_id: str) -> ColumnInfo:
        """根据字段ID查询字段信息 框架提供根据主键查询函数get(查询返回类型, 主键ID)"""
        column_info_mysql: ColumnInfoMySQL | None = await self.session.get(
            ColumnInfoMySQL, column_id
        )
        if column_info_mysql is None:
            raise KeyError(f"metadata column not found: {column_id}")
        # 将ORM模型转为业务模型
        return ColumnInfoMapper.to_entity(column_info_mysql)

    async def get_key_columns_by_table_id(self, table_id) -> list[ColumnInfo]:
        """根据表ID查询指定表的主外键字段列表
        生成sql = SELECT *
            from column_info where table_id = 'fact_order'
            and role in ('primary_key', 'foreign_key')
        """
        stmt = select(ColumnInfoMySQL).where(
            ColumnInfoMySQL.table_id == table_id,
            ColumnInfoMySQL.role.in_(["primary_key", "foreign_key"]),
        )
        # ORM方式执行查询 将结果中每条记录封装为“单个元素”ColumnInfoMySQL对象 故采用scalars
        result = await self.session.scalars(stmt)
        return [ColumnInfoMapper.to_entity(column_info_mysql) for column_info_mysql in result]

    async def get_table_info_by_id(self, table_id: str) -> TableInfo:
        """根据表ID查询表信息"""
        table_info_mysql: TableInfoMySQL | None = await self.session.get(TableInfoMySQL, table_id)
        if table_info_mysql is None:
            raise KeyError(f"metadata table not found: {table_id}")
        return TableInfoMapper.to_entity(table_info_mysql)

    async def get_v1_column_info_by_id(self, column_id: str) -> ColumnInfo:
        result = await self.session.execute(
            text("SELECT * FROM meta_v1_column WHERE column_id = :column_id"),
            {"column_id": column_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise KeyError(f"V1 metadata column not found: {column_id}")
        return ColumnInfo(
            id=row["column_id"],
            name=row["column_name"],
            type=row["data_type"],
            role=row["role"],
            examples=list(self._decode_json(row["examples"], [])),
            description=row["description"],
            alias=list(self._decode_json(row["aliases"], [])),
            table_id=row["table_name"],
            is_sensitive=bool(row["is_sensitive"]),
            value_index_enabled=bool(row["value_index_enabled"]),
        )

    async def get_v1_table_info_by_id(self, table_id: str) -> TableInfo:
        result = await self.session.execute(
            text("SELECT * FROM meta_v1_table WHERE table_name = :table_name"),
            {"table_name": table_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise KeyError(f"V1 metadata table not found: {table_id}")
        return TableInfo(
            id=row["table_name"],
            name=row["table_name"],
            role=row["role"],
            description=row["description"],
            grain=row["grain"],
            time_column=row["time_column"],
            primary_key=list(self._decode_json(row["primary_key"], [])),
            allowed_join_relations=list(self._decode_json(row["allowed_join_relations"], [])),
            alias=list(self._decode_json(row["aliases"], [])),
        )

    async def get_v1_metric_info_by_id(self, metric_id: str) -> MetricInfo:
        result = await self.session.execute(
            text("SELECT * FROM meta_v1_metric WHERE metric_id = :metric_id"),
            {"metric_id": metric_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise KeyError(f"V1 metadata metric not found: {metric_id}")
        return self._v1_metric_from_row(row)

    async def get_v1_metrics_matching_text(self, value: str) -> list[MetricInfo]:
        result = await self.session.execute(text("SELECT * FROM meta_v1_metric"))
        normalized = value.casefold()
        matches: list[tuple[int, MetricInfo]] = []
        for row in result.mappings().all():
            metric = self._v1_metric_from_row(row)
            terms = (metric.id, metric.name, *metric.alias)
            longest = max(
                (len(term) for term in terms if term.casefold() in normalized),
                default=0,
            )
            if longest:
                matches.append((longest, metric))
        return [metric for _, metric in sorted(matches, key=lambda item: item[0], reverse=True)]

    async def get_v1_key_columns_by_table_id(self, table_id: str) -> list[ColumnInfo]:
        result = await self.session.execute(
            text(
                "SELECT column_id FROM meta_v1_column "
                "WHERE table_name = :table_name "
                "AND role IN ('primary_key', 'foreign_key', 'natural_key')"
            ),
            {"table_name": table_id},
        )
        return [
            await self.get_v1_column_info_by_id(column_id) for column_id in result.scalars().all()
        ]

    async def get_v1_relationships_for_tables(self, table_ids: set[str]) -> list[dict]:
        result = await self.session.execute(
            text("SELECT * FROM meta_v1_relationship WHERE allowed = TRUE")
        )
        return [
            dict(row)
            for row in result.mappings().all()
            if row["left_table"] in table_ids and row["right_table"] in table_ids
        ]

    async def get_v1_relationship_path(
        self,
        start_table: str,
        end_table: str,
    ) -> list[dict]:
        if start_table == end_table:
            return []
        result = await self.session.execute(
            text("SELECT * FROM meta_v1_relationship WHERE allowed = TRUE")
        )
        relationships = [dict(row) for row in result.mappings().all()]
        queue: list[tuple[str, list[dict]]] = [(start_table, [])]
        visited = {start_table}
        while queue:
            table_id, path = queue.pop(0)
            for relationship in relationships:
                if relationship["left_table"] == table_id:
                    neighbor = relationship["right_table"]
                elif relationship["right_table"] == table_id:
                    neighbor = relationship["left_table"]
                else:
                    continue
                next_path = [*path, relationship]
                if neighbor == end_table:
                    return next_path
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, next_path))
        return []

    @staticmethod
    def _decode_json(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, str):
            return json.loads(value)
        return value

    @classmethod
    def _v1_metric_from_row(cls, row) -> MetricInfo:
        return MetricInfo(
            id=row["metric_id"],
            name=row["display_name"],
            description=row["description"],
            relevant_columns=list(cls._decode_json(row["relevant_columns"], [])),
            alias=list(cls._decode_json(row["aliases"], [])),
            formula=row["formula"],
            base_grain=row["base_grain"],
            time_column=row["time_column"],
            status_filters={
                key: list(values)
                for key, values in cls._decode_json(row["status_filters"], {}).items()
            },
            allowed_dimensions=list(cls._decode_json(row["allowed_dimensions"], [])),
            component_metrics=list(cls._decode_json(row["component_metrics"], [])),
            version=row["version"],
        )
