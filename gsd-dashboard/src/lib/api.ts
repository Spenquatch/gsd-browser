import type { SessionInfo } from "./types";

const BASE_URL = import.meta.env.VITE_GSD_API_BASE_URL || "";

export interface SessionScreenshot {
  artifact_id: string;
  timestamp: number;
  type: string;
  step: number | null;
  url: string | null;
  /** Optional; navigation target (page URL) for the screenshot capture */
  page_url?: string | null;
  /** Optional; expiry timestamp (epoch seconds) for signed artifact URLs */
  url_expires_at?: number | null;
  has_error: boolean;
  mime_type: string;
  size_bytes: number;
  data_base64: string | null;
}

export interface SessionScreenshotsResponse {
  session_id: string;
  filters: {
    last_n: number;
    screenshot_type: string;
    include_data: boolean;
  };
  screenshots: SessionScreenshot[];
}

export async function fetchSessions(token?: string): Promise<SessionInfo[]> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE_URL}/api/v1/sessions`, { headers });
  if (!res.ok) {
    throw new Error(`Failed to fetch sessions: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSession(
  sessionId: string,
  token?: string,
): Promise<SessionInfo> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE_URL}/api/v1/sessions/${sessionId}`, {
    headers,
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch session: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function terminateSession(
  sessionId: string,
  token?: string,
): Promise<{ ok: boolean; session_id: string }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(
    `${BASE_URL}/api/v1/sessions/${sessionId}/terminate`,
    { method: "POST", headers },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Terminate failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchSessionScreenshots(
  sessionId: string,
  opts: {
    lastN?: number;
    screenshotType?: "agent_step" | "stream_sample" | "all";
    includeData?: boolean;
  } = {},
  token?: string,
): Promise<SessionScreenshotsResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const params = new URLSearchParams();
  params.set("last_n", String(opts.lastN ?? 10));
  params.set("screenshot_type", String(opts.screenshotType ?? "agent_step"));
  params.set("include_data", String(opts.includeData ?? true));

  const res = await fetch(
    `${BASE_URL}/api/v1/sessions/${sessionId}/screenshots?${params.toString()}`,
    { headers },
  );
  if (!res.ok) {
    throw new Error(
      `Failed to fetch session screenshots: ${res.status} ${res.statusText}`,
    );
  }
  return res.json();
}
