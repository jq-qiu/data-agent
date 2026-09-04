from typing import Annotated

from fastapi import APIRouter
from fastapi.params import Depends
from starlette.responses import StreamingResponse

from app.api.dependencies import get_query_service
from app.api.schemas.query_schema import QuerySchema
from app.services.query_service import QueryService

query_router = APIRouter(tags=["查询接口"])

#web层 负责处理客户端（前端）请求，调用业务逻辑，返回结果给客户端
@query_router.post("/api/query")
async def query(query_schema: QuerySchema, query_service:Annotated[QueryService, Depends(get_query_service)]):
    return StreamingResponse(query_service.query_answer(query_schema.query), media_type="text/event-stream")
