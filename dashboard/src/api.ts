import type { InspectionResult, RobotCommandResponse, RobotManualAction, StatusResponse } from "./types";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const temporaryPiTunnelUrl = "https://auto-promotes-twice-lightning.trycloudflare.com";

function resolveApiBaseUrl() {
  if (typeof window === "undefined") {
    return "http://localhost:8000";
  }

  const isLocalDevHost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  if (!isLocalDevHost && window.location.hostname.endsWith("ondigitalocean.app")) {
    return window.location.origin;
  }

  if (
    configuredApiBaseUrl &&
    configuredApiBaseUrl !== "auto" &&
    !configuredApiBaseUrl.includes("<RASPBERRY_PI_IP>")
  ) {
    return configuredApiBaseUrl.replace(/\/$/, "");
  }

  if (!isLocalDevHost) {
    return window.location.origin;
  }

  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export const API_BASE_URL = resolveApiBaseUrl();
let activeApiBaseUrl = API_BASE_URL;

function apiBaseUrlCandidates() {
  if (API_BASE_URL === temporaryPiTunnelUrl) {
    return [API_BASE_URL];
  }
  return [API_BASE_URL, temporaryPiTunnelUrl];
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  let lastError: unknown = null;
  for (const baseUrl of apiBaseUrlCandidates()) {
    try {
      const response = await fetch(`${baseUrl}${path}`, init);
      const parsed = await parseResponse<T>(response);
      activeApiBaseUrl = baseUrl;
      return parsed;
    } catch (caught) {
      lastError = caught;
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Unable to reach backend.");
}

export async function uploadImage(file: File): Promise<InspectionResult> {
  const form = new FormData();
  form.append("image", file);
  return fetchApi<InspectionResult>("/api/predict/upload", {
    method: "POST",
    body: form
  });
}

export async function scanCamera(): Promise<InspectionResult> {
  return fetchApi<InspectionResult>("/api/scan", { method: "POST" });
}

export async function getLatest(): Promise<InspectionResult | null> {
  return fetchApi<InspectionResult | null>("/api/latest");
}

export async function getStatus(): Promise<StatusResponse> {
  return fetchApi<StatusResponse>("/api/status");
}

export async function emergencyStop(): Promise<void> {
  await fetchApi<void>("/api/robot/stop", { method: "POST" });
}

export async function sendRobotCommand(
  action: RobotManualAction,
  options: { speed?: number; duration_seconds?: number | null } = {}
): Promise<RobotCommandResponse> {
  return fetchApi<RobotCommandResponse>("/api/robot/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, ...options })
  });
}

export function imageUrl(path: string | null | undefined): string | null {
  if (!path) {
    return null;
  }
  if (path.startsWith("http")) {
    return path;
  }
  return `${activeApiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}
