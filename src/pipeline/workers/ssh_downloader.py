import hashlib
import logging
import os
import subprocess
from contextlib import ExitStack
from datetime import datetime, timezone
from itertools import islice
from multiprocessing import Event, Process
from pathlib import Path
from shutil import rmtree
from typing import Sequence

from tqdm import tqdm

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")


def chunked(seq: Sequence, n: int):
    it = iter(seq)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            return
        yield chunk


class SSHDownloader(Process):
    def __init__(self,
                 remote_host: str,
                 remote_dir: str,
                 local_dir: str,
                 use_db: bool = True,
                 sleep_s: int = 60) -> None:
        super().__init__()
        self.remote_host = remote_host
        self.remote_dir = Path(remote_dir)
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.local_temp_dir = self.local_dir.parent / f"{self.local_dir.name}.tmp"
        rmtree(self.local_temp_dir, ignore_errors=True)
        self.use_db = use_db
        self.sleep_s = sleep_s
        self._db = None
        self._stop_event = Event()
        self._last_local_hash: str | None = None
        
        self.ssh_base = [
            "ssh",
            "-oBatchMode=yes",
            "-oStrictHostKeyChecking=accept-new",
            "-oServerAliveInterval=15",
            "-oServerAliveCountMax=3",
            self.remote_host,
        ]
        return

    def stop(self) -> None:
        self._stop_event.set()

    def get_db_queue(self) -> set[str]:
        from api.db import Database
        from api.models import CallRecord, PipelineStatus

        if self._db is None:
            self._db = Database()
        with self._db.session() as session:
            return CallRecord.list_ids(session, status=PipelineStatus.QUEUED)

    def get_local_recordings(self) -> list[Path]:
        return sorted(
            [
                path
                for path in self.local_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in AUDIO_EXTS
            ]
        )

    def local_recordings_hash(self) -> str:
        hasher = hashlib.sha1()
        for path in self.get_local_recordings():
            rel = path.relative_to(self.local_dir)
            stat = path.stat()
            hasher.update(str(rel).encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(str(stat.st_size).encode("ascii"))
            hasher.update(b"\x00")
            hasher.update(str(stat.st_mtime_ns).encode("ascii"))
            hasher.update(b"\x00")
        return hasher.hexdigest()
    
    def update_db(self, succeeded_transfers: list[Path], failed_transfers: list[Path]):
        """ Initializes a CallRecord into the database for further processing in the pipeline.
            Any calls on disk not in the DB will also be initialized. 
            Only operates on audio files.

            Handles the following scenarios
            1. New files
            2. Forced queues
            3. Local files not in db
        """
        from api.db import Database
        from api.models import CallRecord, PipelineStatus

        if self._db is None:
            self._db = Database()

        with self._db.session() as session:
            processed_ids: set[str] = set()
            call_records: list[CallRecord] = []

            # Update DB with succeeded_transfers (new remote files OR requested update via CallRecord.status = QUEUED)
            for local_path in succeeded_transfers:
                call_id = local_path.stem
                processed_ids.add(call_id)
                call = session.get(CallRecord, call_id)
                created_at = datetime.fromtimestamp(local_path.stat().st_mtime, tz=timezone.utc)
                if call is None:
                    call = CallRecord(
                        id=call_id,
                        created_at=created_at,
                        duration_sec=0,
                        summary="",
                        audio_file_path=str(local_path),
                        status=PipelineStatus.DOWNLOADED,
                    )
                    call_records.append(call)
                else:
                    call.created_at = created_at
                    call.audio_file_path = str(local_path)
                    call.status = PipelineStatus.DOWNLOADED

            # Update DB failed transfers
            for local_path in failed_transfers:
                call_id = local_path.stem
                processed_ids.add(call_id)
                call = session.get(CallRecord, call_id)
                if call is None:
                    call = CallRecord(
                        id=call_id,
                        created_at=created_at,
                        duration_sec=0,
                        summary="",
                        audio_file_path=str(local_path),
                        status=PipelineStatus.FAILED,
                    )
                    call_records.append(call)
                call.status = PipelineStatus.FAILED

            # Add anything remaining that is not in the database but on disk. Skip any id in the failed list.
            local_files = self.get_local_recordings()
            local_by_id = {path.stem: path for path in local_files}
            remaining_ids = set(local_by_id.keys()) ^ CallRecord.list_ids(session)
            remaining_ids = remaining_ids.difference(processed_ids)
            for call_id in remaining_ids:
                created_at = datetime.fromtimestamp(local_by_id[call_id].stat().st_mtime, tz=timezone.utc)
                call = CallRecord(
                    id=call_id,
                    created_at=created_at,
                    duration_sec=0,
                    summary="",
                    audio_file_path=str(local_by_id[call_id]),
                    status=PipelineStatus.DOWNLOADED,
                )
                call_records.append(call)
            logging.info(f"Updated database with {len(call_records)} new records")
            session.commit()
    
    def find_transfer_size(self, abs_remote_paths: list[str]):
        """
        Returns total_bytes. Works even if some files are missing.
        """
        if not abs_remote_paths:
            return 0

        # One remote command, no $@, no cd
        cmd = [*self.ssh_base, "wc", "-c", *abs_remote_paths]
        out = subprocess.check_output(cmd, text=True)
        total = 0
        for line in out.splitlines():
            parts = line.split()
            if not parts:
                continue
            try:
                n = int(parts[0])
            except ValueError:
                continue
            # BusyBox wc prints "total" when multiple files; ignore that line
            if len(parts) >= 2 and parts[-1] == "total":
                continue
            total += n
        return total

    def prepare_transfer(self, download_queue: set[str] | None) -> tuple[int, list[str], list[str]]:
        queue_paths_rel: list[str] = []
        queue_paths_abs: list[str] = []
        cmd = [*self.ssh_base, "find", str(self.remote_dir), "-type", "f", "-print"]
        out = subprocess.check_output(cmd, text=True)
        abs_remote_paths = sorted([Path(line.strip()) for line in out.splitlines() if line.strip()])

        # Build missing file list 
        for rp in abs_remote_paths:
            rel = rp.relative_to(self.remote_dir)
            lp = self.local_dir / rel
            # Download if file doesnt exist on server or download is queued. 
            if not lp.exists() or (download_queue is None or rel.stem in download_queue):
                queue_paths_rel.append(str(rel))
                queue_paths_abs.append(str(rp))

        total_size = sum([self.find_transfer_size(chunk) for chunk in chunked(queue_paths_abs, 250)])
        logging.info(f"Found {len(queue_paths_rel)} files to download totaling {(total_size / (1024 ** 2)):.2f} MiB")
        return total_size, queue_paths_rel, queue_paths_abs
    
    def transfer(self, total_size: int, queue_paths_rel: list[str]) -> None:
        self.local_temp_dir.mkdir(parents=True, exist_ok=True)
        with ExitStack() as stack:
            remote_prod = stack.enter_context(
                subprocess.Popen(
                    [*self.ssh_base, "tar", "-cf", "-", "-C", str(self.remote_dir), *queue_paths_rel],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=1024 ** 2,
                )
            )
            
            local_cons = stack.enter_context(
                subprocess.Popen(
                    ["tar", "-xf", "-", "-C", str(self.local_temp_dir)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    bufsize=1024 ** 2,
                )
            )

            assert remote_prod.stdout is not None
            assert remote_prod.stderr is not None
            assert local_cons.stdin is not None
            assert local_cons.stderr is not None

            buf = bytearray(1024**2)
            mv = memoryview(buf)

            try:
                with tqdm(total=total_size, unit="B", unit_scale=True, desc="Downloading") as pbar:
                    for n in iter(lambda: remote_prod.stdout.readinto(buf), 0): # type: ignore
                        try:
                            local_cons.stdin.write(mv[:n])
                        except BrokenPipeError:
                            # local tar died; stop ssh so we don't hang
                            remote_prod.kill()
                            raise
                        pbar.update(n)

            finally:
                # Always close tar stdin so it can finish / flush errors
                try:
                    local_cons.stdin.close()
                except Exception:
                    pass
                
            remote_rc = remote_prod.wait()
            local_rc = local_cons.wait()

            remote_err = remote_prod.stderr.read().decode(errors="replace")
            local_err = local_cons.stderr.read().decode(errors="replace")

            if remote_rc != 0:
                raise RuntimeError(f"ssh/remote tar failed rc={remote_rc}\n{remote_err}")
            if local_rc != 0:
                raise RuntimeError(f"local tar failed rc={local_rc}\n{local_err}")
        return
    
    def finalize_transfer(self, queue_paths_rel: list[str]) -> tuple[list[Path], list[Path]]:
        """
        Move all files from recordings.tmp into recordings (only if missing).
        Returns (moved_files.
        """
        moved = []
        skipped = []

        for rel in queue_paths_rel:
            src = self.local_temp_dir / rel
            if not src.is_file():
                skipped.append(src)
                continue

            rel = src.relative_to(self.local_temp_dir)
            dst = self.local_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)

            os.replace(src, dst)   # atomic rename on same filesystem
            moved.append(dst)
                    
        rmtree(self.local_temp_dir, ignore_errors=True)
        logging.info(f"Finalize: moved {len(moved)}, skipped {len(skipped)}")
        return moved, skipped
    
    def run(self) -> None:
        while not self._stop_event.is_set():
            download_queue: set[str] | None = None
            # Check for any files that need to be redownloaded, occurs when CallRecord.status == "QUEUED"
            if self.use_db:
                download_queue = self.get_db_queue()
                if not download_queue:
                    logging.info("No queued calls found.")

            total_size, queue_paths_rel, _queue_paths_abs = self.prepare_transfer(download_queue)
            moved: list[Path] = []
            skipped: list[Path] = []
            if not queue_paths_rel:
                logging.info("No new files to download.")
            else:
                self.transfer(total_size, queue_paths_rel)
                moved, skipped = self.finalize_transfer(queue_paths_rel)

            if self.use_db:
                new_hash = self.local_recordings_hash()
                should_update = (
                    self._last_local_hash is None
                    or new_hash != self._last_local_hash
                    or moved
                    or skipped
                )
                if should_update:
                    self.update_db(moved, skipped)
                    self._last_local_hash = new_hash
                
            self._stop_event.wait(self.sleep_s)
            
