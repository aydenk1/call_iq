import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";

export const runtime = "nodejs";

const SUPPORTED_CHANNELS = new Set(["customer", "store"]);

type AudioTarget = {
  path: string;
  contentType: string;
};

function parseRange(rangeHeader: string | null, size: number) {
  if (!rangeHeader || !rangeHeader.startsWith("bytes=")) {
    return null;
  }
  const [startRaw, endRaw] = rangeHeader.replace("bytes=", "").split("-");
  const start = startRaw ? Number(startRaw) : 0;
  const end = endRaw ? Number(endRaw) : size - 1;
  if (Number.isNaN(start) || Number.isNaN(end) || start > end || end >= size) {
    return null;
  }
  return { start, end };
}

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const request = _request;
  const { id } = await context.params;
  const url = new URL(request.url);
  const channel = url.searchParams.get("channel") ?? "customer";

  if (!SUPPORTED_CHANNELS.has(channel)) {
    return new Response("Unsupported channel", { status: 400 });
  }

  const recordingPath = path.resolve(
    process.cwd(),
    "..",
    "data",
    "recordings",
    `${id}.mp3`,
  );
  const whisperPath = path.resolve(
    process.cwd(),
    "..",
    "data",
    "whisper",
    id,
    `${channel}.wav`,
  );

  let target: AudioTarget | null = null;
  try {
    await stat(recordingPath);
    target = { path: recordingPath, contentType: "audio/mpeg" };
  } catch (error) {
    try {
      await stat(whisperPath);
      target = { path: whisperPath, contentType: "audio/wav" };
    } catch (innerError) {
      console.error("Audio stream error", innerError);
      return new Response("Audio not found", { status: 404 });
    }
  }

  try {
    if (!target) {
      return new Response("Audio not found", { status: 404 });
    }
    const info = await stat(target.path);
    const range = parseRange(request.headers.get("range"), info.size);
    const headers = new Headers({
      "Content-Type": target.contentType,
      "Accept-Ranges": "bytes",
    });

    if (range) {
      headers.set("Content-Range", `bytes ${range.start}-${range.end}/${info.size}`);
      headers.set("Content-Length", String(range.end - range.start + 1));
      const stream = createReadStream(target.path, { start: range.start, end: range.end });
      const body = (typeof Readable.toWeb === "function"
        ? Readable.toWeb(stream)
        : (stream as unknown as ReadableStream)) as ReadableStream;
      return new Response(body, {
        status: 206,
        headers,
      });
    }

    headers.set("Content-Length", String(info.size));
    const stream = createReadStream(target.path);
    const body = (typeof Readable.toWeb === "function"
      ? Readable.toWeb(stream)
      : (stream as unknown as ReadableStream)) as ReadableStream;
    return new Response(body, {
      status: 200,
      headers,
    });
  } catch (error) {
    console.error("Audio stream error", error);
    return new Response("Audio not found", { status: 404 });
  }
}
