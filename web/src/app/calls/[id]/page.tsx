import Link from "next/link";
import { notFound } from "next/navigation";

import AudioScrub from "@/components/AudioScrub";
import Tag from "@/components/Tag";
import Transcript from "@/components/Transcript";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { formatDateTime, formatDuration } from "@/lib/format";
import { callRecords } from "@/lib/sample-data";
import { getTagTone } from "@/lib/tag-tone";

type CallDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default async function CallDetailPage({ params }: CallDetailPageProps) {
  const { id } = await params;
  const callId = decodeURIComponent(id);
  const call = callRecords.find((entry) => entry.id === callId);

  if (!call) {
    notFound();
  }

  const relatedCalls = call.contactProfile?.previousCallIds
    .map((id) => callRecords.find((entry) => entry.id === id))
    .filter((entry): entry is (typeof callRecords)[number] => Boolean(entry));

  return (
    <main className="container space-y-8 py-10">
      <div className="flex items-center justify-between gap-4">
        <Button asChild variant="outline" size="sm">
          <Link href="/">Back to calls</Link>
        </Button>
        <span className="text-xs uppercase tracking-[0.28em] text-muted-foreground">Call detail</span>
      </div>

      <Card>
        <CardHeader className="space-y-3">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">Summary</p>
            <h1 className="text-3xl sm:text-4xl">{call.summary}</h1>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span>{formatDateTime(call.createdAt)}</span>
            <span>{formatDuration(call.durationSec)}</span>
            {call.impliedName && <span>Implied name: {call.impliedName}</span>}
            {call.externalNumber && <span>{call.externalNumber}</span>}
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {call.tags.map((tag) => (
              <Tag key={tag} label={tag} tone={getTagTone(tag)} />
            ))}
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-8 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Audio scrub and transcript</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <AudioScrub src={call.audio.url} durationSec={call.audio.durationSec} />
              <Transcript segments={call.transcript} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Call notes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <p className="text-muted-foreground">
                Capture follow-up tasks, objections, and anything the model should learn next time.
              </p>
              <div className="space-y-3">
                <label className="flex items-center gap-3">
                  <Checkbox defaultChecked />
                  <span>Send onboarding checklist</span>
                </label>
                <label className="flex items-center gap-3">
                  <Checkbox />
                  <span>Schedule live demo</span>
                </label>
                <label className="flex items-center gap-3">
                  <Checkbox />
                  <span>Update CRM with decision date</span>
                </label>
              </div>
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Suggested follow-ups</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm">
                {call.suggestedTasks.map((task) => (
                  <li key={task}>{task}</li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Outcome context</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Status</span>
                <span className="font-semibold text-foreground">{call.outcome?.status ?? "Unknown"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Amount</span>
                <span className="font-semibold text-foreground">{call.outcome?.amount ?? "-"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Lost reason</span>
                <span className="font-semibold text-foreground">{call.outcome?.reason ?? "-"}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Contact profile</CardTitle>
            </CardHeader>
            <CardContent>
              {call.contactProfile ? (
                <div className="space-y-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Contact</span>
                    <span className="font-semibold text-foreground">{call.contactProfile.name}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Phone</span>
                    <span className="font-semibold text-foreground">{call.contactProfile.phone}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Status</span>
                    <span className="font-semibold text-foreground">{call.contactProfile.status}</span>
                  </div>
                  <div className="border-t pt-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Notes</p>
                    <ul className="mt-3 space-y-2">
                      {call.contactProfile.notes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Assign a contact to link past and future calls.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Linked calls</CardTitle>
            </CardHeader>
            <CardContent>
              {relatedCalls && relatedCalls.length > 0 ? (
                <ul className="space-y-2 text-sm">
                  {relatedCalls.map((related) => (
                    <li key={related.id}>
                      <Link className="text-foreground underline decoration-dotted" href={`/calls/${related.id}`}>
                        {related.summary}
                      </Link>
                      <div className="text-xs text-muted-foreground">
                        {formatDateTime(related.createdAt)}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No linked calls yet. Attach one to build a full customer view.</p>
              )}
            </CardContent>
          </Card>
        </aside>
      </section>
    </main>
  );
}

export function generateStaticParams() {
  return callRecords.map((call) => ({ id: call.id }));
}
