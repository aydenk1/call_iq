"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import AudioScrub from "@/components/AudioScrub";
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
import type { CallRecord } from "@/lib/call-types";
import { getTagTone } from "@/lib/tag-tone";
import { updateCallStatus } from "@/lib/calls";
import {
  PIPELINE_STATUS_ORDER,
  formatPipelineStatus,
  getPipelineStatusTone,
  normalizePipelineStatus,
} from "@/lib/pipeline-status";

type SortDirection = "asc" | "desc";

type CallTableProps = {
  calls: CallRecord[];
};

type ExpandedCallDetailsProps = {
  call: CallRecord;
};

function ExpandedCallDetails({ call }: ExpandedCallDetailsProps) {
  const [currentTimeSec, setCurrentTimeSec] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [seekToSec, setSeekToSec] = useState<number | null>(null);
  const linkedCallCount = call.contactProfile?.previousCallIds.length ?? 0;

  const handleTimeUpdate = useCallback((nextTime: number) => {
    setCurrentTimeSec(nextTime);
  }, []);

  const handlePlayState = useCallback((nextPlaying: boolean) => {
    setIsPlaying(nextPlaying);
  }, []);

  const handleSeek = useCallback((startSec: number) => {
    setSeekToSec(startSec);
    setCurrentTimeSec(startSec);
  }, []);

  return (
    <div className="space-y-4">
      <AudioScrub
        src={call.audio.url}
        durationSec={call.audio.durationSec}
        onTimeUpdate={handleTimeUpdate}
        onPlayStateChange={handlePlayState}
        seekToSec={seekToSec}
        onSeekApplied={() => setSeekToSec(null)}
      />
      <Transcript
        segments={call.transcript}
        minRows={linkedCallCount}
        currentTimeSec={currentTimeSec}
        autoScroll={isPlaying}
        scrollBehavior={isPlaying ? "smooth" : "auto"}
        onSeek={handleSeek}
      />
    </div>
  );
}

export default function CallTable({ calls }: CallTableProps) {
  const [callRows, setCallRows] = useState<CallRecord[]>(calls);
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingStatusId, setEditingStatusId] = useState<string | null>(null);
  const [statusUpdating, setStatusUpdating] = useState<Record<string, boolean>>({});
  const [statusError, setStatusError] = useState<Record<string, string | null>>({});

  useEffect(() => {
    setCallRows(calls);
    setEditingStatusId(null);
  }, [calls]);

  const sortedCalls = useMemo(() => {
    return [...callRows].sort((a, b) => {
      const diff = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
      return sortDirection === "asc" ? diff : -diff;
    });
  }, [callRows, sortDirection]);

  const toggleSort = () => {
    setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
  };

  const toggleExpanded = (id: string) => {
    setExpandedId((current) => (current === id ? null : id));
  };

  const handleStatusChange = async (callId: string, nextStatus: string) => {
    if (!nextStatus) {
      return;
    }
    const previousStatus = callRows.find((call) => call.id === callId)?.status;
    setCallRows((prev) =>
      prev.map((call) => (call.id === callId ? { ...call, status: nextStatus } : call)),
    );
    setStatusUpdating((prev) => ({ ...prev, [callId]: true }));
    setStatusError((prev) => ({ ...prev, [callId]: null }));
    try {
      const updated = await updateCallStatus(callId, nextStatus);
      const normalized = normalizePipelineStatus(updated.status);
      setCallRows((prev) =>
        prev.map((call) => (call.id === callId ? { ...call, status: normalized } : call)),
      );
      setEditingStatusId(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update status.";
      setCallRows((prev) =>
        prev.map((call) =>
          call.id === callId ? { ...call, status: previousStatus ?? call.status } : call,
        ),
      );
      setStatusError((prev) => ({ ...prev, [callId]: message }));
    } finally {
      setStatusUpdating((prev) => ({ ...prev, [callId]: false }));
    }
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
            <TableHead>Pipeline</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedCalls.map((call) => {
            const normalizedStatus = normalizePipelineStatus(call.status);
            return (
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
                    <div
                      className="flex flex-wrap items-center gap-2"
                      onClick={(event) => event.stopPropagation()}
                    >
                      {editingStatusId === call.id ? (
                        <select
                          className="h-8 rounded-md border border-input bg-background px-2 text-xs shadow-sm"
                          value={normalizedStatus === "UNKNOWN" ? "" : normalizedStatus}
                          onChange={(event) => handleStatusChange(call.id, event.target.value)}
                          disabled={statusUpdating[call.id]}
                          onBlur={() => setEditingStatusId(null)}
                          autoFocus
                        >
                          <option value="" disabled>
                            Unknown
                          </option>
                          {PIPELINE_STATUS_ORDER.map((value) => (
                            <option key={value} value={value}>
                              {formatPipelineStatus(value)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <button
                          type="button"
                          className="rounded-full"
                          onClick={() => setEditingStatusId(call.id)}
                        >
                          <Tag
                            label={formatPipelineStatus(normalizedStatus)}
                            tone={getPipelineStatusTone(normalizedStatus)}
                          />
                        </button>
                      )}
                      {statusUpdating[call.id] ? (
                        <span className="text-xs text-muted-foreground">Updating...</span>
                      ) : null}
                      {statusError[call.id] ? (
                        <span className="text-xs text-destructive">{statusError[call.id]}</span>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
                {expandedId === call.id && (
                  <TableRow>
                    <TableCell colSpan={5} className="bg-muted/40 py-4">
                      <ExpandedCallDetails call={call} />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
