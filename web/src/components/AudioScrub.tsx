"use client";

import { useCallback, useMemo, useRef, useState } from "react";

import { formatDuration } from "@/lib/format";

type AudioScrubProps = {
  src?: string;
  durationSec: number;
  label?: string;
};

export default function AudioScrub({ src, durationSec, label }: AudioScrubProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [currentSec, setCurrentSec] = useState(0);
  const [audioDuration, setAudioDuration] = useState(durationSec);
  const [isPlaying, setIsPlaying] = useState(false);

  const handleLoadedMetadata = useCallback(() => {
    if (audioRef.current?.duration) {
      setAudioDuration(audioRef.current.duration);
    }
  }, []);

  const handleTimeUpdate = useCallback(() => {
    if (audioRef.current) {
      setCurrentSec(audioRef.current.currentTime);
    }
  }, []);

  const handlePlayPause = useCallback(() => {
    if (!audioRef.current) {
      return;
    }
    if (audioRef.current.paused) {
      void audioRef.current.play();
    } else {
      audioRef.current.pause();
    }
  }, []);

  const handleSeek = useCallback(
    (value: number) => {
      if (!audioRef.current || audioDuration <= 0) {
        return;
      }
      const target = (value / 100) * audioDuration;
      audioRef.current.currentTime = target;
      setCurrentSec(target);
    },
    [audioDuration],
  );

  const percent = useMemo(() => {
    if (audioDuration <= 0) {
      return 0;
    }
    return Math.min(100, Math.max(0, (currentSec / audioDuration) * 100));
  }, [audioDuration, currentSec]);

  if (!src) {
    return (
      <div className="rounded-lg border border-dashed border-border/70 bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
        Audio unavailable.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-muted-foreground">
        <span>{label ?? "Audio scrub"}</span>
        <span>{formatDuration(audioDuration || durationSec)}</span>
      </div>
      <div className="flex items-center gap-3">
        <button
          className="h-9 rounded-md border px-3 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground transition hover:text-foreground"
          type="button"
          onClick={handlePlayPause}
        >
          {isPlaying ? "Pause" : "Play"}
        </button>
        <span className="text-xs text-muted-foreground">
          {formatDuration(currentSec)}
        </span>
      </div>
      <input
        className="w-full accent-primary"
        type="range"
        min="0"
        max="100"
        value={Math.round(percent)}
        onChange={(event) => handleSeek(Number(event.target.value))}
      />
      <audio
        ref={audioRef}
        className="sr-only"
        preload="metadata"
        src={src}
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={handleTimeUpdate}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
      >
        Your browser does not support the audio element.
      </audio>
    </div>
  );
}
