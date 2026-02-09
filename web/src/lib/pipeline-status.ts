export const PIPELINE_STATUS_ORDER = [
  "FAILED",
  "CALL_IN_PROGRESS",
  "DOWNLOAD_QUEUED",
  "DOWNLOADED",
  "TRANSCRIBED",
  "FINISHED",
] as const;

export type KnownPipelineStatus = (typeof PIPELINE_STATUS_ORDER)[number];
export type PipelineStatus = KnownPipelineStatus | "UNKNOWN";

const STATUS_BY_VALUE = new Map<number, PipelineStatus>([
  [-1, "FAILED"],
  [0, "CALL_IN_PROGRESS"],
  [1, "DOWNLOAD_QUEUED"],
  [2, "DOWNLOADED"],
  [3, "TRANSCRIBED"],
  [4, "FINISHED"],
]);

const STATUS_SET = new Set<KnownPipelineStatus>(PIPELINE_STATUS_ORDER);

export const normalizePipelineStatus = (status: unknown): PipelineStatus => {
  if (typeof status === "string") {
    const trimmed = status.trim();
    if (!trimmed) {
      return "UNKNOWN";
    }
    if (/^-?\d+$/.test(trimmed)) {
      return STATUS_BY_VALUE.get(Number(trimmed)) ?? "UNKNOWN";
    }
    const normalized = trimmed.split(".").pop()?.toUpperCase() ?? "";
    if (STATUS_SET.has(normalized as KnownPipelineStatus)) {
      return normalized as KnownPipelineStatus;
    }
    return "UNKNOWN";
  }
  if (typeof status === "number" && Number.isFinite(status)) {
    return STATUS_BY_VALUE.get(status) ?? "UNKNOWN";
  }
  return "UNKNOWN";
};

export const formatPipelineStatus = (status: PipelineStatus | string) => {
  if (!status || status === "UNKNOWN") {
    return "Unknown";
  }
  return status
    .toString()
    .split("_")
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(" ");
};

export const getPipelineStatusTone = (status: PipelineStatus | string) => {
  if (status === "FAILED") {
    return "warn";
  }
  if (status === "FINISHED" || status === "TRANSCRIBED") {
    return "accent";
  }
  return undefined;
};
