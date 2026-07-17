import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routes import inspection, robot, status
from .services.camera_service import CameraService
from .services.fuzzy_logic import FuzzyLogicService
from .services.inspection_service import InspectionService
from .services.openai_vision import OpenAIVisionService
from .services.robot_service import build_robot_controller
from .services.weather_service import WeatherService
from .state import StateService

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Rammlah backend starting")
    settings.validate_for_startup()

    state_service = StateService(
        settings.data_dir,
        robot_enabled=settings.robot_enabled,
        camera_enabled=settings.camera_enabled,
        openai_configured=bool(settings.openai_api_key_value),
    )
    robot_controller = build_robot_controller(settings)
    if settings.robot_enabled and robot_controller.is_ready():
        state_service.set_robot_status("Ready")
    elif settings.robot_enabled:
        state_service.set_robot_status("Disconnected")
    else:
        state_service.set_robot_status("Disabled")

    camera_service = CameraService(settings)
    weather_service = WeatherService(settings)
    fuzzy_service = FuzzyLogicService()
    vision_service = OpenAIVisionService(settings)
    inspection_service = InspectionService(
        settings=settings,
        state=state_service,
        vision_service=vision_service,
        weather_service=weather_service,
        fuzzy_service=fuzzy_service,
        camera_service=camera_service,
        robot_controller=robot_controller,
    )

    app.state.settings = settings
    app.state.state_service = state_service
    app.state.inspection_service = inspection_service
    app.state.robot_controller = robot_controller
    logger.info("Rammlah backend startup complete")
    try:
        yield
    finally:
        robot_controller.close()
        logger.info("Rammlah backend stopped")


app = FastAPI(
    title="Rammlah Raspberry Pi AI Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings.images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=settings.images_dir), name="images")

app.include_router(inspection.router)
app.include_router(status.router)
app.include_router(robot.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "Rammlah Raspberry Pi AI Backend", "status": "Online"}
