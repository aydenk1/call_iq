"use client";

import { useCallback, useMemo, useState } from "react";

import AudioScrub from "@/components/AudioScrub";
import Transcript from "@/components/Transcript";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { TranscriptRun, TranscriptSegment } from "@/lib/call-types";

type AudioTranscriptCardProps = {
  audioUrl?: string;
  audioDurationSec: number;
  transcripts: TranscriptRun[];
  fallbackSegments: TranscriptSegment[];
  minRows?: number;
};

const buildFallbackRun = (segments: TranscriptSegment[]): TranscriptRun => ({
  id: "run-1",
  label: "Run 1",
  segments,
  text: "",
});

export default function AudioTranscriptCard({
  audioUrl,
  audioDurationSec,
  transcripts,
  fallbackSegments,
  minRows,
}: AudioTranscriptCardProps) {
  const runs = useMemo(() => {
    if (transcripts.length > 0) {
      return transcripts;
    }
    if (fallbackSegments.length > 0) {
      return [buildFallbackRun(fallbackSegments)];
    }
    return [];
  }, [transcripts, fallbackSegments]);

  const [selectedId, setSelectedId] = useState<string>(() => {
    if (runs.length === 0) {
      return "run-1";
    }
    return runs[runs.length - 1].id;
  });
  const [currentTimeSec, setCurrentTimeSec] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [seekToSec, setSeekToSec] = useState<number | null>(null);

  const selectedRun = useMemo(() => {
    if (runs.length === 0) {
      return null;
    }
    return runs.find((run) => run.id === selectedId) ?? runs[runs.length - 1];
  }, [runs, selectedId]);

  const dropdownLabel = useMemo(() => {
    if (runs.length <= 1) {
      return "Latest";
    }
    const latestIndex = runs.length - 1;
    const latestLabel = runs[latestIndex]?.label ?? `Run ${runs.length}`;
    return `Latest (${latestLabel})`;
  }, [runs]);

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
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Audio scrub and transcript</CardTitle>
          <p className="mt-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
            {selectedRun ? `${selectedRun.label} selected` : "Transcript unavailable"}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Transcript run
          </span>
          <select
            className="h-9 rounded-md border border-input bg-background px-2 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground shadow-sm"
            value={selectedRun?.id ?? "run-1"}
            onChange={(event) => setSelectedId(event.target.value)}
            disabled={runs.length <= 1}
          >
            {runs.length === 0 ? (
              <option value="run-1">None</option>
            ) : (
              runs.map((run, index) => {
                const isLatest = index === runs.length - 1;
                const label = isLatest && runs.length > 1 ? dropdownLabel : run.label;
                return (
                  <option key={run.id} value={run.id}>
                    {label}
                  </option>
                );
              })
            )}
          </select>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <AudioScrub
          src={audioUrl}
          durationSec={audioDurationSec}
          onTimeUpdate={handleTimeUpdate}
          onPlayStateChange={handlePlayState}
          seekToSec={seekToSec}
          onSeekApplied={() => setSeekToSec(null)}
        />
        {selectedRun ? (
          <Transcript
            segments={selectedRun.segments}
            minRows={minRows}
            currentTimeSec={currentTimeSec}
            autoScroll={isPlaying}
            scrollBehavior={isPlaying ? "smooth" : "auto"}
            maxHeight="50vh"
            onSeek={handleSeek}
          />
        ) : (
          <div className="rounded-lg border border-dashed border-border/70 bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
            Transcript unavailable.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
