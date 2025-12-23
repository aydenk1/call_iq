import CallCard from "@/components/CallCard";
import { formatDateTime, formatDuration } from "@/lib/format";
import { callRecords } from "@/lib/sample-data";

export default function HomePage() {
  const totalDuration = callRecords.reduce((total, call) => total + call.durationSec, 0);
  const latestCall = callRecords[0];

  return (
    <main className="app-shell">
      <header className="flex flex-col gap-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="section-title">Call intelligence</p>
            <h1 className="text-4xl sm:text-5xl">Conversation cockpit</h1>
            <p className="mt-4 text-base text-muted">
              Scan every call, spot revenue signals fast, and dive into the audio when something needs action.
            </p>
          </div>
          <div className="panel grid gap-3 p-5 text-sm">
            <div className="flex items-center justify-between gap-6">
              <span className="text-muted">Calls tracked</span>
              <span className="text-lg font-semibold text-ink">{callRecords.length}</span>
            </div>
            <div className="flex items-center justify-between gap-6">
              <span className="text-muted">Total talk time</span>
              <span className="text-lg font-semibold text-ink">{formatDuration(totalDuration)}</span>
            </div>
            {latestCall && (
              <div className="flex items-center justify-between gap-6">
                <span className="text-muted">Latest call</span>
                <span className="text-sm font-semibold text-ink">{formatDateTime(latestCall.createdAt)}</span>
              </div>
            )}
          </div>
        </div>
      </header>

      <section className="mt-10 space-y-6">
        <div className="flex flex-wrap items-center gap-2">
          <button className="chip chip-accent" type="button">
            All calls
          </button>
          <button className="chip" type="button">
            Potential sale
          </button>
          <button className="chip" type="button">
            Lost sale
          </button>
          <button className="chip" type="button">
            Needs follow-up
          </button>
        </div>

        <div className="space-y-4">
          {callRecords.map((call, index) => (
            <CallCard key={call.id} call={call} defaultOpen={index === 0} />
          ))}
        </div>
      </section>
    </main>
  );
}
