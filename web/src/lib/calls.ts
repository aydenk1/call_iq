import type { CallRecord, TranscriptSegment } from "@/lib/call-types";
import { normalizePipelineStatus } from "@/lib/pipeline-status";

type ApiTranscriptSegment = {
  speaker?: string;
  start?: number;
  end?: number;
  startSec?: number;
  endSec?: number;
  text?: string;
};

type ApiCallRecord = {
  id: string;
  createdAt: string;
  durationSec: number;
  summary?: string;
  status?: unknown;
  impliedName?: string | null;
  externalNumber?: string | null;
  tags?: string[] | null;
  outcome?: CallRecord["outcome"];
  rawWhisperTranscript?: unknown;
  transcriptText?: string | null;
  audio?: {
    durationSec?: number | null;
    previewProgress?: number | null;
    url?: string | null;
  } | null;
  suggestedTasks?: string[] | null;
  contactProfile?: CallRecord["contactProfile"] | null;
};

const SPEAKER_LABELS: Record<string, string> = {
  store: "Agent",
  customer: "Customer",
};

const normalizeSpeaker = (speaker: string) => {
  const trimmed = speaker.trim();
  if (!trimmed) {
    return "Unknown";
  }
  const mapped = SPEAKER_LABELS[trimmed.toLowerCase()];
  if (mapped) {
    return mapped;
  }
  return `${trimmed[0].toUpperCase()}${trimmed.slice(1)}`;
};

const extractTranscriptSegments = (raw: unknown): ApiTranscriptSegment[] => {
  if (!raw) {
    return [];
  }
  if (Array.isArray(raw)) {
    if (raw.length > 0 && typeof raw[0] === "object" && raw[0] !== null && "segments" in raw[0]) {
      return raw.flatMap((entry) =>
        Array.isArray((entry as { segments?: ApiTranscriptSegment[] }).segments)
          ? (entry as { segments?: ApiTranscriptSegment[] }).segments ?? []
          : [],
      );
    }
    return raw as ApiTranscriptSegment[];
  }
  if (typeof raw === "object" && raw !== null && "segments" in raw) {
    const segments = (raw as { segments?: ApiTranscriptSegment[] }).segments;
    return Array.isArray(segments) ? segments : [];
  }
  return [];
};

const summarizeTranscript = (segments: TranscriptSegment[], fallback?: string | null) => {
  const text = segments.map((segment) => segment.text.trim()).join(" ").trim();
  if (text) {
    if (text.length <= 140) {
      return text;
    }
    return `${text.slice(0, 137).trimEnd()}...`;
  }
  const trimmedFallback = fallback?.trim();
  return trimmedFallback || "Call transcript not available.";
};

const normalizeCallRecord = (call: ApiCallRecord): CallRecord => {
  const segments = extractTranscriptSegments(call.rawWhisperTranscript).map((segment) => {
    const startSec = Number.isFinite(segment.startSec)
      ? Number(segment.startSec)
      : Number(segment.start ?? 0);
    const endSec = Number.isFinite(segment.endSec)
      ? Number(segment.endSec)
      : Number(segment.end ?? 0);
    return {
      speaker: normalizeSpeaker(String(segment.speaker ?? "Unknown")),
      startSec,
      endSec,
      text: String(segment.text ?? "").trim(),
    };
  });

  const audioDuration =
    call.audio && call.audio.durationSec != null ? Number(call.audio.durationSec) : Number(call.durationSec);

  const pipelineStatus = normalizePipelineStatus(call.status);

  return {
    id: call.id,
    createdAt: call.createdAt,
    durationSec: Number(call.durationSec),
    summary: call.summary?.trim() || summarizeTranscript(segments, call.transcriptText),
    status: pipelineStatus,
    impliedName: call.impliedName ?? undefined,
    externalNumber: call.externalNumber ?? undefined,
    tags: call.tags ?? [],
    outcome: call.outcome,
    transcript: segments,
    audio: {
      durationSec: Number.isFinite(audioDuration) ? audioDuration : 0,
      previewProgress: call.audio?.previewProgress != null ? Number(call.audio.previewProgress) : 0,
      url: call.audio?.url ?? `${apiBaseUrl}/audio/${call.id}`,
    },
    suggestedTasks: call.suggestedTasks ?? [],
    contactProfile: call.contactProfile ?? undefined,
  };
};

const rawBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.API_BASE_URL ??
  "http://localhost:8000";

const apiBaseUrl = rawBaseUrl.replace(/\/$/, "");

export async function fetchCallRecords(): Promise<CallRecord[]> {
  const response = await fetch(`${apiBaseUrl}/calls`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load calls: ${response.status}`);
  }
  const payload = await response.json();
  if (!Array.isArray(payload)) {
    return [];
  }
  return payload.map((record) => normalizeCallRecord(record));
}

export async function fetchCallRecord(callId: string): Promise<CallRecord | null> {
  const response = await fetch(`${apiBaseUrl}/calls/${encodeURIComponent(callId)}`, {
    cache: "no-store",
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Failed to load call ${callId}: ${response.status}`);
  }
  const payload = await response.json();
  return normalizeCallRecord(payload);
}

export async function updateCallStatus(callId: string, status: string): Promise<CallRecord> {
  const response = await fetch(`${apiBaseUrl}/calls/${encodeURIComponent(callId)}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) {
    throw new Error(`Failed to update status: ${response.status}`);
  }
  const payload = await response.json();
  return normalizeCallRecord(payload);
}
