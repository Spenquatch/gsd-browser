/* global io */

const $ = (id) => document.getElementById(id);

function nowMs() {
  return performance.now();
}

function setPill(el, text, variant) {
  el.textContent = text;
  el.className = `pill ${variant ?? 'pill-muted'}`;
}

function toast(message, variant = 'bad') {
  const host = $('toasts');
  const node = document.createElement('div');
  node.className = `toast ${variant}`;
  node.textContent = message;
  host.appendChild(node);
  setTimeout(() => node.remove(), 4500);
}

async function hmacSha256Hex(secret, message) {
  const enc = new TextEncoder();
  const keyData = enc.encode(secret);
  const msgData = enc.encode(message);
  const key = await crypto.subtle.importKey(
    'raw',
    keyData,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, msgData);
  const bytes = new Uint8Array(signature);
  let out = '';
  for (const b of bytes) out += b.toString(16).padStart(2, '0');
  return out;
}

async function getAuthConfig() {
  const resp = await fetch('/auth/config', { cache: 'no-store' });
  if (!resp.ok) throw new Error(`auth config failed (${resp.status})`);
  return await resp.json();
}

async function issueNonce() {
  const resp = await fetch('/auth/nonce', { cache: 'no-store' });
  if (!resp.ok) throw new Error(`nonce request failed (${resp.status})`);
  return await resp.json();
}

function fmtMs(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toFixed(1)} ms`;
}

function fmtTs(tsSeconds) {
  if (!tsSeconds) return '—';
  const d = new Date(tsSeconds * 1000);
  return d.toLocaleTimeString();
}

let streamSocket = null;
let ctrlSocket = null;
let ctrlSid = null;
let authRequired = false;
let lastFrameWallTs = null;
let fpsCounter = { t0: nowMs(), frames: 0 };
let sampleSeen = 0;
let lastControlState = {
  holder_sid: null,
  held_since_ts: null,
  paused: false,
  active_session_id: null
};

async function connectSockets() {
  const config = await getAuthConfig();
  authRequired = Boolean(config?.auth_required);

  const apiKeyInput = $('apiKey');
  apiKeyInput.disabled = !authRequired;
  if (authRequired && !apiKeyInput.value) {
    toast('Auth is enabled; enter API key then Connect', 'bad');
    return;
  }

  let auth = undefined;
  if (authRequired) {
    const { nonce } = await issueNonce();
    const sig = await hmacSha256Hex(apiKeyInput.value, nonce);
    auth = { nonce, sig };
  }

  setPill($('connStatus'), 'connecting…', 'pill-warn');

  streamSocket = io('/stream', {
    transports: ['websocket'],
    auth,
    reconnection: true,
    reconnectionAttempts: 10,
    timeout: 5000
  });

  ctrlSocket = io('/ctrl', {
    transports: ['websocket'],
    auth,
    reconnection: true,
    reconnectionAttempts: 10,
    timeout: 5000
  });

  streamSocket.on('connect', () => {
    setPill($('connStatus'), 'stream connected', 'pill-good');
  });
  streamSocket.on('disconnect', (reason) => {
    setPill($('connStatus'), `disconnected (${reason})`, 'pill-bad');
  });
  streamSocket.on('connect_error', (err) => {
    setPill($('connStatus'), 'stream auth error', 'pill-bad');
    toast(`Stream connect error: ${err?.message ?? err}`, 'bad');
  });

  ctrlSocket.on('connect_error', (err) => {
    toast(`Control connect error: ${err?.message ?? err}`, 'bad');
  });
  ctrlSocket.on('connect', () => {
    ctrlSid = ctrlSocket?.id ?? null;
    updateControlState(lastControlState);
  });
  ctrlSocket.on('disconnect', () => {
    ctrlSid = null;
    updateControlState(lastControlState);
  });
  ctrlSocket.on('control_state', (state) => updateControlState(state));

  streamSocket.on('frame', (payload) => {
    try {
      const data = payload?.data_base64;
      if (!data) return;
      $('seq').textContent = payload?.seq ?? '—';
      $('serverLatency').textContent = fmtMs(payload?.latency_ms);
      setPill($('modeStatus'), 'mode: cdp', 'pill-muted');

      const img = new Image();
      img.onload = () => {
        const canvas = $('canvas');
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        if (canvas.width !== img.width || canvas.height !== img.height) {
          canvas.width = img.width;
          canvas.height = img.height;
        }
        ctx.drawImage(img, 0, 0);
        $('fallbackImg').style.display = 'none';
        $('canvas').style.display = 'block';
      };
      img.src = `data:image/jpeg;base64,${data}`;

      lastFrameWallTs = nowMs();
      fpsCounter.frames += 1;
    } catch (e) {
      toast(`Render error: ${e?.message ?? e}`, 'bad');
    }
  });

  streamSocket.on('browser_update', (payload) => {
    const b64 = payload?.image_base64;
    if (!b64) return;
    const mime = payload?.mime_type ?? 'image/png';
    $('fallbackImg').src = `data:${mime};base64,${b64}`;
    $('fallbackImg').style.display = 'block';
    $('canvas').style.display = 'none';
    setPill($('modeStatus'), 'mode: screenshot', 'pill-muted');
    lastFrameWallTs = nowMs();
    fpsCounter.frames += 1;
  });
}

function updateControlState(state) {
  lastControlState = {
    holder_sid: state?.holder_sid ?? null,
    held_since_ts: state?.held_since_ts ?? null,
    paused: Boolean(state?.paused),
    active_session_id: state?.active_session_id ?? null
  };

  const holder = lastControlState.holder_sid;
  const heldSince = lastControlState.held_since_ts;
  const paused = lastControlState.paused;

  $('holderSid').textContent = holder ?? '—';
  $('heldSince').textContent = fmtTs(heldSince);
  $('paused').textContent = paused ? 'true' : 'false';

  const isHeld = Boolean(holder);
  const isHeldByMe = Boolean(ctrlSid) && holder === ctrlSid;
  setPill(
    $('ctrlStatus'),
    isHeld ? (isHeldByMe ? 'control: you' : 'control: held') : 'control: free',
    isHeld ? (isHeldByMe ? 'pill-good' : 'pill-warn') : 'pill-muted'
  );

  const connected = Boolean(ctrlSocket?.connected);
  $('btnTake').disabled = !connected || isHeld;
  $('btnRelease').disabled = !connected || !isHeldByMe;
  $('btnPause').disabled = !connected || !isHeldByMe || paused;
  $('btnResume').disabled = !connected || !isHeldByMe || !paused;

  const viewer = $('viewer');
  if (viewer) viewer.classList.toggle('ctrl-enabled', isCtrlInputEnabled());
}

function isCtrlInputEnabled() {
  if (!ctrlSocket?.connected) return false;
  if (!lastControlState.paused) return false;
  if (!lastControlState.holder_sid) return false;
  return Boolean(ctrlSid) && lastControlState.holder_sid === ctrlSid;
}

async function pollHealthz() {
  try {
    const resp = await fetch('/healthz', { cache: 'no-store' });
    if (!resp.ok) return;
    const data = await resp.json();
    const mode = data?.streaming_mode ?? '—';
    if (mode === 'cdp') setPill($('modeStatus'), 'mode: cdp', 'pill-muted');
    if (mode === 'screenshot') setPill($('modeStatus'), 'mode: screenshot', 'pill-muted');

    const totals = data?.sampler_totals ?? {};
    const seen = totals?.seen ?? 0;
    const stored = totals?.stored ?? 0;
    $('samples').textContent = `${seen}/${stored}`;

    if (seen > sampleSeen) {
      sampleSeen = seen;
      $('samplePulse').classList.add('on');
      setTimeout(() => $('samplePulse').classList.remove('on'), 350);
    }
  } catch {
    // ignore
  }
}

function tickFps() {
  const elapsed = nowMs() - fpsCounter.t0;
  if (elapsed >= 1000) {
    const fps = (fpsCounter.frames / elapsed) * 1000;
    $('fps').textContent = fps.toFixed(1);
    fpsCounter = { t0: nowMs(), frames: 0 };
  }

  if (lastFrameWallTs !== null) {
    const age = nowMs() - lastFrameWallTs;
    if (age > 3000 && streamSocket?.connected) {
      setPill($('connStatus'), 'connected (stalled)', 'pill-warn');
    }
  }

  requestAnimationFrame(tickFps);
}

function surfaceElement() {
  const canvas = $('canvas');
  if (canvas && canvas.style.display !== 'none') return canvas;
  return $('fallbackImg');
}

function surfaceSize(el) {
  if (!el) return null;

  if (el.tagName.toLowerCase() === 'canvas') {
    return { width: el.width, height: el.height };
  }

  const w = el.naturalWidth || 0;
  const h = el.naturalHeight || 0;
  if (w > 0 && h > 0) return { width: w, height: h };
  return null;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function surfaceCoordsFromEvent(evt) {
  const el = surfaceElement();
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;

  const size = surfaceSize(el);
  if (!size) return null;

  const relX = (evt.clientX - rect.left) / rect.width;
  const relY = (evt.clientY - rect.top) / rect.height;
  const x = clamp(relX * size.width, 0, size.width);
  const y = clamp(relY * size.height, 0, size.height);
  return { x, y };
}

function modifiersFromEvent(evt) {
  return {
    altKey: Boolean(evt.altKey),
    ctrlKey: Boolean(evt.ctrlKey),
    metaKey: Boolean(evt.metaKey),
    shiftKey: Boolean(evt.shiftKey)
  };
}

function normalizeWheelDelta(evt, rectHeight) {
  let dx = evt.deltaX;
  let dy = evt.deltaY;
  if (evt.deltaMode === 1) {
    dx *= 16;
    dy *= 16;
  } else if (evt.deltaMode === 2) {
    dx *= rectHeight || 1;
    dy *= rectHeight || 1;
  }
  return { dx, dy };
}

function emitCtrl(event, payload, { ack = false } = {}) {
  if (!ctrlSocket?.connected) return;
  if (!isCtrlInputEnabled()) return;

  if (ack) {
    ctrlSocket.emit(event, payload, (resp) => {
      if (resp?.ok) return;
      const err = resp?.error ?? 'unknown_error';
      const now = nowMs();
      if (!emitCtrl._lastRejectToastAt || now - emitCtrl._lastRejectToastAt > 2000) {
        emitCtrl._lastRejectToastAt = now;
        toast(`Input rejected (${event}): ${err}`, 'bad');
      }
    });
    return;
  }

  ctrlSocket.emit(event, payload);
}

function viewerHasFocus() {
  const viewer = $('viewer');
  if (!viewer) return false;
  const active = document.activeElement;
  return active === viewer || viewer.contains(active);
}

function wireInputCapture() {
  const viewer = $('viewer');
  if (!viewer) return;

  const focusViewer = () => {
    if (viewerHasFocus()) return;
    viewer.focus({ preventScroll: true });
  };

  viewer.addEventListener('pointerdown', (evt) => {
    focusViewer();
    if (!isCtrlInputEnabled()) return;

    evt.preventDefault();

    const coords = surfaceCoordsFromEvent(evt);
    if (!coords) return;

    const button = evt.button === 2 ? 'right' : evt.button === 1 ? 'middle' : 'left';
    const clickCount = Math.max(1, Number.isFinite(evt.detail) ? evt.detail : 1);
    emitCtrl(
      'input_click',
      { ...coords, button, click_count: clickCount, ...modifiersFromEvent(evt) },
      { ack: true }
    );
  });

  viewer.addEventListener('contextmenu', (evt) => {
    if (!isCtrlInputEnabled()) return;
    evt.preventDefault();
  });

  let lastMoveAt = 0;
  viewer.addEventListener('pointermove', (evt) => {
    if (!isCtrlInputEnabled()) return;
    const now = nowMs();
    if (now - lastMoveAt < 50) return;
    lastMoveAt = now;

    const coords = surfaceCoordsFromEvent(evt);
    if (!coords) return;

    emitCtrl('input_move', { ...coords, ...modifiersFromEvent(evt) });
  });

  viewer.addEventListener(
    'wheel',
    (evt) => {
      focusViewer();
      if (!isCtrlInputEnabled()) return;
      evt.preventDefault();

      const coords = surfaceCoordsFromEvent(evt);
      if (!coords) return;

      const surface = surfaceElement();
      const rect = surface?.getBoundingClientRect();
      const { dx, dy } = normalizeWheelDelta(evt, rect?.height);
      emitCtrl(
        'input_wheel',
        {
          ...coords,
          delta_x: dx,
          delta_y: dy,
          ...modifiersFromEvent(evt)
        },
        { ack: false }
      );
    },
    { passive: false }
  );

  window.addEventListener('keydown', (evt) => {
    if (!isCtrlInputEnabled()) return;
    if (!viewerHasFocus()) return;

    evt.preventDefault();
    evt.stopPropagation();

    emitCtrl(
      'input_keydown',
      {
        key: evt.key,
        code: evt.code,
        repeat: Boolean(evt.repeat),
        ...modifiersFromEvent(evt)
      },
      { ack: true }
    );

    if (
      evt.key &&
      evt.key.length === 1 &&
      !evt.ctrlKey &&
      !evt.metaKey &&
      !evt.altKey
    ) {
      emitCtrl('input_type', { text: evt.key }, { ack: true });
    }
  });

  window.addEventListener('keyup', (evt) => {
    if (!isCtrlInputEnabled()) return;
    if (!viewerHasFocus()) return;

    evt.preventDefault();
    evt.stopPropagation();

    emitCtrl(
      'input_keyup',
      {
        key: evt.key,
        code: evt.code,
        ...modifiersFromEvent(evt)
      },
      { ack: true }
    );
  });
}

function wireButtons() {
  $('btnConnect').addEventListener('click', async () => {
    try {
      await connectSockets();
      toast('Connected', 'good');
    } catch (e) {
      toast(e?.message ?? String(e), 'bad');
    }
  });

  $('btnTake').addEventListener('click', () => {
    ctrlSocket?.emit('take_control', {});
    ctrlSocket?.emit('pause_agent', {});
    $('viewer')?.focus({ preventScroll: true });
  });
  $('btnRelease').addEventListener('click', () => ctrlSocket?.emit('release_control', {}));
  $('btnPause').addEventListener('click', () => ctrlSocket?.emit('pause_agent', {}));
  $('btnResume').addEventListener('click', () => ctrlSocket?.emit('resume_agent', {}));
}

async function boot() {
  wireButtons();
  wireInputCapture();
  tickFps();
  setInterval(pollHealthz, 1000);

  try {
    const cfg = await getAuthConfig();
    authRequired = Boolean(cfg?.auth_required);
    $('apiKey').disabled = !authRequired;
    if (!authRequired) {
      await connectSockets();
    }
  } catch (e) {
    toast(`Startup error: ${e?.message ?? e}`, 'bad');
  }
}

boot();
