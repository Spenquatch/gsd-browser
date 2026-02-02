import { useParams } from "react-router-dom";
import { SessionViewer } from "../components/SessionViewer";
import { ControlPanel } from "../components/ControlPanel";
import { Hud } from "../components/Hud";
import { useStreamSocket } from "../hooks/useStreamSocket";
import { useControlSocket } from "../hooks/useControlSocket";

export function LiveSessionPage() {
  const { id: sessionId } = useParams<{ id: string }>();

  const stream = useStreamSocket({ sessionId: sessionId ?? "" });
  const control = useControlSocket({ sessionId: sessionId ?? "" });

  if (!sessionId) {
    return (
      <div className="flex h-full items-center justify-center text-gray-500">
        No session ID provided.
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
        <SessionViewer
          sessionId={sessionId}
          frame={stream.frame}
          connected={stream.connected}
          controlActive={control.controlState?.holder_sid != null}
          onInput={control.sendInput}
        />
        <Hud stats={stream.stats} />
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
