from secrets import compare_digest
from uuid import uuid4

from fastapi import APIRouter, File, Header, HTTPException, Request, Response, UploadFile, status

from ..schemas import ExecutionMode, ImageSource, InspectionResult, PiCaptureCompleteRequest, PiCaptureRequest

router = APIRouter(tags=["inspection"])

ALLOWED_UPLOAD_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _validate_upload_type(image: UploadFile) -> bool:
    content_type = (image.content_type or "").lower()
    return not content_type or content_type in ALLOWED_UPLOAD_TYPES


def _require_pi_agent_token(request: Request, token: str | None) -> None:
    expected = request.app.state.settings.raspberry_pi_agent_token_value
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RASPBERRY_PI_AGENT_TOKEN is not configured on the backend.",
        )
    if not token or not compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Raspberry Pi agent token.",
        )


@router.post("/predict/upload", response_model=InspectionResult)
async def predict_upload(request: Request, image: UploadFile = File(...)) -> InspectionResult:
    if not _validate_upload_type(image):
        return await request.app.state.inspection_service.analyze_and_decide(
            b"",
            ImageSource.dashboard_upload,
        )
    image_bytes = await image.read()
    return await request.app.state.inspection_service.analyze_and_decide(
        image_bytes,
        ImageSource.dashboard_upload,
    )


@router.post("/predict/pi-upload", response_model=InspectionResult)
async def predict_pi_upload(
    request: Request,
    image: UploadFile = File(...),
    x_rammlah_agent_token: str | None = Header(default=None),
) -> InspectionResult:
    _require_pi_agent_token(request, x_rammlah_agent_token)
    if not _validate_upload_type(image):
        return await request.app.state.inspection_service.analyze_and_decide(
            b"",
            ImageSource.raspberry_pi_camera,
        )
    image_bytes = await image.read()
    return await request.app.state.inspection_service.analyze_and_decide(
        image_bytes,
        ImageSource.raspberry_pi_camera,
    )


@router.post("/scan", response_model=InspectionResult)
async def scan(request: Request) -> InspectionResult:
    if not request.app.state.settings.camera_enabled:
        if not request.app.state.settings.raspberry_pi_agent_token_value:
            result = InspectionResult(
                success=False,
                image_source=ImageSource.raspberry_pi_camera,
                execution_mode=ExecutionMode.prototype,
                robot_status=request.app.state.state_service.robot_status,
                robot_action="No Action",
                reason="RASPBERRY_PI_AGENT_TOKEN is not configured. Raspberry Pi capture requests are disabled.",
                error="RASPBERRY_PI_AGENT_TOKEN is not configured.",
            )
            request.app.state.state_service.set_latest_result(result)
            return result

        capture_request = PiCaptureRequest(request_id=uuid4().hex)
        request.app.state.state_service.set_pi_capture_request(capture_request)
        result = InspectionResult(
            success=True,
            image_source=ImageSource.raspberry_pi_camera,
            execution_mode=ExecutionMode.prototype,
            robot_status=request.app.state.state_service.robot_status,
            robot_action="Waiting for Raspberry Pi Capture",
            reason="Capture request sent to Raspberry Pi. Waiting for the Pi agent to upload the image.",
        )
        request.app.state.state_service.set_camera_status("Waiting for Pi")
        request.app.state.state_service.set_latest_result(result)
        return result

    return await request.app.state.inspection_service.scan_from_camera()


@router.get("/latest", response_model=InspectionResult | None)
async def latest(request: Request) -> InspectionResult | None:
    return request.app.state.state_service.get_latest_result()


@router.get("/pi-agent/capture-request", response_model=PiCaptureRequest | None)
async def get_pi_capture_request(
    request: Request,
    response: Response,
    x_rammlah_agent_token: str | None = Header(default=None),
) -> PiCaptureRequest | None:
    _require_pi_agent_token(request, x_rammlah_agent_token)
    capture_request = request.app.state.state_service.get_pi_capture_request()
    if capture_request is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return capture_request


@router.post("/pi-agent/capture-request/{request_id}/complete")
async def complete_pi_capture_request(
    request_id: str,
    payload: PiCaptureCompleteRequest,
    request: Request,
    x_rammlah_agent_token: str | None = Header(default=None),
) -> dict[str, bool]:
    _require_pi_agent_token(request, x_rammlah_agent_token)
    cleared = request.app.state.state_service.clear_pi_capture_request(request_id)
    if not cleared:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture request not found.")

    if not payload.success:
        result = InspectionResult(
            success=False,
            image_source=ImageSource.raspberry_pi_camera,
            execution_mode=ExecutionMode.prototype,
            robot_status=request.app.state.state_service.robot_status,
            robot_action="No Action",
            reason=payload.error or "Raspberry Pi capture failed.",
            error=payload.error or "Raspberry Pi capture failed.",
        )
        request.app.state.state_service.set_camera_status("Error")
        request.app.state.state_service.set_latest_result(result)
    else:
        request.app.state.state_service.set_camera_status("Connected")

    return {"success": True}
