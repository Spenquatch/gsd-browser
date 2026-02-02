import { useState } from "react";
import type { StreamStats } from "../lib/types";

interface HudProps {
  stats: StreamStats;
}

export function Hud({ stats }: HudProps) {
  const [visible, setVisible] = useState(false);

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setVisible((v) => !v)}
        className="absolute right-2 top-2 rounded bg-black/50 px-2 py-1 text-xs text-white/70 hover:text-white"
      >
        {visible ? "Hide HUD" : "HUD"}
      </button>

      {/* HUD overlay */}
      {visible && (
        <div className="absolute right-2 top-10 rounded bg-black/70 px-3 py-2 font-mono text-xs text-green-400">
          <div>FPS: {stats.fps}</div>
          <div>Latency: {stats.latencyMs.toFixed(0)}ms</div>
          <div>Seq: {stats.frameSeq}</div>
          <div>Frames: {stats.framesReceived}</div>
        </div>
      )}
    </>
  );
}
