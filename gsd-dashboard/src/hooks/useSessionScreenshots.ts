import { useCallback, useEffect, useState } from "react";
import { fetchSessionScreenshots, type SessionScreenshot } from "../lib/api";
import { useGsdToken } from "../lib/auth";

export interface UseSessionScreenshotsOpts {
  sessionId: string;
  lastN?: number;
  screenshotType?: "agent_step" | "stream_sample" | "all";
  includeData?: boolean;
  pollMs?: number;
}

export interface UseSessionScreenshotsResult {
  screenshots: SessionScreenshot[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useSessionScreenshots(
  opts: UseSessionScreenshotsOpts,
): UseSessionScreenshotsResult {
  const {
    sessionId,
    lastN = 10,
    screenshotType = "agent_step",
    includeData = true,
    pollMs = 0,
  } = opts;
  const [screenshots, setScreenshots] = useState<SessionScreenshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const getToken = useGsdToken();

  const load = useCallback(async () => {
    if (!sessionId) {
      setScreenshots([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const data = await fetchSessionScreenshots(
        sessionId,
        { lastN, screenshotType, includeData },
        token ?? undefined,
      );
      setScreenshots(data.screenshots ?? []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load session screenshots",
      );
    } finally {
      setLoading(false);
    }
  }, [sessionId, lastN, screenshotType, includeData, getToken]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!pollMs || pollMs <= 0) return;
    const handle = setInterval(load, pollMs);
    return () => clearInterval(handle);
  }, [pollMs, load]);

  return { screenshots, loading, error, refresh: load };
}

