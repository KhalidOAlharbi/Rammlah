export type Prediction = "Clean" | "Dust" | "Crack";
export type ImageSource = "dashboard_upload" | "raspberry_pi_camera";
export type ExecutionMode = "Test" | "Prototype";
export type RobotManualAction =
  | "forward"
  | "reverse"
  | "left"
  | "right"
  | "brush_on"
  | "brush_off"
  | "return_home"
  | "stop";

export interface InspectionResult {
  success: boolean;
  image_source: ImageSource;
  execution_mode: ExecutionMode;
  prediction: Prediction | null;
  confidence: number | null;
  dust_coverage_percent: number | null;
  wind_speed_mps: number | null;
  rainfall_mm: number | null;
  fuzzy_logic_used: boolean;
  fuzzy_score: number | null;
  fuzzy_decision: "Clean" | "Postpone" | null;
  cleaning_required: boolean;
  robot_action: string;
  robot_status: string;
  robot_executed: boolean;
  maintenance_alert: boolean;
  reason: string;
  weather_error: string | null;
  error: string | null;
  image_url: string | null;
  timestamp: string;
}

export interface StatusResponse {
  backend: "Online";
  camera: "Connected" | "Disabled" | "Error" | string;
  openai: "Configured" | "Missing Key" | "Error" | string;
  weather: "Online" | "Error" | "Not Checked" | string;
  robot: "Ready" | "Disabled" | "Disconnected" | "Cleaning" | "Stopped" | string;
  robot_enabled: boolean;
  current_mode: ExecutionMode;
  timestamp: string;
}

export interface RobotCommandResponse {
  success: boolean;
  action: RobotManualAction;
  robot_status: string;
  message: string;
  timestamp: string;
}
