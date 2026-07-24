import json
import logging
from pathlib import Path
from threading import RLock
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from .schemas import ExecutionMode, InspectionResult, PiCaptureCompletion, PiCaptureRequestStatus, StatusResponse

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
        self._pi_capture_request = PiCaptureRequestStatus()

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

    def request_pi_capture(self, countdown_seconds: int = 10) -> PiCaptureRequestStatus:
        with self._lock:
            if self._pi_capture_request.state in ("pending", "capturing"):
                return self._pi_capture_request

            now = datetime.now(timezone.utc)
            self._pi_capture_request = PiCaptureRequestStatus(
                request_id=uuid4().hex,
                state="pending",
                countdown_seconds=countdown_seconds,
                requested_at=now,
                capture_at=now + timedelta(seconds=countdown_seconds),
            )
            self.camera_status = "Capture Requested"
            return self._pi_capture_request

    def get_pi_capture_request(self) -> PiCaptureRequestStatus:
        with self._lock:
            return self._pi_capture_request

    def claim_pi_capture_request(self) -> Optional[PiCaptureRequestStatus]:
        with self._lock:
            if self._pi_capture_request.state != "pending":
                return None

            self._pi_capture_request.state = "capturing"
            self._pi_capture_request.started_at = datetime.now(timezone.utc)
            self.camera_status = "Capturing"
            return self._pi_capture_request

    def complete_pi_capture_request(
        self,
        request_id: str,
        completion: PiCaptureCompletion,
    ) -> PiCaptureRequestStatus:
        with self._lock:
            if self._pi_capture_request.request_id != request_id:
                return self._pi_capture_request

            self._pi_capture_request.state = "completed" if completion.success else "failed"
            self._pi_capture_request.completed_at = datetime.now(timezone.utc)
            self._pi_capture_request.image_url = completion.image_url
            self._pi_capture_request.prediction = completion.prediction
            self._pi_capture_request.error = completion.error
            self.camera_status = "Connected" if completion.success else "Error"
            return self._pi_capture_request

    def as_debug_json(self) -> str:
        with self._lock:
            return json.dumps(self.get_status().model_dump(mode="json"), indent=2)
