export type TranscriptSegment = {
  speaker: string;
  startSec: number;
  endSec: number;
  text: string;
};

export type TranscriptRun = {
  id: string;
  label: string;
  segments: TranscriptSegment[];
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
  status: string;
  impliedName?: string;
  externalNumber?: string;
  tags: string[];
  outcome?: CallOutcome;
  transcript: TranscriptSegment[];
  transcripts: TranscriptRun[];
  audio: {
    durationSec: number;
    previewProgress: number;
    url?: string;
  };
  suggestedTasks: string[];
  contactProfile?: ContactProfile;
};

export type Caller = {
  id: string;
  impliedName?: string;
  profile: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type CallerWithCalls = {
  caller: Caller;
  calls: CallRecord[];
};
