from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import TranscriptionInfo


class OpenAIWhisperBackend:
    name = "openai-whisper"

    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        num_workers: int,
    ) -> None:
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.compute_type = compute_type
        self.num_workers = num_workers
        self._model = None

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            logging.info(f"Forcing use of device: {device}")
            return device
        try:
            import torch

            if torch.cuda.is_available():
                logging.info("Using device: cuda")
                return "cuda"
        except Exception:
            pass
        logging.info("Using device: cpu")
        return "cpu"

    def _load_model(self):
        if self._model is None:
            try:
                import whisper
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "openai-whisper backend selected but 'whisper' is not installed. "
                    "Install it with 'pip install -U openai-whisper'."
                ) from exc
            logging.info("Loading openai-whisper model %s on %s", self.model_name, self.device)
            self._model = whisper.load_model(self.model_name, device=self.device)
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        batch_size: int,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], TranscriptionInfo]:
        model = self._load_model()
        result = model.transcribe(str(audio_path), **kwargs)
        raw_segments = result.get("segments", [])
        segments: list[dict[str, Any]] = []
        for idx, seg in enumerate(raw_segments):
            segments.append(
                {
                    "id": seg.get("id", idx),
                    "seek": seg.get("seek", 0),
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": seg.get("text", ""),
                    "tokens": seg.get("tokens", []),
                    "temperature": seg.get("temperature"),
                    "avg_logprob": seg.get("avg_logprob"),
                    "compression_ratio": seg.get("compression_ratio"),
                    "no_speech_prob": seg.get("no_speech_prob"),
                }
            )
        duration = result.get("duration")
        if duration is None and segments:
            duration = max(seg.get("end") or 0 for seg in segments)
        return segments, TranscriptionInfo(
            model=self.model_name,
            language=result.get("language"),
            language_probability=None,
            duration=duration,
        )
