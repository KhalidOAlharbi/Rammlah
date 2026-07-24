import io
import logging
import os
import signal
import time

import httpx


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("rammlah-pi-agent")

STOP_REQUESTED = False


def _handle_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def capture_jpeg() -> bytes:
    try:
        from picamera2 import Picamera2
    except Exception as exc:
        raise RuntimeError("Picamera2 is not available. Install python3-picamera2 on Raspberry Pi OS.") from exc

    output = io.BytesIO()
    camera = Picamera2()
    try:
        camera.configure(camera.create_still_configuration(main={"format": "RGB888"}))
        camera.start()
        time.sleep(1.5)
        camera.capture_file(output, format="jpeg")
        return output.getvalue()
    finally:
        camera.stop()


def upload_capture(api_base_url: str, token: str, image_bytes: bytes) -> dict:
    url = f"{api_base_url.rstrip('/')}/api/predict/pi-upload"
    headers = {"X-Rammlah-Agent-Token": token}
    files = {"image": ("pi_capture.jpg", image_bytes, "image/jpeg")}
    with httpx.Client(timeout=90.0) as client:
        response = client.post(url, headers=headers, files=files)
        response.raise_for_status()
        return response.json()


def main() -> None:
    api_base_url = os.getenv("RAMMLAH_API_BASE_URL", "").strip()
    token = os.getenv("RAMMLAH_AGENT_TOKEN", "").strip()
    interval_seconds = int(os.getenv("RAMMLAH_SCAN_INTERVAL_SECONDS", "300"))

    if not api_base_url:
        raise RuntimeError("RAMMLAH_API_BASE_URL is required, for example https://rammlah-app-d57uq.ondigitalocean.app")
    if not token:
        raise RuntimeError("RAMMLAH_AGENT_TOKEN is required and must match RASPBERRY_PI_AGENT_TOKEN on DigitalOcean.")

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    logger.info("Rammlah Pi agent started: api=%s interval=%ss", api_base_url, interval_seconds)
    while not STOP_REQUESTED:
        try:
            image_bytes = capture_jpeg()
            result = upload_capture(api_base_url, token, image_bytes)
            logger.info(
                "Uploaded capture: success=%s prediction=%s action=%s",
                result.get("success"),
                result.get("prediction"),
                result.get("robot_action"),
            )
        except Exception:
            logger.exception("Capture upload failed")

        for _ in range(interval_seconds):
            if STOP_REQUESTED:
                break
            time.sleep(1)

    logger.info("Rammlah Pi agent stopped")


if __name__ == "__main__":
    main()
