import { useCallback, useEffect, useState } from "react";
import type { SessionInfo } from "../lib/types";
import { fetchSession } from "../lib/api";
import { useGsdToken } from "../lib/auth";

export interface UseSessionResult {
  session: SessionInfo | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useSession(sessionId: string): UseSessionResult {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const getToken = useGsdToken();

  const load = useCallback(async () => {
    if (!sessionId) {
      setLoading(false);
      return;
    }
    try {
      const token = await getToken();
      const data = await fetchSession(sessionId, token ?? undefined);
      setSession(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load session");
    } finally {
      setLoading(false);
    }
  }, [sessionId, getToken]);

  useEffect(() => {
    load();
  }, [load]);

  return { session, loading, error, refresh: load };
}
