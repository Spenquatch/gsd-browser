import { useParams } from "react-router-dom";
import { SessionViewer } from "../components/SessionViewer";
import { ControlPanel } from "../components/ControlPanel";
import { Hud } from "../components/Hud";
import { useStreamSocket } from "../hooks/useStreamSocket";
import { useControlSocket } from "../hooks/useControlSocket";
import { useSession } from "../hooks/useSession";
import { useSessionScreenshots } from "../hooks/useSessionScreenshots";

export function LiveSessionPage() {
  const { id: sessionId } = useParams<{ id: string }>();

  const { session, loading, error } = useSession(sessionId ?? "");
  const streamUrl = session?.stream_url ?? undefined;

  const stream = useStreamSocket({ sessionId: sessionId ?? "", streamUrl });
  const control = useControlSocket({ sessionId: sessionId ?? "", streamUrl });
  const screenshots = useSessionScreenshots({
    sessionId: sessionId ?? "",
    lastN: 12,
    screenshotType: "agent_step",
    includeData: true,
    pollMs: session?.status === "active" ? 5000 : 0,
  });

  if (!sessionId) {
    return (
      <div className="flex h-full items-center justify-center text-gray-500">
        No session ID provided.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-gray-500">
        Loading session...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center text-red-500">
        {error}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-2">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-medium text-gray-700">
            Session{" "}
            <span className="font-mono text-gray-900">
              {sessionId.slice(0, 12)}
            </span>
          </h2>
          <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
            {session?.status ?? "unknown"}
          </span>
          <ConnectionBadge connected={stream.connected} />
        </div>
        <ControlPanel
          sessionId={sessionId}
          controlState={control.controlState}
          onTakeControl={control.takeControl}
          onReleaseControl={control.releaseControl}
          onPause={control.pause}
          onResume={control.resume}
        />
      </div>

      {/* Session viewer */}
      <div className="relative flex-1">
        {streamUrl ? (
          <>
            <SessionViewer
              sessionId={sessionId}
              frame={stream.frame}
              connected={stream.connected}
              controlActive={control.controlState?.holder_sid != null}
              onInput={control.sendInput}
            />
            <Hud stats={stream.stats} />
          </>
        ) : (
          <div className="flex h-full items-center justify-center bg-gray-900 text-gray-400">
            Live stream unavailable (no stream URL configured for this session).
          </div>
        )}
      </div>

      {/* Artifacts */}
      <div className="border-t border-gray-200 bg-white px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-900">Screenshots</h3>
          <button
            onClick={screenshots.refresh}
            className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
          >
            Refresh
          </button>
        </div>

        {screenshots.loading && (
          <div className="text-xs text-gray-500">Loading screenshots...</div>
        )}
        {screenshots.error && (
          <div className="text-xs text-red-600">{screenshots.error}</div>
        )}

        {!screenshots.loading && !screenshots.error && screenshots.screenshots.length === 0 && (
          <div className="text-xs text-gray-500">No screenshots captured yet.</div>
        )}

        {screenshots.screenshots.length > 0 && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {screenshots.screenshots.map((shot) => {
              const src =
                shot.data_base64 && shot.mime_type
                  ? `data:${shot.mime_type};base64,${shot.data_base64}`
                  : null;
              return (
                <a
                  key={shot.artifact_id}
                  href={src ?? undefined}
                  target="_blank"
                  rel="noreferrer"
                  className="group block overflow-hidden rounded border border-gray-200 bg-gray-50"
                  title={`${new Date(shot.timestamp * 1000).toLocaleString()} • step=${shot.step ?? "—"}`}
                >
                  {src ? (
                    <img
                      src={src}
                      alt={`Screenshot ${shot.artifact_id}`}
                      className="h-24 w-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex h-24 items-center justify-center text-xs text-gray-500">
                      No data
                    </div>
                  )}
                  <div className="flex items-center justify-between px-2 py-1 text-[10px] text-gray-600">
                    <span className="font-mono">{shot.step ?? "—"}</span>
                    <span className={shot.has_error ? "text-red-600" : ""}>
                      {shot.has_error ? "error" : ""}
                    </span>
                  </div>
                </a>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function ConnectionBadge({ connected }: { connected: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
        connected
          ? "bg-green-100 text-green-800"
          : "bg-red-100 text-red-800"
      }`}
    >
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${
          connected ? "bg-green-500" : "bg-red-500"
        }`}
      />
      {connected ? "Connected" : "Disconnected"}
    </span>
  );
}
