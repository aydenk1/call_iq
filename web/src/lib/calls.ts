import type { CallRecord } from "@/lib/call-types";

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
  return response.json();
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
  return response.json();
}
