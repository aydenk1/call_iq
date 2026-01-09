from __future__ import annotations

import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

from .base import TranscriptionInfo, TranscriptionResult, WhisperBackend
from whisper import Whisper
from pipeline.utils import chunked

_MODEL: Whisper | None = None
_MODEL_NAME: str | None = None
_MODEL_DEVICE: str | None = None


def _init_worker(model_name: str, device: str) -> None:
    global _MODEL, _MODEL_NAME, _MODEL_DEVICE
    _MODEL_NAME = model_name
    _MODEL_DEVICE = device
    try:
        import torch

        torch.set_num_threads(10)
        torch.set_num_interop_threads(10)
    except Exception:
        pass

    _MODEL = OpenAIWhisperBackend._load_model(_MODEL_NAME, _MODEL_DEVICE)
    

def _transcribe_worker(audio_paths: list[Path], kwargs: dict[str, Any]) -> tuple[list[list[dict[str, Any]]], list[TranscriptionInfo]]:
    if _MODEL is None:
        if _MODEL_NAME is None or _MODEL_DEVICE is None:
            raise RuntimeError("Worker model not initialized.")
        _init_worker(_MODEL_NAME, _MODEL_DEVICE)
    
    all_segments, all_t_infos = [], []
    for audio_path in audio_paths:
        result = _MODEL.transcribe(str(audio_path), **kwargs)
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
        t_info = TranscriptionInfo(
            model=_MODEL_NAME or "unknown",
            language=result.get("language"),
            language_probability=None,
            duration=duration,
        )
        all_segments.append(segments)
        all_t_infos.append(t_info)
    return all_segments, all_t_infos


class OpenAIWhisperBackend(WhisperBackend):
    name = "openai-whisper"

    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        num_workers: int,
        model_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.compute_type = compute_type
        self.num_workers = num_workers
        self._model = None
        self.model_kwargs = dict(model_kwargs or {})

    @staticmethod
    def convert_kwarg(**kwargs) -> dict:
        new_kwargs = {}
        for k, v in kwargs.items():
            if k == "log_prob_threshold":
                k = "logprob_threshold"
            if k == "log_progress":
                k = "verbose"
                v = True if v == True else None
            if k == "vad_parameters":
                continue
            new_kwargs[k] = v
        return new_kwargs

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

    @staticmethod
    def _load_model(model_name, device):
        try:
            import whisper
            import torch
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "openai-whisper backend selected but 'whisper' is not installed. "
                "Install it with 'pip install -U openai-whisper'."
            ) from exc
        if hasattr(torch, "set_float32_matmul_precision"):
            torch.set_float32_matmul_precision("high")
        logging.info("Loading openai-whisper model %s on %s", model_name, device)
        model = whisper.load_model(model_name, device=device)
        # if hasattr(model, "generation_config"):
        #     model.generation_config.cache_implementation = "static"
        #     model.generation_config.max_new_tokens = 256
        # if hasattr(torch, "compile"):
        #     try:
        #         model.forward = torch.compile(model.forward, mode="max-autotune", fullgraph=True)
        #     except Exception:
        #         logging.warning("torch.compile failed; continuing without compilation.")
        return model
    
    @property
    def model(self):
        if self._model is None:
            self._model = self._load_model(self.model_name, self.device)
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        batch_size: int,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], TranscriptionInfo]:
        result = self.model.transcribe(str(audio_path), **kwargs)
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
                    "words": seg.get("words", []),
                    "tokens": seg.get("tokens", []),
                    "temperature": seg.get("temperature"),
                    "avg_logprob": seg.get("avg_logprob"),
                    "compression_ratio": seg.get("compression_ratio"),
                    "no_speech_prob": seg.get("no_speech_prob"),
                }
            )
        duration = result.get("duration", 0)
        if duration is None and segments:
            duration = max(seg.get("end") or 0 for seg in segments)
        return segments, TranscriptionInfo(
            model=self.model_name,
            language=result.get("language"),
            language_probability=None,
            duration=duration,
        )

    def __call__(
        self,
        audio_paths: list[Path],
        batch_size: int,
        **kwargs: Any,
    ) -> Iterable[TranscriptionResult]:
        if not audio_paths:
            return
        call_kwargs = dict(self.model_kwargs)
        call_kwargs.update(kwargs)
        call_kwargs = self.convert_kwarg(**call_kwargs)

        if self.num_workers <= 1:
            for audio_path in audio_paths:
                try:
                    segments, info = self.transcribe(audio_path, batch_size, **call_kwargs)
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
            return
        
        max_workers = max(1, min(self.num_workers, len(audio_paths)))
        batches = list(chunked(audio_paths, len(audio_paths) // max_workers))
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=ctx,
            initializer=_init_worker,
            initargs=(self.model_name, self.device),
        ) as executor:
            future_to_audio = {
                executor.submit(_transcribe_worker, batch, call_kwargs): batch
                for batch in batches
            }
            for future in as_completed(future_to_audio):
                audio_paths = future_to_audio[future]
                all_segments, all_t_infos = future.result()
                for segments, info, audio_path in zip(all_segments, all_t_infos, audio_paths):
                    yield TranscriptionResult(
                        audio_path=audio_path,
                        segments=segments,
                        info=info,
                        error=None,
                    )
