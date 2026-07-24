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
    robot_enabled: bool = Field(default=False, alias="ROBOT_ENABLED")

    robot_serial_port: str = Field(default="/dev/ttyUSB0", alias="ROBOT_SERIAL_PORT")
    robot_baud_rate: int = Field(default=9600, alias="ROBOT_BAUD_RATE")
    forward_timeout_seconds: int = Field(default=60, alias="FORWARD_TIMEOUT_SECONDS")
    return_timeout_seconds: int = Field(default=60, alias="RETURN_TIMEOUT_SECONDS")

    scan_interval_seconds: int = Field(default=30, alias="SCAN_INTERVAL_SECONDS")
    follow_up_scan_delay_seconds: float = Field(default=2.0, alias="FOLLOW_UP_SCAN_DELAY_SECONDS")

    allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:8080",
        alias="ALLOWED_ORIGINS",
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
