from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]

DEFAULT_SERIAL_COMMANDS = {
    "clean_forward": "CLEAN_FORWARD",
    "clean_reverse": "CLEAN_REVERSE",
    "return_home": "RETURN_HOME",
    "stop": "STOP",
    "emergency_stop": "EMERGENCY_STOP",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: Optional[SecretStr] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.6-luna", alias="OPENAI_MODEL")
    openai_timeout_seconds: float = Field(default=45.0, alias="OPENAI_TIMEOUT_SECONDS")
    max_image_dimension: int = Field(default=1280, alias="MAX_IMAGE_DIMENSION")
    raspberry_pi_agent_token: Optional[SecretStr] = Field(default=None, alias="RASPBERRY_PI_AGENT_TOKEN")

    latitude: Optional[float] = Field(default=None, alias="LATITUDE")
    longitude: Optional[float] = Field(default=None, alias="LONGITUDE")

    camera_enabled: bool = Field(default=True, alias="CAMERA_ENABLED")
    camera_capture_width: int = Field(default=1280, ge=320, alias="CAMERA_CAPTURE_WIDTH")
    camera_capture_height: int = Field(default=720, ge=240, alias="CAMERA_CAPTURE_HEIGHT")
    robot_enabled: bool = Field(default=False, alias="ROBOT_ENABLED")
    robot_controller: str = Field(default="serial", alias="ROBOT_CONTROLLER")

    robot_serial_port: str = Field(default="/dev/ttyUSB0", alias="ROBOT_SERIAL_PORT")
    robot_baud_rate: int = Field(default=9600, alias="ROBOT_BAUD_RATE")
    forward_timeout_seconds: int = Field(default=60, alias="FORWARD_TIMEOUT_SECONDS")
    return_timeout_seconds: int = Field(default=60, alias="RETURN_TIMEOUT_SECONDS")
    robot_drive_speed: float = Field(default=0.20, ge=0.0, le=1.0, alias="ROBOT_DRIVE_SPEED")
    robot_brush_speed: float = Field(default=1.0, ge=0.0, le=1.0, alias="ROBOT_BRUSH_SPEED")
    robot_pwm_frequency_hz: int = Field(default=1000, ge=1, alias="ROBOT_PWM_FREQUENCY_HZ")
    robot_brush_lead_seconds: float = Field(default=2.0, ge=0.0, le=10.0, alias="ROBOT_BRUSH_LEAD_SECONDS")

    allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:8080",
        alias="ALLOWED_ORIGINS",
    )
    allowed_origin_regex: Optional[str] = Field(
        default=(
            r"^https?://("
            r"localhost|127\.0\.0\.1|raspberrypi\.local|"
            r"172\.20\.10\.\d+|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+"
            r")(:\d+)?$"
        ),
        alias="ALLOWED_ORIGIN_REGEX",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    data_dir: Path = BACKEND_DIR / "data"
    images_dir: Path = BACKEND_DIR / "images"
    captures_dir: Path = BACKEND_DIR / "images" / "captures"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def openai_api_key_value(self) -> str:
        if self.openai_api_key is None:
            return ""
        return self.openai_api_key.get_secret_value()

    @property
    def raspberry_pi_agent_token_value(self) -> str:
        if self.raspberry_pi_agent_token is None:
            return ""
        return self.raspberry_pi_agent_token.get_secret_value()

    @property
    def robot_commands(self) -> dict[str, str]:
        return DEFAULT_SERIAL_COMMANDS.copy()

    def validate_for_startup(self) -> None:
        if not self.openai_api_key_value:
            raise RuntimeError(
                "OPENAI_API_KEY is missing. Create backend/.env from backend/.env.example "
                "and set OPENAI_API_KEY before starting the API server."
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.captures_dir.mkdir(parents=True, exist_ok=True)
    return settings
