"""按应用配置创建供开放式 NL2SQL 节点使用的聊天模型客户端。"""

import asyncio

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.conf.api_key import resolve_api_key
from app.conf.app_config import app_config

api_key = resolve_api_key(app_config.llm.api_key_env, "硅基流动")

llm = ChatOpenAI(
    model=app_config.llm.model,
    base_url=app_config.llm.base_url,
    api_key=SecretStr(api_key),
    temperature=0,
    timeout=app_config.llm.timeout,
    max_retries=app_config.llm.max_retries,
)

if __name__ == '__main__':
    # result = llm.invoke("请介绍自己")
    # print(result.content)

    async def test_llm():
        result = await llm.ainvoke("请介绍自己")
        print(result.content)
    asyncio.run(test_llm())
