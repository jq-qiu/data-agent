"""构建旧版元知识索引的兼容命令行入口。"""

import argparse
import asyncio
from pathlib import Path

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import dw_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.meta_knowledge_service import MetaKnowledgeService


async def build(meta_config_path:Path):
    try:
        # 调用业务逻辑层-处理核心业务逻辑
        # 1.初始化工作
        dw_mysql_client_manager.init()
        meta_mysql_client_manager.init()
        qdrant_client_manager.init()
        embedding_client_manager.init()
        es_client_manager.init()

        # 2. 通过MySQL客户端管理器获取操作不同库的Session对象
        async with (dw_mysql_client_manager.session_factory() as dw_session,
                    meta_mysql_client_manager.session_factory() as meta_session):
            # 3. 创建业务层对象
            meta_knowledge_service = MetaKnowledgeService(
                meta_mysql_repository=MetaMySQLRepository(meta_session),
                dw_mysql_repository=DWMySQLRepository(dw_session),
                column_qdrant_repository=ColumnQdrantRepository(qdrant_client_manager.client),
                embedding_client=embedding_client_manager.client,
                value_es_repository=ValueESRepository(es_client_manager.client),
                metric_qdrant_repository=MetricQdrantRepository(qdrant_client_manager.client)
            )
            # 4. 调用业务对象 build 函数完成元数据知识库构建
            await meta_knowledge_service.build(meta_config_path)
    finally:
        # 异常时也要关闭连接，避免连接池和 HTTP 连接泄漏。
        await dw_mysql_client_manager.close()
        await meta_mysql_client_manager.close()
        await qdrant_client_manager.close()
        await es_client_manager.close()









if __name__ == '__main__':
    """需求：通过脚本参数 传入人工配置文件路径（包含同步表、字段、说明信息）"""
    #1.通过argparse获取脚本参数 获取构建元数据知识库人为补齐的元数据信息
    #1.1 创建参数解析器对象
    parser = argparse.ArgumentParser(
        prog='python -m app.scripts.build_meta_knowledge',
        description='通过脚本+额外脚本(-c 传递)参数实现',
        epilog='========结束==========')
    #1.2 添加可选参数
    default_config_path = Path(__file__).parents[2] / "conf" / "meta_config.yaml"
    parser.add_argument(
        '-c',
        '--conf',
        type=Path,
        default=default_config_path,
        help=f'元数据配置文件路径，默认使用：{default_config_path}'
    )
    #1.3 调用函数将提取到脚本参数封装到Namespace对象
    parse_args = parser.parse_args()
    #1.4 获取到脚本参数中-yaml文件路径
    config_path: Path = parse_args.conf.resolve()
    if not config_path.is_file():
        parser.error(f"元数据配置文件不存在：{config_path}")

    #2.执行构建元数据知识库
    asyncio.run(build(config_path))
