from fastapi import APIRouter, Request

from ..schemas import RobotStopResponse

router = APIRouter(prefix="/robot", tags=["robot"])


@router.post("/stop", response_model=RobotStopResponse)
async def stop_robot(request: Request) -> RobotStopResponse:
    await request.app.state.inspection_service.emergency_stop()
    return RobotStopResponse(
        success=True,
        robot_status="Stopped",
        message="Emergency stop command sent.",
    )
