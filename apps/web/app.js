import { createCameraResources, safeAnalyzeError } from "./lifecycle.mjs";

/**
 * Stage 8 live barcode framing client (B21–B25).
 * Ready/green gates + one-action camera guidance. No decode/serial display.
 * Preview frames stay in memory.
 */

const MAX_SAMPLE_HZ = 5;
const MIN_SAMPLE_MS = Math.ceil(1000 / MAX_SAMPLE_HZ);
const ANALYZE_TIMEOUT_MS = 2500;
const API_BASE = "http://127.0.0.1:8000";

/** Camera-referent English copy for guidance_action enum values. */
const GUIDANCE_COPY = {
  none: "",
  camera_closer: "Move the camera closer.",
  camera_farther: "Move the camera farther away.",
  camera_left: "Move the camera left.",
  camera_right: "Move the camera right.",
  camera_up: "Move the camera up.",
  camera_down: "Move the camera down.",
  camera_steady: "Hold the camera steady.",
  reduce_glare: "Move the camera or light to reduce glare.",
};

const els = {
  preview: document.getElementById("preview"),
  freeze: document.getElementById("freeze"),
  overlay: document.getElementById("overlay"),
  status: document.getElementById("status"),
  error: document.getElementById("error"),
  btnStart: document.getElementById("btnStart"),
  btnStop: document.getElementById("btnStop"),
  btnAnalyze: document.getElementById("btnAnalyze"),
  btnShutter: document.getElementById("btnShutter"),
  btnRetake: document.getElementById("btnRetake"),
  autoSample: document.getElementById("autoSample"),
};

/** @type {"live" | "frozen"} */
let mode = "live";
/** @type {object | null} */
let lastResult = null;
let starting = false;
let cameraStartEpoch = 0;
let lastSampleAt = 0;

const resources = createCameraResources({
  video: els.preview,
  canvases: [els.freeze, els.overlay],
  clearIntervalFn: (timer) => window.clearInterval(timer),
  onTrackEnded: () => stopCamera("Camera ended"),
});

function setError(message) {
  if (!message) {
    els.error.hidden = true;
    els.error.textContent = "";
    return;
  }
  els.error.hidden = false;
  els.error.textContent = message;
}

function setStatus(text, kind = "searching") {
  els.status.textContent = text;
  els.status.dataset.kind = kind;
}

function syncButtons() {
  const live = mode === "live" && !!resources.stream;
  els.btnAnalyze.disabled = !live || !!resources.requestController;
  els.btnShutter.disabled = !live;
  els.btnRetake.disabled = mode !== "frozen";
  els.btnStart.disabled = starting || !!resources.stream;
  els.btnStop.disabled = !resources.stream;
  els.autoSample.disabled = !live;
}

function resizeCanvases() {
  const rect = els.preview.getBoundingClientRect();
  const w = Math.max(1, Math.floor(rect.width));
  const h = Math.max(1, Math.floor(rect.height));
  for (const c of [els.freeze, els.overlay]) {
    if (c.width !== w || c.height !== h) {
      c.width = w;
      c.height = h;
    }
  }
}

/**
 * Draw video into a canvas using object-fit: contain letterboxing.
 * @param {HTMLVideoElement} video
 * @param {HTMLCanvasElement} canvas
 */
function drawVideoContained(video, canvas) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const cw = canvas.width;
  const ch = canvas.height;
  ctx.clearRect(0, 0, cw, ch);
  const vw = video.videoWidth || cw;
  const vh = video.videoHeight || ch;
  const scale = Math.min(cw / vw, ch / vh);
  const dw = vw * scale;
  const dh = vh * scale;
  const dx = (cw - dw) / 2;
  const dy = (ch - dh) / 2;
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, cw, ch);
  ctx.drawImage(video, dx, dy, dw, dh);
  return { dx, dy, dw, dh, vw, vh };
}

function clearOverlay() {
  const ctx = els.overlay.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, els.overlay.width, els.overlay.height);
}

/**
 * @param {{x0:number,y0:number,x1:number,y1:number} | null | undefined} box
 * @param {"ready" | "guidance" | "neutral"} style
 */
function drawOverlayBox(box, style = "neutral") {
  clearOverlay();
  if (!box) return;
  const ctx = els.overlay.getContext("2d");
  if (!ctx) return;
  const video = mode === "frozen" ? null : els.preview;
  const cw = els.overlay.width;
  const ch = els.overlay.height;
  let dx = 0;
  let dy = 0;
  let dw = cw;
  let dh = ch;
  if (video && video.videoWidth && video.videoHeight) {
    const scale = Math.min(cw / video.videoWidth, ch / video.videoHeight);
    dw = video.videoWidth * scale;
    dh = video.videoHeight * scale;
    dx = (cw - dw) / 2;
    dy = (ch - dh) / 2;
  } else if (mode === "frozen") {
    // freeze canvas already letterboxed; box maps onto full freeze content area
    // Use same contain math from freeze video dims stored on dataset if present.
    const vw = Number(els.freeze.dataset.vw || cw);
    const vh = Number(els.freeze.dataset.vh || ch);
    const scale = Math.min(cw / vw, ch / vh);
    dw = vw * scale;
    dh = vh * scale;
    dx = (cw - dw) / 2;
    dy = (ch - dh) / 2;
  }
  const x = dx + box.x0 * dw;
  const y = dy + box.y0 * dh;
  const w = (box.x1 - box.x0) * dw;
  const h = (box.y1 - box.y0) * dh;
  if (style === "ready") {
    ctx.strokeStyle = "#3dff8a";
  } else if (style === "guidance") {
    ctx.strokeStyle = "#4f8cff";
  } else {
    ctx.strokeStyle = "#5dffa6";
  }
  ctx.lineWidth = Math.max(2, Math.round(Math.min(cw, ch) * 0.006));
  ctx.strokeRect(x, y, w, h);
}

/**
 * @param {object | null | undefined} result
 */
function applyResult(result) {
  lastResult = result;
  const readiness = result?.readiness;
  const count = result?.count_status;
  const action = result?.guidance_action || "none";

  if (readiness === "ready") {
    setStatus("Ready — you may take the picture", "ready");
    drawOverlayBox(result.barcode_box, "ready");
    return;
  }
  if (readiness === "guidance") {
    const copy = GUIDANCE_COPY[action] || "Adjust the camera.";
    setStatus(copy, "guidance");
    drawOverlayBox(result.barcode_box, "guidance");
    return;
  }
  // abstain or missing readiness: count-based copy, no directional action
  if (count === "multiple") {
    setStatus("Multiple barcodes — abstain", "multiple");
    clearOverlay();
  } else if (count === "none") {
    setStatus("No barcode", "none");
    clearOverlay();
  } else if (count === "unknown") {
    setStatus("Unknown — abstain", "searching");
    clearOverlay();
  } else if (count === "one") {
    // one without readiness (older server) — show box neutrally
    setStatus("One barcode", "one");
    drawOverlayBox(result.barcode_box, "neutral");
  } else {
    setStatus("Searching…", "searching");
    clearOverlay();
  }
}

/**
 * Capture current frame as JPEG Blob.
 * @returns {Promise<Blob | null>}
 */
async function captureFrameBlob() {
  resizeCanvases();
  const scratch = document.createElement("canvas");
  const video = els.preview;
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return null;
  // Bound sample resolution for API budget.
  const maxSide = 1280;
  const scale = Math.min(1, maxSide / Math.max(vw, vh));
  scratch.width = Math.max(1, Math.round(vw * scale));
  scratch.height = Math.max(1, Math.round(vh * scale));
  const ctx = scratch.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(video, 0, 0, scratch.width, scratch.height);
  const blob = await new Promise((resolve) => {
    scratch.toBlob((blob) => resolve(blob), "image/jpeg", 0.85);
  });
  ctx.clearRect(0, 0, scratch.width, scratch.height);
  scratch.width = 1;
  scratch.height = 1;
  return blob;
}

async function analyzeOnce() {
  if (resources.requestController || mode !== "live" || !resources.stream)
    return;
  const now = performance.now();
  if (now - lastSampleAt < MIN_SAMPLE_MS) return;
  lastSampleAt = now;
  syncButtons();
  setError("");
  setStatus("Searching…", "searching");
  const analysisEpoch = cameraStartEpoch;
  const controller = resources.beginRequest();
  let timedOut = false;
  resources.setRequestTimeout(
    window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, ANALYZE_TIMEOUT_MS),
  );
  try {
    const blob = await captureFrameBlob();
    if (controller.signal.aborted || analysisEpoch !== cameraStartEpoch) return;
    if (!blob) {
      setStatus("No frame yet", "error");
      return;
    }
    const form = new FormData();
    form.append("image", blob, "frame.jpg");
    const response = await fetch(`${API_BASE}/v1/barcode/analyze`, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    if (controller.signal.aborted || analysisEpoch !== cameraStartEpoch) return;
    if (!response.ok) {
      setStatus("Analyze failed", "error");
      setError(safeAnalyzeError(response.status));
      clearOverlay();
      return;
    }
    const data = await response.json().catch(() => ({}));
    if (controller.signal.aborted || analysisEpoch !== cameraStartEpoch) return;
    // Hard guard: never surface unexpected payload-like keys.
    if ("payload" in data || "decoded" in data || "raw_string" in data) {
      setStatus("Rejected unsafe response", "error");
      setError("Server response contained disallowed fields.");
      clearOverlay();
      return;
    }
    applyResult(data);
  } catch {
    if (
      (controller.signal.aborted && !timedOut) ||
      analysisEpoch !== cameraStartEpoch
    )
      return;
    if (timedOut) {
      setStatus("Analyze timed out", "error");
      setError("Analysis exceeded the local time budget.");
      clearOverlay();
      return;
    }
    setStatus("API unreachable", "error");
    setError("Could not reach the loopback API.");
    clearOverlay();
  } finally {
    resources.finishRequest(controller);
    syncButtons();
  }
}

async function startCamera() {
  if (starting || resources.stream) return;
  const startEpoch = ++cameraStartEpoch;
  starting = true;
  setError("");
  syncButtons();
  if (!navigator.mediaDevices?.getUserMedia) {
    starting = false;
    setStatus("Camera unavailable", "error");
    setError("This browser does not expose getUserMedia.");
    syncButtons();
    return;
  }
  let acquiredStream = null;
  try {
    acquiredStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    });
    if (startEpoch !== cameraStartEpoch) {
      resources.releaseStream(acquiredStream);
      return;
    }
    resources.attachStream(acquiredStream);
    mode = "live";
    els.freeze.classList.add("hidden");
    els.preview.classList.remove("hidden");
    await els.preview.play();
    if (startEpoch !== cameraStartEpoch) {
      resources.releaseStream(acquiredStream);
      return;
    }
  } catch (err) {
    if (startEpoch !== cameraStartEpoch) {
      if (acquiredStream) resources.releaseStream(acquiredStream);
      return;
    }
    resources.stop();
    setStatus("Camera unavailable", "error");
    const name =
      err && typeof err === "object" && "name" in err ? err.name : "";
    setError(
      name === "NotAllowedError"
        ? "Camera permission denied. Allow camera access and try again."
        : name === "NotFoundError"
          ? "No camera device found."
          : "Could not open camera.",
    );
    return;
  } finally {
    if (startEpoch === cameraStartEpoch) starting = false;
    syncButtons();
  }
  resizeCanvases();
  setStatus("Live — searching…", "searching");
  syncButtons();
  if (els.autoSample.checked) startAutoSample();
}

function stopAutoSample() {
  resources.clearSampleTimer();
}

function startAutoSample() {
  stopAutoSample();
  resources.setSampleTimer(
    window.setInterval(() => {
      void analyzeOnce();
    }, MIN_SAMPLE_MS),
  );
}

function shutter() {
  if (!resources.stream || mode !== "live") return;
  resizeCanvases();
  const geom = drawVideoContained(els.preview, els.freeze);
  if (geom) {
    els.freeze.dataset.vw = String(els.preview.videoWidth || geom.vw);
    els.freeze.dataset.vh = String(els.preview.videoHeight || geom.vh);
  }
  els.freeze.classList.remove("hidden");
  els.preview.classList.add("hidden");
  mode = "frozen";
  stopAutoSample();
  // Keep lastResult overlay with frozen prefix.
  if (lastResult?.readiness === "ready") {
    drawOverlayBox(lastResult.barcode_box, "ready");
    setStatus("Frozen — Ready (you may keep this picture)", "ready");
  } else if (lastResult?.readiness === "guidance") {
    const action = lastResult.guidance_action || "none";
    const copy = GUIDANCE_COPY[action] || "Adjust the camera.";
    drawOverlayBox(lastResult.barcode_box, "guidance");
    setStatus(`Frozen — ${copy}`, "guidance");
  } else if (lastResult?.count_status === "multiple") {
    setStatus("Frozen — multiple (abstain)", "multiple");
    clearOverlay();
  } else if (lastResult?.count_status === "none") {
    setStatus("Frozen — no barcode", "none");
    clearOverlay();
  } else if (lastResult?.count_status === "one") {
    drawOverlayBox(lastResult.barcode_box, "neutral");
    setStatus("Frozen — one barcode", "one");
  } else {
    setStatus("Frozen frame", "searching");
    clearOverlay();
  }
  syncButtons();
}

async function retake() {
  stopCamera();
  await startCamera();
}

function stopCamera(status = "Camera idle") {
  cameraStartEpoch += 1;
  starting = false;
  resources.stop();
  mode = "live";
  els.freeze.classList.add("hidden");
  els.preview.classList.remove("hidden");
  lastResult = null;
  setStatus(status, "searching");
  setError("");
  syncButtons();
}

els.btnStart.addEventListener("click", () => {
  void startCamera();
});
els.btnStop.addEventListener("click", () => stopCamera());
els.btnAnalyze.addEventListener("click", () => {
  void analyzeOnce();
});
els.btnShutter.addEventListener("click", () => shutter());
els.btnRetake.addEventListener("click", () => {
  void retake();
});
els.autoSample.addEventListener("change", () => {
  if (els.autoSample.checked && mode === "live" && resources.stream)
    startAutoSample();
  else stopAutoSample();
});

window.addEventListener("pagehide", () => stopCamera());
window.addEventListener("beforeunload", () => stopCamera());
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    stopCamera("Camera stopped while page was hidden");
  }
});

window.addEventListener("resize", () => {
  resizeCanvases();
  if (!lastResult) return;
  if (lastResult.readiness === "ready") {
    drawOverlayBox(lastResult.barcode_box, "ready");
  } else if (lastResult.readiness === "guidance") {
    drawOverlayBox(lastResult.barcode_box, "guidance");
  } else if (lastResult.count_status === "one") {
    drawOverlayBox(lastResult.barcode_box, "neutral");
  }
});

setStatus("Camera idle", "searching");
syncButtons();
