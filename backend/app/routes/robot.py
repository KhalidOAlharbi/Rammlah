import asyncio

from fastapi import APIRouter, HTTPException, Request

from ..schemas import RobotCommandRequest, RobotCommandResponse, RobotStopResponse
from ..services.robot_service import RobotControllerError

router = APIRouter(prefix="/robot", tags=["robot"])


def _manual_status(action: str) -> str:
    if action in {"forward", "reverse", "left", "right"}:
        return "Manual Drive"
    if action == "brush_on":
        return "Brush Running"
    if action == "return_home":
        return "Returning Home"
    if action in {"brush_off", "stop"}:
        return "Stopped"
    return "Ready"


@router.post("/stop", response_model=RobotStopResponse)
async def stop_robot(request: Request) -> RobotStopResponse:
    await request.app.state.inspection_service.emergency_stop()
    return RobotStopResponse(
        success=True,
        robot_status="Stopped",
        message="Emergency stop command sent.",
    )


@router.post("/command", response_model=RobotCommandResponse)
async def command_robot(request: Request, payload: RobotCommandRequest) -> RobotCommandResponse:
    settings = request.app.state.settings
    state = request.app.state.state_service
    robot = request.app.state.robot_controller

    if not settings.robot_enabled:
        raise HTTPException(status_code=409, detail="Robot is disabled. Set ROBOT_ENABLED=true on the Raspberry Pi.")
    if not robot.is_ready():
        state.set_robot_status("Disconnected")
        raise HTTPException(status_code=409, detail="Robot controller is not ready.")
    if state.cleaning_active and payload.action.value != "stop":
        raise HTTPException(status_code=409, detail="Automatic cleaning is active. Stop the robot before manual control.")
    if state.emergency_stop_active and payload.action.value != "stop":
        raise HTTPException(status_code=409, detail="Emergency stop is active. Send Stop before manual control.")

    try:
        await asyncio.to_thread(
            robot.run_manual_command,
            payload.action.value,
            speed=payload.speed,
            duration_seconds=payload.duration_seconds,
        )
    except RobotControllerError as exc:
        state.set_robot_status("Error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    robot_status = _manual_status(payload.action.value)
    if payload.duration_seconds and payload.action.value != "brush_off":
        robot_status = "Stopped"
    state.set_robot_status(robot_status)
    state.set_emergency_stop(False)
    return RobotCommandResponse(
        success=True,
        action=payload.action,
        robot_status=robot_status,
        message=f"Robot command sent: {payload.action.value}",
    )
