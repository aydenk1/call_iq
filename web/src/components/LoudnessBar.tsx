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
    <div className="space-y-3" style={style}>
      <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-muted-foreground">
        <span>{label ?? "Audio spectrum"}</span>
        <span>{formatDuration(durationSec)}</span>
      </div>
      <div className="relative h-10 overflow-hidden rounded-full border bg-muted/40">
        <div className="absolute inset-y-0 left-0 bg-primary/10" style={{ width: `var(--progress)` }} />
        <div
          className="absolute top-0 bottom-0 w-px bg-foreground/70"
          style={{ left: `var(--playhead)` }}
        />
      </div>
      <input className="w-full accent-primary" type="range" min="0" max="100" defaultValue={percent} />
    </div>
  );
}
