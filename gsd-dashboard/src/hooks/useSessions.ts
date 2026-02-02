import { useCallback, useEffect, useState } from "react";
import type { SessionInfo } from "../lib/types";
import { fetchSessions } from "../lib/api";
import { useGsdToken } from "../lib/auth";

export interface UseSessionsResult {
  sessions: SessionInfo[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useSessions(): UseSessionsResult {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const getToken = useGsdToken();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const data = await fetchSessions(token ?? undefined);
      setSessions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    load();
    // Poll every 10 seconds
    const interval = setInterval(load, 10_000);
    return () => clearInterval(interval);
  }, [load]);

  return { sessions, loading, error, refresh: load };
}
