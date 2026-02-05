interface StatusBarProps {
  connected: boolean;
  controlActive: boolean;
  paused: boolean;
}

export function StatusBar({ connected, controlActive, paused }: StatusBarProps) {
  return (
    <div className="flex items-center gap-2">
      <Pill active={connected} label={connected ? "Connected" : "Disconnected"} />
      {controlActive && <Pill active label="Controlling" />}
      {paused && <Pill active={false} label="Paused" />}
    </div>
  );
}

function Pill({ active, label }: { active: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
        active ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"
      }`}
    >
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${
          active ? "bg-green-500" : "bg-gray-400"
        }`}
      />
      {label}
    </span>
  );
}
