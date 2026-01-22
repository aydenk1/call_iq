from __future__ import annotations

from typing import Any

from .base import TranscriptionInfo, TranscriptionResult, WhisperBackend
from .faster_whisper_backend import FasterWhisperBackend
from .openai_whisper_backend import OpenAIWhisperBackend
from .whisperx_alignment_backend import WhisperXAlignmentBackend

backends: list[type[WhisperBackend]] = [FasterWhisperBackend, OpenAIWhisperBackend, WhisperXAlignmentBackend]

def create_backend(
    backend_name: str,
    model_name: str,
    device: str,
    compute_type: str,
    num_workers: int,
    batch_size: int,
    model_kwargs: dict[str, Any] | None = None,
) -> WhisperBackend:
    key = backend_name.strip().lower()
    for Backend in backends:
        if key == Backend.name:
            return Backend(
                model_name=model_name,
                device=device,
                compute_type=compute_type,
                num_workers=num_workers,
                batch_size=batch_size,
                model_kwargs=model_kwargs
            )
    raise ValueError(f"Unknown whisper backend: {backend_name}")
