from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImageSource(str, Enum):
    dashboard_upload = "dashboard_upload"
    raspberry_pi_camera = "raspberry_pi_camera"


class ExecutionMode(str, Enum):
    test = "Test"
    prototype = "Prototype"


class RobotManualAction(str, Enum):
    forward = "forward"
    reverse = "reverse"
    left = "left"
    right = "right"
    brush_on = "brush_on"
    brush_off = "brush_off"
    return_home = "return_home"
    stop = "stop"


Prediction = Literal["Clean", "Dust", "Crack"]


class VisionAnalysis(BaseModel):
    prediction: Prediction
    confidence: float = Field(ge=0.0, le=1.0)
    dust_coverage_percent: float = Field(ge=0.0, le=100.0)
    reason: str = Field(min_length=1, max_length=180)

    @field_validator("reason")
    @classmethod
    def reason_must_be_display_safe(cls, value: str) -> str:
        return value.replace("\n", " ").strip()


class WeatherData(BaseModel):
    wind_speed_mps: float = Field(ge=0.0)
    rainfall_mm: float = Field(ge=0.0)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FuzzyInputs(BaseModel):
    dust_coverage_percent: float
    wind_speed_mps: float
    rainfall_mm: float


class FuzzyResult(BaseModel):
    used: bool = True
    score: float = Field(ge=0.0, le=100.0)
    decision: Literal["Clean", "Postpone"]
    inputs: FuzzyInputs


class InspectionResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    success: bool
    image_source: ImageSource
    execution_mode: ExecutionMode
    prediction: Optional[Prediction] = None
    confidence: Optional[float] = None
    dust_coverage_percent: Optional[float] = None
    wind_speed_mps: Optional[float] = None
    rainfall_mm: Optional[float] = None
    fuzzy_logic_used: bool = False
    fuzzy_score: Optional[float] = None
    fuzzy_decision: Optional[Literal["Clean", "Postpone"]] = None
    cleaning_required: bool = False
    robot_action: str = "No Action"
    robot_status: str = "Idle"
    robot_executed: bool = False
    maintenance_alert: bool = False
    reason: str = ""
    weather_error: Optional[str] = None
    error: Optional[str] = None
    image_url: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusResponse(BaseModel):
    backend: str = "Online"
    camera: str
    openai: str
    weather: str
    robot: str
    robot_enabled: bool
    current_mode: ExecutionMode
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RobotStopResponse(BaseModel):
    success: bool
    robot_status: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RobotCommandRequest(BaseModel):
    action: RobotManualAction
    speed: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    duration_seconds: Optional[float] = Field(default=1.0, ge=0.0, le=10.0)


class RobotCommandResponse(BaseModel):
    success: bool
    action: RobotManualAction
    robot_status: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PiCaptureRequest(BaseModel):
    request_id: str
    capture_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PiCaptureCompleteRequest(BaseModel):
    success: bool
    image_url: Optional[str] = None
    prediction: Optional[Prediction] = None
    error: Optional[str] = None
