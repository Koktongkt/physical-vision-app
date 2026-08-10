/**
 * Owns the browser resources that can outlive one UI action.
 * This module is DOM-light so its cleanup contract can be tested with Node.
 */

export function clearCanvas(canvas) {
  const context = canvas.getContext("2d");
  if (context) context.clearRect(0, 0, canvas.width, canvas.height);
}

export function stopStreamTracks(stream) {
  for (const track of stream.getTracks()) {
    try {
      track.stop();
    } catch {
      // Continue releasing the remaining tracks.
    }
  }
}

export function safeAnalyzeError(status) {
  switch (status) {
    case 403:
      return "Local API request rejected.";
    case 413:
      return "Frame exceeded the local size budget.";
    case 503:
      return "Local analyzer is busy.";
    case 504:
      return "Analysis exceeded the local time budget.";
    default:
      return "Local analysis failed.";
  }
}

export function createCameraResources({
  video,
  canvases,
  clearIntervalFn = globalThis.clearInterval,
  clearTimeoutFn = globalThis.clearTimeout,
  createAbortController = () => new AbortController(),
  onTrackEnded = () => {},
}) {
  let stopping = false;
  const endedListeners = new Map();

  const resources = {
    stream: null,
    sampleTimer: null,
    requestController: null,
    requestTimeout: null,

    attachStream(stream) {
      resources.stream = stream;
      video.srcObject = stream;
      for (const track of stream.getTracks()) {
        const listener = () => onTrackEnded();
        endedListeners.set(track, listener);
        track.addEventListener?.("ended", listener);
      }
    },

    releaseStream(stream) {
      for (const track of stream.getTracks()) {
        const listener = endedListeners.get(track);
        if (listener) track.removeEventListener?.("ended", listener);
        endedListeners.delete(track);
      }
      if (resources.stream === stream) {
        resources.stream = null;
        if (video.srcObject === stream) video.srcObject = null;
      }
      stopStreamTracks(stream);
    },

    setSampleTimer(timer) {
      resources.clearSampleTimer();
      resources.sampleTimer = timer;
    },

    clearSampleTimer() {
      if (resources.sampleTimer != null) {
        clearIntervalFn(resources.sampleTimer);
        resources.sampleTimer = null;
      }
    },

    beginRequest() {
      if (resources.requestController) {
        throw new Error("analysis request already active");
      }
      const controller = createAbortController();
      resources.requestController = controller;
      return controller;
    },

    setRequestTimeout(timeout) {
      resources.clearRequestTimeout();
      resources.requestTimeout = timeout;
    },

    clearRequestTimeout() {
      if (resources.requestTimeout != null) {
        clearTimeoutFn(resources.requestTimeout);
        resources.requestTimeout = null;
      }
    },

    finishRequest(controller) {
      if (resources.requestController === controller) {
        resources.clearRequestTimeout();
        resources.requestController = null;
      }
    },

    stop() {
      if (stopping) return false;
      stopping = true;
      try {
        resources.clearSampleTimer();
        resources.clearRequestTimeout();
        resources.requestController?.abort();
        resources.requestController = null;

        const activeStream = resources.stream;
        if (activeStream) resources.releaseStream(activeStream);
        video.srcObject = null;
        for (const canvas of canvases) clearCanvas(canvas);
        return Boolean(activeStream);
      } finally {
        stopping = false;
      }
    },
  };

  return resources;
}
