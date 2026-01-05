from __future__ import annotations

from .base import TranscriptionInfo, TranscriptionResult, WhisperBackend
from .faster_whisper_backend import FasterWhisperBackend
from .openai_whisper_backend import OpenAIWhisperBackend


def create_whisper_backend(
    backend: str,
    model_name: str,
    device: str,
    compute_type: str,
    num_workers: int,
) -> WhisperBackend:
    key = backend.strip().lower()
    if key in {"faster-whisper", "faster_whisper", "ctranslate2"}:
        return FasterWhisperBackend(
            model_name=model_name,
            device=device,
            compute_type=compute_type,
            num_workers=num_workers,
        )
    if key in {"openai-whisper", "openai_whisper", "openai", "whisper"}:
        return OpenAIWhisperBackend(
            model_name=model_name,
            device=device,
            compute_type=compute_type,
            num_workers=num_workers,
        )
    raise ValueError(f"Unknown whisper backend: {backend}")
