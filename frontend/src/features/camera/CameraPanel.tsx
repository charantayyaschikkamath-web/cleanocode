import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import type { OccupancyEvidence, VisionHealth } from "./types";
import "./camera.css";

type CameraPanelProps = {
  roomId: string;
  apiBaseUrl?: string;
  initialCoverageConfirmed?: boolean;
};

type CameraState = "idle" | "starting" | "live" | "stopped" | "error";

function endpoint(base: string, path: string): string {
  return `${base.replace(/\/$/, "")}${path}`;
}

function statusLabel(status?: string): string {
  switch (status) {
    case "AVAILABLE": return "Evidence available";
    case "UNAVAILABLE": return "Inference unavailable";
    default: return "Unknown — do not infer empty";
  }
}

function formatTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString();
}

export default function CameraPanel({
  roomId,
  apiBaseUrl = "",
  initialCoverageConfirmed = false,
}: CameraPanelProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const uploadedVideoRef = useRef<HTMLVideoElement | null>(null);
  const uploadedCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const cancelUploadRef = useRef(false);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const sendingRef = useRef(false);
  const mountedRef = useRef(true);
  const latestResponseRef = useRef<number | null>(null);
  const coverageConfirmedRef = useRef(initialCoverageConfirmed);
  const maxFrameBytesRef = useRef(2_000_000);
  const maxFrameAgeMsRef = useRef(4_000);
  const latestWasRealRef = useRef(false);
  const detectorAvailableRef = useRef(false);

  const [cameraState, setCameraState] = useState<CameraState>("idle");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [coverageConfirmed, setCoverageConfirmed] = useState(initialCoverageConfirmed);
  const [health, setHealth] = useState<VisionHealth | null>(null);
  const [evidence, setEvidence] = useState<OccupancyEvidence | null>(null);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [simulatedCount, setSimulatedCount] = useState("0");
  const [simulationBusy, setSimulationBusy] = useState(false);
  const [uploadedVideoUrl, setUploadedVideoUrl] = useState<string | null>(null);
  const [uploadedVideoName, setUploadedVideoName] = useState("");
  const [sampleInterval, setSampleInterval] = useState("2");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ processed: number; total: number } | null>(null);

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const list = (await navigator.mediaDevices.enumerateDevices()).filter((item) => item.kind === "videoinput");
      if (!mountedRef.current) return;
      setDevices(list);
      setSelectedDeviceId((current) => current && list.some((device) => device.deviceId === current)
        ? current
        : (list[0]?.deviceId ?? ""));
    } catch {
      if (mountedRef.current) setDevices([]);
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const response = await fetch(endpoint(apiBaseUrl, "/api/vision/health"), { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`Health check returned ${response.status}`);
      const value = (await response.json()) as VisionHealth;
      maxFrameBytesRef.current = value.max_frame_bytes;
      maxFrameAgeMsRef.current = value.max_frame_age_ms;
      detectorAvailableRef.current = value.detector_available;
      if (mountedRef.current) setHealth(value);
    } catch (cause) {
      if (mountedRef.current) {
        setHealth(null);
        setError(cause instanceof Error ? cause.message : "Vision backend could not be reached.");
      }
    }
  }, [apiBaseUrl]);

  const stopCamera = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    sendingRef.current = false;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraState("stopped");
    setStale(false);
  }, []);

  const sendOneFrame = useCallback(async () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!detectorAvailableRef.current) return;
    if (!video || !canvas || sendingRef.current || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
    const track = streamRef.current?.getVideoTracks()[0];
    if (!track || track.readyState !== "live") {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      timerRef.current = null;
      if (mountedRef.current) {
        setEvidence(null);
        setStale(true);
        setCameraState("error");
        setError("The camera stream ended. Occupancy is unknown; reconnect the camera and press Start camera.");
      }
      return;
    }
    if (track.muted) {
      if (mountedRef.current) {
        setEvidence(null);
        setStale(true);
        setError("The camera stopped delivering fresh frames. Occupancy is unknown until frames resume.");
      }
      return;
    }
    if (!video.videoWidth || !video.videoHeight) return;
    const width = Math.min(video.videoWidth, 640);
    const height = Math.max(1, Math.round((video.videoHeight / video.videoWidth) * width));
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) {
      setError("This browser could not prepare a temporary camera frame.");
      return;
    }
    context.drawImage(video, 0, 0, width, height);
    sendingRef.current = true;
    try {
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.62));
      if (!blob) throw new Error("Could not encode a temporary camera frame.");
      if (blob.size > maxFrameBytesRef.current) throw new Error("Frame exceeds the backend size limit.");
      const query = new URLSearchParams({
        room_id: roomId,
        coverage_confirmed: String(coverageConfirmedRef.current),
        camera_label: "Browser/USB camera",
      });
      const response = await fetch(endpoint(apiBaseUrl, `/api/vision/frame?${query.toString()}`), {
        method: "POST",
        headers: { "Content-Type": "image/jpeg", Accept: "application/json" },
        body: blob,
        signal: AbortSignal.timeout(6000),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null) as { detail?: { message?: string } } | null;
        throw new Error(detail?.detail?.message || `Vision analysis returned ${response.status}.`);
      }
      const result = (await response.json()) as OccupancyEvidence;
      if (mountedRef.current) {
        setEvidence(result);
        setError("");
        latestResponseRef.current = Date.now();
        latestWasRealRef.current = result.provenance === "REAL";
        setStale(false);
      }
    } catch (cause) {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      timerRef.current = null;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
      if (mountedRef.current) {
        setEvidence(null);
        setStale(true);
        setCameraState("error");
        setError(cause instanceof Error ? cause.message : "The camera frame could not be analyzed.");
      }
    } finally {
      // The Blob and canvas pixels are not saved or reused after this request.
      canvas.width = 1;
      canvas.height = 1;
      sendingRef.current = false;
    }
  }, [apiBaseUrl, roomId]);

  const startCamera = useCallback(async () => {
    setError("");
    setEvidence(null);
    setCameraState("starting");
    latestResponseRef.current = null;
    latestWasRealRef.current = false;
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("This browser does not support camera access. Use HTTPS or localhost in a supported browser.");
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      const videoConstraint: MediaTrackConstraints = {
        width: { ideal: 640 },
        height: { ideal: 480 },
        ...(selectedDeviceId ? { deviceId: { exact: selectedDeviceId } } : {}),
      };
      const stream = await navigator.mediaDevices.getUserMedia({ video: videoConstraint, audio: false });
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const activeVideoTrack = stream.getVideoTracks()[0];
      activeVideoTrack?.addEventListener("ended", () => {
        if (!mountedRef.current) return;
        if (timerRef.current !== null) window.clearInterval(timerRef.current);
        timerRef.current = null;
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        if (videoRef.current) videoRef.current.srcObject = null;
        latestResponseRef.current = null;
        latestWasRealRef.current = false;
        setEvidence(null);
        setStale(true);
        setCameraState("error");
        setError("The camera disconnected. Occupancy is unknown; reconnect the camera and press Start camera.");
      }, { once: true });
      if (!videoRef.current) throw new Error("Camera preview is not ready.");
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      await refreshDevices();
      if (!activeVideoTrack || activeVideoTrack.readyState !== "live") {
        throw new Error("The camera stopped before the live stream became ready. Check the device and try again.");
      }
      setCameraState("live");
      latestResponseRef.current = null;
      // One in-flight request maximum. No frames are buffered for retry.
      timerRef.current = window.setInterval(() => { void sendOneFrame(); }, 1000);
      void sendOneFrame();
    } catch (cause) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setCameraState("error");
      setError(cause instanceof Error ? cause.message : "Camera permission/device error.");
      setEvidence(null);
    }
  }, [refreshDevices, selectedDeviceId, sendOneFrame]);

  const submitSimulation = useCallback(async () => {
    setSimulationBusy(true);
    setError("");
    try {
      const response = await fetch(endpoint(apiBaseUrl, "/api/vision/simulated"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          room_id: roomId,
          person_count: Number(simulatedCount),
          coverage_confirmed: coverageConfirmed,
          camera_label: "Manual demo input",
        }),
        signal: AbortSignal.timeout(6000),
      });
      if (!response.ok) throw new Error(`Simulation request returned ${response.status}.`);
      const simulated = (await response.json()) as OccupancyEvidence;
      setEvidence(simulated);
      setStale(false);
      latestResponseRef.current = null;
      latestWasRealRef.current = false;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not submit simulated occupancy.");
    } finally {
      setSimulationBusy(false);
    }
  }, [apiBaseUrl, coverageConfirmed, roomId, simulatedCount]);

  useEffect(() => {
    mountedRef.current = true;
    void refreshHealth();
    void refreshDevices();
    const onDeviceChange = () => { void refreshDevices(); };
    navigator.mediaDevices?.addEventListener?.("devicechange", onDeviceChange);
    const freshnessTimer = window.setInterval(() => {
      const last = latestResponseRef.current;
      setStale(latestWasRealRef.current && last !== null && Date.now() - last > maxFrameAgeMsRef.current);
    }, 500);
    return () => {
      mountedRef.current = false;
      window.clearInterval(freshnessTimer);
      navigator.mediaDevices?.removeEventListener?.("devicechange", onDeviceChange);
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      if (canvasRef.current) {
        canvasRef.current.width = 1;
        canvasRef.current.height = 1;
      }
    };
  }, [refreshDevices, refreshHealth]);

  useEffect(() => {
    return () => {
      if (uploadedVideoUrl) URL.revokeObjectURL(uploadedVideoUrl);
      cancelUploadRef.current = true;
      if (uploadedCanvasRef.current) {
        uploadedCanvasRef.current.width = 1;
        uploadedCanvasRef.current.height = 1;
      }
    };
  }, [uploadedVideoUrl]);

  const onVideoSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("video/")) {
      setError("Choose a supported video file (MP4 or WebM is recommended).");
      event.target.value = "";
      return;
    }
    if (file.size > 250 * 1024 * 1024) {
      setError("This video is larger than the 250 MB local-processing limit. Choose a smaller file.");
      event.target.value = "";
      return;
    }
    const url = URL.createObjectURL(file);
    setUploadedVideoUrl(url);
    setUploadedVideoName(file.name);
    setUploadProgress(null);
    setEvidence(null);
    setStale(false);
    setError("");
    latestResponseRef.current = null;
    latestWasRealRef.current = false;
  };

  const stopVideoAnalysis = () => {
    cancelUploadRef.current = true;
  };

  const analyzeUploadedVideo = useCallback(async () => {
    const video = uploadedVideoRef.current;
    const canvas = uploadedCanvasRef.current;
    if (!video || !canvas || !uploadedVideoUrl) {
      setError("Choose a video before starting analysis.");
      return;
    }
    if (!detectorAvailableRef.current) {
      setError("Local person detection is not configured. Set VISION_MODEL_PATH to a reviewed local ONNX model and restart the backend. The video remains on this device.");
      return;
    }
    if (!Number.isFinite(video.duration) || video.duration <= 0 || video.readyState < HTMLMediaElement.HAVE_METADATA) {
      setError("The video is not ready or its duration could not be read. Try another MP4/WebM file.");
      return;
    }
    if (video.duration > 30 * 60) {
      setError("For safety and predictable demo timing, choose a recording no longer than 30 minutes.");
      return;
    }

    // Uploaded recordings are retrospective samples. They are never eligible to
    // start a real-time empty-room timer, even when the operator attested to view coverage.
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraState("stopped");
    cancelUploadRef.current = false;
    setUploadBusy(true);
    setUploadProgress({ processed: 0, total: 0 });
    setError("");
    setEvidence(null);
    setStale(false);

    const desiredStep = Math.max(1, Number(sampleInterval) || 2);
    const step = Math.max(desiredStep, video.duration / 300);
    const total = Math.max(1, Math.min(300, Math.ceil(video.duration / step)));
    setUploadProgress({ processed: 0, total });

    const seekTo = async (timeSeconds: number) => {
      if (Math.abs(video.currentTime - timeSeconds) < 0.015 && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) return;
      await new Promise<void>((resolve, reject) => {
        let timeout = 0;
        const cleanup = () => {
          video.removeEventListener("seeked", onSeeked);
          video.removeEventListener("error", onError);
          window.clearTimeout(timeout);
        };
        const onSeeked = () => { cleanup(); resolve(); };
        const onError = () => { cleanup(); reject(new Error("The browser could not decode a video frame.")); };
        video.addEventListener("seeked", onSeeked, { once: true });
        video.addEventListener("error", onError, { once: true });
        timeout = window.setTimeout(() => { cleanup(); reject(new Error("Timed out seeking within the uploaded video.")); }, 5000);
        video.currentTime = Math.min(Math.max(0, timeSeconds), Math.max(0, video.duration - 0.01));
      });
    };

    try {
      let processed = 0;
      for (let index = 0; index < total; index += 1) {
        if (cancelUploadRef.current) break;
        const at = Math.min(index * step, Math.max(0, video.duration - 0.01));
        await seekTo(at);
        if (!video.videoWidth || !video.videoHeight) throw new Error("The selected video has no decodable image at the sampled position.");
        const width = Math.min(video.videoWidth, 640);
        const height = Math.max(1, Math.round((video.videoHeight / video.videoWidth) * width));
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext("2d", { alpha: false });
        if (!context) throw new Error("This browser could not prepare an in-memory video frame.");
        context.drawImage(video, 0, 0, width, height);
        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.62));
        canvas.width = 1;
        canvas.height = 1;
        if (!blob) throw new Error("Could not encode a video frame for analysis.");
        if (blob.size > maxFrameBytesRef.current) throw new Error("A sampled frame exceeds the backend frame-size limit. Try a lower-resolution video.");
        const query = new URLSearchParams({
          room_id: roomId,
          coverage_confirmed: "false",
          camera_label: "Uploaded video (retrospective sample)",
        });
        const response = await fetch(endpoint(apiBaseUrl, `/api/vision/frame?${query.toString()}`), {
          method: "POST",
          headers: { "Content-Type": "image/jpeg", Accept: "application/json" },
          body: blob,
          signal: AbortSignal.timeout(10000),
        });
        if (!response.ok) {
          const detail = await response.json().catch(() => null) as { detail?: { message?: string } } | null;
          throw new Error(detail?.detail?.message || `Video frame analysis returned ${response.status}.`);
        }
        const result = (await response.json()) as OccupancyEvidence;
        processed += 1;
        if (mountedRef.current) {
          setEvidence(result);
          setError("");
          setStale(false);
          latestResponseRef.current = Date.now();
          latestWasRealRef.current = false;
          setUploadProgress({ processed, total });
        }
      }
      if (mountedRef.current) {
        setError(cancelUploadRef.current ? "Video analysis stopped by the operator. The displayed result is the last processed sample." : "");
      }
    } catch (cause) {
      if (mountedRef.current) {
        setEvidence(null);
        setStale(true);
        setError(cause instanceof Error ? cause.message : "The uploaded video could not be analyzed.");
      }
    } finally {
      canvas.width = 1;
      canvas.height = 1;
      if (mountedRef.current) setUploadBusy(false);
    }
  }, [apiBaseUrl, roomId, sampleInterval, uploadedVideoUrl]);

  const onDeviceSelected = (event: ChangeEvent<HTMLSelectElement>) => {
    const nextDeviceId = event.target.value;
    setSelectedDeviceId(nextDeviceId);
    if (cameraState === "live") {
      stopCamera();
      // User has already explicitly opted in, but restart is still initiated by a clear action below.
    }
  };

  const evidenceIsStale = stale && evidence?.provenance === "REAL";
  const displayedStatus = evidenceIsStale ? "UNKNOWN" : evidence?.status;
  const evidenceEligible = Boolean(evidence?.eligible_for_empty_timer && !evidenceIsStale && coverageConfirmed);
  const headline = evidence
    ? evidence.provenance === "SIMULATED" ? "Simulated occupancy input" : statusLabel(displayedStatus)
    : cameraState === "live" ? "Waiting for valid camera evidence" : "Camera not running";
  const badgeStatus = evidence?.provenance === "SIMULATED" ? "simulated" : displayedStatus?.toLowerCase() ?? (cameraState === "live" ? "unknown" : "neutral");
  const signalText = evidenceIsStale ? "Unknown — camera frame stale" : !evidence ? "Unknown" : evidence.signal === "PERSON_DETECTED"
    ? "Person detected in current/recent valid frames"
    : evidence.signal === "NO_PERSON_DETECTED"
      ? "No person detected — not proof the room is empty"
      : "Unknown / unavailable";

  return (
    <section className="ct-camera" aria-labelledby="ct-camera-title">
      <header className="ct-camera__header">
        <div>
          <p className="ct-camera__eyebrow">ROOM EVIDENCE · {roomId}</p>
          <h2 id="ct-camera-title">Camera & occupancy evidence</h2>
          <p className="ct-camera__subhead">Person presence only. No face recognition, identity matching or tracking.</p>
        </div>
        <span className={`ct-camera__badge ct-camera__badge--${badgeStatus}`}>
          {headline}
        </span>
      </header>

      <div className="ct-camera__privacy" role="note">
        <strong>Privacy boundary</strong>
        <span>Camera starts only after you click Start. A downsized frame is sent to the configured CampusTwin backend for transient analysis. This module never saves frames, puts them in logs/reports, or sends them to the copilot. Use a trusted local backend.</span>
      </div>

      <div className="ct-camera__grid">
        <div className="ct-camera__preview-wrap">
          <div className="ct-camera__preview">
            <video ref={videoRef} autoPlay muted playsInline aria-label="Live camera preview" />
            {cameraState !== "live" && (
              <div className="ct-camera__preview-empty">
                <span aria-hidden="true">◉</span>
                <strong>{cameraState === "error" ? "Camera unavailable" : "Camera preview is off"}</strong>
                <small>Nothing is captured until you start the camera.</small>
              </div>
            )}
          </div>
          <canvas ref={canvasRef} className="ct-camera__hidden-canvas" aria-hidden="true" />
          <div className="ct-camera__device-row">
            <label htmlFor="ct-camera-device">Camera device</label>
            <select id="ct-camera-device" value={selectedDeviceId} onChange={onDeviceSelected} disabled={cameraState === "starting"}>
              {devices.length === 0 && <option value="">No camera detected yet</option>}
              {devices.map((device, index) => <option value={device.deviceId} key={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}
            </select>
          </div>
          <div className="ct-camera__actions">
            {cameraState === "live" ? (
              <button type="button" className="ct-camera__button ct-camera__button--secondary" onClick={stopCamera}>Stop camera</button>
            ) : (
              <button type="button" className="ct-camera__button" onClick={() => void startCamera()} disabled={cameraState === "starting"}>
                {cameraState === "starting" ? "Requesting access…" : "Start camera"}
              </button>
            )}
            <span className="ct-camera__muted">Audio is never requested.</span>
          </div>
        </div>

        <div className="ct-camera__evidence-panel">
          <div className="ct-camera__evidence-title">
            <div><span className="ct-camera__section-label">LATEST RESULT</span><h3 aria-live="polite" aria-atomic="true">{signalText}</h3></div>
            <span className={`ct-camera__status-dot ${evidence?.provenance === "REAL" && !stale && evidence.status === "AVAILABLE" ? "is-live" : "is-muted"}`} aria-hidden="true" />
          </div>
          <dl className="ct-camera__facts">
            <div><dt>Data origin</dt><dd>{evidence?.provenance ?? "—"}</dd></div>
            <div><dt>Raw detections</dt><dd>{evidence?.raw_person_count ?? "—"}</dd></div>
            <div><dt>Rolling median</dt><dd>{evidence?.smoothed_person_count ?? "—"} <small>({evidence?.smoothing_window ?? health?.smoothing_window ?? 5} frames)</small></dd></div>
            <div><dt>Coverage attested</dt><dd>{evidence?.coverage_confirmed ? "Yes" : "No"}</dd></div>
            <div><dt>Rule eligibility</dt><dd>{evidenceEligible ? "May contribute to dwell rule" : "Not eligible"}</dd></div>
            <div><dt>Last evidence</dt><dd>{formatTime(evidence?.received_at)}</dd></div>
            <div><dt>Person confidence threshold</dt><dd>{health?.detector_confidence_threshold == null ? "—" : `${Math.round(health.detector_confidence_threshold * 100)}%`}</dd></div>
            <div><dt>Persistence</dt><dd>{evidence?.persistence_status ?? (health?.persistence_sink_configured ? "Ready" : "Not configured")}</dd></div>
          </dl>
          {evidence?.reason_code && <p className="ct-camera__reason"><strong>{evidence.reason_code}</strong></p>}
          <p className="ct-camera__explanation">{evidence?.explanation ?? "Start a camera or select the clearly labelled simulation fallback. Until valid evidence arrives, occupancy stays UNKNOWN."}</p>
          {(stale || evidence?.reason_code === "STALE_FRAME") && <p className="ct-camera__warning" role="status">The latest frame is stale. Occupancy has reverted to unknown; no empty-room event should be inferred.</p>}
          {!coverageConfirmed && <p className="ct-camera__warning">Coverage is not confirmed. A no-person result cannot contribute to likely-empty evaluation.</p>}
          {health && !health.detector_available && <p className="ct-camera__warning">{health.message}</p>}
        </div>
      </div>

      <section className="ct-video-upload" aria-labelledby="ct-video-upload-title">
        <div className="ct-video-upload__heading">
          <div>
            <p className="ct-camera__eyebrow">ALTERNATIVE INPUT</p>
            <h3 id="ct-video-upload-title">Analyze a recorded video</h3>
            <p>Use a campus recording when a live camera is not practical. Video decoding happens in this browser; only sampled, downsized JPEG frames are sent for temporary inference.</p>
          </div>
          <span className="ct-video-upload__privacy">Local file · no video upload</span>
        </div>
        <div className="ct-video-upload__controls">
          <label className="ct-video-upload__file-label" htmlFor="ct-video-file">Choose video file</label>
          <input id="ct-video-file" type="file" accept="video/mp4,video/webm,video/quicktime,video/*" onChange={onVideoSelected} disabled={uploadBusy} />
          <label htmlFor="ct-video-sample-interval">Sample interval</label>
          <select id="ct-video-sample-interval" value={sampleInterval} onChange={(event) => setSampleInterval(event.target.value)} disabled={uploadBusy}>
            <option value="1">Every 1 second</option>
            <option value="2">Every 2 seconds</option>
            <option value="5">Every 5 seconds</option>
            <option value="10">Every 10 seconds</option>
          </select>
          {uploadedVideoUrl && !uploadBusy && <button type="button" className="ct-camera__button" onClick={() => void analyzeUploadedVideo()}>Analyze recorded video</button>}
          {uploadBusy && <button type="button" className="ct-camera__button ct-camera__button--secondary" onClick={stopVideoAnalysis}>Stop analysis</button>}
        </div>
        {uploadedVideoUrl && <div className="ct-video-upload__preview-wrap">
          <div className="ct-video-upload__filename"><strong>{uploadedVideoName}</strong><span>Stored only in this browser tab</span></div>
          <video ref={uploadedVideoRef} className="ct-video-upload__preview" src={uploadedVideoUrl} controls preload="metadata" playsInline aria-label="Selected local video preview" />
          <canvas ref={uploadedCanvasRef} className="ct-camera__hidden-canvas" aria-hidden="true" />
          {uploadProgress && <div className="ct-video-upload__progress" role="status"><div><span>Frames analyzed</span><strong>{uploadProgress.processed} / {uploadProgress.total}</strong></div><progress max={Math.max(1, uploadProgress.total)} value={uploadProgress.processed} /></div>}
        </div>}
        <p className="ct-video-upload__note">Recorded video is retrospective evidence: the coverage flag is deliberately false, so it cannot trigger a real-time “likely empty” timer. Limits: 250 MB, 30 minutes and at most 300 sampled frames per analysis. No audio is extracted or sent.</p>
      </section>

      <div className="ct-camera__coverage">
        <label className="ct-camera__check-label">
          <input type="checkbox" checked={coverageConfirmed} onChange={(event) => {
            coverageConfirmedRef.current = event.target.checked;
            setCoverageConfirmed(event.target.checked);
          }} />
          <span><strong>I reviewed this camera view and confirmed it covers the relevant room area.</strong><small>This is an operator attestation, not an automated guarantee. Uncovered corners, blocked views or changing layouts can invalidate it.</small></span>
        </label>
      </div>

      <details className="ct-camera__simulation">
        <summary>Demo fallback · submit simulated occupancy</summary>
        <div className="ct-camera__simulation-body">
          <p>This path is for rehearsal when a camera or approved local model is unavailable. It stays labelled <strong>SIMULATED</strong> and can never qualify as real empty-room evidence.</p>
          <label htmlFor="ct-sim-count">Simulated people count</label>
          <select id="ct-sim-count" value={simulatedCount} onChange={(event) => setSimulatedCount(event.target.value)}>
            <option value="0">0 people</option><option value="1">1 person</option><option value="2">2 people</option>
          </select>
          <button type="button" className="ct-camera__button ct-camera__button--secondary" onClick={() => void submitSimulation()} disabled={simulationBusy}>
            {simulationBusy ? "Submitting…" : "Submit simulated evidence"}
          </button>
        </div>
      </details>

      {error && <p className="ct-camera__error" role="alert">{error} Camera evidence must remain unknown until a valid result arrives.</p>}
      <footer className="ct-camera__footer">
        <span>Backend: {health?.detector_available ? "Local detector ready" : "Detector unavailable"}</span>
        <span>Model license reviewed: {health?.model_license_reviewed ? "Yes" : "No"}</span>
        <span>Evidence sink: {health?.persistence_sink_configured ? "Configured" : "Not connected"}</span>
      </footer>
    </section>
  );
}
