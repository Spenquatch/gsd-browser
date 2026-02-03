import { useCallback } from "react";
import { Link } from "react-router-dom";
import { useSessions } from "../hooks/useSessions";
import { terminateSession } from "../lib/api";
import { useGsdToken } from "../lib/auth";

export function SessionsPage() {
  const { sessions, loading, error, refresh } = useSessions();
  const getToken = useGsdToken();

  const handleTerminate = useCallback(
    async (sessionId: string) => {
      try {
        const token = await getToken();
        await terminateSession(sessionId, token ?? undefined);
        refresh();
      } catch (err) {
        console.error("Failed to terminate session:", err);
      }
    },
    [getToken, refresh],
  );

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Sessions</h1>

      {loading && (
        <div className="text-sm text-gray-500">Loading sessions...</div>
      )}

      {error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !error && sessions.length === 0 && (
        <div className="text-sm text-gray-500">
          No sessions yet. Start a browser automation task to see sessions here.
        </div>
      )}

      {sessions.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                  Session
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                  Created
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {sessions.map((session) => (
                <tr key={session.session_id}>
                  <td className="whitespace-nowrap px-4 py-3 text-sm font-mono text-gray-900">
                    {session.session_id.slice(0, 12)}...
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <StatusBadge status={session.status} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                    {new Date(session.created_at * 1000).toLocaleString()}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-sm">
                    <div className="flex items-center gap-3">
                      {(session.status === "active" || session.status === "paused") && (
                        <Link
                          to={`/sessions/${session.session_id}`}
                          className="font-medium text-gsd-600 hover:text-gsd-800"
                        >
                          View Live
                        </Link>
                      )}
                      {session.status !== "terminated" && (
                        <button
                          onClick={() => handleTerminate(session.session_id)}
                          className="font-medium text-red-600 hover:text-red-800"
                        >
                          Terminate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "bg-green-100 text-green-800",
    paused: "bg-yellow-100 text-yellow-800",
    terminated: "bg-gray-100 text-gray-800",
    create: "bg-blue-100 text-blue-800",
  };

  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] ?? "bg-gray-100 text-gray-800"}`}
    >
      {status}
    </span>
  );
}
