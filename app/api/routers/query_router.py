from typing import Annotated

from fastapi import APIRouter
from fastapi.params import Depends
from starlette.responses import StreamingResponse

from app.api.dependencies import get_query_service
from app.api.schemas.query_schema import QuerySchema
from app.services.query_service import QueryService

query_router = APIRouter(tags=["查询接口"])


@query_router.post("/api/query")
async def query(
    query_schema: QuerySchema,
    query_service: Annotated[QueryService, Depends(get_query_service)],
) -> StreamingResponse:
    return StreamingResponse(
        query_service.query_answer(query_schema.resolved_question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
