import CallTable from "@/components/CallTable";
import RefreshOnReturn from "@/components/RefreshOnReturn";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchCallRecords } from "@/lib/calls";
import { formatDateTime, formatDuration } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const callRecords = await fetchCallRecords();
  const totalDuration = callRecords.reduce((total, call) => total + call.durationSec, 0);
  const latestCall = callRecords[0];

  return (
    <main className="container space-y-10 py-10">
      <RefreshOnReturn />
      <header className="flex flex-col gap-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">Call intelligence</p>
            <h1 className="text-4xl sm:text-5xl">Conversation cockpit</h1>
            <p className="mt-4 text-base text-muted-foreground">
              Scan every call, spot revenue signals fast, and dive into the audio when something needs action.
            </p>
          </div>
          <Card className="w-full max-w-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">At a glance</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Calls tracked</span>
                <span className="text-base font-semibold text-foreground">{callRecords.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Total talk time</span>
                <span className="text-base font-semibold text-foreground">{formatDuration(totalDuration)}</span>
              </div>
              {latestCall && (
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Latest call</span>
                  <span className="text-sm font-semibold text-foreground">{formatDateTime(latestCall.createdAt)}</span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </header>

      <section className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" size="sm">
            All calls
          </Button>
          <Button type="button" size="sm" variant="secondary">
            Potential sale
          </Button>
          <Button type="button" size="sm" variant="secondary">
            Lost sale
          </Button>
          <Button type="button" size="sm" variant="secondary">
            Needs follow-up
          </Button>
        </div>

        <CallTable calls={callRecords} />
      </section>
    </main>
  );
}
