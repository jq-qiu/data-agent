from fastapi import FastAPI

from app.api.routers.hello_router import hello_router
from app.api.routers.query_router import query_router
from app.core.lifespan import lifespan

# 1.创建fastapi实例对象
app = FastAPI(title="掌柜问数", lifespan=lifespan)

#2.注册自定义路由
app.include_router(hello_router)
app.include_router(query_router)

