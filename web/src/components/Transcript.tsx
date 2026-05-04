"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { formatTimestamp } from "@/lib/format";
import type { TranscriptSegment } from "@/lib/call-types";
import { cn } from "@/lib/utils";

type TranscriptProps = {
  segments: TranscriptSegment[];
  minRows?: number;
  currentTimeSec?: number;
  autoScroll?: boolean;
  scrollBehavior?: ScrollBehavior;
  height?: string;
  maxHeight?: string;
  onSeek?: (startSec: number) => void;
};

const CUSTOMER_TOKENS = ["customer"];
const AGENT_TOKENS = ["store"];

const getSpeakerAlign = (speaker: string) => {
  const normalized = speaker.toLowerCase();
  if (CUSTOMER_TOKENS.some((token) => normalized.includes(token))) {
    return "customer";
  }
  if (AGENT_TOKENS.some((token) => normalized.includes(token))) {
    return "agent";
  }
  return "agent";
};

const getActiveIndex = (segments: TranscriptSegment[], currentTimeSec?: number) => {
  if (!Number.isFinite(currentTimeSec)) {
    return -1;
  }
  const current = currentTimeSec ?? 0;
  if (segments.length === 0) {
    return -1;
  }
  let activeIndex = -1;
  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index];
    if (current >= segment.startSec) {
      activeIndex = index;
    } else {
      break;
    }
  }
  return activeIndex;
};

export default function Transcript({
  segments,
  minRows,
  currentTimeSec,
  autoScroll = true,
  scrollBehavior = "auto",
  height,
  maxHeight,
  onSeek,
}: TranscriptProps) {
  const safeMinRows = Number.isFinite(minRows) ? Math.max(0, Number(minRows)) : 0;
  const fillerCount = Math.max(0, safeMinRows - segments.length);
  const [rowMetrics, setRowMetrics] = useState<{ height: number; marginBottom: number } | null>(
    null,
  );
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const rowRefs = useRef<Array<HTMLDivElement | HTMLButtonElement | null>>([]);

  rowRefs.current = [];

  const activeIndex = useMemo(
    () => getActiveIndex(segments, currentTimeSec),
    [segments, currentTimeSec],
  );

  useEffect(() => {
    if (!safeMinRows) {
      return;
    }
    const rowEl = rowRefs.current.find(Boolean);
    if (!rowEl) {
      return;
    }
    const styles = window.getComputedStyle(rowEl);
    const marginBottom = Number.parseFloat(styles.marginBottom) || 0;
    setRowMetrics({
      height: rowEl.getBoundingClientRect().height,
      marginBottom,
    });
  }, [safeMinRows, segments.length, fillerCount]);

  useEffect(() => {
    if (!autoScroll || activeIndex < 0) {
      return;
    }
    const container = scrollContainerRef.current;
    const activeRow = rowRefs.current[activeIndex];
    if (!container || !activeRow) {
      return;
    }
    const rafId = window.requestAnimationFrame(() => {
      const containerRect = container.getBoundingClientRect();
      const rowRect = activeRow.getBoundingClientRect();
      const offsetTop = rowRect.top - containerRect.top;
      const targetScroll = Math.max(
        0,
        container.scrollTop + offsetTop - containerRect.height / 2 + rowRect.height / 2,
      );
      container.scrollTo({ top: targetScroll, behavior: scrollBehavior });
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [activeIndex, autoScroll, scrollBehavior]);

  const clampedHeight =
    !height && rowMetrics && safeMinRows
      ? rowMetrics.height * safeMinRows + rowMetrics.marginBottom * Math.max(0, safeMinRows - 1)
      : undefined;
  const maxHeightValue = clampedHeight
    ? maxHeight
      ? `min(${clampedHeight}px, ${maxHeight})`
      : `${clampedHeight}px`
    : maxHeight;
  const shouldClamp = Boolean(clampedHeight);
  const isClickable = Boolean(onSeek);

  return (
    <div
      className={cn("space-y-3", (height || shouldClamp || maxHeight) && "overflow-y-auto pr-2")}
      ref={scrollContainerRef}
      style={{
        ...(height ? { height } : {}),
        ...(maxHeightValue ? { maxHeight: maxHeightValue } : {}),
      }}
    >
      {segments.map((segment, index) => {
        const align = getSpeakerAlign(segment.speaker);
        const isActive = index === activeIndex;
        return (
          <div
            className={cn("flex", align === "customer" ? "justify-end text-right" : "justify-start text-left")}
            key={`${segment.speaker}-${segment.startSec}-${segment.endSec}-${index}`}
          >
            {isClickable ? (
              <button
                type="button"
                className={cn(
                  "grid gap-3 rounded-lg border px-4 py-3 text-sm transition-colors",
                  isActive ? "border-primary/50 bg-primary/10" : "bg-muted/40",
                  "cursor-pointer hover:border-primary/40 hover:bg-primary/5",
                )}
                ref={(el) => {
                  rowRefs.current[index] = el;
                }}
                style={{ gridTemplateColumns: align === "customer" ? "1fr 80px" : "80px 1fr" }}
                onClick={() => onSeek?.(segment.startSec)}
              >
                <div className={cn(align === "customer" && "order-2")}>
                  <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                    {segment.speaker}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {formatTimestamp(segment.startSec)} - {formatTimestamp(segment.endSec)}
                  </div>
                </div>
                <p className="leading-relaxed text-foreground">{segment.text}</p>
              </button>
            ) : (
              <div
                className={cn(
                  "grid gap-3 rounded-lg border px-4 py-3 text-sm transition-colors",
                  isActive ? "border-primary/50 bg-primary/10" : "bg-muted/40",
                )}
                ref={(el) => {
                  rowRefs.current[index] = el;
                }}
                style={{ gridTemplateColumns: align === "customer" ? "1fr 80px" : "80px 1fr" }}
              >
                <div className={cn(align === "customer" && "order-2")}>
                  <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                    {segment.speaker}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {formatTimestamp(segment.startSec)} - {formatTimestamp(segment.endSec)}
                  </div>
                </div>
                <p className="leading-relaxed text-foreground">{segment.text}</p>
              </div>
            )}
          </div>
        );
      })}
      {Array.from({ length: fillerCount }).map((_, index) => (
        <div
          className="flex justify-start text-left"
          key={`transcript-filler-${index}`}
          ref={(el) => {
            rowRefs.current[segments.length + index] = el;
          }}
        >
          <div
            className="grid gap-3 rounded-lg border border-dashed bg-muted/20 px-4 py-3 text-sm text-muted-foreground/70"
            style={{ gridTemplateColumns: "80px 1fr" }}
          >
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground/70">--</div>
              <div className="text-xs text-muted-foreground/70">--:-- - --:--</div>
            </div>
            <p className="leading-relaxed"> </p>
          </div>
        </div>
      ))}
    </div>
  );
}
