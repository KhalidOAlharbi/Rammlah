import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import Settings

logger = logging.getLogger(__name__)


class CameraServiceError(RuntimeError):
    pass


@dataclass
class CameraCapture:
    image_bytes: bytes
    path: Path


class CameraService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def capture_jpeg(self) -> CameraCapture:
        if not self.settings.camera_enabled:
            raise CameraServiceError("Camera is disabled. Set CAMERA_ENABLED=true on the Raspberry Pi.")

        try:
            from picamera2 import Picamera2
        except Exception as exc:
            raise CameraServiceError("Picamera2 is not available on this machine.") from exc

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.settings.captures_dir / f"pi_capture_{timestamp}.jpg"
        logger.info("Camera capture started: %s", path)
        try:
            camera = Picamera2()
            camera.configure(camera.create_still_configuration(main={"format": "RGB888"}))
            camera.start()
            camera.capture_file(str(path))
            camera.stop()
            image_bytes = path.read_bytes()
            logger.info("Camera capture saved: %s", path)
            return CameraCapture(image_bytes=image_bytes, path=path)
        except Exception as exc:
            logger.exception("Camera capture failed")
            raise CameraServiceError(f"Camera capture failed: {exc}") from exc
