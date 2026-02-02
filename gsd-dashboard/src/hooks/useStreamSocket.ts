import { useCallback, useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";
import type { FrameEvent, StreamStats } from "../lib/types";
import { useGsdToken } from "../lib/auth";

const BASE_URL = import.meta.env.VITE_GSD_API_BASE_URL || "";

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
  const getToken = useGsdToken();

  const connectSocket = useCallback(async () => {
    if (!sessionId) return;

    const jwt = tokenProp ?? (await getToken());
    const url = streamUrl || BASE_URL || window.location.origin;

    const socket = io(url, {
      path: "/socket.io",
      transports: ["websocket", "polling"],
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
      setFrame(data);
      fpsCountRef.current++;
      setStats((prev) => ({
        ...prev,
        latencyMs: data.latency_ms,
        frameSeq: data.seq,
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
