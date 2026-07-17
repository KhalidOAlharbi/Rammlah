from fastapi import APIRouter, Request

from ..schemas import StatusResponse

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status", response_model=StatusResponse)
async def status(request: Request) -> StatusResponse:
    return request.app.state.state_service.get_status()
