from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class TranscriptionInfo:
    model: str
    language: str | None
    language_probability: float | None
    duration: float | None


class WhisperBackend(Protocol):
    name: str

    def transcribe(
        self,
        audio_path: Path,
        batch_size: int,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], TranscriptionInfo]:
        ...
