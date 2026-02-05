import { useCallback, useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";
import type { FrameEvent, StreamStats } from "../lib/types";
import { useGsdToken } from "../lib/auth";

function normalizeStreamBaseUrl(raw: string): string {
  const trimmed = (raw || "").trim().replace(/\/+$/, "");
  if (!trimmed) return trimmed;
  if (trimmed.endsWith("/stream")) return trimmed.slice(0, -"/stream".length);
  if (trimmed.endsWith("/ctrl")) return trimmed.slice(0, -"/ctrl".length);
  return trimmed;
}

interface UseStreamSocketOpts {
  sessionId: string;
  /** Override stream URL (for embeddable mode) */
  streamUrl?: string;
  /** Override JWT token (for embeddable mode) */
  token?: string;
}

export interface UseStreamSocketResult {
  connected: boolean;
  frame: FrameEvent | null;
  stats: StreamStats;
}

type BrowserUpdatePayload = {
  image_base64?: unknown;
  mime_type?: unknown;
  timestamp?: unknown;
  session_id?: unknown;
  metadata?: unknown;
};

export function useStreamSocket(opts: UseStreamSocketOpts): UseStreamSocketResult {
  const { sessionId, streamUrl, token: tokenProp } = opts;
  const [connected, setConnected] = useState(false);
  const [frame, setFrame] = useState<FrameEvent | null>(null);
  const [stats, setStats] = useState<StreamStats>({
    fps: 0,
    latencyMs: 0,
    frameSeq: 0,
    framesReceived: 0,
  });

  const socketRef = useRef<Socket | null>(null);
  const fpsCountRef = useRef(0);
  const fpsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const seqRef = useRef(0);
  const getToken = useGsdToken();

  const connectSocket = useCallback(async () => {
    if (!sessionId) return;

    const jwt = tokenProp ?? (await getToken());
    const url = normalizeStreamBaseUrl(streamUrl || "");
    if (!url) return;

    const socket = io(`${url}/stream`, {
      path: "/socket.io",
      transports: ["websocket", "polling"],
      query: { session_id: sessionId },
      auth: jwt ? { token: jwt } : undefined,
      autoConnect: true,
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
    });

    socket.on("connect", () => {
      setConnected(true);
      socket.emit("join_session", { session_id: sessionId });
    });

    socket.on("disconnect", () => {
      setConnected(false);
    });

    socket.on("frame", (data: FrameEvent) => {
      setFrame({ ...data, mime_type: data.mime_type ?? "image/jpeg" });
      fpsCountRef.current++;
      setStats((prev) => ({
        ...prev,
        latencyMs: data.latency_ms,
        frameSeq: data.seq,
        framesReceived: prev.framesReceived + 1,
      }));
    });

    socket.on("browser_update", (payload: BrowserUpdatePayload) => {
      const b64 = payload?.image_base64;
      if (typeof b64 !== "string" || !b64) return;
      const mime = typeof payload?.mime_type === "string" ? payload.mime_type : "image/png";
      const nextSeq = (seqRef.current += 1);
      const ts = typeof payload?.timestamp === "number" ? payload.timestamp : Date.now() / 1000;
      const metadataRaw = payload?.metadata;
      const metadata =
        metadataRaw && typeof metadataRaw === "object" ? (metadataRaw as Record<string, unknown>) : {};

      const nextFrame: FrameEvent = {
        seq: nextSeq,
        session_id: typeof payload?.session_id === "string" ? payload.session_id : sessionId,
        received_ts: ts,
        emitted_ts: ts,
        latency_ms: 0,
        data_base64: b64,
        mime_type: mime,
        metadata,
      };

      setFrame(nextFrame);
      fpsCountRef.current++;
      setStats((prev) => ({
        ...prev,
        latencyMs: 0,
        frameSeq: nextSeq,
        framesReceived: prev.framesReceived + 1,
      }));
    });

    socketRef.current = socket;

    // FPS counter — update every second
    fpsIntervalRef.current = setInterval(() => {
      setStats((prev) => ({
        ...prev,
        fps: fpsCountRef.current,
      }));
      fpsCountRef.current = 0;
    }, 1000);
  }, [sessionId, streamUrl, tokenProp, getToken]);

  useEffect(() => {
    connectSocket();
    return () => {
      socketRef.current?.disconnect();
      socketRef.current = null;
      if (fpsIntervalRef.current) {
        clearInterval(fpsIntervalRef.current);
      }
    };
  }, [connectSocket]);

  return { connected, frame, stats };
}
