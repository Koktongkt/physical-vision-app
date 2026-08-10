import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { createCameraResources, safeAnalyzeError } from "../lifecycle.mjs";

function fakeCanvas() {
  const calls = [];
  return {
    width: 640,
    height: 480,
    calls,
    getContext() {
      return {
        clearRect(...args) {
          calls.push(args);
        },
      };
    },
  };
}

function fakeTrack() {
  return {
    stopped: 0,
    stop() {
      this.stopped += 1;
    },
    addEventListener() {},
    removeEventListener() {},
  };
}

test("stop clears an analyze timeout while frame capture is still pending", () => {
  const tracks = [fakeTrack(), fakeTrack()];
  const stream = { getTracks: () => tracks };
  const video = { srcObject: stream };
  const freeze = fakeCanvas();
  const overlay = fakeCanvas();
  const clearedTimers = [];
  const clearedTimeouts = [];
  const resources = createCameraResources({
    video,
    canvases: [freeze, overlay],
    clearIntervalFn: (timer) => clearedTimers.push(timer),
    clearTimeoutFn: (timer) => clearedTimeouts.push(timer),
  });

  resources.attachStream(stream);
  resources.setSampleTimer(17);
  const request = resources.beginRequest();
  resources.setRequestTimeout(23);
  resources.stop();
  resources.finishRequest(request);

  assert.deepEqual(clearedTimers, [17]);
  assert.deepEqual(clearedTimeouts, [23]);
  assert.equal(request.signal.aborted, true);
  assert.deepEqual(
    tracks.map((track) => track.stopped),
    [1, 1],
  );
  assert.equal(video.srcObject, null);
  assert.deepEqual(freeze.calls, [[0, 0, 640, 480]]);
  assert.deepEqual(overlay.calls, [[0, 0, 640, 480]]);
  assert.equal(resources.stream, null);
  assert.equal(resources.sampleTimer, null);
  assert.equal(resources.requestController, null);
  assert.equal(resources.requestTimeout, null);
});

test("server-controlled error content cannot become browser error copy", () => {
  const sentinel = "PAYLOAD-CANARY-C:/private/attacker.invalid";

  assert.equal(safeAnalyzeError(403, sentinel), "Local API request rejected.");
  assert.equal(
    safeAnalyzeError(413, sentinel),
    "Frame exceeded the local size budget.",
  );
  assert.equal(safeAnalyzeError(503, sentinel), "Local analyzer is busy.");
  assert.equal(
    safeAnalyzeError(504, sentinel),
    "Analysis exceeded the local time budget.",
  );
  assert.equal(safeAnalyzeError(500, sentinel), "Local analysis failed.");
  assert.doesNotMatch(
    [403, 413, 503, 504, 500]
      .map((status) => safeAnalyzeError(status, sentinel))
      .join(" "),
    /PAYLOAD-CANARY|private|attacker\.invalid/,
  );
});

test("repeated stop is idempotent and still clears display buffers", () => {
  const track = fakeTrack();
  const video = { srcObject: null };
  const freeze = fakeCanvas();
  const overlay = fakeCanvas();
  const resources = createCameraResources({
    video,
    canvases: [freeze, overlay],
  });

  resources.attachStream({ getTracks: () => [track] });

  assert.equal(resources.stop(), true);
  assert.equal(resources.stop(), false);
  assert.equal(track.stopped, 1);
  assert.equal(freeze.calls.length, 2);
  assert.equal(overlay.calls.length, 2);
  assert.equal(video.srcObject, null);
});

test("a browser track-ended event asks the application to stop the session", () => {
  let endedListener = null;
  let endedCalls = 0;
  const track = {
    stop() {},
    addEventListener(name, listener) {
      if (name === "ended") endedListener = listener;
    },
    removeEventListener() {},
  };
  const resources = createCameraResources({
    video: { srcObject: null },
    canvases: [fakeCanvas(), fakeCanvas()],
    onTrackEnded: () => {
      endedCalls += 1;
    },
  });

  resources.attachStream({ getTracks: () => [track] });
  endedListener();

  assert.equal(endedCalls, 1);
});

test("a second analysis request cannot overlap the active request", () => {
  const resources = createCameraResources({
    video: { srcObject: null },
    canvases: [fakeCanvas(), fakeCanvas()],
  });

  const first = resources.beginRequest();
  assert.throws(() => resources.beginRequest(), /already active/);
  resources.finishRequest(first);
  const second = resources.beginRequest();

  assert.notEqual(second, first);
  assert.equal(second.signal.aborted, false);
});

test("releasing a stale stream cannot detach or stop the current stream", () => {
  const staleTrack = fakeTrack();
  const currentTrack = fakeTrack();
  const stale = { getTracks: () => [staleTrack] };
  const current = { getTracks: () => [currentTrack] };
  const video = { srcObject: null };
  const resources = createCameraResources({
    video,
    canvases: [fakeCanvas(), fakeCanvas()],
  });

  resources.attachStream(stale);
  resources.attachStream(current);
  resources.releaseStream(stale);

  assert.equal(staleTrack.stopped, 1);
  assert.equal(currentTrack.stopped, 0);
  assert.equal(resources.stream, current);
  assert.equal(video.srcObject, current);
});

test("the web app wires explicit and browser lifecycle exits to cleanup", async () => {
  const [app, html] = await Promise.all([
    readFile(path.resolve("apps/web/app.js"), "utf8"),
    readFile(path.resolve("apps/web/index.html"), "utf8"),
  ]);

  assert.match(app, /createCameraResources/);
  assert.match(html, /id="btnStop"/);
  assert.match(app, /btnStop\.addEventListener/);
  assert.match(app, /addEventListener\("pagehide"/);
  assert.match(app, /addEventListener\("beforeunload"/);
  assert.match(app, /visibilityState === "hidden"/);
});

test("analysis is bounded, cancellable, content-free, and loopback-only", async () => {
  const [app, html] = await Promise.all([
    readFile(path.resolve("apps/web/app.js"), "utf8"),
    readFile(path.resolve("apps/web/index.html"), "utf8"),
  ]);

  assert.match(app, /const API_BASE = "http:\/\/127\.0\.0\.1:8000"/);
  assert.doesNotMatch(html, /id="apiBase"/);
  assert.match(app, /signal: controller\.signal/);
  assert.match(app, /ANALYZE_TIMEOUT_MS/);
  assert.match(app, /resources\.setRequestTimeout/);
  assert.match(app, /analysisEpoch !== cameraStartEpoch/);
  assert.match(app, /scratch\.width = 1/);
  assert.match(app, /scratch\.height = 1/);
  assert.doesNotMatch(
    app,
    /data\.message_key|data\.error|localStorage|sessionStorage|indexedDB|caches\.|serviceWorker|console\./,
  );
});
