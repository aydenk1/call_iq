#!/usr/bin/env python3
"""Build UI call records from whisper conversation JSON files."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SPEAKER_LABELS = {
    "store": "Agent",
    "customer": "Customer",
}


@dataclass
class UiSegment:
    speaker: str
    startSec: float
    endSec: float
    text: str


def _parse_created_at(timestamp: dict[str, Any]) -> str:
    if not timestamp:
        return "1970-01-01T00:00:00+00:00"

    dt_utc = timestamp.get("datetime_utc")
    if isinstance(dt_utc, str) and dt_utc:
        return dt_utc

    epoch = timestamp.get("datetime_ep", 0)
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return "1970-01-01T00:00:00+00:00"


def _summary_from_segments(segments: list[UiSegment]) -> str:
    if not segments:
        return "Call transcript not available."
    text = " ".join(seg.text.strip() for seg in segments).strip()
    if len(text) <= 140:
        return text
    return f"{text[:137].rstrip()}..."


def _load_conversation(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    segments: list[UiSegment] = []
    for seg in data.get("segments", []):
        speaker = str(seg.get("speaker", "Unknown"))
        speaker = SPEAKER_LABELS.get(speaker, speaker.title())
        segments.append(
            UiSegment(
                speaker=speaker,
                startSec=float(seg.get("start", 0)),
                endSec=float(seg.get("end", 0)),
                text=str(seg.get("text", "")).strip(),
            )
        )

    created_at = _parse_created_at(data.get("timestamp", {}))
    duration = float(data.get("duration", 0))

    return {
        "id": data.get("call_uuid", path.parent.name),
        "createdAt": created_at,
        "durationSec": duration,
        "summary": _summary_from_segments(segments),
        "tags": [],
        "transcript": [seg.__dict__ for seg in segments],
        "audio": {
            "durationSec": duration,
            "previewProgress": 0,
            "url": f"/api/audio/{data.get('call_uuid', path.parent.name)}",
        },
        "suggestedTasks": [],
    }


def _sort_key(call: dict[str, Any]) -> float:
    created_at = call.get("createdAt", "")
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--whisper-dir",
        type=Path,
        default=Path("data/whisper"),
        help="Directory containing call UUID folders with conversation.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("web/src/lib/call-records.json"),
        help="Output JSON path for the UI",
    )
    args = parser.parse_args()

    whisper_dir: Path = args.whisper_dir
    out_path: Path = args.out

    conversation_paths = sorted(whisper_dir.rglob("conversation.json"))
    calls = [_load_conversation(path) for path in conversation_paths]
    calls.sort(key=_sort_key, reverse=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(calls, indent=2, ensure_ascii=True))
    print(f"Wrote {len(calls)} calls to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
