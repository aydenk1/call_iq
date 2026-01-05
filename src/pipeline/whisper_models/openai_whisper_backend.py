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
        self._align_model = None
        self._align_metadata = None
        self._align_language = None
        self._align_device = None
        self._align_model_name = None

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

    def _load_align_model(
        self,
        language: str,
        *,
        device: str,
        model_name: str | None,
    ):
        if (
            self._align_model is None
            or self._align_language != language
            or self._align_device != device
            or self._align_model_name != model_name
        ):
            try:
                import whisperx
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "whisperx alignment requested but 'whisperx' is not installed. "
                    "Install it with 'pip install -U whisperx'."
                ) from exc
            logging.info(
                "Loading whisperx alignment model for language=%s on %s",
                language,
                device,
            )
            self._align_model, self._align_metadata = whisperx.load_align_model(
                language_code=language,
                device=device,
                model_name=model_name,
            )
            self._align_language = language
            self._align_device = device
            self._align_model_name = model_name
        return self._align_model, self._align_metadata

    def _align_segments(
        self,
        audio_path: Path,
        segments: list[dict[str, Any]],
        *,
        language: str | None,
        device: str,
        model_name: str | None,
        return_char_alignments: bool,
    ) -> list[dict[str, Any]]:
        if not language:
            logging.warning("Skipping whisperx alignment; language is unknown.")
            return segments
        try:
            import whisperx
        except ImportError:
            logging.warning("Skipping whisperx alignment; whisperx is not installed.")
            return segments
        try:
            align_model, metadata = self._load_align_model(
                language,
                device=device,
                model_name=model_name,
            )
            aligned = whisperx.align(
                segments,
                align_model,
                metadata,
                str(audio_path),
                device=device,
                return_char_alignments=return_char_alignments,
            )
        except Exception:  # pragma: no cover - depends on runtime env
            logging.exception("Failed whisperx alignment; returning unaligned segments.")
            return segments
        return aligned.get("segments", segments)

    def transcribe(
        self,
        audio_path: Path,
        batch_size: int,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], TranscriptionInfo]:
        align_with_whisperx = bool(kwargs.pop("whisperx_align", False))
        align_model_name = kwargs.pop("whisperx_align_model", None)
        align_device = kwargs.pop("whisperx_align_device", None) or self.device
        return_char_alignments = bool(kwargs.pop("whisperx_return_char_alignments", False))

        model = self._load_model()
        result = model.transcribe(str(audio_path), **kwargs)
        raw_segments = result.get("segments", [])
        if align_with_whisperx and raw_segments:
            raw_segments = self._align_segments(
                audio_path,
                raw_segments,
                language=result.get("language"),
                device=align_device,
                model_name=align_model_name,
                return_char_alignments=return_char_alignments,
            )
        segments: list[dict[str, Any]] = []
        for idx, seg in enumerate(raw_segments):
            segments.append(
                {
                    "id": seg.get("id", idx),
                    "seek": seg.get("seek", 0),
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": seg.get("text", ""),
                    "words": seg.get("words", []),
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
