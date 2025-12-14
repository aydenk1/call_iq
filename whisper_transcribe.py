from __future__ import annotations

import dataclasses
import json
import logging
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

from tqdm import tqdm

from subprocess_pool import SubprocessPool

from faster_whisper import WhisperModel, BatchedInferencePipeline
from faster_whisper.transcribe import Segment, Word

try:
    import torch
except ImportError:  # pragma: no cover - torch is available via env.yml
    torch = None  # type: ignore[assignment]

class WhisperTranscribe:
    def __init__(
        self,
        input_root: Path,
        output_root: Path,
        overwrite: bool = False,
        model_name: str = "large-v3-turbo",
        device: str | None = "cuda",
        language: str | None = "en",
        batch_size: int = 64,
    ) -> None:
        """Configure the transcription pipeline and ensure output directories exist."""
        self.input_root = Path(input_root)
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.overwrite = overwrite

        self.model_name = model_name
        self.language = language
        self.decode_options = {}

        self.batch_size = batch_size
        self.requested_device = device
        self.num_workers = max(1, (os.cpu_count() or 2))
        self.device = self._resolve_device()
        self.compute_type = self._default_compute_type(self.device)

        self._model: WhisperModel | None = None
        self._pipeline: BatchedInferencePipeline | None = None

    def iter_inputs(self, exts: Iterable[str] = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")) -> list[Path]:
        """Yield every input audio file that matches the provided extensions."""
        exts = tuple(e.lower() for e in exts)
        return sorted([p for p in self.input_root.rglob("*") if p.is_file() and p.suffix.lower() in exts])

    def out_paths(self, src: Path) -> tuple[Path, Path]:
        """Return output paths for the left and right channels derived from src."""
        rel = src.relative_to(self.input_root)
        stem = rel.with_suffix("")  # drop input extension
        base = self.output_root / stem
        base.mkdir(parents=True, exist_ok=True)
        left = base / "customer.wav"  # left
        right = base / "store.wav"        # right
        return left, right

    def ffmpeg_split_cmd(self, src: Path, out_left: Path, out_right: Path) -> list[str]:
        """Build the ffmpeg command that normalizes and splits stereo audio."""
        ow = "-y" if self.overwrite else "-n"

        fc = (
            "[0:a]channelsplit=channel_layout=stereo[left][right];"
            "[left]dynaudnorm=p=0.9:s=5,aresample=16000,pan=mono|c0=c0[left_m];"
            "[right]dynaudnorm=p=0.9:s=5,aresample=16000,pan=mono|c0=c0[right_m]"
        )

        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            ow,
            "-i", str(src),
            "-filter_complex", fc,

            "-map", "[left_m]",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(out_left),

            "-map", "[right_m]",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(out_right),
        ]

    def build_commands(self) -> list[list[str]]:
        """Assemble split commands for any recordings that still need processing."""
        cmds: list[list[str]] = []
        for src in self.iter_inputs():
            out_left, out_right = self.out_paths(src)
            if not self.overwrite and out_left.exists() and out_right.exists():
                continue
            cmds.append(self.ffmpeg_split_cmd(src, out_left, out_right))
        return cmds
    
    def preprocess_audio(self) -> None:
        """Split every stereo recording into normalized mono speaker channels."""
        commands = self.build_commands()
        if not commands:
            logging.info("No new recordings require channel splitting.")
            return

        pool = SubprocessPool(
            max_workers=self.num_workers,
            capture_stdout=True,
            capture_stderr=True,
            nice=10,
            desc="Splitting",
        )
        results = pool.run(commands)

        failed = [r for r in results if r.rc != 0]
        logging.info("Split complete. total=%d failed=%d", len(results), len(failed))
        if failed:
            logging.error("Example failure cmd: %s", " ".join(failed[0].cmd))
            logging.error("stderr: %s", failed[0].stderr.strip())
    
    @staticmethod
    def _resolve_device() -> str:
        """Return the best available device (CUDA, MPS, or CPU)."""
        if torch is not None:
            if torch.cuda.is_available():
                return "cuda"
            has_mps = getattr(torch.backends, "mps", None)
            if has_mps and torch.backends.mps.is_available():
                return "mps"
        return "cpu"

    def _default_compute_type(self, device: str) -> str:
        """Pick an efficient compute precision for the given device."""
        if device == "cuda":
            return "float16"
        return "int8"

    def _load_model(self) -> WhisperModel:
        """Lazy-load the faster-whisper model instance."""
        if self._model is None:
            logging.info(f'Loading faster-whisper model {self.model_name} on {self.device} ({self.compute_type} {self.num_workers})')
                
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                num_workers=self.num_workers,
                cpu_threads=max(1, os.cpu_count() or 1),
            )
            self._pipeline = None  # reset pipeline so it can be rebuilt with the new model
        return self._model

    def _load_pipeline(self) -> BatchedInferencePipeline:
        """Lazy-load the batched inference pipeline built from the model."""
        if self._pipeline is None: 
            logging.info("Initializing batched inference pipeline for faster-whisper")
            self._pipeline = BatchedInferencePipeline(self._load_model())
        return self._pipeline

    def iter_split_outputs(self, exts: Iterable[str] = (".wav",)) -> list[Path]:
        """Return the mono channel files ready for transcription."""
        exts = tuple(e.lower() for e in exts)
        outputs = [p for p in self.output_root.rglob("*") if p.is_file() and p.suffix.lower() in exts]
        return sorted(outputs)

    def _transcribe_kwargs(self) -> dict[str, Any]:
        """Build the kwargs dict forwarded to faster-whisper."""
        kwargs: dict[str, Any] = {**self.decode_options}
        if self.language:
            kwargs.setdefault("language", self.language)
        # Suppress the built-in tqdm bar because we already show progress externally.
        kwargs.setdefault("log_progress", False)
        # Preserve timestamps by default just like WhisperModel.transcribe.
        kwargs.setdefault("without_timestamps", False)
        return {k: v for k, v in kwargs.items() if v is not None}

    def _transcribe_file(
        self,
        pipeline: BatchedInferencePipeline,
        audio_path: Path,
        transcribe_kwargs: dict[str, Any],
    ) -> None:
        """Transcribe a single mono channel and persist its transcript."""
        segments_iter, info = pipeline.transcribe(
            str(audio_path),
            batch_size=self.batch_size,
            **transcribe_kwargs,
        )
        segments = list(segments_iter)
        self._write_transcript(audio_path, info, segments)

    def transcribe_outputs(self) -> None:
        """Transcribe each split file in parallel, tracking failures and progress."""
        targets: list[Path] = []
        for audio_path in self.iter_split_outputs():
            transcript_path = audio_path.with_suffix(".json")
            if transcript_path.exists() and not self.overwrite:
                continue
            targets.append(audio_path)

        if not targets:
            logging.info("No files need transcription.")
            return

        pipeline = self._load_pipeline()
        failed: list[tuple[Path, Exception]] = []
        transcribe_kwargs = self._transcribe_kwargs()
        with tqdm(total=len(targets), desc="Transcribing", unit="file") as pbar:
            with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                future_to_audio = {
                    executor.submit(
                        self._transcribe_file,
                        pipeline,
                        audio_path,
                        transcribe_kwargs=transcribe_kwargs,
                    ): audio_path
                    for audio_path in targets
                }
                for future in as_completed(future_to_audio):
                    audio_path = future_to_audio[future]
                    try:
                        future.result()
                    except Exception as exc:  # pragma: no cover - whisper errors depend on runtime env
                        logging.exception("Failed to transcribe %s", audio_path)
                        failed.append((audio_path, exc))
                    finally:
                        pbar.update(1)

        logging.info("Transcription complete. total=%d failed=%d", len(targets), len(failed))
        if failed:
            example_audio, example_exc = failed[0]
            logging.error("Example transcription failure %s: %s", example_audio, example_exc)

    def _segments_to_dicts(self, segments: list[Segment]) -> list[dict[str, Any]]:
        """Convert Segment objects into dictionaries ready for JSON."""
        output: list[dict[str, Any]] = []
        for seg in segments:
            output.append(dataclasses.asdict(seg))
            # item: dict[str, Any] = {
            #     "id": seg.id,
            #     "seek": seg.seek,
            #     "start": seg.start,
            #     "end": seg.end,
            #     "text": seg.text,
            #     "tokens": seg.tokens,
            #     "temperature": seg.temperature,
            #     "avg_logprob": seg.avg_logprob,
            #     "compression_ratio": seg.compression_ratio,
            #     "no_speech_prob": seg.no_speech_prob,
            # }
            # words: list[Word] | None = getattr(seg, "words", None)
            # if words:
            #     item["words"] = [
            #         {
            #             "start": w.start,
            #             "end": w.end,
            #             "word": w.word,
            #             "probability": w.probability,
            #         }
            #         for w in words
            #     ]
            # output.append(item)
        return output

    def _write_transcript(self, audio_path: Path, info: Any, segments: list[Segment]) -> None:
        """Write the transcription metadata and segments to disk as JSON."""
        transcript_path = audio_path.with_suffix(".json")
        text = " ".join(seg.text.strip() for seg in segments).strip()
        payload = {
            "audio_file": str(audio_path),
            "channel": audio_path.stem,
            "model": self.model_name,
            "text": text,
            "language": getattr(info, "language", None),
            "language_probability": getattr(info, "language_probability", None),
            "duration": getattr(info, "duration", None),
            "segments": self._segments_to_dicts(segments),
        }
        transcript_path.write_text(json.dumps(payload, indent=2))

    def run(self) -> None:
        """Execute the full pipeline: split audio then transcribe outputs."""
        self.preprocess_audio()
        self.transcribe_outputs()
