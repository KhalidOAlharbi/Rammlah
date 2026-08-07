import asyncio
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import Settings
from ..schemas import ExecutionMode, ImageSource, InspectionResult, VisionAnalysis
from ..state import StateService
from .camera_service import CameraService, CameraServiceError
from .fuzzy_logic import FuzzyLogicError, FuzzyLogicService
from .openai_vision import InvalidImageError, OpenAIVisionError, OpenAIVisionService
from .robot_service import RobotController, RobotControllerError
from .weather_service import WeatherService, WeatherServiceError

logger = logging.getLogger(__name__)


class InspectionService:
    def __init__(
        self,
        settings: Settings,
        state: StateService,
        vision_service: OpenAIVisionService,
        weather_service: WeatherService,
        fuzzy_service: FuzzyLogicService,
        camera_service: CameraService,
        robot_controller: RobotController,
        *,
        run_cleaning_in_background: bool = True,
    ):
        self.settings = settings
        self.state = state
        self.vision_service = vision_service
        self.weather_service = weather_service
        self.fuzzy_service = fuzzy_service
        self.camera_service = camera_service
        self.robot = robot_controller
        self.run_cleaning_in_background = run_cleaning_in_background
        self._cleaning_lock = asyncio.Lock()
        self._camera_scan_lock = asyncio.Lock()

    async def analyze_and_decide(
        self,
        image_bytes: bytes,
        image_source: ImageSource,
        image_path: Optional[Path] = None,
    ) -> InspectionResult:
        logger.info("Inspection started: image_source=%s", image_source.value)
        mode = ExecutionMode.test if image_source == ImageSource.dashboard_upload else ExecutionMode.prototype
        self.state.set_current_mode(mode)

        try:
            self._validate_image(image_bytes)
            saved_path = image_path or self._save_image(image_bytes, image_source)
            image_url = self._image_url(saved_path)
        except InvalidImageError as exc:
            result = self._base_result(image_source, mode, success=False, image_url=None)
            result.robot_action = "No Action"
            result.robot_status = self.state.robot_status
            result.error = str(exc)
            result.reason = str(exc)
            self.state.set_latest_result(result)
            return result

        try:
            analysis = await asyncio.to_thread(self.vision_service.analyze_image, image_bytes)
            self.state.set_openai_status("Configured")
        except OpenAIVisionError as exc:
            self.state.set_openai_status("Error")
            await self._stop_robot_if_moving()
            result = self._base_result(image_source, mode, success=False, image_url=image_url)
            result.robot_action = "No Action"
            result.robot_status = self.state.robot_status
            result.error = str(exc)
            result.reason = "OpenAI analysis failed. Robot movement blocked."
            self.state.set_latest_result(result)
            return result

        result = self._base_result(image_source, mode, success=True, image_url=image_url)
        result.prediction = analysis.prediction
        result.confidence = analysis.confidence
        result.dust_coverage_percent = analysis.dust_coverage_percent
        result.reason = analysis.reason

        if analysis.prediction == "Clean":
            self._apply_clean_decision(result)
        elif analysis.prediction == "Crack":
            await self._apply_crack_decision(result)
        elif analysis.prediction == "Dust":
            await self._apply_dust_decision(result, analysis)

        self.state.set_latest_result(result)

        if self._physical_execution_allowed(result, image_source):
            accepted = await self._start_cleaning_sequence()
            result.robot_executed = accepted
            if accepted:
                if self.run_cleaning_in_background:
                    result.robot_status = "Cleaning Forward"
                    result.robot_action = "Cleaning Started"
                else:
                    latest = self.state.get_latest_result()
                    if latest is not None and latest.error:
                        return latest
                    result.robot_status = self.state.robot_status
                    result.robot_action = "Cleaning Completed" if self.state.robot_status == "Home" else "Cleaning Started"
            else:
                result.robot_status = self.state.robot_status
                result.robot_action = "Cleaning Blocked"
            self.state.set_latest_result(result)

        logger.info(
            "Inspection complete: prediction=%s cleaning_required=%s robot_action=%s",
            result.prediction,
            result.cleaning_required,
            result.robot_action,
        )
        return result

    async def scan_from_camera(self) -> InspectionResult:
        async with self._camera_scan_lock:
            try:
                capture = await asyncio.to_thread(self.camera_service.capture_jpeg)
                self.state.set_camera_status("Connected")
            except CameraServiceError as exc:
                self.state.set_camera_status("Error")
                result = self._base_result(
                    ImageSource.raspberry_pi_camera,
                    ExecutionMode.prototype,
                    success=False,
                    image_url=None,
                )
                result.error = str(exc)
                result.reason = str(exc)
                result.robot_action = "No Action"
                result.robot_status = self.state.robot_status
                self.state.set_latest_result(result)
                return result

            return await self.analyze_and_decide(
                capture.image_bytes,
                ImageSource.raspberry_pi_camera,
                image_path=capture.path,
            )

    async def emergency_stop(self) -> None:
        logger.warning("Emergency stop requested")
        self.state.set_emergency_stop(True)
        try:
            await asyncio.to_thread(self.robot.emergency_stop)
        except Exception:
            logger.exception("Emergency stop command failed")
        self.state.set_robot_status("Stopped")

    def _base_result(
        self,
        image_source: ImageSource,
        mode: ExecutionMode,
        *,
        success: bool,
        image_url: Optional[str],
    ) -> InspectionResult:
        return InspectionResult(
            success=success,
            image_source=image_source,
            execution_mode=mode,
            image_url=image_url,
            robot_status=self.state.robot_status if self.state.robot_status else "Idle",
        )

    def _apply_clean_decision(self, result: InspectionResult) -> None:
        result.cleaning_required = False
        result.maintenance_alert = False
        result.robot_action = "No Action"
        result.robot_status = "Idle"
        result.fuzzy_logic_used = False
        result.reason = "Panel appears clean. No cleaning required."

    async def _apply_crack_decision(self, result: InspectionResult) -> None:
        result.cleaning_required = False
        result.maintenance_alert = True
        result.robot_action = "Stop Robot"
        result.robot_status = "Stopped"
        result.fuzzy_logic_used = False
        result.reason = "Crack detected. Cleaning is blocked and maintenance is required."
        await self._stop_robot_if_moving()
        self.state.set_robot_status("Stopped")

    async def _apply_dust_decision(self, result: InspectionResult, analysis: VisionAnalysis) -> None:
        dust = analysis.dust_coverage_percent
        if dust < 25:
            result.prediction = "Clean"
            result.cleaning_required = False
            result.robot_action = "No Action"
            result.robot_status = "Idle"
            result.fuzzy_logic_used = False
            result.reason = "Dust coverage is below 25 percent. Panel is treated as clean."
            return

        if 25 <= dust < 30 and result.image_source == ImageSource.dashboard_upload:
            result.cleaning_required = False
            result.robot_action = "Upload Another Image"
            result.robot_status = "Idle"
            result.fuzzy_logic_used = False
            result.reason = "Dust coverage is uncertain. Upload another image."
            return

        try:
            weather = await self.weather_service.get_current_weather()
            self.state.set_weather_status("Online")
            result.wind_speed_mps = weather.wind_speed_mps
            result.rainfall_mm = weather.rainfall_mm
        except WeatherServiceError as exc:
            self.state.set_weather_status("Error")
            result.cleaning_required = False
            result.robot_action = "Postpone Cleaning"
            result.robot_status = "Idle"
            result.reason = "Weather data unavailable"
            result.weather_error = str(exc)
            return

        if result.image_source == ImageSource.dashboard_upload:
            if weather.wind_speed_mps > 4:
                result.cleaning_required = False
                result.robot_action = "Postpone Cleaning"
                result.robot_status = "Idle"
                result.reason = "Safety First - high wind."
                return

            if 2 <= weather.wind_speed_mps <= 4:
                result.cleaning_required = False
                result.robot_action = "Postpone Cleaning"
                result.robot_status = "Idle"
                result.reason = "Wind may provide partial natural self-cleaning."
                return

            if weather.rainfall_mm > 5:
                result.cleaning_required = False
                result.robot_action = "Postpone Cleaning"
                result.robot_status = "Idle"
                result.reason = "Natural rainfall is sufficient."
                return

            if 0.3 <= weather.rainfall_mm <= 5:
                result.cleaning_required = False
                result.robot_action = "Postpone Cleaning"
                result.robot_status = "Idle"
                result.reason = "Partial natural cleaning is expected."
                return

        if 25 <= dust < 30:
            result.fuzzy_logic_used = False
            result.cleaning_required = True
        else:
            try:
                fuzzy = self.fuzzy_service.calculate(dust, weather.wind_speed_mps, weather.rainfall_mm)
                result.fuzzy_logic_used = True
                result.fuzzy_score = fuzzy.score
                result.fuzzy_decision = fuzzy.decision
                result.cleaning_required = (
                    True
                    if result.image_source == ImageSource.raspberry_pi_camera
                    else fuzzy.decision == "Clean"
                )
            except FuzzyLogicError as exc:
                await self._stop_robot_if_moving()
                result.cleaning_required = False
                result.robot_action = "Postpone Cleaning"
                result.robot_status = self.state.robot_status
                result.reason = "Fuzzy calculation failed. Robot movement blocked."
                result.error = str(exc)
                return

        if result.cleaning_required:
            if result.image_source == ImageSource.dashboard_upload:
                result.robot_action = "Cleaning Recommended - Test Mode"
                result.robot_status = "Idle"
                result.robot_executed = False
                result.reason = "Dust detected and weather conditions allow cleaning. Test Mode keeps motors disabled."
            else:
                result.robot_action = "Cleaning Approved"
                result.robot_status = "Idle"
                if result.fuzzy_logic_used and result.fuzzy_decision == "Postpone":
                    result.reason = "Dust detected and weather conditions allow cleaning. Prototype cleaning is enabled."
                else:
                    result.reason = "Dust detected and weather conditions allow cleaning."
        else:
            result.robot_action = "Postpone Cleaning"
            result.robot_status = "Idle"
            result.reason = "Fuzzy score is below the cleaning threshold."

    def _physical_execution_allowed(self, result: InspectionResult, image_source: ImageSource) -> bool:
        if image_source != ImageSource.raspberry_pi_camera:
            return False
        if result.prediction != "Dust":
            return False
        if not result.cleaning_required:
            return False
        if not self.settings.robot_enabled:
            result.robot_action = "Cleaning Approved - Robot Disabled"
            return False
        if result.maintenance_alert:
            return False
        if self.state.emergency_stop_active:
            result.robot_action = "Cleaning Blocked - Emergency Stop Active"
            return False
        if self.state.cleaning_active:
            result.robot_action = "Cleaning Blocked - Cycle Already Running"
            return False
        if not self.robot.is_ready():
            result.robot_action = "Cleaning Approved - Robot Not Ready"
            return False
        return True

    async def _start_cleaning_sequence(self) -> bool:
        if self._cleaning_lock.locked():
            return False

        if self.run_cleaning_in_background:
            asyncio.create_task(self._run_cleaning_sequence())
            return True

        await self._run_cleaning_sequence()
        return True

    async def _run_cleaning_sequence(self) -> None:
        async with self._cleaning_lock:
            self.state.set_cleaning_active(True)
            self.state.set_robot_status("Cleaning Forward")
            try:
                logger.info("Cleaning sequence: forward")
                await asyncio.to_thread(self.robot.clean_forward)
                self.state.set_robot_status("Cleaning Return")
                logger.info("Cleaning sequence: reverse cleaning")
                await asyncio.to_thread(self.robot.clean_reverse)
                logger.info("Cleaning sequence: ensure home")
                await asyncio.to_thread(self.robot.return_home)
                await asyncio.to_thread(self.robot.stop)
                self.state.set_robot_status("Home")
                logger.info("Cleaning sequence complete: home")
            except Exception as exc:
                logger.exception("Cleaning sequence failed")
                try:
                    await asyncio.to_thread(self.robot.stop)
                except Exception:
                    logger.exception("Robot stop failed after cleaning error")
                self.state.set_robot_status("Stopped")
                latest = self.state.get_latest_result()
                if latest is not None:
                    latest.success = False
                    latest.error = str(exc)
                    latest.robot_status = "Stopped"
                    latest.robot_action = "Cleaning Failed - Robot Stopped"
                    latest.reason = "Robot cleaning sequence failed. Motors stopped."
                    self.state.set_latest_result(latest)
            finally:
                self.state.set_cleaning_active(False)

    async def _stop_robot_if_moving(self) -> None:
        if self.state.cleaning_active or self.robot.is_ready():
            try:
                await asyncio.to_thread(self.robot.stop)
            except Exception:
                logger.exception("Robot stop command failed")

    def _validate_image(self, image_bytes: bytes) -> None:
        if not image_bytes:
            raise InvalidImageError("Image file is empty.")
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise InvalidImageError("Invalid image. Upload a JPG, PNG, or WEBP file.") from exc

    def _save_image(self, image_bytes: bytes, source: ImageSource) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        prefix = "upload" if source == ImageSource.dashboard_upload else "pi_capture"
        path = self.settings.captures_dir / f"{prefix}_{timestamp}.jpg"
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode not in ("RGB", "L"):
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    if "A" in image.getbands():
                        background.paste(image, mask=image.getchannel("A"))
                        image = background
                    else:
                        image = image.convert("RGB")
                elif image.mode == "L":
                    image = image.convert("RGB")
                image.save(path, format="JPEG", quality=90, optimize=True)
        except (UnidentifiedImageError, OSError) as exc:
            raise InvalidImageError("Invalid image. Upload a JPG, PNG, or WEBP file.") from exc
        return path

    def _image_url(self, path: Path) -> str:
        try:
            relative = path.resolve().relative_to(self.settings.images_dir.resolve())
        except ValueError:
            return ""
        return f"/images/{relative.as_posix()}"
