import type { CallRecord, Caller, CallerWithCalls, TranscriptRun, TranscriptSegment } from "@/lib/call-types";
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

type ApiCaller = {
  id: string;
  impliedName?: string | null;
  profile?: Record<string, unknown> | null;
  createdAt?: string;
  updatedAt?: string;
};

type ApiCallerWithCalls = {
  caller: ApiCaller;
  calls: ApiCallRecord[];
};

type ApiTranscriptRun = {
  segments?: ApiTranscriptSegment[] | null;
  text?: string | null;
  metadata?: Record<string, unknown> | null;
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

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const normalizeSegments = (segments: ApiTranscriptSegment[]): TranscriptSegment[] =>
  segments.map((segment) => {
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

const normalizeTranscriptRun = (raw: unknown, index: number): TranscriptRun | null => {
  let segments: ApiTranscriptSegment[] = [];
  let text = "";

  if (Array.isArray(raw)) {
    segments = raw as ApiTranscriptSegment[];
  } else if (isObjectRecord(raw)) {
    const candidate = raw as ApiTranscriptRun;
    segments = Array.isArray(candidate.segments) ? candidate.segments : [];
    text = typeof candidate.text === "string" ? candidate.text.trim() : "";
  } else {
    return null;
  }

  const normalizedSegments = normalizeSegments(segments);
  if (normalizedSegments.length === 0 && !text) {
    return null;
  }

  return {
    id: `run-${index + 1}`,
    label: `Run ${index + 1}`,
    segments: normalizedSegments,
    text,
  };
};

const normalizeTranscriptRuns = (raw: unknown): TranscriptRun[] => {
  if (!raw) {
    return [];
  }
  if (Array.isArray(raw)) {
    if (raw.length === 0) {
      return [];
    }
    const hasWrappedRuns = raw.some((entry) => isObjectRecord(entry) && "segments" in entry);
    if (hasWrappedRuns) {
      return raw
        .map((entry, index) => normalizeTranscriptRun(entry, index))
        .filter((entry): entry is TranscriptRun => Boolean(entry));
    }
    const single = normalizeTranscriptRun(raw, 0);
    return single ? [single] : [];
  }
  if (isObjectRecord(raw) && "segments" in raw) {
    const single = normalizeTranscriptRun(raw, 0);
    return single ? [single] : [];
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
  const transcriptRuns = normalizeTranscriptRuns(call.rawWhisperTranscript);
  const latestTranscript = transcriptRuns[transcriptRuns.length - 1];
  const segments = latestTranscript?.segments ?? [];

  const audioDuration =
    call.audio && call.audio.durationSec != null ? Number(call.audio.durationSec) : Number(call.durationSec);
  const rawAudioUrl = typeof call.audio?.url === "string" ? call.audio.url.trim() : "";
  const fallbackAudioUrl = `/api/audio/${encodeURIComponent(call.id)}`;
  const audioUrl = rawAudioUrl || fallbackAudioUrl;

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
    transcripts: transcriptRuns,
    audio: {
      durationSec: Number.isFinite(audioDuration) ? audioDuration : 0,
      previewProgress: call.audio?.previewProgress != null ? Number(call.audio.previewProgress) : 0,
      url: audioUrl,
    },
    suggestedTasks: call.suggestedTasks ?? [],
    contactProfile: call.contactProfile ?? undefined,
  };
};

const normalizeCaller = (caller: ApiCaller): Caller => {
  return {
    id: caller.id,
    impliedName: caller.impliedName ?? undefined,
    profile: caller.profile ?? {},
    createdAt: caller.createdAt ?? "",
    updatedAt: caller.updatedAt ?? "",
  };
};

const resolveApiBaseCandidates = () => {
  const configured = [
    process.env.API_BASE_URL,
    process.env.NEXT_PUBLIC_API_BASE_URL,
  ]
    .map((value) => (value ?? "").trim())
    .filter((value) => value.length > 0)
    .map((value) => value.replace(/\/$/, ""));

  configured.push("http://127.0.0.1:8000", "http://localhost:8000");

  return [...new Set(configured)];
};

const apiBaseCandidates = resolveApiBaseCandidates();
const apiBaseUrl = apiBaseCandidates[0] ?? "http://localhost:8000";

const fetchFromApi = async (path: string, init?: RequestInit): Promise<Response> => {
  let lastError: unknown = null;
  for (const base of apiBaseCandidates) {
    try {
      return await fetch(`${base}${path}`, init);
    } catch (error) {
      lastError = error;
    }
  }
  const detail = lastError instanceof Error ? lastError.message : "unknown network error";
  throw new Error(`Failed to reach API (${apiBaseCandidates.join(", ")}): ${detail}`);
};

type FetchCallRecordsPage = {
  records: CallRecord[];
  hasMore: boolean;
  totalCount: number;
};

type FetchCallRecordsOptions = {
  limit?: number;
  offset?: number;
  q?: string;
};

export async function fetchCallRecords(): Promise<CallRecord[]> {
  const response = await fetchFromApi("/calls", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load calls: ${response.status}`);
  }
  const payload = await response.json();
  if (!Array.isArray(payload)) {
    return [];
  }
  return payload.map((record) => normalizeCallRecord(record));
}

export async function fetchCallRecordsPage(
  options: FetchCallRecordsOptions = {},
): Promise<FetchCallRecordsPage> {
  const limit = Number.isFinite(options.limit) ? Number(options.limit) : 50;
  const offset = Number.isFinite(options.offset) ? Number(options.offset) : 0;
  const q = typeof options.q === "string" ? options.q.trim() : "";
  const safeLimit = Math.max(1, Math.min(200, limit));
  const safeOffset = Math.max(0, offset);
  const searchParams = new URLSearchParams({
    limit: String(safeLimit + 1),
    offset: String(safeOffset),
  });
  if (q) {
    searchParams.set("q", q);
  }
  const callsPath = `/calls?${searchParams.toString()}`;
  const countParams = new URLSearchParams();
  if (q) {
    countParams.set("q", q);
  }
  const countPath = countParams.toString() ? `/calls/count?${countParams.toString()}` : "/calls/count";

  const [response, countResponse] = await Promise.all([
    fetchFromApi(callsPath, { cache: "no-store" }),
    fetchFromApi(countPath, { cache: "no-store" }),
  ]);
  if (!response.ok) {
    throw new Error(`Failed to load calls: ${response.status}`);
  }
  if (!countResponse.ok) {
    throw new Error(`Failed to load call count: ${countResponse.status}`);
  }
  const payload = await response.json();
  const countPayload = await countResponse.json();
  const totalCount = typeof countPayload?.count === "number" ? countPayload.count : 0;
  if (!Array.isArray(payload)) {
    return { records: [], hasMore: false, totalCount };
  }
  const sliced = payload.slice(0, safeLimit);
  return {
    records: sliced.map((record) => normalizeCallRecord(record)),
    hasMore: payload.length > safeLimit,
    totalCount,
  };
}

export async function fetchCallRecord(callId: string): Promise<CallRecord | null> {
  const response = await fetchFromApi(`/calls/${encodeURIComponent(callId)}`, {
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
  const endpoint =
    typeof window === "undefined"
      ? `${apiBaseUrl}/calls/${encodeURIComponent(callId)}/status`
      : `/api/calls/${encodeURIComponent(callId)}/status`;
  const response = await fetch(endpoint, {
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

export async function fetchCallerWithCalls(callerId: string): Promise<CallerWithCalls | null> {
  const response = await fetchFromApi(`/callers/${encodeURIComponent(callerId)}`, {
    cache: "no-store",
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Failed to load caller ${callerId}: ${response.status}`);
  }
  const payload = (await response.json()) as ApiCallerWithCalls;
  return {
    caller: normalizeCaller(payload.caller),
    calls: Array.isArray(payload.calls) ? payload.calls.map((record) => normalizeCallRecord(record)) : [],
  };
}
