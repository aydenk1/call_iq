import Link from "next/link";
import { notFound } from "next/navigation";

import LoudnessBar from "@/components/LoudnessBar";
import Tag from "@/components/Tag";
import Transcript from "@/components/Transcript";
import { formatDateTime, formatDuration } from "@/lib/format";
import { callRecords } from "@/lib/sample-data";
import { getTagTone } from "@/lib/tag-tone";

type CallDetailPageProps = {
  params: { id: string };
};

export default function CallDetailPage({ params }: CallDetailPageProps) {
  const call = callRecords.find((entry) => entry.id === params.id);

  if (!call) {
    notFound();
  }

  const relatedCalls = call.contactProfile?.previousCallIds
    .map((id) => callRecords.find((entry) => entry.id === id))
    .filter((entry): entry is (typeof callRecords)[number] => Boolean(entry));

  return (
    <main className="app-shell">
      <div className="flex items-center justify-between gap-4">
        <Link className="chip" href="/">
          Back to calls
        </Link>
        <span className="section-title">Call detail</span>
      </div>

      <header className="mt-6 panel p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="section-title">Summary</p>
            <h1 className="text-3xl sm:text-4xl">{call.summary}</h1>
            <div className="call-meta">
              <span>{formatDateTime(call.createdAt)}</span>
              <span>{formatDuration(call.durationSec)}</span>
              {call.impliedName && <span>Implied name: {call.impliedName}</span>}
              {call.externalNumber && <span>{call.externalNumber}</span>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {call.tags.map((tag) => (
              <Tag key={tag} label={tag} tone={getTagTone(tag)} />
            ))}
          </div>
        </div>
      </header>

      <section className="detail-grid mt-8">
        <div className="space-y-6">
          <div className="detail-card">
            <h3>Audio scrub and transcript</h3>
            <LoudnessBar durationSec={call.audio.durationSec} progress={call.audio.previewProgress} label="Loudness spectrum" />
            <Transcript segments={call.transcript} />
          </div>

          <div className="detail-card">
            <h3>Call notes</h3>
            <p className="mt-2 text-sm text-muted">
              Capture follow-up tasks, objections, and anything the model should learn next time.
            </p>
            <div className="list-divider grid gap-3 text-sm">
              <label className="flex items-center gap-3">
                <input type="checkbox" defaultChecked />
                Send onboarding checklist
              </label>
              <label className="flex items-center gap-3">
                <input type="checkbox" />
                Schedule live demo
              </label>
              <label className="flex items-center gap-3">
                <input type="checkbox" />
                Update CRM with decision date
              </label>
            </div>
          </div>
        </div>

        <aside className="space-y-6">
          <div className="detail-card">
            <h3>Suggested follow-ups</h3>
            <ul className="list-divider grid gap-2 text-sm">
              {call.suggestedTasks.map((task) => (
                <li key={task}>{task}</li>
              ))}
            </ul>
          </div>

          <div className="detail-card">
            <h3>Outcome context</h3>
            <div className="mt-3 grid gap-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted">Status</span>
                <span className="font-semibold text-ink">{call.outcome?.status ?? "Unknown"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted">Amount</span>
                <span className="font-semibold text-ink">{call.outcome?.amount ?? "-"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted">Lost reason</span>
                <span className="font-semibold text-ink">{call.outcome?.reason ?? "-"}</span>
              </div>
            </div>
          </div>

          <div className="detail-card">
            <h3>Contact profile</h3>
            {call.contactProfile ? (
              <div className="mt-3 grid gap-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted">Contact</span>
                  <span className="font-semibold text-ink">{call.contactProfile.name}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted">Phone</span>
                  <span className="font-semibold text-ink">{call.contactProfile.phone}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted">Status</span>
                  <span className="font-semibold text-ink">{call.contactProfile.status}</span>
                </div>
                <div className="list-divider">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted">Notes</p>
                  <ul className="mt-3 grid gap-2">
                    {call.contactProfile.notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <p className="mt-2 text-sm text-muted">Assign a contact to link past and future calls.</p>
            )}
          </div>

          <div className="detail-card">
            <h3>Linked calls</h3>
            {relatedCalls && relatedCalls.length > 0 ? (
              <ul className="list-divider grid gap-2 text-sm">
                {relatedCalls.map((related) => (
                  <li key={related.id}>
                    <Link className="text-ink underline decoration-dotted" href={`/calls/${related.id}`}>
                      {related.summary}
                    </Link>
                    <div className="text-xs text-muted">{formatDateTime(related.createdAt)}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-muted">No linked calls yet. Attach one to build a full customer view.</p>
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}
