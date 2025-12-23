import { formatTimestamp } from "@/lib/format";
import type { TranscriptSegment } from "@/lib/sample-data";

type TranscriptProps = {
  segments: TranscriptSegment[];
};

export default function Transcript({ segments }: TranscriptProps) {
  return (
    <div className="transcript">
      {segments.map((segment) => (
        <div className="transcript-row" key={`${segment.speaker}-${segment.startSec}`}>
          <div>
            <div className="speaker text-xs uppercase tracking-[0.2em] text-muted">
              {segment.speaker}
            </div>
            <div className="text-xs text-muted">
              {formatTimestamp(segment.startSec)} - {formatTimestamp(segment.endSec)}
            </div>
          </div>
          <p className="text-sm leading-relaxed text-ink">{segment.text}</p>
        </div>
      ))}
    </div>
  );
}
