import callRecordsRaw from "./call-records.json";

export type TranscriptSegment = {
  speaker: string;
  startSec: number;
  endSec: number;
  text: string;
};

export type CallOutcome = {
  status: "potential" | "lost" | "neutral";
  amount?: string;
  reason?: string;
};

export type ContactProfile = {
  name: string;
  phone: string;
  status: string;
  notes: string[];
  previousCallIds: string[];
};

export type CallRecord = {
  id: string;
  createdAt: string;
  durationSec: number;
  summary: string;
  impliedName?: string;
  externalNumber?: string;
  tags: string[];
  outcome?: CallOutcome;
  transcript: TranscriptSegment[];
  audio: {
    durationSec: number;
    previewProgress: number;
    url?: string;
  };
  suggestedTasks: string[];
  contactProfile?: ContactProfile;
};

export const callRecords = callRecordsRaw as CallRecord[];
