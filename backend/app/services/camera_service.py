import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

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
        self._lock = RLock()
        self._camera: Any = None

    def capture_jpeg(self) -> CameraCapture:
        if not self.settings.camera_enabled:
            raise CameraServiceError("Camera is disabled. Set CAMERA_ENABLED=true on the Raspberry Pi.")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.settings.captures_dir / f"pi_capture_{timestamp}.jpg"
        logger.info("Camera capture started: %s", path)
        with self._lock:
            try:
                camera = self._get_camera()
                camera.capture_file(str(path))
                image_bytes = path.read_bytes()
                logger.info("Camera capture saved: %s", path)
                return CameraCapture(image_bytes=image_bytes, path=path)
            except Exception as exc:
                logger.exception("Camera capture failed")
                self.close()
                raise CameraServiceError(f"Camera capture failed: {exc}") from exc

    def close(self) -> None:
        with self._lock:
            if self._camera is None:
                return
            try:
                self._camera.stop()
            except Exception:
                logger.debug("Camera stop during close failed", exc_info=True)
            try:
                self._camera.close()
            except Exception:
                logger.exception("Camera close failed")
            finally:
                self._camera = None

    def _get_camera(self):
        if self._camera is not None:
            return self._camera

        try:
            from picamera2 import Picamera2
        except Exception as exc:
            raise CameraServiceError("Picamera2 is not available on this machine.") from exc

        camera = Picamera2()
        camera.configure(
            camera.create_still_configuration(
                main={
                    "format": "RGB888",
                    "size": (
                        self.settings.camera_capture_width,
                        self.settings.camera_capture_height,
                    ),
                }
            )
        )
        camera.start()
        self._camera = camera
        logger.info(
            "Camera session started at %sx%s",
            self.settings.camera_capture_width,
            self.settings.camera_capture_height,
        )
        return camera
