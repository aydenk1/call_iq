import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchCallerWithCalls } from "@/lib/calls";
import { formatDateTime, formatDuration } from "@/lib/format";

type CallerDetailPageProps = {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ returnTo?: string }>;
};

export const dynamic = "force-dynamic";

export default async function CallerDetailPage({ params, searchParams }: CallerDetailPageProps) {
  const { id } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const callerId = decodeURIComponent(id);
  const returnToRaw = resolvedSearchParams?.returnTo ?? "/";
  const returnTo = returnToRaw.startsWith("/") ? returnToRaw : "/";
  const payload = await fetchCallerWithCalls(callerId);

  if (!payload) {
    notFound();
  }

  const { caller, calls } = payload;

  return (
    <main className="container space-y-8 py-10">
      <div className="flex items-center justify-between gap-4">
        <Button asChild variant="outline" size="sm">
          <Link href={returnTo}>Back to calls</Link>
        </Button>
        <span className="text-xs uppercase tracking-[0.28em] text-muted-foreground">Caller profile</span>
      </div>

      <Card>
        <CardHeader className="space-y-3">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">Caller</p>
            <h1 className="text-3xl sm:text-4xl">{caller.impliedName || "Unknown caller"}</h1>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span>{caller.id}</span>
            <span>{calls.length} calls</span>
          </div>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Call history</CardTitle>
        </CardHeader>
        <CardContent>
          {calls.length ? (
            <ul className="space-y-3">
              {calls.map((call) => (
                <li key={call.id} className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
                  <div className="space-y-1">
                    <Link
                      className="font-medium text-foreground hover:underline"
                      href={`/calls/${call.id}?returnTo=${encodeURIComponent(returnTo)}`}
                    >
                      {call.summary}
                    </Link>
                    <div className="text-xs text-muted-foreground">{formatDateTime(call.createdAt)}</div>
                  </div>
                  <div className="text-xs text-muted-foreground">{formatDuration(call.durationSec)}</div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No calls found for this caller yet.</p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
