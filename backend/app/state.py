import json
import logging
from pathlib import Path
from threading import RLock
from typing import Optional

from .schemas import ExecutionMode, InspectionResult, StatusResponse

logger = logging.getLogger(__name__)


class StateService:
    def __init__(self, data_dir: Path, robot_enabled: bool, camera_enabled: bool, openai_configured: bool):
        self._lock = RLock()
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.latest_result_path = self.data_dir / "latest_result.json"
        self._latest_result: Optional[InspectionResult] = self._load_latest_result()
        self.camera_status = "Disabled" if not camera_enabled else "Connected"
        self.openai_status = "Configured" if openai_configured else "Missing Key"
        self.weather_status = "Not Checked"
        self.robot_status = "Disabled" if not robot_enabled else "Disconnected"
        self.robot_enabled = robot_enabled
        self.current_mode = ExecutionMode.test
        self.cleaning_active = False
        self.emergency_stop_active = False
        self.follow_up_scan_scheduled = False

    def _load_latest_result(self) -> Optional[InspectionResult]:
        if not self.latest_result_path.exists():
            return None
        try:
            return InspectionResult.model_validate_json(self.latest_result_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load latest result: %s", exc)
            return None

    def set_latest_result(self, result: InspectionResult) -> None:
        with self._lock:
            self._latest_result = result
            self.latest_result_path.write_text(
                result.model_dump_json(indent=2),
                encoding="utf-8",
            )

    def get_latest_result(self) -> Optional[InspectionResult]:
        with self._lock:
            return self._latest_result

    def set_camera_status(self, value: str) -> None:
        with self._lock:
            self.camera_status = value

    def set_openai_status(self, value: str) -> None:
        with self._lock:
            self.openai_status = value

    def set_weather_status(self, value: str) -> None:
        with self._lock:
            self.weather_status = value

    def set_robot_status(self, value: str) -> None:
        with self._lock:
            self.robot_status = value

    def set_current_mode(self, mode: ExecutionMode) -> None:
        with self._lock:
            self.current_mode = mode

    def set_cleaning_active(self, value: bool) -> None:
        with self._lock:
            self.cleaning_active = value
            if value:
                self.robot_status = "Cleaning"

    def set_emergency_stop(self, value: bool) -> None:
        with self._lock:
            self.emergency_stop_active = value
            if value:
                self.robot_status = "Stopped"

    def mark_follow_up_scan_scheduled(self) -> None:
        with self._lock:
            self.follow_up_scan_scheduled = True

    def get_status(self) -> StatusResponse:
        with self._lock:
            return StatusResponse(
                camera=self.camera_status,
                openai=self.openai_status,
                weather=self.weather_status,
                robot=self.robot_status,
                robot_enabled=self.robot_enabled,
                current_mode=self.current_mode,
            )

    def as_debug_json(self) -> str:
        with self._lock:
            return json.dumps(self.get_status().model_dump(mode="json"), indent=2)
