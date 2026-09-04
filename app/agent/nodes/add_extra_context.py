from datetime import datetime

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState, DateInfoState, DBInfoState
from app.core.log import logger


async def add_extra_context(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    write = runtime.stream_writer
    write({"type": "progress", "step": "添加额外上下文", "status": "running"})

    try:
        # 1.封装日期信息
        # 1.1 获取当天对象
        today = datetime.today()
        # 1.2 获取日期、星期数
        date = today.strftime("%Y-%m-%d")
        weekday = today.strftime("%A")
        # 1.3 获取当前季度
        quarter = f"Q{(today.month - 1) // 3 + 1}"
        # 1.4 封装日期state
        date_state = DateInfoState(
            date=date,
            weekday=weekday,
            quarter=quarter
        )

        # 2.封装"数仓"数据库信息
        dw_mysql_repository = runtime.context["dw_mysql_repository"]
        # 2.1 通过调用"dw库"持久层获取数据库信息
        db_info: dict[str, str] = await dw_mysql_repository.get_db_info()

        # 2.2 封装数据库state
        db_info_state = DBInfoState(
            version=db_info["version"],
            dialect=db_info["dialect"]
        )
        write({"type": "progress", "step": "添加额外上下文", "status": "success"})
        logger.info(f"添加额外上下文成功：{db_info_state}, {date_state}")

        # 3.更新state中
        return {"date_info": date_state, "db_info": db_info_state}
    except Exception as e:
        logger.error(f"添加上下文发生异常：{e}")
        write({"type": "progress", "step": "添加上下文", "status": "error"})
        raise
