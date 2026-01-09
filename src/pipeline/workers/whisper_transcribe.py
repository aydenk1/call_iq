from __future__ import annotations

import dataclasses
import json
import logging
import os
import time
from dataclasses import dataclass
from multiprocessing import Event, Process
from pathlib import Path
from typing import Any, Self

from sqlmodel import select
from tqdm import tqdm

from api.db import Database
from api.models import CallRecord, PipelineStatus
from pipeline.utils import AUDIO_EXTS, SubprocessPool, chunked, configure_logging, setup_worker_logging, update_call_record_status
from pipeline.whisper_models import TranscriptionInfo, TranscriptionResult, WhisperBackend, create_backend
from pipeline.whisper_models.whisperx_alignment_backend import WhisperXAlignmentBackend


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
        alignment_model_kwargs: dict[str, Any],
        whisper_backend: str = "faster-whisper",
        alignment_backend: str = "whisperx",
        sleep_s: float = 60,
        db_commit_batch_size: int = 64,
        log_level: int | None = None,
        log_dir: Path | None = None,
    ) -> None:
        """Configure the transcription pipeline and ensure output directories exist."""
        super().__init__()

        self.input_root: Path = Path(input_root)
        self.output_root: Path = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

        self.model_name: str = device_config[device]["model_name"]
        self.batch_size: int = device_config[device]["batch_size"]

        self.num_workers: int = self._resolve_cpu_count(device_config[device]["num_workers"])
        self.device: str = device_config[device]["device"]
        self.compute_type: str = device_config[device]["compute_type"]
        self.merge_segments_s = merge_segments_s
        
        # Ensure rest of pipeline runs if earlier options are forced
        self.force_preprocess: bool = force["preprocess"]
        self.force_transcribe: bool = force["transcribe"] or self.force_preprocess
        self.force_postprocess: bool = force["postprocess"] or self.force_transcribe

        self.whisper_model_kwargs: dict[str, Any] = whisper_model_kwargs
        self.whisper_backend_name: str = whisper_backend

        self.activate_word_alignment: bool = True if len(alignment_backend) else False
        self.alignment_model_kwargs: dict[str, Any] = alignment_model_kwargs
        self.alignment_backend_name: str = alignment_backend

        self.sleep_s: float = sleep_s
        self.db_commit_batch_size: int = db_commit_batch_size
        self.log_level = log_level
        self.log_dir = log_dir

        self.left_channel_name: str = "customer"
        self.right_channel_name: str = "store"

        self._db = None
        self._stop_event = Event()

        self._whisper_backend: WhisperBackend | None = None
        self._word_alignment_backend: WhisperBackend | None = None
        self._transcribe_config = {
            "backend": self.whisper_backend_name,
            "model_name": self.model_name,
            "batch_size": self.batch_size,
            "num_workers": self.num_workers,
            "device": self.device,
            "compute_type": self.compute_type,
            "merge_segments_s": self.merge_segments_s,
            "force": {
                "preprocess": self.force_preprocess,
                "transcribe": self.force_transcribe,
                "postprocess": self.force_postprocess,
            },
            "whisper_model_kwargs": dict(self.whisper_model_kwargs),
            "alignment_model_kwargs": dict(self.alignment_model_kwargs),
        }
    
    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = Database()
        return self._db
    
    @property
    def whisper_backend(self) -> WhisperBackend:
        if self._whisper_backend is None:
            self._whisper_backend = create_backend(
                backend_name=self.whisper_backend_name,
                model_name=self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                num_workers=self.num_workers,
                model_kwargs=self.whisper_model_kwargs,
            )
        return self._whisper_backend

    @property
    def word_alignment_backend(self) -> WhisperBackend:
        if self._word_alignment_backend is None:
            self._word_alignment_backend = create_backend(
                backend_name=self.alignment_backend_name,
                model_name=self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                num_workers=self.num_workers,
                model_kwargs=self.whisper_model_kwargs,
            )
        return self._word_alignment_backend


    def stop(self, timeout: float = 60.0, terminate_timeout: float = 10.0) -> None:
        self._stop_event.set()
        if os.getpid() == self.pid or self.pid is None:
            return
        self.join(timeout=timeout)
        if self.is_alive():
            self.terminate()
            self.join(timeout=terminate_timeout)

    @staticmethod
    def _resolve_cpu_count(num_workers) -> int:
        if num_workers != "auto":
            return num_workers
        
        cpu_count = os.cpu_count()
        if cpu_count is None:
            return 1
        return cpu_count
        
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
            return call_ids

        failed: dict[str, Exception] = {}
        results: list[TranscriptionResult] = []
        with tqdm(total=len(targets), desc="Transcribing", unit="file") as pbar:
            for result in self.whisper_backend(
                targets,
                batch_size=self.batch_size,
            ):
                results.append(result)
                pbar.update(1)
                

        if self.activate_word_alignment:
            aligned_results: list[TranscriptionResult] = []
            with tqdm(total=len(targets), desc="Transcribing", unit="file") as pbar:
                for result in self.word_alignment_backend(results):
                    aligned_results.append(result)
                    pbar.update(1)
            results = aligned_results

        for result in results:
            if result.error:  # pragma: no cover - whisper errors depend on runtime env
                logging.exception(f"Failed to transcribe {result.audio_path}")
                failed[result.audio_path.parent.name] = result.error
            self._write_transcript(result.audio_path, result.info, result.segments)
                
        logging.info(f"Transcription complete. total={len(targets)} failed={len(failed)}")
        if failed:
            logging.error(f"Transcription failures:\n{failed}")

        return (call_ids - failed.keys())

    def _write_transcript(
        self,
        audio_path: Path,
        info: TranscriptionInfo,
        segments: list[dict[str, Any]],
    ) -> None:
        """Write the transcription metadata and segments to disk as JSON."""
        transcript_path = audio_path.with_suffix(".json")
        text = " ".join(str(seg.get("text", "")).strip() for seg in segments).strip()
        payload = {
            "audio_file": str(audio_path),
            "channel": audio_path.stem,
            "model": info.model,
            "text": text,
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "segments": segments,
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
            complete_transcript.metadata["whisper_transcribe"] = dict(self._transcribe_config)
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
                conversation = self.output_root / call_id / f"conversation.json"
                try:
                    conversation_transcript = Transcript.from_json(json.loads(conversation.read_text()))
                    raw_list = list(call_record.raw_whisper_transcript) if len(call_record.raw_whisper_transcript) else []
                    raw_list.append(conversation_transcript.to_dict())
                    call_record.raw_whisper_transcript = raw_list
                    call_record.transcript_text = conversation_transcript.text
                    call_record.set_status(session, PipelineStatus.TRANSCRIBED, source=self.name)
                    successfull_calls += 1
                except Exception:
                    logging.exception(f"Failed to read transcript JSON under {self.output_root / call_id}")
                    failed_calls.append(call_id)
                    call_record.set_status(session, PipelineStatus.FAILED, source=self.name)
            session.commit()
        logging.info(f"Updated {successfull_calls} call_records with transcripts.")
        return

    def run(self) -> None:
        """Execute the pipeline using DB state as the trigger."""
        if self.log_level is not None:
            if self.log_dir is None:
                raise ValueError("log_dir is required when log_level is set.")
            setup_worker_logging(self.name, self.log_level, self.log_dir)
     
        while not self._stop_event.is_set():
            calls = self.get_call_ids()
            logging.info(f"Found {len(calls)} calls with CallRecord.Status == 'DOWNLOADED'")
            for call_chunk in chunked(calls, self.db_commit_batch_size):
                if not call_chunk:
                    break
                
                st = time.perf_counter()
                completed_ids = self.run_transcription_pipeline(set(call_chunk))
                logging.info(f"Finished transcription chunk in {(time.perf_counter()-st) / 60:.3} mins")
                if completed_ids:
                    self.update_db(completed_ids)
            self._stop_event.wait(self.sleep_s)


def _load_config(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    import yaml

    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[3]
    config = _load_config(base_dir / "config.yml")
    config["whisper"].pop("activate")

    work_dir = Path(config["global"]["work_dir"])
    if not work_dir.is_absolute():
        work_dir = base_dir / work_dir
    recording_dir = work_dir / config["global"]["recording_dir"]
    whisper_dir = work_dir / config["global"]["whisper_dir"]

    log_level = logging.DEBUG if config["global"]["verbose"] else logging.INFO
    configure_logging(log_level)
    log_dir = work_dir / "logs"

    db = Database()
    db.create_db_and_tables()

    from pipeline.main import get_call_ids

    update_call_record_status(db, get_call_ids(), PipelineStatus.DOWNLOADED)

    transcriber = WhisperTranscribe(
        input_root=recording_dir,
        output_root=whisper_dir,
        **config["whisper"],
        log_level=log_level,
        log_dir=log_dir,
    )
    completed_ids = transcriber.run_transcription_pipeline(set(get_call_ids()))
    if completed_ids:
        transcriber.update_db(completed_ids)
