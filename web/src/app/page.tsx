import Link from "next/link";

import CallTable from "@/components/CallTable";
import RefreshOnReturn from "@/components/RefreshOnReturn";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchCallRecordsPage } from "@/lib/calls";
import { formatDateTime, formatDuration } from "@/lib/format";

export const dynamic = "force-dynamic";

type HomePageProps = {
  searchParams?: Promise<{ page?: string; q?: string }>;
};

const PAGE_SIZE = 25;

export default async function HomePage({ searchParams }: HomePageProps) {
  const resolvedParams = searchParams ? await searchParams : {};
  const pageRaw = resolvedParams?.page ?? "1";
  const query = (resolvedParams?.q ?? "").trim();
  const pageNumber = Number(pageRaw);
  const currentPage = Number.isFinite(pageNumber) && pageNumber > 0 ? Math.floor(pageNumber) : 1;
  const offset = (currentPage - 1) * PAGE_SIZE;
  const { records: callRecords, hasMore, totalCount } = await fetchCallRecordsPage({
    limit: PAGE_SIZE,
    offset,
    q: query,
  });
  const totalDuration = callRecords.reduce((total, call) => total + call.durationSec, 0);
  const latestCall = callRecords[0];
  const prevPage = currentPage > 1 ? currentPage - 1 : null;
  const nextPage = hasMore ? currentPage + 1 : null;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const pageHref = (page: number) => {
    const params = new URLSearchParams();
    if (page > 1) {
      params.set("page", String(page));
    }
    if (query) {
      params.set("q", query);
    }
    const encoded = params.toString();
    return encoded ? `/?${encoded}` : "/";
  };

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
                <span className="text-muted-foreground">Calls loaded</span>
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
        <form className="flex flex-wrap items-center gap-2" method="get">
          <input
            className="h-9 w-full max-w-lg rounded-md border border-input bg-background px-3 text-sm"
            defaultValue={query}
            name="q"
            placeholder="Search transcript, external number, or implied name"
            type="search"
          />
          <Button type="submit" size="sm">Search</Button>
          {query ? (
            <Button asChild type="button" size="sm" variant="outline">
              <Link href="/">Clear</Link>
            </Button>
          ) : null}
        </form>
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

        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Page {currentPage} of {totalPages}
          </span>
          <div className="flex items-center gap-2">
            {prevPage ? (
              <Button asChild size="sm" variant="outline">
                <Link href={pageHref(prevPage)}>Previous</Link>
              </Button>
            ) : (
              <Button size="sm" variant="outline" disabled>
                Previous
              </Button>
            )}
            {nextPage ? (
              <Button asChild size="sm" variant="outline">
                <Link href={pageHref(nextPage)}>Next</Link>
              </Button>
            ) : (
              <Button size="sm" variant="outline" disabled>
                Next
              </Button>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
