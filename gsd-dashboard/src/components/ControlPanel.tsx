import type { ControlStateEvent } from "../lib/types";

interface ControlPanelProps {
  sessionId: string;
  controlState: ControlStateEvent | null;
  onTakeControl: () => void;
  onReleaseControl: () => void;
  onPause: () => void;
  onResume: () => void;
}

export function ControlPanel({
  controlState,
  onTakeControl,
  onReleaseControl,
  onPause,
  onResume,
}: ControlPanelProps) {
  const hasControl = controlState?.holder_sid != null;
  const isPaused = controlState?.paused ?? false;

  return (
    <div className="flex items-center gap-2">
      {/* Control toggle */}
      {hasControl ? (
        <button
          onClick={onReleaseControl}
          className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
        >
          Release Control
        </button>
      ) : (
        <button
          onClick={onTakeControl}
          className="rounded-md bg-gsd-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-gsd-700"
        >
          Take Control
        </button>
      )}

      {/* Pause/Resume */}
      {isPaused ? (
        <button
          onClick={onResume}
          className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
        >
          Resume Agent
        </button>
      ) : (
        <button
          onClick={onPause}
          className="rounded-md bg-yellow-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-yellow-700"
        >
          Pause Agent
        </button>
      )}

      {/* Status pills */}
      {hasControl && (
        <span className="rounded-full bg-gsd-100 px-2 py-0.5 text-xs font-medium text-gsd-800">
          Controlling
        </span>
      )}
      {isPaused && (
        <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
          Paused
        </span>
      )}
    </div>
  );
}
