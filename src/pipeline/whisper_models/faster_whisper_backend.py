from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import ctranslate2
from faster_whisper import BatchedInferencePipeline, WhisperModel

from .base import TranscriptionInfo, TranscriptionResult


class FasterWhisperBackend:
    name = "faster-whisper"

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
        self._model: WhisperModel | None = None
        self._pipeline: BatchedInferencePipeline | None = None

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            logging.info(f"Forcing use of device: {device}")
            return device
        try:
            if int(ctranslate2.get_cuda_device_count()) > 0:
                logging.info("Using device: cuda")
                return "cuda"
        except Exception:
            pass
        logging.info("Using device: cpu")
        return "cpu"

    def _load_model(self) -> WhisperModel:
        if self._model is None:
            logging.info(
                "Loading faster-whisper model %s on %s (%s %s)",
                self.model_name,
                self.device,
                self.compute_type,
                self.num_workers,
            )
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                num_workers=self.num_workers,
                cpu_threads=self.num_workers,
            )
            self._pipeline = None
        return self._model

    def _load_pipeline(self) -> BatchedInferencePipeline:
        if self._pipeline is None:
            logging.info("Initializing batched inference pipeline for faster-whisper")
            self._pipeline = BatchedInferencePipeline(self._load_model())
        return self._pipeline

    def transcribe(
        self,
        audio_path: Path,
        batch_size: int,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], TranscriptionInfo]:
        pipeline = self._load_pipeline()
        segments_iter, info = pipeline.transcribe(
            str(audio_path),
            batch_size=batch_size,
            **kwargs,
        )
        segments = [asdict(seg) for seg in segments_iter]
        return segments, TranscriptionInfo(
            model=self.model_name,
            language=getattr(info, "language", None),
            language_probability=getattr(info, "language_probability", None),
            duration=getattr(info, "duration", None),
        )

    def __call__(
        self,
        audio_paths: list[Path],
        batch_size: int,
        **kwargs: Any,
    ) -> Iterable[TranscriptionResult]:
        if not audio_paths:
            return
        
        self._load_pipeline()
        max_workers = max(1, self.num_workers // 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_audio = {
                executor.submit(self.transcribe, audio_path, batch_size, **kwargs): audio_path
                for audio_path in audio_paths
            }
        
            for future in as_completed(future_to_audio):
                audio_path = future_to_audio[future]
                try:
                    segments, info = future.result()
                except Exception as exc:
                    yield TranscriptionResult(
                        audio_path=audio_path,
                        segments=None,
                        info=None,
                        error=exc,
                    )
                else:
                    yield TranscriptionResult(
                        audio_path=audio_path,
                        segments=segments,
                        info=info,
                        error=None,
                    )
