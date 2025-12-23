import Link from "next/link";

import LoudnessBar from "@/components/LoudnessBar";
import Tag from "@/components/Tag";
import Transcript from "@/components/Transcript";
import { formatDateTime, formatDuration } from "@/lib/format";
import type { CallRecord } from "@/lib/sample-data";
import { getTagTone } from "@/lib/tag-tone";

type CallCardProps = {
  call: CallRecord;
  defaultOpen?: boolean;
};

export default function CallCard({ call, defaultOpen = false }: CallCardProps) {
  return (
    <details className="call-card group" open={defaultOpen}>
      <summary className="call-summary">
        <div>
          <p className="section-title">Call summary</p>
          <h3>{call.summary}</h3>
          <div className="call-meta">
            <span>{formatDateTime(call.createdAt)}</span>
            <span>{formatDuration(call.durationSec)}</span>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {call.tags.map((tag) => (
              <Tag key={tag} label={tag} tone={getTagTone(tag)} />
            ))}
          </div>
        </div>
        <div className="call-actions">
          <span className="call-open-indicator" aria-hidden="true">
            >
          </span>
          <Link className="info-button" href={`/calls/${call.id}`} aria-label="Open call details">
            I
          </Link>
        </div>
      </summary>
      <div className="call-body">
        <div className="flex flex-wrap gap-2">
          {call.impliedName && <Tag label={`Implied name: ${call.impliedName}`} />}
          {call.externalNumber && <Tag label={`External: ${call.externalNumber}`} />}
          {call.outcome?.reason && <Tag label={`Lost reason: ${call.outcome.reason}`} tone="warn" />}
        </div>
        <LoudnessBar durationSec={call.audio.durationSec} progress={call.audio.previewProgress} />
        <Transcript segments={call.transcript} />
      </div>
    </details>
  );
}
