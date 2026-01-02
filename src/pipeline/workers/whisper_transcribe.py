from __future__ import annotations

import dataclasses
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from multiprocessing import Event, Process
from pathlib import Path
from typing import Any, Self

import ctranslate2
from faster_whisper import BatchedInferencePipeline, WhisperModel
from faster_whisper.transcribe import Segment
from sqlmodel import select
from tqdm import tqdm

from api.db import Database
from api.models import CallRecord, PipelineStatus
from pipeline.utils.const import AUDIO_EXTS, chunked
from pipeline.utils.subprocess_pool import SubprocessPool


@dataclass
class Transcript:
    call_uuid: str
    duration: float
    metadata: dict
    segments: list[ConversationSegment]

    def __post_init__(self):
        """ Enforce sorted segments """
        self.segments = sorted(self.segments, key=lambda s: (s.start, s.end))

    @classmethod
    def from_json(cls, json: dict[str, Any]) -> Self:
        return cls(
            call_uuid=json["call_uuid"],
            duration=json["duration"],
            metadata=json["metadata"],
            segments=[ConversationSegment.from_json(segment) for segment in json["segments"]]
        )

    @classmethod
    def from_whisper_json(cls, json: dict[str, Any]) -> Self:
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
                segments.append(ConversationSegment.from_whisper_json(segment, json["channel"]))
            
            return cls(
                call_uuid=call_uuid,
                duration=duration,
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
    def from_json(cls, json: dict[str, Any]) -> Self:
        try:            
            return cls(
                **json
            )
        except KeyError as e:
            raise ValueError(f"Missing required field: {e}") from e

    @classmethod
    def from_whisper_json(cls, json: dict[str, Any], speaker: str) -> Self:
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



class WhisperTranscribe(Process):
    def __init__(
        self,
        input_root: Path,
        output_root: Path,
        device: str,
        device_config: dict[str, Any],
        merge_segments_s: float | None,
        force: dict[str, bool],
        whisper_model_kwargs: dict[str, Any],
        sleep_s: float = 60,
        db_commit_batch_size: int = 32,
    ) -> None:
        """Configure the transcription pipeline and ensure output directories exist."""
        super().__init__()
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
        self.sleep_s: float = sleep_s
        self.db_commit_batch_size: int = db_commit_batch_size

        self.left_channel_name: str = "customer"
        self.right_channel_name: str = "store"

        self._db = None
        self._stop_event = Event()

        self._model: WhisperModel | None = None
        self._pipeline: BatchedInferencePipeline | None = None
    
    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = Database()
        return self._db

    def stop(self, timeout: float = 60.0, terminate_timeout: float = 10.0) -> None:
        self._stop_event.set()
        if os.getpid() == self.pid or self.pid is None:
            return
        self.join(timeout=timeout)
        if self.is_alive():
            self.terminate()
            self.join(timeout=terminate_timeout)

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

    def get_call_ids(self) -> list[str]:
        """Return call_ids in DB with status == DOWNLOADED, ordered by newest first."""
        with self.db.session() as session:
            statement = (
                select(CallRecord)
                .where(CallRecord.status == PipelineStatus.DOWNLOADED)
                .order_by(CallRecord.created_at.desc())
            )
            records = list(session.exec(statement))

        call_ids: list[str] = []
        for call in records:
            if not call.audio_file_path:
                logging.warning(f"Downloaded call {call.id} missing audio_file_path")
                continue
            audio_path = Path(call.audio_file_path)
            if not audio_path.exists():
                logging.warning(f"Downloaded call {call.id} missing audio file {audio_path}")
                continue
            call_ids.append(call.id)
        return call_ids

    def iter_inputs(self, call_ids: set | None) -> dict[str, Path]:
        """ Yield every input audio file that matches the provided extensions.
            Checks if the input id is in call_ids if provided.
            If call_ids are not provided, creates a list based on the files found.

            Return
            id_src_files: dict[str(id), Path(path_to_src_file)]
        
        """
        exts = tuple(e.lower() for e in AUDIO_EXTS)
        src_files = [p for p in self.input_root.rglob("*") if p.is_file() and p.suffix.lower() in exts]

        if call_ids is None:
            id_src_files = {src_file.stem: src_file for src_file in src_files}
            return dict(sorted(id_src_files.items()))           
        else:
            id_src_files = {src_file.stem: src_file for src_file in src_files if src_file.stem in call_ids}
            return dict(sorted(id_src_files.items()))
    
    def split_audio_path(self, id: str, mkdir: bool = False) -> tuple[Path, Path]:
        """ Turn audio file id to output audio files paths. """
        output_dir = self.output_root / id
        if mkdir:
            output_dir.mkdir(parents=True, exist_ok=True)
        left = output_dir / f"{self.left_channel_name}.wav"
        right = output_dir / f"{self.right_channel_name}.wav"   
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

    def build_commands(self, force_preprocess: bool, call_ids: set | None) -> tuple[list[list[str]], dict[str, Path]]:
        """Assemble split commands for any recordings that still need processing."""
        cmds: list[list[str]] = []
        src_files = self.iter_inputs(call_ids)
        for id in src_files:
            out_left, out_right = self.split_audio_path(id, mkdir=True)
            if not force_preprocess and out_left.exists() and out_right.exists():
                continue
            cmds.append(self.ffmpeg_split_cmd(src_files[id], out_left, out_right))
        return cmds, src_files
    
    def preprocess_audio(self, force_preprocess: bool, call_ids: set | None) -> set:
        """Split every stereo recording into normalized mono speaker channels."""
        commands, src_files = self.build_commands(force_preprocess, call_ids)
        if not commands:
            logging.info("No new recordings require channel splitting.")
            return set(src_files)

        pool = SubprocessPool(
            max_workers=self.num_workers,
            capture_stdout=True,
            capture_stderr=True,
            nice=10,
            desc="Splitting",
        )
        results = pool.run(commands)
        _call_ids = list(src_files)
        failed = {_call_ids[idx]: (commands[idx], r) for idx, r in enumerate(results) if r.rc != 0}
        logging.info(f"Split complete. total={len(results)} failed={len(failed)}")
        if failed:
            logging.error(f"Splitting failures: \n{failed}")
        return set(src_files) - failed.keys()

    def _transcribe_file(self, pipeline: BatchedInferencePipeline, audio_path: Path, transcribe_kwargs: dict[str, Any],) -> None:
        """Transcribe a single mono channel and persist its transcript."""
        segments_iter, info = pipeline.transcribe(
            str(audio_path),
            batch_size=self.batch_size,
            **transcribe_kwargs,
        )
        segments = list(segments_iter)
        self._write_transcript(audio_path, info, segments)

    def transcribe(self, force_transcribe: bool, call_ids: set) -> set:
        """Transcribe each split file in parallel, tracking failures and progress."""
        targets: list[Path] = []
        for call_id in call_ids:
            audio_paths = self.split_audio_path(call_id)
            for audio_path in audio_paths:
                if force_transcribe or not audio_path.with_suffix(".json").exists():
                    targets.append(audio_path)

        if not targets:
            logging.info("No files need transcription.")
            return set()

        pipeline = self._load_pipeline()
        failed: dict[str, Exception] = {}
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
                        logging.exception(f"Failed to transcribe {audio_path}")
                        failed[audio_path.parent.name] = exc
                    finally:
                        pbar.update(1)

        logging.info(f"Transcription complete. total={len(targets)} failed={len(failed)}")
        if failed:
            logging.error(f"Transcription failures:\n{failed}")

        return (call_ids - failed.keys())

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

    def postprocess_transcripts(self, force_postprocess: bool, call_ids: set[str]) -> set[str]:
        """
        Stitch `customer.json` + `store.json` into a single, time-ordered conversation.

        Writes per-call outputs next to the channel transcripts:
        - `conversation.json`: structured timeline plus raw per-channel segments
        - `conversation.txt`: LLM-friendly "Speaker: text" transcript
        """
        transcripts: list[Transcript] = []
        failed_calls = set()
        if not self.output_root.exists():
            return set()

        for call_id in call_ids:
            left_path = self.output_root / call_id / f"{self.left_channel_name}.json"
            right_path = self.output_root / call_id / f"{self.right_channel_name}.json"
            if not left_path.exists() or not right_path.exists():
                logging.error(f"One of these paths does not exist for transcription merging\n{left_path}\n{right_path}")
                failed_calls.add(call_id)
                continue

            out_json = self.output_root / call_id / "conversation.json"
            out_txt = self.output_root / call_id / "conversation.txt"
            if not force_postprocess and out_json.exists():
                continue

            try:
                left_transcript = Transcript.from_whisper_json(json.loads(left_path.read_text()))
                right_transcript = Transcript.from_whisper_json(json.loads(right_path.read_text()))
            except Exception:
                logging.exception(f"Failed to read transcript JSON under {self.output_root / call_id}")
                failed_calls.add(call_id)
                continue
            
            complete_transcript = Transcript.merge_transcripts(left_transcript, right_transcript, self.merge_segments_s)
            out_json.write_text(json.dumps(complete_transcript.to_dict(), indent=2))
            out_txt.write_text(complete_transcript.text)
            transcripts.append(complete_transcript)

        logging.info(f"Post-processed {len(transcripts)} transcripts")
        return call_ids - failed_calls

    def run_transcription_pipeline(self, call_ids: set[str] | None) -> set[str]:
        """Execute one pass of the full pipeline: split audio then transcribe outputs."""
        call_ids = self.preprocess_audio(self.force_preprocess, call_ids)
        call_ids = self.transcribe(self.force_transcribe, call_ids)
        call_ids = self.postprocess_transcripts(self.force_postprocess, call_ids)
        return call_ids
    
    def update_db(self, call_ids: set[str]) -> None:
        if not len(call_ids):
            logging.info("No calls to update in the DB.")
            return
        
        with self.db.session() as session:
            record_map: dict[str, CallRecord] = {}
            successfull_calls: int = 0
            failed_calls: list = []
            for chunk in chunked(list(call_ids), 1000):
                record_map.update(CallRecord.get_from_id(session, chunk))
            
            for call_id in record_map:
                call_record = record_map[call_id]
                # speaker_1_transpath = self.output_root / call_id / f"{self.left_channel_name}.json"
                # speaker_2_transpath = self.output_root / call_id / f"{self.right_channel_name}.json"
                conversation = self.output_root / call_id / f"conversation.json"
                try:
                    # speaker_1_transcript = Transcript.from_json(json.loads(speaker_1_transpath.read_text()))
                    # speaker_2_transcript = Transcript.from_json(json.loads(speaker_2_transpath.read_text()))
                    conversation_transcript = Transcript.from_json(json.loads(conversation.read_text()))
                    call_record.raw_whisper_transcript = conversation_transcript.to_dict()
                    call_record.transcript_text = conversation_transcript.text
                    call_record.status = PipelineStatus.TRANSCRIBED
                    successfull_calls += 1
                except Exception:
                    logging.exception(f"Failed to read transcript JSON under {self.output_root / call_id}")
                    failed_calls.append(call_id)
                    call_record.status = PipelineStatus.FAILED
            session.commit()
        logging.info(f"Updated {successfull_calls} call_records with transcripts.")
        return

    def run(self) -> None:
        """Execute the pipeline using DB state as the trigger."""
        while not self._stop_event.is_set():
            for call_ids in chunked(self.get_call_ids(), self.db_commit_batch_size):
                if not call_ids:
                    logging.info("No downloaded calls found.")
                    self._stop_event.wait(self.sleep_s)
                    continue

                completed_ids = self.run_transcription_pipeline(set(call_ids))
                if completed_ids:
                    self.update_db(completed_ids)
            self._stop_event.wait(self.sleep_s)
