import { SessionViewer } from "../components/SessionViewer";
import { ControlPanel } from "../components/ControlPanel";
import { Hud } from "../components/Hud";
import { useStreamSocket } from "../hooks/useStreamSocket";
import { useControlSocket } from "../hooks/useControlSocket";

interface GsdSessionViewerProps {
  /** JWT token for authentication (required) */
  token: string;
  /** Session ID to view (required) */
  sessionId: string;
  /** WebSocket URL for the streaming server (required) */
  streamUrl: string;
  /** Callback when session ends */
  onSessionEnd?: () => void;
}

/**
 * Standalone embeddable component for viewing a GSD browser session.
 * Does not depend on Clerk — accepts a raw JWT token.
 */
export function GsdSessionViewer({
  token,
  sessionId,
  streamUrl,
}: GsdSessionViewerProps) {
  const stream = useStreamSocket({ sessionId, streamUrl, token });
  const control = useControlSocket({ sessionId, streamUrl, token });
  const holderSid = control.controlState?.holder_sid ?? null;
  const isHeld = holderSid != null;
  const isHeldByMe = Boolean(holderSid && control.socketId && holderSid === control.socketId);
  const isPaused = control.controlState?.paused ?? false;

  return (
    <div className="flex h-full flex-col bg-gray-900">
      {/* Toolbar */}
      <div className="flex items-center justify-between bg-gray-800 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-300">
            Session {sessionId.slice(0, 12)}
          </span>
          <span
            className={`inline-flex h-2 w-2 rounded-full ${
              stream.connected ? "bg-green-500" : "bg-red-500"
            }`}
          />
        </div>
        <ControlPanel
          sessionId={sessionId}
          controlState={control.controlState}
          isHeld={isHeld}
          isHeldByMe={isHeldByMe}
          lastError={control.lastError}
          onTakeControl={control.takeControl}
          onReleaseControl={control.releaseControl}
          onPause={control.pause}
          onResume={control.resume}
        />
      </div>

      {/* Viewer */}
      <div className="relative flex-1">
        <SessionViewer
          sessionId={sessionId}
          frame={stream.frame}
          connected={stream.connected}
          controlActive={isHeldByMe && isPaused}
          onInput={control.sendInput}
        />
        <Hud stats={stream.stats} />
      </div>
    </div>
  );
}
