import io
import logging
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("rammlah-pi-agent")
logging.getLogger("httpx").setLevel(logging.WARNING)

STOP_REQUESTED = False


def _handle_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def load_env_file(path: str = ".env.pi-agent") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


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


def poll_capture_request(api_base_url: str, token: str) -> dict | None:
    url = f"{api_base_url.rstrip('/')}/api/pi-agent/capture-request"
    headers = {"X-Rammlah-Agent-Token": token}
    with httpx.Client(timeout=15.0) as client:
        response = client.get(url, headers=headers)
        if response.status_code in (204, 404, 405):
            return None
        response.raise_for_status()
        return response.json()


def complete_capture_request(
    api_base_url: str,
    token: str,
    request_id: str,
    *,
    success: bool,
    result: dict | None = None,
    error: str | None = None,
) -> dict:
    url = f"{api_base_url.rstrip('/')}/api/pi-agent/capture-request/{request_id}/complete"
    headers = {"X-Rammlah-Agent-Token": token}
    payload = {
        "success": success,
        "image_url": result.get("image_url") if result else None,
        "prediction": result.get("prediction") if result else None,
        "error": error,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sleep_until_capture(capture_at: str | None) -> None:
    target = _parse_datetime(capture_at)
    if target is None:
        return

    while not STOP_REQUESTED:
        remaining = (target - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 1.0))


def handle_requested_capture(api_base_url: str, token: str, capture_request: dict) -> None:
    request_id = capture_request.get("request_id")
    if not request_id:
        logger.warning("Ignoring capture request without request_id")
        return

    logger.info("Dashboard capture request received: request_id=%s", request_id)
    _sleep_until_capture(capture_request.get("capture_at"))
    if STOP_REQUESTED:
        return

    try:
        image_bytes = capture_jpeg()
        result = upload_capture(api_base_url, token, image_bytes)
        complete_capture_request(api_base_url, token, request_id, success=True, result=result)
        logger.info(
            "Dashboard capture uploaded: request_id=%s success=%s prediction=%s action=%s",
            request_id,
            result.get("success"),
            result.get("prediction"),
            result.get("robot_action"),
        )
    except Exception as exc:
        logger.exception("Dashboard capture request failed")
        try:
            complete_capture_request(api_base_url, token, request_id, success=False, error=str(exc))
        except Exception:
            logger.exception("Could not report dashboard capture failure")


def upload_scheduled_capture(api_base_url: str, token: str) -> None:
    image_bytes = capture_jpeg()
    result = upload_capture(api_base_url, token, image_bytes)
    logger.info(
        "Uploaded capture: success=%s prediction=%s action=%s",
        result.get("success"),
        result.get("prediction"),
        result.get("robot_action"),
    )


def main() -> None:
    load_env_file()
    api_base_url = os.getenv("RAMMLAH_API_BASE_URL", "").strip()
    token = os.getenv("RAMMLAH_AGENT_TOKEN", "").strip()
    interval_seconds = int(os.getenv("RAMMLAH_SCAN_INTERVAL_SECONDS", "300"))
    poll_interval_seconds = int(os.getenv("RAMMLAH_COMMAND_POLL_INTERVAL_SECONDS", "5"))

    if not api_base_url:
        raise RuntimeError("RAMMLAH_API_BASE_URL is required, for example https://rammlah-app-d57uq.ondigitalocean.app")
    if not token:
        raise RuntimeError("RAMMLAH_AGENT_TOKEN is required and must match RASPBERRY_PI_AGENT_TOKEN on DigitalOcean.")

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    logger.info(
        "Rammlah Pi agent started: api=%s interval=%ss poll=%ss",
        api_base_url,
        interval_seconds,
        poll_interval_seconds,
    )
    next_scheduled_capture_at = time.monotonic()
    while not STOP_REQUESTED:
        try:
            capture_request = poll_capture_request(api_base_url, token)
            if capture_request:
                handle_requested_capture(api_base_url, token, capture_request)
                next_scheduled_capture_at = time.monotonic() + interval_seconds
            elif time.monotonic() >= next_scheduled_capture_at:
                upload_scheduled_capture(api_base_url, token)
                next_scheduled_capture_at = time.monotonic() + interval_seconds
        except Exception:
            logger.exception("Capture upload failed")

        for _ in range(poll_interval_seconds):
            if STOP_REQUESTED:
                break
            time.sleep(1)

    logger.info("Rammlah Pi agent stopped")


if __name__ == "__main__":
    main()
