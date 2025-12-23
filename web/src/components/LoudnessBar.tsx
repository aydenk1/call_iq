import type { CSSProperties } from "react";

import { formatDuration } from "@/lib/format";

type LoudnessBarProps = {
  durationSec: number;
  progress: number;
  label?: string;
};

export default function LoudnessBar({ durationSec, progress, label }: LoudnessBarProps) {
  const clamped = Math.min(1, Math.max(0, progress));
  const percent = Math.round(clamped * 100);
  const style = {
    "--playhead": `${percent}%`,
    "--progress": `${percent}%`,
  } as CSSProperties;

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-muted">
        <span>{label ?? "Audio spectrum"}</span>
        <span>{formatDuration(durationSec)}</span>
      </div>
      <div className="spectrum mt-3" style={style}>
        <div className="spectrum-progress" />
      </div>
      <input className="scrubber mt-3" type="range" min="0" max="100" defaultValue={percent} />
    </div>
  );
}
