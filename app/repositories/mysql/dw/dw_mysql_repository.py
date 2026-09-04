import asyncio

from sqlalchemy import Result, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.nl2sql.validator import ValidatedSQL


class DWMySQLRepository:
    """跟MySQL数据库（数仓数据库）交互持久层 必须通过Session对象进行CURD"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_column_type_by_table_id(self, table_id: str) -> dict[str, str]:
        """根据表ID/表名称查询该表下所有字段信息 目的获取字段数据类型"""
        sql = f"show columns from {table_id}"
        result: Result = await self.session.execute(text(sql))
        # 查询结果是多列多行 返回列表 包装对象
        return {row.Field: row.Type for row in result.fetchall()}

    async def get_column_values_by_table_id(
        self, table_id: str, column_name: str, limit: int = 10
    ) -> list[str]:
        """查询指定个数某张表某个字段取值"""
        sql = f"SELECT distinct {column_name} from {table_id} limit {limit}"
        result: Result = await self.session.execute(text(sql))
        # 结果：一列多行
        return result.scalars().fetchall()

    async def get_db_info(self) -> dict[str, str]:
        """查询数仓数据库版本以及SQL方言"""
        # 1.获取数据库版本
        sql = "SELECT VERSION()"
        result = await self.session.execute(text(sql))
        version = result.scalar()
        # 2.获取数据库方言
        dialect = self.session.get_bind().dialect.name

        # 3.返回结果
        return {"version": version, "dialect": dialect}

    async def validate_sql(self, validated_sql: ValidatedSQL):
        await asyncio.wait_for(
            self.session.execute(text(f"EXPLAIN {validated_sql.sql}")),
            timeout=validated_sql.timeout_seconds,
        )

    async def execute_sql(self, validated_sql: ValidatedSQL) -> list[dict]:
        result = await asyncio.wait_for(
            self.session.execute(text(validated_sql.sql)),
            timeout=validated_sql.timeout_seconds,
        )
        return [
            dict(row_mapping) for row_mapping in result.mappings().fetchmany(validated_sql.max_rows)
        ]
