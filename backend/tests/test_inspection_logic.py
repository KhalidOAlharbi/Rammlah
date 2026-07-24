import asyncio

import pytest

from app.config import Settings
from app.schemas import FuzzyInputs, FuzzyResult, ImageSource, VisionAnalysis, WeatherData
from app.services.camera_service import CameraCapture
from app.services.inspection_service import InspectionService
from app.services.robot_service import MockRobotController
from app.services.weather_service import WeatherServiceError
from app.state import StateService


class FakeVisionService:
    def __init__(self, *results: VisionAnalysis):
        self.results = list(results)
        self.calls = 0

    def analyze_image(self, image_bytes: bytes) -> VisionAnalysis:
        self.calls += 1
        if len(self.results) == 1:
            return self.results[0]
        return self.results.pop(0)


class FakeWeatherService:
    def __init__(self, weather: WeatherData | None = None, error: Exception | None = None):
        self.weather = weather or WeatherData(wind_speed_mps=0.5, rainfall_mm=0.0)
        self.error = error
        self.calls = 0

    async def get_current_weather(self) -> WeatherData:
        self.calls += 1
        if self.error:
            raise self.error
        return self.weather


class FakeFuzzyService:
    def __init__(self, score: float = 70):
        self.score = score
        self.calls = 0

    def calculate(self, dust_coverage_percent: float, wind_speed_mps: float, rainfall_mm: float) -> FuzzyResult:
        self.calls += 1
        return FuzzyResult(
            score=self.score,
            decision="Clean" if self.score >= 60 else "Postpone",
            inputs=FuzzyInputs(
                dust_coverage_percent=dust_coverage_percent,
                wind_speed_mps=wind_speed_mps,
                rainfall_mm=rainfall_mm,
            ),
        )


class FakeCameraService:
    def __init__(self, image_bytes: bytes, path):
        self.image_bytes = image_bytes
        self.path = path
        self.calls = 0

    def capture_jpeg(self) -> CameraCapture:
        self.calls += 1
        return CameraCapture(image_bytes=self.image_bytes, path=self.path)


def analysis(prediction: str, dust: float = 0, confidence: float = 0.9) -> VisionAnalysis:
    return VisionAnalysis(
        prediction=prediction,
        confidence=confidence,
        dust_coverage_percent=dust,
        reason=f"{prediction} panel",
    )


def make_service(
    tmp_path,
    image_bytes: bytes,
    vision: FakeVisionService,
    *,
    weather: FakeWeatherService | None = None,
    fuzzy: FakeFuzzyService | None = None,
    robot_enabled: bool = False,
    camera_enabled: bool = False,
    run_inline: bool = True,
    schedule_follow_up: bool = False,
):
    settings = Settings(
        OPENAI_API_KEY="test-key",
        LATITUDE=24.0,
        LONGITUDE=46.0,
        CAMERA_ENABLED=camera_enabled,
        ROBOT_ENABLED=robot_enabled,
        FOLLOW_UP_SCAN_DELAY_SECONDS=0.01,
        data_dir=tmp_path / "data",
        images_dir=tmp_path / "images",
        captures_dir=tmp_path / "images" / "captures",
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.captures_dir.mkdir(parents=True, exist_ok=True)

    state = StateService(
        settings.data_dir,
        robot_enabled=settings.robot_enabled,
        camera_enabled=settings.camera_enabled,
        openai_configured=True,
    )
    robot = MockRobotController(ready=True)
    robot.connect()
    camera = FakeCameraService(image_bytes, settings.captures_dir / "followup.jpg")
    service = InspectionService(
        settings=settings,
        state=state,
        vision_service=vision,
        weather_service=weather or FakeWeatherService(),
        fuzzy_service=fuzzy or FakeFuzzyService(),
        camera_service=camera,
        robot_controller=robot,
        run_cleaning_in_background=not run_inline,
        schedule_follow_up_scans=schedule_follow_up,
    )
    return service, state, robot, camera


@pytest.mark.asyncio
async def test_clean_image_does_not_run_fuzzy_logic(tmp_path, image_bytes):
    fuzzy = FakeFuzzyService()
    weather = FakeWeatherService()
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Clean")),
        weather=weather,
        fuzzy=fuzzy,
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.prediction == "Clean"
    assert result.cleaning_required is False
    assert result.fuzzy_logic_used is False
    assert fuzzy.calls == 0
    assert weather.calls == 0


@pytest.mark.asyncio
async def test_crack_stops_robot_and_never_cleans(tmp_path, image_bytes):
    service, _, robot, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Crack", dust=80)),
        robot_enabled=True,
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.raspberry_pi_camera)

    assert result.maintenance_alert is True
    assert result.cleaning_required is False
    assert result.robot_status == "Stopped"
    assert "STOP" in robot.commands
    assert "CLEAN_FORWARD" not in robot.commands


@pytest.mark.asyncio
async def test_dust_below_25_percent_does_not_enter_fuzzy_logic(tmp_path, image_bytes):
    fuzzy = FakeFuzzyService()
    weather = FakeWeatherService()
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=24.9)),
        weather=weather,
        fuzzy=fuzzy,
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.cleaning_required is False
    assert result.fuzzy_logic_used is False
    assert fuzzy.calls == 0
    assert weather.calls == 0


@pytest.mark.asyncio
async def test_dust_25_to_below_30_requests_another_capture(tmp_path, image_bytes):
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=27)),
    )

    upload_result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)
    camera_result = await service.analyze_and_decide(image_bytes, ImageSource.raspberry_pi_camera)

    assert upload_result.robot_action == "Upload Another Image"
    assert camera_result.robot_action == "Capture Again"
    assert upload_result.fuzzy_logic_used is False


@pytest.mark.asyncio
async def test_dust_30_or_higher_evaluates_weather(tmp_path, image_bytes):
    weather = FakeWeatherService(WeatherData(wind_speed_mps=3.0, rainfall_mm=0.0))
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=30)),
        weather=weather,
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert weather.calls == 1
    assert result.robot_action == "Postpone Cleaning"


@pytest.mark.asyncio
async def test_wind_above_4_prevents_cleaning(tmp_path, image_bytes):
    fuzzy = FakeFuzzyService()
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=70)),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=4.1, rainfall_mm=0.0)),
        fuzzy=fuzzy,
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.cleaning_required is False
    assert result.reason == "Safety First - high wind."
    assert fuzzy.calls == 0


@pytest.mark.asyncio
async def test_wind_from_2_to_4_postpones_cleaning(tmp_path, image_bytes):
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=70)),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=2.0, rainfall_mm=0.0)),
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.cleaning_required is False
    assert result.reason == "Wind may provide partial natural self-cleaning."


@pytest.mark.asyncio
async def test_rainfall_above_5_prevents_cleaning(tmp_path, image_bytes):
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=70)),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=1.0, rainfall_mm=5.1)),
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.cleaning_required is False
    assert result.reason == "Natural rainfall is sufficient."


@pytest.mark.asyncio
async def test_rainfall_from_point_3_to_5_postpones_cleaning(tmp_path, image_bytes):
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=70)),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=1.0, rainfall_mm=0.3)),
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.cleaning_required is False
    assert result.reason == "Partial natural cleaning is expected."


@pytest.mark.asyncio
async def test_safe_weather_enters_fuzzy_logic(tmp_path, image_bytes):
    fuzzy = FakeFuzzyService(score=70)
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=70)),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=1.0, rainfall_mm=0.1)),
        fuzzy=fuzzy,
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert fuzzy.calls == 1
    assert result.fuzzy_logic_used is True


@pytest.mark.asyncio
async def test_fuzzy_score_60_or_above_recommends_cleaning(tmp_path, image_bytes):
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=70)),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=1.0, rainfall_mm=0.0)),
        fuzzy=FakeFuzzyService(score=60),
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.cleaning_required is True
    assert result.robot_action == "Cleaning Recommended - Test Mode"
    assert result.robot_executed is False


@pytest.mark.asyncio
async def test_fuzzy_score_below_60_postpones_cleaning(tmp_path, image_bytes):
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=70)),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=1.0, rainfall_mm=0.0)),
        fuzzy=FakeFuzzyService(score=59.9),
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.cleaning_required is False
    assert result.robot_action == "Postpone Cleaning"


@pytest.mark.asyncio
async def test_dashboard_upload_never_calls_physical_robot(tmp_path, image_bytes):
    service, _, robot, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=80)),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=1.0, rainfall_mm=0.0)),
        fuzzy=FakeFuzzyService(score=90),
        robot_enabled=True,
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.execution_mode == "Test"
    assert result.robot_executed is False
    assert "CLEAN_FORWARD" not in robot.commands


@pytest.mark.asyncio
async def test_raspberry_pi_camera_can_call_robot_when_enabled(tmp_path, image_bytes):
    service, _, robot, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=80)),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=1.0, rainfall_mm=0.0)),
        fuzzy=FakeFuzzyService(score=90),
        robot_enabled=True,
        camera_enabled=True,
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.raspberry_pi_camera)

    assert result.execution_mode == "Prototype"
    assert result.robot_executed is True
    assert "CLEAN_FORWARD" in robot.commands
    assert "CLEAN_REVERSE" in robot.commands
    assert "RETURN_HOME" in robot.commands


@pytest.mark.asyncio
async def test_crack_overrides_high_dust_coverage(tmp_path, image_bytes):
    service, _, robot, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Crack", dust=95)),
        robot_enabled=True,
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.raspberry_pi_camera)

    assert result.prediction == "Crack"
    assert result.maintenance_alert is True
    assert result.cleaning_required is False
    assert "CLEAN_FORWARD" not in robot.commands


@pytest.mark.asyncio
async def test_weather_failure_blocks_cleaning(tmp_path, image_bytes):
    service, _, _, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=80)),
        weather=FakeWeatherService(error=WeatherServiceError("network down")),
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.cleaning_required is False
    assert result.robot_action == "Postpone Cleaning"
    assert result.weather_error == "network down"


@pytest.mark.asyncio
async def test_robot_timeout_triggers_stop(tmp_path, image_bytes):
    service, state, robot, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=80)),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=1.0, rainfall_mm=0.0)),
        fuzzy=FakeFuzzyService(score=90),
        robot_enabled=True,
        camera_enabled=True,
    )
    robot.timeout_on = "CLEAN_FORWARD"

    await service.analyze_and_decide(image_bytes, ImageSource.raspberry_pi_camera)

    assert "STOP" in robot.commands
    assert state.robot_status == "Stopped"


@pytest.mark.asyncio
async def test_robot_returns_home_and_schedules_next_camera_scan(tmp_path, image_bytes):
    service, state, robot, camera = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(analysis("Dust", dust=80), analysis("Clean")),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=1.0, rainfall_mm=0.0)),
        fuzzy=FakeFuzzyService(score=90),
        robot_enabled=True,
        camera_enabled=True,
        schedule_follow_up=True,
    )

    await service.analyze_and_decide(image_bytes, ImageSource.raspberry_pi_camera)
    await asyncio.sleep(0.05)

    assert "RETURN_HOME" in robot.commands
    assert state.follow_up_scan_scheduled is True
    assert camera.calls >= 1
