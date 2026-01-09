from __future__ import annotations

import logging
from typing import Any, Iterable

import whisperx

from .base import TranscriptionResult, WhisperBackend


class WhisperXAlignmentBackend(WhisperBackend):
    name = "whisperx-alignment"

    def __init__(
        self,
        device: str,
        model_name: str,
        alignment_kwargs: dict[str, Any],
    ) -> None:
        self.device = device
        self.model_name = model_name
        self.language: str = alignment_kwargs.get("language", "en")
        self.return_char_alignments: bool = alignment_kwargs.get("return_char_alignments", False)
        
        self._model = {"model": None, "metadata": None}

    @property
    def model(self):
        if self._model["model"] is None or self._model["metadata"] is None:
            model, metadata = self._load_align_model()
            self._model["model"] = model
            self._model["metadata"] = metadata
        return self._model

    def _load_align_model(self):
        logging.info(
            "Loading whisperx alignment model for language=%s on %s",
            self.language,
            self.device,
        )
        align_model, align_metadata = whisperx.load_align_model(
            language_code=self.language,
            device=self.device,
            model_name=self.model_name,
        )
        return align_model, align_metadata

    def __call__(self, results: list[TranscriptionResult]) -> Iterable[TranscriptionResult]:
        for result in results:
            if result.error or not result.segments or result.info is None:
                logging.info(f"Skipping whisperx alignment; error: {result.error} segments: {result.segments} info: {result.info}")
                yield result
                
            try:
                aligned = whisperx.align(
                    result.segments,
                    self.model["model"],
                    self.model["metadata"],
                    str(result.audio_path),
                    device=self.device,
                    return_char_alignments=self.return_char_alignments,
                )

                aligned_segments = aligned.get("segments", result.segments)
                yield TranscriptionResult(
                    audio_path=result.audio_path,
                    segments=aligned_segments,
                    info=result.info,
                    error=result.error,
                )
            except Exception:  # pragma: no cover - depends on runtime env
                logging.exception("Failed whisperx alignment; returning unaligned segments.")
                yield result
