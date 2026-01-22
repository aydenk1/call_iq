from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, ClassVar


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


class WhisperBackend:
    name: ClassVar[str]

    def __init__(
            self,
            model_name: str,
            device: str,
            compute_type: str,
            num_workers: int,
            batch_size: int,
            model_kwargs: dict[str, Any] | None = None,
    ) -> None:
        ...
        
    def __call__(
        self,
        targets,
    ) -> Iterable[TranscriptionResult]:
        ...
