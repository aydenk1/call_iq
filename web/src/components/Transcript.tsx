import { formatTimestamp } from "@/lib/format";
import type { TranscriptSegment } from "@/lib/call-types";

type TranscriptProps = {
  segments: TranscriptSegment[];
  minRows?: number;
};

export default function Transcript({ segments, minRows }: TranscriptProps) {
  const safeMinRows = Number.isFinite(minRows) ? Math.max(0, Number(minRows)) : 0;
  const fillerCount = Math.max(0, safeMinRows - segments.length);
  return (
    <div className="space-y-3">
      {segments.map((segment, index) => (
        <div
          className="grid gap-3 rounded-lg border bg-muted/40 px-4 py-3 text-sm"
          key={`${segment.speaker}-${segment.startSec}-${segment.endSec}-${index}`}
          style={{ gridTemplateColumns: "80px 1fr" }}
        >
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
              {segment.speaker}
            </div>
            <div className="text-xs text-muted-foreground">
              {formatTimestamp(segment.startSec)} - {formatTimestamp(segment.endSec)}
            </div>
          </div>
          <p className="leading-relaxed text-foreground">{segment.text}</p>
        </div>
      ))}
      {Array.from({ length: fillerCount }).map((_, index) => (
        <div
          className="grid gap-3 rounded-lg border border-dashed bg-muted/20 px-4 py-3 text-sm text-muted-foreground/70"
          key={`transcript-filler-${index}`}
          style={{ gridTemplateColumns: "80px 1fr" }}
        >
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground/70">--</div>
            <div className="text-xs text-muted-foreground/70">--:-- - --:--</div>
          </div>
          <p className="leading-relaxed"> </p>
        </div>
      ))}
    </div>
  );
}
