"use client";

import Link from "next/link";
import { Fragment, useMemo, useState } from "react";

import LoudnessBar from "@/components/LoudnessBar";
import Tag from "@/components/Tag";
import Transcript from "@/components/Transcript";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime, formatDuration } from "@/lib/format";
import type { CallRecord } from "@/lib/sample-data";
import { getTagTone } from "@/lib/tag-tone";

type SortDirection = "asc" | "desc";

type CallTableProps = {
  calls: CallRecord[];
};

export default function CallTable({ calls }: CallTableProps) {
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const sortedCalls = useMemo(() => {
    return [...calls].sort((a, b) => {
      const diff = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
      return sortDirection === "asc" ? diff : -diff;
    });
  }, [calls, sortDirection]);

  const toggleSort = () => {
    setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
  };

  const toggleExpanded = (id: string) => {
    setExpandedId((current) => (current === id ? null : id));
  };

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[38%]">Summary</TableHead>
            <TableHead>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="-ml-3 h-8 text-muted-foreground hover:text-foreground"
                onClick={toggleSort}
              >
                Call time
                <span className="ml-2 text-xs uppercase">{sortDirection}</span>
              </Button>
            </TableHead>
            <TableHead>Duration</TableHead>
            <TableHead>Tags</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedCalls.map((call) => (
            <Fragment key={call.id}>
              <TableRow
                className="cursor-pointer"
                onClick={() => toggleExpanded(call.id)}
                data-state={expandedId === call.id ? "selected" : undefined}
              >
                <TableCell className="py-2">
                  <div className="flex flex-col gap-1">
                    <Link
                      className="font-medium text-foreground hover:underline"
                      href={`/calls/${call.id}`}
                      onClick={(event) => event.stopPropagation()}
                    >
                      {call.summary}
                    </Link>
                    <span className="text-xs text-muted-foreground">{call.externalNumber ?? "-"}</span>
                  </div>
                </TableCell>
                <TableCell className="py-2 text-sm text-muted-foreground">
                  {formatDateTime(call.createdAt)}
                </TableCell>
                <TableCell className="py-2 text-sm text-muted-foreground">
                  {formatDuration(call.durationSec)}
                </TableCell>
                <TableCell className="py-2">
                  <div className="flex flex-wrap gap-2">
                    {call.tags.map((tag) => (
                      <Tag key={tag} label={tag} tone={getTagTone(tag)} />
                    ))}
                  </div>
                </TableCell>
                <TableCell className="py-2">
                  <Tag
                    label={call.outcome?.status ?? "Unknown"}
                    tone={call.outcome?.status === "lost" ? "warn" : call.outcome?.status === "potential" ? "accent" : undefined}
                  />
                </TableCell>
              </TableRow>
              {expandedId === call.id && (
                <TableRow>
                  <TableCell colSpan={5} className="bg-muted/40 py-4">
                    <div className="space-y-4">
                      <LoudnessBar
                        durationSec={call.audio.durationSec}
                        progress={call.audio.previewProgress}
                        label="Audio scrub"
                      />
                      <Transcript segments={call.transcript} />
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
