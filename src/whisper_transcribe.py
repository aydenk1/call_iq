from __future__ import annotations

import dataclasses

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable
from datetime import datetime, timezone

from faster_whisper import BatchedInferencePipeline, WhisperModel
from faster_whisper.transcribe import Segment, Word
from tqdm import tqdm

from subprocess_pool import SubprocessPool

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
        self.decode_options = {"vad_parameters": {"min_silence_duration_ms": 3000}}
        self.merge_segments_s: float | None = None

        self.batch_size = batch_size
        self.num_workers = max(1, (os.cpu_count() or 2))
        self.device = self._resolve_device()
        self.compute_type = self._default_compute_type(self.device)

        self._model: WhisperModel | None = None
        self._pipeline: BatchedInferencePipeline | None = None

        self.segment_metadata_passthrough_keys = {"start", "end", "text","avg_logprob", "compression_ratio", "no_speech_prob","temperature"}

    def iter_inputs(self, exts: Iterable[str] = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")) -> list[Path]:
        """Yield every input audio file that matches the provided extensions."""
        exts = tuple(e.lower() for e in exts)
        return sorted([p for p in self.input_root.rglob("*") if p.is_file() and p.suffix.lower() in exts])
    
    def whisper_out_path(self, src: Path):
        """Return output folder for whisper to work in given an input path"""
        rel = src.relative_to(self.input_root)
        stem = rel.with_suffix("")  # drop input extension
        base = self.output_root / stem
        return base

    def out_paths(self, src: Path) -> tuple[Path, Path]:
        """Return output paths for the left and right channels derived from src."""
        base = self.whisper_out_path(src)
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

    def build_commands(self) -> tuple[list[list[str]], list[Path]]:
        """Assemble split commands for any recordings that still need processing."""
        cmds: list[list[str]] = []
        src_files = self.iter_inputs()
        for src in src_files:
            out_left, out_right = self.out_paths(src)
            if not self.overwrite and out_left.exists() and out_right.exists():
                continue
            cmds.append(self.ffmpeg_split_cmd(src, out_left, out_right))
        return cmds, src_files
    
    def preprocess_audio(self) -> None:
        """Split every stereo recording into normalized mono speaker channels."""
        commands, src_files = self.build_commands()
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

        for src in src_files:
            timestamp_file = self.whisper_out_path(src) / "timestamp.json"
            timestamp = src.stat().st_mtime
            timestamp_file.write_text(json.dumps({
                "datetime_utc": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
                "datetime_ep": timestamp
                }))

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

    def merge_segments(self, segments: list[dict], gap_threshold_s: float = 2.0) -> list[dict[str, Any]]:
        """
        Merge adjacent whisper segments into larger utterances.

        Assumptions:
        - Segments belong to a single speaker/channel (no speaker switching here).
        - Segment dicts contain at least: {"start": float, "end": float, "text": str}.
        - Two consecutive segments are stitched when their gap is <= gap_threshold_s (secs).

        NOTE Not tested, will need to passthrough all information as well.
        
        Returns a compact list of utterances suitable for downstream data extraction.
        """
        if not segments:
            return []

        normalized: list[dict[str, Any]] = []
        for idx, seg in enumerate(segments):
            if not isinstance(seg, dict):
                continue
            start = seg.get("start", None)
            end = seg.get("end", None)
            text = seg.get("text", "")

            try:
                start_f = float(start)
                end_f = float(end)
            except (TypeError, ValueError):
                continue

            if end_f < start_f:
                logging.info("Segment end is before start! %s", seg)
                continue

            text_s = str(text).strip()
            if not text_s:
                continue

            normalized.append(
                {
                    "start": start_f,
                    "end": end_f,
                    "text": text_s,
                    "_source_index": idx,
                }
            )

        if not normalized:
            return []

        normalized.sort(key=lambda s: (s["start"], s["end"]))
        merged: list[dict[str, Any]] = []

        cur_start = normalized[0]["start"]
        cur_end = normalized[0]["end"]
        cur_text_parts: list[str] = [normalized[0]["text"]]
        cur_source_indices: list[int] = [normalized[0]["_source_index"]]

        for seg in normalized[1:]:
            seg_start = seg["start"]
            seg_end = seg["end"]
            seg_text = seg["text"]

            gap = seg_start - cur_end
            if gap <= gap_threshold_s:
                cur_text_parts.append(seg_text)
                cur_end = max(cur_end, seg_end)
                cur_source_indices.append(seg["_source_index"])
            else:
                merged.append(
                    {
                        "start": cur_start,
                        "end": cur_end,
                        "midpoint": (cur_start + cur_end) / 2.0,
                        "text": " ".join(cur_text_parts).strip(),
                    }
                )
                cur_start = seg_start
                cur_end = seg_end
                cur_text_parts = [seg_text]
                cur_source_indices = [seg["_source_index"]]

        merged.append(
            {
                "start": cur_start,
                "end": cur_end,
                "midpoint": (cur_start + cur_end) / 2.0,
                "text": " ".join(cur_text_parts).strip(),
            }
        )

        return merged

    def _write_transcript(self, audio_path: Path, info: Any, segments: list[Segment]) -> None:
        """Write the transcription metadata and segments to disk as JSON."""
        transcript_path = audio_path.with_suffix(".json")
        text = " ".join(seg.text.strip() for seg in segments).strip()
        segments_raw = [dataclasses.asdict(seg) for seg in segments]
        payload = {
            "audio_file": str(audio_path),
            "channel": audio_path.stem,
            "model": self.model_name,
            "text": text,
            "language": getattr(info, "language", None),
            "language_probability": getattr(info, "language_probability", None),
            "duration": getattr(info, "duration", None),
            "segments": segments_raw,
        }
        if self.merge_segments_s is not None:
            payload["merged_segments"] = self.merge_segments(segments_raw, gap_threshold_s=self.merge_segments_s)
        transcript_path.write_text(json.dumps(payload, indent=2))

    def postprocess_transcripts(self) -> list[Path]:
        """
        Stitch `customer.json` + `store.json` into a single, time-ordered conversation.

        Writes per-call outputs next to the channel transcripts:
        - `conversation.json`: structured timeline plus raw per-channel segments
        - `conversation.txt`: LLM-friendly "Speaker: text" transcript
        """
        written: list[Path] = []
        
        audio_file_metadata = {"audio_file", "model", "language"}
        if not self.output_root.exists():
            return written

        for call_dir in sorted([p for p in self.output_root.iterdir() if p.is_dir()]):
            customer_path = call_dir / "customer.json"
            store_path = call_dir / "store.json"
            timestamp = call_dir / "timestamp.json"
            if not customer_path.exists() or not store_path.exists() or not timestamp.exists():
                logging.error(f"One of these paths does not exist for transcription merging\n{customer_path}\n{store_path}")
                continue

            out_json = call_dir / "conversation.json"
            out_txt = call_dir / "conversation.txt"
            if not self.overwrite and out_json.exists():
                continue

            try:
                customer = json.loads(customer_path.read_text())
                store = json.loads(store_path.read_text())
                timestamp = json.loads(timestamp.read_text())
            except Exception:
                logging.exception(f"Failed to read transcript JSON under {call_dir}")
                continue

            transcripts = [customer, store]
            segments_with_channel = []
            recording_metadata = {}
            for tr in transcripts:
                channel = str(tr.get("channel"))
                recording_metadata[f"{channel}_metadata"] = {key: tr[key] for key in audio_file_metadata}
                for seg in tr.get("segments", []):
                    seg_w_metadata = {k: v for k, v in seg.items() if k in self.segment_metadata_passthrough_keys}
                    seg_w_metadata["channel"] = channel
                    segments_with_channel.append(seg_w_metadata)

            segments_with_channel.sort(key=lambda t: (t["start"], t["end"], t["channel"]))
            conversation_text = "\n".join([f'{t["channel"]}: {t["text"]}' for t in segments_with_channel]).strip()

            duration = None
            try:
                duration = max(
                    float(customer.get("duration") or 0.0),
                    float(store.get("duration") or 0.0),
                )
            except (TypeError, ValueError):
                duration = None

            payload = {
                "call_id": call_dir.name,
                "call_datetime_utc": timestamp["datetime_utc"],
                "call_datetime_ep": timestamp["datetime_ep"],
                "duration": duration,
                "conversation_text": conversation_text,
            }
            payload.update(recording_metadata)
            payload["segments_with_channel"] = segments_with_channel

            out_json.write_text(json.dumps(payload, indent=2))
            out_txt.write_text(conversation_text + "\n")
            written.extend([out_json, out_txt])

        logging.info("Postprocess complete. calls=%d outputs=%d", len(written) // 2, len(written))
        return written
    
    def run(self) -> None:
        """Execute the full pipeline: split audio then transcribe outputs."""
        self.preprocess_audio()
        self.transcribe_outputs()
        self.postprocess_transcripts()
