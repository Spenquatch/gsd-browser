import type { ControlStateEvent } from "../lib/types";

interface ControlPanelProps {
  sessionId: string;
  controlState: ControlStateEvent | null;
  isHeldByMe: boolean;
  isHeld: boolean;
  lastError?: string | null;
  onTakeControl: () => void;
  onReleaseControl: () => void;
  onPause: () => void;
  onResume: () => void;
}

export function ControlPanel({
  controlState,
  isHeldByMe,
  isHeld,
  lastError,
  onTakeControl,
  onReleaseControl,
  onPause,
  onResume,
}: ControlPanelProps) {
  const isPaused = controlState?.paused ?? false;
  const holderSid = controlState?.holder_sid ?? null;

  return (
    <div className="flex items-center gap-2">
      {/* Control toggle */}
      {isHeldByMe ? (
        <button
          onClick={onReleaseControl}
          className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
        >
          Release Control
        </button>
      ) : (
        <button
          onClick={onTakeControl}
          disabled={isHeld}
          className="rounded-md bg-gsd-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-gsd-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Take Control
        </button>
      )}

      {/* Pause/Resume */}
      {isPaused ? (
        <button
          onClick={onResume}
          disabled={!isHeldByMe}
          className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Resume Agent
        </button>
      ) : (
        <button
          onClick={onPause}
          disabled={!isHeldByMe}
          className="rounded-md bg-yellow-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-yellow-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Pause Agent
        </button>
      )}

      {/* Status pills */}
      {isHeldByMe && (
        <span className="rounded-full bg-gsd-100 px-2 py-0.5 text-xs font-medium text-gsd-800">
          Controlling
        </span>
      )}
      {!isHeldByMe && holderSid && (
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-800">
          Held
        </span>
      )}
      {isPaused && (
        <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
          Paused
        </span>
      )}
      {lastError && (
        <span className="max-w-[22rem] truncate text-xs text-red-600" title={lastError}>
          {lastError}
        </span>
      )}
    </div>
  );
}
