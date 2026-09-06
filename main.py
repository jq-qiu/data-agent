from fastapi import FastAPI

from app.api.routers.query_router import query_router
from app.core.lifespan import lifespan
from app.deployment import deployment_router, mount_frontend

# 1.创建fastapi实例对象
app = FastAPI(title="掌柜问数", lifespan=lifespan)

# 2.注册产品 API，再将前端挂载为最低优先级的根路径应用
app.include_router(query_router)
app.include_router(deployment_router)
mount_frontend(app)

