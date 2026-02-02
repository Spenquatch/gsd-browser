import type { SessionInfo } from "./types";

const BASE_URL = import.meta.env.VITE_GSD_API_BASE_URL || "";

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
