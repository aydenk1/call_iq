from __future__ import annotations

import dataclasses
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Self

import ctranslate2
from faster_whisper import BatchedInferencePipeline, WhisperModel
from faster_whisper.transcribe import Segment
from tqdm import tqdm

from subprocess_pool import SubprocessPool


@dataclass
class Transcript:
    call_uuid: str
    duration: float
    timestamp: str
    metadata: dict
    segments: list[ConversationSegment]

    def __post_init__(self):
        """ Enforce sorted segments """
        self.segments = sorted(self.segments, key=lambda s: (s.start, s.end))

    @classmethod
    def from_json(cls, json: dict[str, Any], timestamp: str) -> Self:
        try:
            call_uuid = json["audio_file"].split("/")[-2]
            duration = json["duration"]
            metadata = {
                    json["channel"]: {
                        "audio_file": json["audio_file"],
                        "model": json["model"],
                    }       
                }
            segments = []
            for segment in json["segments"]:
                segments.append(ConversationSegment.from_json(segment, json["channel"]))
            
            return cls(
                call_uuid=call_uuid,
                duration=duration,
                timestamp=timestamp,
                metadata=metadata,
                segments=segments,
            )
        except KeyError as e:
            raise ValueError(f"Missing required field: {e}") from e
        
    def merge_segments(self, merge_threshold_s: float) -> None:
        """ In-place merging of segments that are adjacent with a gap <= merge_threshold_s (seconds) """
        if not self.segments:
            return
        
        merged_segs = []
        cur = self.segments[0]
        for seg in self.segments[1:]:
            gap = seg.start - cur.end
            if gap <= merge_threshold_s:
                cur.end = max(cur.end, seg.end)
                cur.text = f"{cur.text} {seg.text}".strip()
            else:
                merged_segs.append(cur)
                cur = seg
        merged_segs.append(cur)
        self.segments = merged_segs
        return
    
    @staticmethod
    def merge_transcripts(transcript_1: Transcript, transcript_2: Transcript, merge_threshold_s: float | None = None) -> Transcript:
        if transcript_1.call_uuid != transcript_2.call_uuid:
            raise ValueError(f"Transcript 1 call_uuid: {transcript_1.call_uuid} != Transcript 2 call_uuid: {transcript_2.call_uuid}")
        if transcript_1.timestamp != transcript_2.timestamp:
            raise ValueError(f"Transcript 1 timestamp: {transcript_1.timestamp} != Transcript 2 timestamp: {transcript_2.timestamp}")
        duration = max(transcript_1.duration, transcript_2.duration)
        merged_metadata = {**transcript_1.metadata, **transcript_2.metadata}

        if merge_threshold_s is not None:
            transcript_1.merge_segments(merge_threshold_s)
            transcript_2.merge_segments(merge_threshold_s)

        merged_conversation = sorted(
            [*transcript_1.segments, *transcript_2.segments],
            key=lambda s: (s.start, s.end, s.speaker)
        )

        return Transcript(
            call_uuid=transcript_1.call_uuid,
            duration=duration,
            timestamp=transcript_1.timestamp,
            metadata=merged_metadata,
            segments=merged_conversation
        )
    
    @property
    def text(self) -> str:
        return "\n".join([f"{seg.speaker}: {seg.text}" for seg in self.segments]).strip()
    
    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["text"] = self.text
        return data



@dataclass
class ConversationSegment:
    speaker: str
    text: str
    start: float
    end: float
    avg_logprob: float
    compression_ratio: float
    
    @classmethod
    def from_json(cls, json: dict[str, Any], speaker: str) -> Self:
        try:
            speaker = speaker
            text = json["text"]
            start = json["start"]
            end = json["end"]
            avg_logprob = json["avg_logprob"]
            compression_ratio = json["compression_ratio"]
            
            return cls(
                speaker=speaker,
                text=text,
                start=start,
                end=end,
                avg_logprob=avg_logprob,
                compression_ratio=compression_ratio
            )
        except KeyError as e:
            raise ValueError(f"Missing required field: {e}") from e



class WhisperTranscribe:
    def __init__(
        self,
        input_root: Path,
        output_root: Path,
        device: str,
        device_config: dict[str, Any],
        merge_segments_s: float | None,
        force: dict[str, bool],
        whisper_model_kwargs: dict[str, Any]
    ) -> None:
        """Configure the transcription pipeline and ensure output directories exist."""
        self.input_root: Path = Path(input_root)
        self.output_root: Path = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

        self.model_name: str = device_config[device]["model_name"]
        self.batch_size: int = device_config[device]["batch_size"]

        self.num_workers: int = self._resolve_cpu_count(device_config[device]["num_workers"])
        self.device: str = self._resolve_device(device_config[device]["device"]) 
        self.compute_type: str = device_config[device]["compute_type"]
        self.merge_segments_s = merge_segments_s
        
        # Ensure rest of pipeline runs if earlier options are forced
        self.force_preprocess: bool = force["preprocess"]
        self.force_transcribe: bool = force["transcribe"] or self.force_preprocess
        self.force_postprocess: bool = force["postprocess"] or self.force_transcribe

        self.whisper_model_kwargs: dict[str, Any] = whisper_model_kwargs

        self._model: WhisperModel | None = None
        self._pipeline: BatchedInferencePipeline | None = None

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
        fc = (
            "[0:a]channelsplit=channel_layout=stereo[left][right];"
            "[left]highpass=f=120,lowpass=f=7500,"
            "agate=threshold=0.01:ratio=10:attack=10:release=250,"
            #"loudnorm=I=-18:TP=-2:LRA=11,"
            "aresample=16000,pan=mono|c0=c0[left_m];"
            "[right]highpass=f=120,lowpass=f=7500,"
            "agate=threshold=0.01:ratio=10:attack=10:release=250,"
            #"loudnorm=I=-18:TP=-2:LRA=11,"
            "aresample=16000,pan=mono|c0=c0[right_m]"
        )

        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
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

    def build_commands(self, force_preprocess: bool) -> tuple[list[list[str]], list[Path]]:
        """Assemble split commands for any recordings that still need processing."""
        cmds: list[list[str]] = []
        src_files = self.iter_inputs()
        for src in src_files:
            out_left, out_right = self.out_paths(src)
            if not force_preprocess and out_left.exists() and out_right.exists():
                continue
            cmds.append(self.ffmpeg_split_cmd(src, out_left, out_right))
        return cmds, src_files
    
    def preprocess_audio(self, force_preprocess: bool) -> None:
        """Split every stereo recording into normalized mono speaker channels."""
        commands, src_files = self.build_commands(force_preprocess)
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
    def _resolve_device(device) -> str:
        """Return the best available device (CUDA or CPU)."""
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
    
    @staticmethod
    def _resolve_cpu_count(num_workers) -> int:
        if num_workers != "auto":
            return num_workers
        
        cpu_count = os.cpu_count()
        if cpu_count is None:
            return 1
        return cpu_count

    def _load_model(self) -> WhisperModel:
        """Lazy-load the faster-whisper model instance."""
        if self._model is None:
            logging.info(f'Loading faster-whisper model {self.model_name} on {self.device} ({self.compute_type} {self.num_workers})')
                
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                num_workers=self.num_workers,
                cpu_threads=self.num_workers,
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

    def transcribe(self, force_transcribe: bool) -> None:
        """Transcribe each split file in parallel, tracking failures and progress."""
        targets: list[Path] = []
        for audio_path in self.iter_split_outputs():
            transcript_path = audio_path.with_suffix(".json")
            if transcript_path.exists() and not force_transcribe:
                continue
            targets.append(audio_path)

        if not targets:
            logging.info("No files need transcription.")
            return

        pipeline = self._load_pipeline()
        failed: list[tuple[Path, Exception]] = []
        with tqdm(total=len(targets), desc="Transcribing", unit="file") as pbar:
            with ThreadPoolExecutor(max_workers=self.num_workers // 2) as executor:
                future_to_audio = {
                    executor.submit(
                        self._transcribe_file,
                        pipeline,
                        audio_path,
                        transcribe_kwargs=self.whisper_model_kwargs,
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
        transcript_path.write_text(json.dumps(payload, indent=2))

    def postprocess_transcripts(self, force_postprocess: bool) -> list[Transcript]:
        """
        Stitch `customer.json` + `store.json` into a single, time-ordered conversation.

        Writes per-call outputs next to the channel transcripts:
        - `conversation.json`: structured timeline plus raw per-channel segments
        - `conversation.txt`: LLM-friendly "Speaker: text" transcript
        """
        transcripts: list[Transcript] = []
        if not self.output_root.exists():
            return transcripts

        for call_dir in sorted([p for p in self.output_root.iterdir() if p.is_dir()]):
            customer_path = call_dir / "customer.json"
            store_path = call_dir / "store.json"
            timestamp = call_dir / "timestamp.json"
            if not customer_path.exists() or not store_path.exists() or not timestamp.exists():
                logging.error(f"One of these paths does not exist for transcription merging\n{customer_path}\n{store_path}")
                continue

            out_json = call_dir / "conversation.json"
            out_txt = call_dir / "conversation.txt"
            if not force_postprocess and out_json.exists():
                continue

            try:
                timestamp = json.loads(timestamp.read_text())
                customer = Transcript.from_json(json.loads(customer_path.read_text()), timestamp)
                store = Transcript.from_json(json.loads(store_path.read_text()), timestamp)
            except Exception:
                logging.exception(f"Failed to read transcript JSON under {call_dir}")
                continue
            
            complete_transcript = Transcript.merge_transcripts(customer, store, self.merge_segments_s)
            out_json.write_text(json.dumps(complete_transcript.to_dict(), indent=2))
            out_txt.write_text(complete_transcript.text)
            transcripts.append(complete_transcript)

        logging.info(f"Post-processed {len(transcripts)} transcripts")
        return transcripts
    
    def run(self) -> None:
        """Execute the full pipeline: split audio then transcribe outputs."""
        self.preprocess_audio(self.force_preprocess)
        self.transcribe(self.force_transcribe)
        self.postprocess_transcripts(self.force_postprocess)
