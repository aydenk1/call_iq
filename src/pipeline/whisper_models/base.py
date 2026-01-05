from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol


@dataclass(frozen=True)
class TranscriptionInfo:
    model: str
    language: str | None
    language_probability: float | None
    duration: float | None


@dataclass(frozen=True)
class TranscriptionResult:
    audio_path: Path
    segments: list[dict[str, Any]] | None
    info: TranscriptionInfo | None
    error: Exception | None


class WhisperBackend(Protocol):
    name: str

    def transcribe(
        self,
        audio_path: Path,
        batch_size: int,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], TranscriptionInfo]:
        ...

    def __call__(
        self,
        audio_paths: list[Path],
        batch_size: int,
        **kwargs: Any,
    ) -> Iterable[TranscriptionResult]:
        ...
