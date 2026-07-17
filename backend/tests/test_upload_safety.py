import pytest

from app.config import Settings
from app.schemas import ImageSource, VisionAnalysis, WeatherData
from app.services.robot_service import MockRobotController
from test_inspection_logic import FakeFuzzyService, FakeVisionService, FakeWeatherService, make_service


@pytest.mark.asyncio
async def test_upload_mode_blocks_robot_even_with_robot_enabled(tmp_path, image_bytes):
    service, _, robot, _ = make_service(
        tmp_path,
        image_bytes,
        FakeVisionService(
            VisionAnalysis(
                prediction="Dust",
                confidence=0.95,
                dust_coverage_percent=88,
                reason="Dusty panel",
            )
        ),
        weather=FakeWeatherService(WeatherData(wind_speed_mps=0.5, rainfall_mm=0.0)),
        fuzzy=FakeFuzzyService(score=95),
        robot_enabled=True,
    )

    result = await service.analyze_and_decide(image_bytes, ImageSource.dashboard_upload)

    assert result.execution_mode == "Test"
    assert result.robot_executed is False
    assert result.robot_action == "Cleaning Recommended - Test Mode"
    assert not any(command.startswith("CLEAN") for command in robot.commands)


def test_missing_openai_key_causes_clear_startup_configuration_error(tmp_path):
    settings = Settings(
        OPENAI_API_KEY="",
        data_dir=tmp_path / "data",
        images_dir=tmp_path / "images",
        captures_dir=tmp_path / "images" / "captures",
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is missing"):
        settings.validate_for_startup()


def test_mock_robot_records_timeout_and_stop():
    robot = MockRobotController(ready=True)
    robot.connect()
    robot.timeout_on = "CLEAN_FORWARD"

    with pytest.raises(Exception):
        robot.clean_forward()
    robot.stop()

    assert robot.commands == ["CLEAN_FORWARD", "STOP"]
