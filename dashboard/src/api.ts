import type { InspectionResult, StatusResponse } from "./types";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL;

export const API_BASE_URL = configuredApiBaseUrl ? configuredApiBaseUrl.replace(/\/$/, "") : "";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function uploadImage(file: File): Promise<InspectionResult> {
  const form = new FormData();
  form.append("image", file);
  const response = await fetch(`${API_BASE_URL}/api/predict/upload`, {
    method: "POST",
    body: form
  });
  return parseResponse<InspectionResult>(response);
}

export async function scanCamera(): Promise<InspectionResult> {
  const response = await fetch(`${API_BASE_URL}/api/scan`, { method: "POST" });
  return parseResponse<InspectionResult>(response);
}

export async function getLatest(): Promise<InspectionResult | null> {
  const response = await fetch(`${API_BASE_URL}/api/latest`);
  return parseResponse<InspectionResult | null>(response);
}

export async function getStatus(): Promise<StatusResponse> {
  const response = await fetch(`${API_BASE_URL}/api/status`);
  return parseResponse<StatusResponse>(response);
}

export async function emergencyStop(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/robot/stop`, { method: "POST" });
  await parseResponse(response);
}

export function imageUrl(path: string | null | undefined): string | null {
  if (!path) {
    return null;
  }
  if (path.startsWith("http")) {
    return path;
  }
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}
