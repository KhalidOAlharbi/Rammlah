from secrets import compare_digest

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile, status

from ..schemas import ImageSource, InspectionResult, PiCaptureCompletion, PiCaptureRequestStatus

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
    return await request.app.state.inspection_service.scan_from_camera()


@router.post("/pi-capture/request", response_model=PiCaptureRequestStatus)
async def request_pi_capture(request: Request) -> PiCaptureRequestStatus:
    return request.app.state.state_service.request_pi_capture(countdown_seconds=10)


@router.get("/pi-capture/status", response_model=PiCaptureRequestStatus)
async def pi_capture_status(request: Request) -> PiCaptureRequestStatus:
    return request.app.state.state_service.get_pi_capture_request()


@router.get(
    "/pi-agent/capture-request",
    response_model=PiCaptureRequestStatus,
    status_code=status.HTTP_200_OK,
    responses={204: {"description": "No pending capture request"}},
)
async def pi_agent_capture_request(
    request: Request,
    x_rammlah_agent_token: str | None = Header(default=None),
) -> PiCaptureRequestStatus:
    _require_pi_agent_token(request, x_rammlah_agent_token)
    capture_request = request.app.state.state_service.claim_pi_capture_request()
    if capture_request is None:
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT)
    return capture_request


@router.post("/pi-agent/capture-request/{request_id}/complete", response_model=PiCaptureRequestStatus)
async def complete_pi_agent_capture_request(
    request_id: str,
    completion: PiCaptureCompletion,
    request: Request,
    x_rammlah_agent_token: str | None = Header(default=None),
) -> PiCaptureRequestStatus:
    _require_pi_agent_token(request, x_rammlah_agent_token)
    return request.app.state.state_service.complete_pi_capture_request(request_id, completion)


@router.get("/latest", response_model=InspectionResult | None)
async def latest(request: Request) -> InspectionResult | None:
    return request.app.state.state_service.get_latest_result()
