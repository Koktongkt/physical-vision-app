/**
 * Stage 6 live barcode framing client (B21 + B22 wiring).
 * No decode/serial display. Preview frames stay in memory.
 */

const MAX_SAMPLE_HZ = 5;
const MIN_SAMPLE_MS = Math.ceil(1000 / MAX_SAMPLE_HZ);

const els = {
  preview: document.getElementById("preview"),
  freeze: document.getElementById("freeze"),
  overlay: document.getElementById("overlay"),
  status: document.getElementById("status"),
  error: document.getElementById("error"),
  apiBase: document.getElementById("apiBase"),
  btnStart: document.getElementById("btnStart"),
  btnAnalyze: document.getElementById("btnAnalyze"),
  btnShutter: document.getElementById("btnShutter"),
  btnRetake: document.getElementById("btnRetake"),
  autoSample: document.getElementById("autoSample"),
};

/** @type {MediaStream | null} */
let stream = null;
/** @type {"live" | "frozen"} */
let mode = "live";
/** @type {object | null} */
let lastResult = null;
let analyzing = false;
let lastSampleAt = 0;
/** @type {number | null} */
let sampleTimer = null;

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

function apiBase() {
  return (els.apiBase.value || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function syncButtons() {
  const live = mode === "live" && !!stream;
  els.btnAnalyze.disabled = !live || analyzing;
  els.btnShutter.disabled = !live;
  els.btnRetake.disabled = mode !== "frozen";
  els.btnStart.disabled = !!stream && mode === "live";
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
 */
function drawOverlayBox(box) {
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
  ctx.strokeStyle = "#5dffa6";
  ctx.lineWidth = Math.max(2, Math.round(Math.min(cw, ch) * 0.006));
  ctx.strokeRect(x, y, w, h);
}

function applyResult(result) {
  lastResult = result;
  const status = result?.count_status;
  if (status === "one") {
    setStatus("One barcode", "one");
    drawOverlayBox(result.barcode_box);
  } else if (status === "multiple") {
    setStatus("Multiple barcodes — abstain", "multiple");
    clearOverlay();
  } else if (status === "none") {
    setStatus("No barcode", "none");
    clearOverlay();
  } else if (status === "unknown") {
    setStatus("Unknown", "searching");
    clearOverlay();
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
  return new Promise((resolve) => {
    scratch.toBlob((blob) => resolve(blob), "image/jpeg", 0.85);
  });
}

async function analyzeOnce() {
  if (analyzing || mode !== "live" || !stream) return;
  const now = performance.now();
  if (now - lastSampleAt < MIN_SAMPLE_MS) return;
  lastSampleAt = now;
  analyzing = true;
  syncButtons();
  setError("");
  setStatus("Searching…", "searching");
  try {
    const blob = await captureFrameBlob();
    if (!blob) {
      setStatus("No frame yet", "error");
      return;
    }
    const form = new FormData();
    form.append("image", blob, "frame.jpg");
    const response = await fetch(`${apiBase()}/v1/barcode/analyze`, {
      method: "POST",
      body: form,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const key = data.message_key || data.error || `HTTP ${response.status}`;
      setStatus("Analyze failed", "error");
      setError(`Analyze error: ${key}`);
      clearOverlay();
      return;
    }
    // Hard guard: never surface unexpected payload-like keys.
    if ("payload" in data || "decoded" in data || "raw_string" in data) {
      setStatus("Rejected unsafe response", "error");
      setError("Server response contained disallowed fields.");
      clearOverlay();
      return;
    }
    applyResult(data);
  } catch (err) {
    setStatus("API unreachable", "error");
    setError(
      err instanceof Error
        ? `Could not reach API (${err.message}). Is uvicorn running on ${apiBase()}?`
        : "Could not reach API.",
    );
    clearOverlay();
  } finally {
    analyzing = false;
    syncButtons();
  }
}

/**
 * Prefer a simple laptop/webcam stream first. `facingMode: environment` is for
 * phones; on many desktops it yields a black or failed track.
 * @returns {Promise<MediaStream>}
 */
async function openCameraStream() {
  const attempts = [
    {
      audio: false,
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    },
    // Fallback: any camera at all.
    { audio: false, video: true },
    // Phones: rear camera if available.
    {
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    },
  ];
  let lastErr = null;
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error("getUserMedia failed");
}

/**
 * Wait until the video element has real dimensions (or timeout).
 * @param {HTMLVideoElement} video
 * @param {number} timeoutMs
 */
function waitForVideoDimensions(video, timeoutMs = 4000) {
  if (video.videoWidth > 0 && video.videoHeight > 0) {
    return Promise.resolve(true);
  }
  return new Promise((resolve) => {
    const onReady = () => {
      cleanup();
      resolve(video.videoWidth > 0 && video.videoHeight > 0);
    };
    const timer = window.setTimeout(onReady, timeoutMs);
    const cleanup = () => {
      window.clearTimeout(timer);
      video.removeEventListener("loadedmetadata", onReady);
      video.removeEventListener("loadeddata", onReady);
      video.removeEventListener("playing", onReady);
    };
    video.addEventListener("loadedmetadata", onReady);
    video.addEventListener("loadeddata", onReady);
    video.addEventListener("playing", onReady);
  });
}

async function startCamera() {
  setError("");
  if (!navigator.mediaDevices?.getUserMedia) {
    setStatus("Camera unavailable", "error");
    setError("This browser does not expose getUserMedia.");
    return;
  }
  // Secure context required (http://127.0.0.1 / localhost / https). file:// often fails.
  if (!window.isSecureContext) {
    setStatus("Insecure context", "error");
    setError(
      "Open via http://127.0.0.1:5173 (python -m http.server), not file://.",
    );
    return;
  }
  try {
    // Stop any previous stream first.
    if (stream) {
      for (const track of stream.getTracks()) track.stop();
      stream = null;
    }
    stream = await openCameraStream();
  } catch (err) {
    stream = null;
    setStatus("Camera permission denied", "error");
    const name =
      err && typeof err === "object" && "name" in err ? err.name : "";
    setError(
      name === "NotAllowedError"
        ? "Camera permission denied. Allow camera access and try again."
        : name === "NotFoundError"
          ? "No camera device found."
          : "Could not open camera.",
    );
    syncButtons();
    return;
  }
  els.preview.srcObject = stream;
  els.preview.muted = true;
  els.preview.playsInline = true;
  mode = "live";
  els.freeze.classList.add("hidden");
  els.preview.classList.remove("hidden");
  clearOverlay();
  try {
    await els.preview.play();
  } catch (err) {
    setStatus("Preview blocked", "error");
    setError(
      err instanceof Error
        ? `Video play() failed: ${err.message}`
        : "Video play() failed.",
    );
  }
  resizeCanvases();
  const hasFrames = await waitForVideoDimensions(els.preview);
  if (!hasFrames) {
    setStatus("Live — black/no frames", "error");
    setError(
      "Camera track opened but no video frames yet. Check Windows camera privacy (Settings → Privacy → Camera), close other apps using the webcam, and confirm the correct camera is enabled. Then click Start camera again.",
    );
  } else {
    setStatus("Live — searching…", "searching");
    setError("");
  }
  syncButtons();
  if (els.autoSample.checked) startAutoSample();
}

function stopAutoSample() {
  if (sampleTimer != null) {
    window.clearInterval(sampleTimer);
    sampleTimer = null;
  }
}

function startAutoSample() {
  stopAutoSample();
  sampleTimer = window.setInterval(() => {
    void analyzeOnce();
  }, MIN_SAMPLE_MS);
}

function shutter() {
  if (!stream || mode !== "live") return;
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
  // Keep lastResult overlay.
  if (lastResult?.count_status === "one") {
    drawOverlayBox(lastResult.barcode_box);
    setStatus("Frozen — one barcode", "one");
  } else if (lastResult?.count_status === "multiple") {
    setStatus("Frozen — multiple (abstain)", "multiple");
  } else if (lastResult?.count_status === "none") {
    setStatus("Frozen — no barcode", "none");
  } else {
    setStatus("Frozen frame", "searching");
  }
  syncButtons();
}

function retake() {
  mode = "live";
  els.freeze.classList.add("hidden");
  els.preview.classList.remove("hidden");
  lastResult = null;
  clearOverlay();
  setStatus("Live — searching…", "searching");
  setError("");
  syncButtons();
  if (els.autoSample.checked) startAutoSample();
}

els.btnStart.addEventListener("click", () => {
  void startCamera();
});
els.btnAnalyze.addEventListener("click", () => {
  void analyzeOnce();
});
els.btnShutter.addEventListener("click", () => shutter());
els.btnRetake.addEventListener("click", () => retake());
els.autoSample.addEventListener("change", () => {
  if (els.autoSample.checked && mode === "live" && stream) startAutoSample();
  else stopAutoSample();
});

window.addEventListener("resize", () => {
  resizeCanvases();
  if (lastResult?.count_status === "one")
    drawOverlayBox(lastResult.barcode_box);
});

setStatus("Camera idle", "searching");
syncButtons();
