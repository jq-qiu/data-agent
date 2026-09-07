"""管理数仓和元数据库的异步引擎及 Session 工厂生命周期。"""

import asyncio

from sqlalchemy import Result, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.conf.app_config import DBConfig, app_config


class MysqlClientManager:
    """
    用于操作dw,meta数据客户端管理器
    """

    def __init__(self, db_config: DBConfig):
        self.db_config = db_config
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("MySQL engine is not initialized; call init() first")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        # Repository 按请求创建 Session；Manager 不保存具体请求的事务状态。
        if self._session_factory is None:
            raise RuntimeError("MySQL session factory is not initialized; call init() first")
        return self._session_factory

    def _get_url(self):
        return f"mysql+asyncmy://{self.db_config.user}:{self.db_config.password}@{self.db_config.host}:{self.db_config.port}/{self.db_config.database}?charset=utf8mb4"

    def init(self):
        """创建引擎对象，用于创建数据库连接,内部集成连接池"""
        # Engine 持有连接池，初始化一次后由多个短生命周期 Session 复用。
        self._engine = create_async_engine(
            url=self._get_url(),
            echo=False,
            pool_size=10,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=30
        )
        # 创建Session工厂
        self._session_factory = async_sessionmaker(
            # 绑定异步引擎
            bind=self.engine,
            # 只有你手动调用 session.flush() 或 session.commit() 时，才会把内存中的对象变更同步到数据库；
            autoflush=False,
            # 提交后，ORM 对象的属性仍保留内存中的值，访问时不触发任何数据库 IO
            expire_on_commit=False
        )

    async def close(self):
        """关闭连接池；业务 Repository 只接收 Session，不管理全局引擎。"""

        if self._engine:
            await self._engine.dispose()


# 操作数仓mySQL客户端管理器对象
dw_mysql_client_manager = MysqlClientManager(app_config.db_dw)
# 操作元数据库mySQL客户端管理器对象
meta_mysql_client_manager = MysqlClientManager(app_config.db_meta)

if __name__ == '__main__':
    # 操作数仓MySQL
    dw_mysql_client_manager.init()


    async def test():
        # 获取操作DBSession对象
        async with AsyncSession(dw_mysql_client_manager.engine) as dw_session:
            ## 案例一
            # sql = "show tables"
            # # 执行自定义SQL
            # result:Result =  await dw_session.execute(text(sql))
            # # 获取结果 一列多行采用 .scalars().fetchall()
            # print(result.scalars().fetchall())
            ## 案例二
            # sql = "select md5('abc')"
            # result:Result = await dw_session.execute(text(sql))
            # #  获取结果 一列一行采用 .scalar()
            # print(result.scalar())
            # 案例三
            sql = "show tables"
            # 执行自定义SQL
            result: Result = await dw_session.execute(text(sql))
            # 获取结果 如果获取字段名称对应字段取值 采用.mappings().fetchall()
            print(result.mappings().fetchall())


    # asyncio.run(test())
    async def test_session_factory():
        async with dw_mysql_client_manager.session_factory() as dw_session:
            result: Result = await dw_session.execute(text("show tables"))
            print(result.scalars().fetchall())

    asyncio.run(test_session_factory())
