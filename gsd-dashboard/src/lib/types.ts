/** Server-side session state */
export interface SessionInfo {
  session_id: string;
  status: "create" | "active" | "paused" | "terminated";
  tenant_id: string;
  subject_id: string;
  worker_id: string;
  stream_url?: string;
  created_at: number;
  last_activity_at: number;
}

/** Socket.IO frame event from /stream namespace */
export interface FrameEvent {
  seq: number;
  session_id: string;
  received_ts: number;
  emitted_ts: number;
  latency_ms: number;
  data_base64: string;
  /** Optional; defaults to image/jpeg for CDP frames */
  mime_type?: string;
  metadata: Record<string, unknown>;
}

/** Control state broadcast from /ctrl namespace */
export interface ControlStateEvent {
  session_id: string;
  holder_sid: string | null;
  paused: boolean;
  held_since_ts: number | null;
}

/** Input event sent to server via /ctrl namespace */
export interface InputEvent {
  type: "click" | "move" | "wheel" | "keydown" | "keyup" | "type";
  session_id: string;
  x?: number;
  y?: number;
  button?: "left" | "middle" | "right";
  delta_x?: number;
  delta_y?: number;
  key?: string;
  text?: string;
}

/** Streaming stats for HUD display */
export interface StreamStats {
  fps: number;
  latencyMs: number;
  frameSeq: number;
  framesReceived: number;
}
