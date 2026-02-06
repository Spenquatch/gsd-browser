import { useCallback, useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";
import type { ControlStateEvent, InputEvent } from "../lib/types";
import { useGsdToken } from "../lib/auth";

function normalizeStreamBaseUrl(raw: string): string {
  const trimmed = (raw || "").trim().replace(/\/+$/, "");
  if (!trimmed) return trimmed;
  if (trimmed.endsWith("/stream")) return trimmed.slice(0, -"/stream".length);
  if (trimmed.endsWith("/ctrl")) return trimmed.slice(0, -"/ctrl".length);
  return trimmed;
}

function extractAckError(resp: unknown, fallback: string): string | null {
  if (!resp || typeof resp !== "object") return null;
  const ok = (resp as { ok?: unknown }).ok;
  if (ok !== false) return null;
  const err = (resp as { error?: unknown }).error;
  if (typeof err === "string" && err.trim()) return err;
  return fallback;
}

interface UseControlSocketOpts {
  sessionId: string;
  streamUrl?: string;
  token?: string;
}

export interface UseControlSocketResult {
  controlState: ControlStateEvent | null;
  socketId: string | null;
  lastError: string | null;
  takeControl: () => void;
  releaseControl: () => void;
  pause: () => void;
  resume: () => void;
  sendInput: (event: InputEvent) => void;
}

export function useControlSocket(opts: UseControlSocketOpts): UseControlSocketResult {
  const { sessionId, streamUrl, token: tokenProp } = opts;
  const [controlState, setControlState] = useState<ControlStateEvent | null>(null);
  const [socketId, setSocketId] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const socketRef = useRef<Socket | null>(null);
  const getToken = useGsdToken();

  const connectSocket = useCallback(async () => {
    if (!sessionId) return;

    const jwt = tokenProp ?? (await getToken());
    const url = normalizeStreamBaseUrl(streamUrl || "");
    if (!url) return;

    const socket = io(`${url}/ctrl`, {
      path: "/socket.io",
      transports: ["websocket", "polling"],
      query: { session_id: sessionId },
      auth: jwt ? { token: jwt } : undefined,
      autoConnect: true,
      reconnection: true,
    });

    socket.on("connect", () => {
      setSocketId(socket.id ?? null);
      setLastError(null);
    });

    socket.on("disconnect", () => {
      setSocketId(null);
    });

    socket.on("connect_error", (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to connect control socket";
      setLastError(msg);
    });

    socket.on("control_state", (data: ControlStateEvent) => {
      setControlState(data);
    });

    socketRef.current = socket;
  }, [sessionId, streamUrl, tokenProp, getToken]);

  useEffect(() => {
    connectSocket();
    return () => {
      socketRef.current?.disconnect();
      socketRef.current = null;
    };
  }, [connectSocket]);

  const takeControl = useCallback(() => {
    socketRef.current?.emit("take_control", { session_id: sessionId }, (resp: unknown) => {
      setLastError(extractAckError(resp, "take_control_failed"));
    });
  }, [sessionId]);

  const releaseControl = useCallback(() => {
    socketRef.current?.emit("release_control", { session_id: sessionId }, (resp: unknown) => {
      setLastError(extractAckError(resp, "release_control_failed"));
    });
  }, [sessionId]);

  const pause = useCallback(() => {
    socketRef.current?.emit("pause_agent", { session_id: sessionId }, (resp: unknown) => {
      setLastError(extractAckError(resp, "pause_agent_failed"));
    });
  }, [sessionId]);

  const resume = useCallback(() => {
    socketRef.current?.emit("resume_agent", { session_id: sessionId }, (resp: unknown) => {
      setLastError(extractAckError(resp, "resume_agent_failed"));
    });
  }, [sessionId]);

  const sendInput = useCallback(
    (event: InputEvent) => {
      const eventName = `input_${event.type}`;
      socketRef.current?.emit(eventName, { ...event, session_id: sessionId });
    },
    [sessionId],
  );

  return { controlState, socketId, lastError, takeControl, releaseControl, pause, resume, sendInput };
}
