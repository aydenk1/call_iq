import { formatTimestamp } from "@/lib/format";
import type { TranscriptSegment } from "@/lib/sample-data";

type TranscriptProps = {
  segments: TranscriptSegment[];
};

export default function Transcript({ segments }: TranscriptProps) {
  return (
    <div className="space-y-3">
      {segments.map((segment) => (
        <div
          className="grid gap-3 rounded-lg border bg-muted/40 px-4 py-3 text-sm"
          key={`${segment.speaker}-${segment.startSec}`}
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
    </div>
  );
}
