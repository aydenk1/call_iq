"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { markCallsForRefresh } from "@/components/RefreshOnReturn";
import { updateCallStatus } from "@/lib/calls";
import {
  PIPELINE_STATUS_ORDER,
  formatPipelineStatus,
  normalizePipelineStatus,
} from "@/lib/pipeline-status";

type PipelineStatusCardProps = {
  callId: string;
  status: string;
};

export default function PipelineStatusCard({ callId, status }: PipelineStatusCardProps) {
  const normalizedStatus = normalizePipelineStatus(status);
  const initialSelection = normalizedStatus === "UNKNOWN" ? PIPELINE_STATUS_ORDER[0] : normalizedStatus;
  const [currentStatus, setCurrentStatus] = useState(normalizedStatus);
  const [selectedStatus, setSelectedStatus] = useState(initialSelection);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpdate = async () => {
    if (selectedStatus === currentStatus) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const updated = await updateCallStatus(callId, selectedStatus);
      const updatedStatus = normalizePipelineStatus(updated.status);
      setCurrentStatus(updatedStatus);
      setSelectedStatus(updatedStatus);
      markCallsForRefresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update status.";
      setError(message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pipeline status</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Current</span>
          <span className="font-semibold text-foreground">{formatPipelineStatus(currentStatus)}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-muted-foreground" htmlFor={`status-${callId}`}>
            Set status
          </label>
          <select
            id={`status-${callId}`}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm"
            value={selectedStatus}
            onChange={(event) => setSelectedStatus(event.target.value)}
          >
            {PIPELINE_STATUS_ORDER.map((value) => (
              <option key={value} value={value}>
                {formatPipelineStatus(value)}
              </option>
            ))}
          </select>
          <Button size="sm" onClick={handleUpdate} disabled={isSaving || selectedStatus === currentStatus}>
            {isSaving ? "Updating..." : "Apply"}
          </Button>
        </div>
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
        <p className="text-xs text-muted-foreground">
          Set to "Downloaded" to re-run transcription, or "Download queued" to re-run ingestion.
        </p>
      </CardContent>
    </Card>
  );
}
