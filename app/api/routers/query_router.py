from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from starlette.responses import StreamingResponse

from app.api.dependencies import get_query_service
from app.api.schemas.query_schema import QuerySchema
from app.services.query_service import QueryService

query_router = APIRouter(tags=["查询接口"])


_SYNTHETIC_DEMO_QUESTIONS = {
    "D01": "为什么2018年5月相比2018年4月PR州GMV下降？请按地区分析流量、促销和库存。",
    "D02": "为什么2018年5月相比2018年4月SP州informatica_acessorios品类GMV下降？请按地区、按品类分析流量、促销和库存。",
    "D03": "为什么2018年5月相比2018年4月SC州GMV下降？请按地区分析流量、促销和库存。",
    "D04": "为什么2018年5月相比2018年4月SP州eletrodomesticos品类GMV下降？请按地区、按品类分析流量、促销和库存。",
    "D05": "为什么2018年5月相比2018年4月SP州GMV下降？请按地区分析流量、促销和库存。",
    "D06": "为什么2018年5月相比2018年4月SP州cool_stuff品类GMV下降？请按地区、按品类分析流量、促销和库存。",
    "D07": "为什么2018年5月相比2018年4月MG州GMV下降？请按地区分析流量、促销和库存。",
    "D08": "为什么2018年5月相比2018年4月PA州GMV下降？请按地区分析流量、促销和库存。",
    "D09": "为什么2018年5月相比2018年4月RJ州GMV下降？请按地区分析流量、促销和库存。",
    "D10": "为什么2018年5月相比2018年4月ES州GMV下降？请按地区分析流量、促销和库存。",
}


@query_router.post("/api/demo/synthetic-diagnosis/{case_id}")
async def synthetic_diagnosis_demo(
    case_id: str,
    query_service: Annotated[QueryService, Depends(get_query_service)],
) -> StreamingResponse:
    question = _SYNTHETIC_DEMO_QUESTIONS.get(case_id)
    if question is None:
        raise HTTPException(status_code=422, detail="unknown synthetic case")
    return StreamingResponse(
        query_service.synthetic_diagnosis_events(case_id, question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
