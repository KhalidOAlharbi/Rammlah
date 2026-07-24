import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Bot,
  Camera,
  CheckCircle2,
  CloudRain,
  Gauge,
  Octagon,
  RefreshCw,
  ShieldAlert,
  UploadCloud,
  Wind,
  Wifi
} from "lucide-react";
import {
  emergencyStop,
  getLatest,
  getPiCaptureStatus,
  getStatus,
  imageUrl,
  requestPiCapture,
  scanCamera,
  uploadImage
} from "./api";
import type { InspectionResult, PiCaptureRequestStatus, Prediction, StatusResponse } from "./types";

type LoadState = "idle" | "uploading" | "scanning" | "stopping" | "refreshing";

const PI_CAPTURE_TIMEOUT_MS = 120_000;

function formatNumber(value: number | null | undefined, suffix = "", digits = 1) {
  if (value === null || value === undefined) {
    return "Not used";
  }
  return `${value.toFixed(digits)}${suffix}`;
}

function formatTime(value: string | null | undefined) {
  if (!value) {
    return "No scan";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium"
  }).format(new Date(value));
}

function predictionClass(prediction: Prediction | null | undefined, success = true) {
  if (!success) {
    return "danger";
  }
  if (prediction === "Clean") {
    return "success";
  }
  if (prediction === "Dust") {
    return "warning";
  }
  if (prediction === "Crack") {
    return "danger";
  }
  return "neutral";
}

function sourceLabel(source: InspectionResult["image_source"] | null | undefined) {
  if (source === "dashboard_upload") {
    return "Upload";
  }
  if (source === "raspberry_pi_camera") {
    return "Pi Camera";
  }
  return "No source";
}

function decisionStage(result: InspectionResult | null) {
  if (!result) {
    return "Awaiting Scan";
  }
  if (!result.success) {
    return "Error";
  }
  if (result.prediction === "Clean") {
    return "Classification";
  }
  if (result.prediction === "Crack") {
    return "Maintenance Stop";
  }
  if (result.fuzzy_logic_used) {
    return "Fuzzy Logic";
  }
  if (result.prediction === "Dust" && (result.wind_speed_mps !== null || result.rainfall_mm !== null)) {
    return "Weather Gate";
  }
  if (result.prediction === "Dust") {
    return "Dust Threshold";
  }
  return "Inspection";
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function secondsUntil(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  return Math.max(0, Math.ceil((new Date(value).getTime() - Date.now()) / 1000));
}

function MetricCard({
  label,
  value,
  tone = "neutral",
  icon
}: {
  label: string;
  value: string;
  tone?: "neutral" | "success" | "warning" | "danger";
  icon?: React.ReactNode;
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-icon" aria-hidden="true">
        {icon}
      </div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </article>
  );
}

function StatusPill({ label, value }: { label: string; value: string }) {
  const tone =
    value === "Error" || value === "Missing Key" || value === "Stopped"
      ? "danger"
      : value === "Online" || value === "Connected" || value === "Ready" || value === "Configured"
        ? "success"
        : value === "Cleaning"
          ? "warning"
          : "neutral";

  return (
    <span className={`status-pill ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </span>
  );
}

export default function App() {
  const [latest, setLatest] = useState<InspectionResult | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [captureCountdown, setCaptureCountdown] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const resultImageUrl = useMemo(() => imageUrl(latest?.image_url), [latest?.image_url]);
  const visibleImage = previewUrl || resultImageUrl;
  const tone = predictionClass(latest?.prediction, latest?.success ?? true);

  async function refreshAll(nextState: LoadState = "refreshing") {
    setLoadState(nextState);
    setError(null);
    try {
      const [latestResult, statusResult] = await Promise.all([getLatest(), getStatus()]);
      setLatest(latestResult);
      setStatus(statusResult);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to reach backend.");
    } finally {
      setLoadState("idle");
    }
  }

  useEffect(() => {
    refreshAll("idle");
    const latestTimer = window.setInterval(() => {
      getLatest().then(setLatest).catch(() => undefined);
    }, 2000);
    const statusTimer = window.setInterval(() => {
      getStatus().then(setStatus).catch(() => undefined);
    }, 5000);
    return () => {
      window.clearInterval(latestTimer);
      window.clearInterval(statusTimer);
    };
  }, []);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setPreviewUrl(URL.createObjectURL(file));
    setLoadState("uploading");
    setError(null);
    try {
      const result = await uploadImage(file);
      setLatest(result);
      setStatus(await getStatus());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed.");
    } finally {
      setLoadState("idle");
      event.target.value = "";
    }
  }

  async function handleScan() {
    setPreviewUrl(null);
    setLoadState("scanning");
    setError(null);
    setCaptureCountdown(null);
    try {
      const captureRequest = await requestPiCapture();
      await waitForPiCapture(captureRequest);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Camera scan failed.";
      if (message.includes("Not Found") || message.includes("404") || message.includes("405")) {
        try {
          await scanDirectCamera();
        } catch (fallbackError) {
          setError(fallbackError instanceof Error ? fallbackError.message : "Camera scan failed.");
        }
      } else {
        setError(message);
      }
    } finally {
      setCaptureCountdown(null);
      setLoadState("idle");
    }
  }

  async function scanDirectCamera() {
    const result = await scanCamera();
    setLatest(result);
    setStatus(await getStatus());
  }

  async function waitForPiCapture(initialRequest: PiCaptureRequestStatus) {
    let captureRequest = initialRequest;
    const startedAt = Date.now();

    while (Date.now() - startedAt < PI_CAPTURE_TIMEOUT_MS) {
      const nextCountdown = secondsUntil(captureRequest.capture_at);
      setCaptureCountdown(nextCountdown);

      if (captureRequest.state === "completed") {
        const [latestResult, statusResult] = await Promise.all([getLatest(), getStatus()]);
        setLatest(latestResult);
        setStatus(statusResult);
        return;
      }

      if (captureRequest.state === "failed") {
        throw new Error(captureRequest.error || "Raspberry Pi camera capture failed.");
      }

      await sleep(1000);
      captureRequest = await getPiCaptureStatus();
    }

    throw new Error("Timed out waiting for the Raspberry Pi camera capture.");
  }

  async function handleStop() {
    setLoadState("stopping");
    setError(null);
    try {
      await emergencyStop();
      setStatus(await getStatus());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Emergency stop failed.");
    } finally {
      setLoadState("idle");
    }
  }

  const busy = loadState !== "idle";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark">R</div>
          <div>
            <h1>Rammlah</h1>
            <p>Solar panel inspection and cleaning control</p>
          </div>
        </div>
        <div className="mode-strip">
          <span className={latest?.execution_mode === "Prototype" ? "mode prototype" : "mode test"}>
            {latest?.execution_mode === "Prototype" ? "Prototype Mode" : "Test Mode - Motors Disabled"}
          </span>
          <StatusPill label="Backend" value={status?.backend || "Offline"} />
        </div>
      </header>

      <section className="control-band" aria-label="Dashboard controls">
        <input
          ref={fileInputRef}
          className="hidden-input"
          type="file"
          accept="image/jpeg,image/jpg,image/png,image/webp"
          onChange={handleFileChange}
        />
        <button className="button primary" disabled={busy} onClick={() => fileInputRef.current?.click()}>
          <UploadCloud size={18} />
          Upload Test Image
        </button>
        <button className="button" disabled={busy} onClick={handleScan}>
          <Camera size={18} />
          {captureCountdown !== null && captureCountdown > 0
            ? `Capture in ${captureCountdown}s`
            : loadState === "scanning"
              ? "Capturing..."
              : "Capture from Raspberry Pi"}
        </button>
        <button className="button danger" disabled={loadState === "stopping"} onClick={handleStop}>
          <Octagon size={18} />
          Emergency Stop
        </button>
        <button className="icon-button" disabled={busy} onClick={() => refreshAll()} title="Refresh status">
          <RefreshCw size={19} className={loadState === "refreshing" ? "spin" : ""} />
        </button>
      </section>

      {error ? (
        <section className="alert danger">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </section>
      ) : null}

      <section className="dashboard-grid">
        <div className="panel-view">
          <div className={`condition-ribbon ${tone}`}>
            <span>Current Panel Condition</span>
            <strong>{latest?.prediction || "No Scan"}</strong>
          </div>
          <div className="image-frame">
            {visibleImage ? (
              <img src={visibleImage} alt="Latest inspected solar panel" />
            ) : (
              <div className="empty-image">
                <Camera size={36} />
                <span>No image</span>
              </div>
            )}
          </div>
          <div className="reason-row">
            {tone === "success" ? <CheckCircle2 size={19} /> : <ShieldAlert size={19} />}
            <span>{latest?.error || latest?.weather_error || latest?.reason || "Awaiting backend result."}</span>
          </div>
        </div>

        <div className="metrics-grid">
          <MetricCard
            label="AI Confidence"
            value={formatNumber(
              latest?.confidence === null || latest?.confidence === undefined ? null : latest.confidence * 100,
              "%"
            )}
            tone={tone}
            icon={<Gauge size={20} />}
          />
          <MetricCard
            label="Dust Coverage"
            value={formatNumber(latest?.dust_coverage_percent, "%")}
            tone={latest?.dust_coverage_percent && latest.dust_coverage_percent >= 30 ? "warning" : "neutral"}
            icon={<AlertTriangle size={20} />}
          />
          <MetricCard
            label="Wind Speed"
            value={formatNumber(latest?.wind_speed_mps, " m/s")}
            icon={<Wind size={20} />}
          />
          <MetricCard
            label="Rainfall"
            value={formatNumber(latest?.rainfall_mm, " mm")}
            icon={<CloudRain size={20} />}
          />
          <MetricCard
            label="Fuzzy Logic Used"
            value={latest?.fuzzy_logic_used ? "Yes" : "No"}
            tone={latest?.fuzzy_logic_used ? "success" : "neutral"}
            icon={<Gauge size={20} />}
          />
          <MetricCard
            label="Fuzzy Score"
            value={formatNumber(latest?.fuzzy_score, "")}
            tone={latest?.fuzzy_decision === "Clean" ? "success" : "neutral"}
            icon={<Gauge size={20} />}
          />
          <MetricCard
            label="Fuzzy Decision"
            value={latest?.fuzzy_decision || "Not used"}
            tone={latest?.fuzzy_decision === "Clean" ? "success" : "neutral"}
            icon={<CheckCircle2 size={20} />}
          />
          <MetricCard
            label="Cleaning Required"
            value={latest?.cleaning_required ? "Yes" : "No"}
            tone={latest?.cleaning_required ? "warning" : "success"}
            icon={<Bot size={20} />}
          />
          <MetricCard
            label="Robot Action"
            value={latest?.robot_action || "No Action"}
            tone={latest?.robot_action?.includes("Stop") ? "danger" : "neutral"}
            icon={<Bot size={20} />}
          />
          <MetricCard
            label="Robot Status"
            value={latest?.robot_status || status?.robot || "Unknown"}
            tone={status?.robot === "Stopped" ? "danger" : status?.robot === "Cleaning" ? "warning" : "neutral"}
            icon={<Bot size={20} />}
          />
          <MetricCard
            label="Maintenance Alert"
            value={latest?.maintenance_alert ? "Yes" : "No"}
            tone={latest?.maintenance_alert ? "danger" : "success"}
            icon={<ShieldAlert size={20} />}
          />
          <MetricCard
            label="Image Source"
            value={sourceLabel(latest?.image_source)}
            icon={<Camera size={20} />}
          />
          <MetricCard
            label="Decision Stage"
            value={decisionStage(latest)}
            tone={decisionStage(latest) === "Weather Gate" ? "warning" : "neutral"}
            icon={<ShieldAlert size={20} />}
          />
          <MetricCard
            label="Last Scan Time"
            value={formatTime(latest?.timestamp)}
            icon={<RefreshCw size={20} />}
          />
        </div>
      </section>

      <section className="status-band" aria-label="System status">
        <StatusPill label="Camera" value={status?.camera || "Unknown"} />
        <StatusPill label="OpenAI" value={status?.openai || "Unknown"} />
        <StatusPill label="Weather" value={status?.weather || "Not Checked"} />
        <StatusPill label="Robot" value={status?.robot || "Unknown"} />
        <StatusPill label="Robot Enabled" value={status?.robot_enabled ? "Yes" : "No"} />
        <StatusPill label="Mode" value={status?.current_mode || "Test"} />
        <StatusPill label="Network" value={status ? "Online" : "Offline"} />
        <span className="api-tag">
          <Wifi size={15} />
          API
        </span>
      </section>
    </main>
  );
}
