from fastapi import APIRouter, File, Request, UploadFile

from ..schemas import ImageSource, InspectionResult

router = APIRouter(prefix="/api", tags=["inspection"])

ALLOWED_UPLOAD_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/predict/upload", response_model=InspectionResult)
async def predict_upload(request: Request, image: UploadFile = File(...)) -> InspectionResult:
    content_type = (image.content_type or "").lower()
    if content_type and content_type not in ALLOWED_UPLOAD_TYPES:
        return await request.app.state.inspection_service.analyze_and_decide(
            b"",
            ImageSource.dashboard_upload,
        )
    image_bytes = await image.read()
    return await request.app.state.inspection_service.analyze_and_decide(
        image_bytes,
        ImageSource.dashboard_upload,
    )


@router.post("/scan", response_model=InspectionResult)
async def scan(request: Request) -> InspectionResult:
    return await request.app.state.inspection_service.scan_from_camera()


@router.get("/latest", response_model=InspectionResult | None)
async def latest(request: Request) -> InspectionResult | None:
    return request.app.state.state_service.get_latest_result()
