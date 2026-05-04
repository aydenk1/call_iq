import hashlib
import logging
import os
import subprocess
from contextlib import ExitStack
from multiprocessing import Event, Process
from pathlib import Path
from shutil import rmtree

from tqdm import tqdm

from api.db import Database
from api.models import CallRecord, PipelineStatus
from pipeline.utils import AUDIO_EXTS, chunked, setup_worker_logging


class SSHDownloader(Process):
    def __init__(self,
                 remote_host: str,
                 remote_dir: str,
                 local_dir: str,
                 sleep_s: int = 60,
                 log_level: int | None = None,
                 log_dir: Path | None = None) -> None:
        super().__init__()
        self.remote_host = remote_host
        self.remote_dir = Path(remote_dir)
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.local_temp_dir = self.local_dir.parent / f"{self.local_dir.name}.tmp"
        rmtree(self.local_temp_dir, ignore_errors=True)
        self.sleep_s = sleep_s
        self.log_level = log_level
        self.log_dir = log_dir
        self._stop_event = Event()
        self._db: Database | None = None
        
        self.ssh_base = [
            "ssh",
            "-oBatchMode=yes",
            "-oStrictHostKeyChecking=accept-new",
            "-oServerAliveInterval=15",
            "-oServerAliveCountMax=3",
            self.remote_host,
        ]
        return
    
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

    def get_db_queue(self) -> dict[str, str]:
        with self.db.session() as session:
            call_ids = CallRecord.list_ids(session, status=PipelineStatus.DOWNLOAD_QUEUED)
            call_records = CallRecord.get_from_id(session, call_ids)

            call_filename_map = {}
            for call_id in call_ids:
                if "recording_filename" in call_records[call_id].raw_call_log:
                    call_filename_map[call_id] = call_records[call_id].raw_call_log["recording_filename"]
                else:
                    call_filename_map[call_id] = call_filename_map
            return call_filename_map


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
    
    def update_db(
            self, 
            succeeded_transfers: list[Path], 
            skipped_transfers: list[Path], 
            failed_transfers: list[Path]
        ) -> tuple[int, int, int]: 
        """ Updates all call records that have been successfully downloaded with
            the saved audio path and sets status to DOWNLOADED.

            Raise an exception if the call_id is not found. 
        """
        with self.db.session() as session:
            cr_sucessful: int = 0
            cr_skipped: int = 0
            cr_failed: int = 0
            ids = {p.stem for p in succeeded_transfers + skipped_transfers + failed_transfers if p.suffix in AUDIO_EXTS}
            if not ids:
                logging.info("No call records to update")
                return cr_sucessful, cr_skipped, cr_failed

            record_map: dict[str, CallRecord] = {}
            for chunk in chunked(list(ids), 1000):
                record_map.update(CallRecord.get_from_id(session, chunk))
            missing = ids - record_map.keys()
            
            if len(missing):
                raise Exception(f"{self.name} The following call_ids are not found in the database.\n{missing}")

            # Update DB with succeeded_transfers, None should not be an issue due to the id check
            for local_path in succeeded_transfers:
                if local_path.suffix in AUDIO_EXTS:
                    call = record_map[local_path.stem]
                    call.audio_file_path = str(local_path)
                    call.set_status(session, PipelineStatus.DOWNLOADED, source=self.name)
                    cr_sucessful += 1
            
            # Updated DB skipped_transfers
            for local_path in skipped_transfers:
                if local_path.suffix in AUDIO_EXTS:
                    call = record_map[local_path.stem]
                    call.audio_file_path = str(local_path)
                    call.set_status(session, PipelineStatus.DOWNLOADED, source=self.name)
                    cr_skipped += 1

            # Update DB failed_transfers
            for local_path in failed_transfers:
                if local_path.suffix in AUDIO_EXTS:
                    call = record_map[local_path.stem]
                    call.set_status(session, PipelineStatus.FAILED, source=self.name)
                    cr_failed += 1
    
            session.commit()
            return cr_sucessful, cr_skipped, cr_failed
    
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

    def prepare_transfer(self, download_queue: dict[str, str] | None = None) -> tuple[int, list[str], list[str], list[Path]]:
        """ Finds remote files and adds them to the download queue if not already on disk. """
        queue_paths_rel: list[str] = []
        queue_paths_abs: list[str] = []
        skipped_paths: list[Path] = []

        # Scan entire directory for files if no queue is provided
        if download_queue is None:
            cmd = [*self.ssh_base, "find", str(self.remote_dir), "-type", "f", "-print"]
            out = subprocess.check_output(cmd, text=True)
            abs_remote_paths = sorted([Path(line.strip()) for line in out.splitlines() if line.strip()])
            for rp in abs_remote_paths:
                rel = rp.relative_to(self.remote_dir)
                lp = self.local_dir / rel
                if not lp.exists():
                        queue_paths_rel.append(str(rel))
                        queue_paths_abs.append(str(rp))
                else:
                    skipped_paths.append(lp)
        
        # Build abs_path from known call files in the database
        else:    
            for call_id in download_queue:
                rel = Path(download_queue[call_id])
                lp = self.local_dir / rel
                rp = self.remote_dir / rel
                queue_paths_rel.append(str(rel))
                queue_paths_abs.append(str(rp))

        total_size = sum([self.find_transfer_size(chunk) for chunk in chunked(queue_paths_abs, 250)])
        return total_size, queue_paths_rel, queue_paths_abs, skipped_paths
    
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
    
    def finalize_transfer(self, queue_paths_rel: list[str], download_queue: dict[str, str]) -> tuple[list[Path], list[Path]]:
        """
        Move all files from recordings.tmp into recordings.
        Rename files to their call_id name if they have a specified different file name. Must handle both for backwards compatiability. 
        Returns (moved_files, failed_files)
        """
        moved = []
        failed = []
        rvsd_download_queue = {v: k for k, v in download_queue.items()}

        for rel in queue_paths_rel:
            src = self.local_temp_dir / rel
            if not src.is_file():
                failed.append(src)
                continue
            
            # Rename file to normalize recording name to {call_id}.mp3
            dst = self.local_dir / f"{rvsd_download_queue[rel]}.mp3"
            dst.parent.mkdir(parents=True, exist_ok=True)

            os.replace(src, dst)   # atomic rename on same filesystem
            moved.append(dst)
                    
        rmtree(self.local_temp_dir, ignore_errors=True)
        return moved, failed

    def run(self) -> None:
        """ Start file sync based off of DB records """
        if self.log_level is not None:
            if self.log_dir is None:
                raise ValueError("log_dir is required when log_level is set.")
            setup_worker_logging(self.name, self.log_level, self.log_dir)

        while not self._stop_event.is_set():
            # Check for any files that need to be redownloaded, occurs when CallRecord.status == "QUEUED"
            logging.info(f"Started event loop after {self.sleep_s}s")
            download_queue = self.get_db_queue()
            logging.info(f"Found {len(download_queue)} calls with CallRecord.status == 'QUEUED'")

            if len(download_queue):
                successful: list[Path] = []
                failed: list[Path] = []
                total_size, queue_paths_rel, _queue_paths_abs, skipped = self.prepare_transfer(download_queue)
                logging.info(f"Found {len(queue_paths_rel)} files to download totaling {(total_size / (1024 ** 2)):.2f} MiB")

                
                if not queue_paths_rel:
                    logging.info("No new files to download.")
                else:
                    self.transfer(total_size, queue_paths_rel)
                    successful, failed = self.finalize_transfer(queue_paths_rel, download_queue)
                    logging.info(f"Finalize transfer {self.local_temp_dir} -> {self.local_dir}: moved {len(successful)}, failed {len(failed)}")

                ss, sk, f = self.update_db(successful, skipped, failed)
                logging.info(f"Updated the DB:\t{ss} successful\t{sk} skipped\t{f} failed")
            self._stop_event.wait(self.sleep_s)
            
