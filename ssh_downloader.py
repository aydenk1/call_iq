import logging
import os
import subprocess
from contextlib import ExitStack
from itertools import islice
from pathlib import Path
from shutil import rmtree
from typing import Sequence

from tqdm import tqdm


def chunked(seq: Sequence, n: int):
    it = iter(seq)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            return
        yield chunk


class SSHDownloader:
    def __init__(self,
                 remote_host: str,
                 remote_dir: str,
                 local_dir: str) -> None:
        
        self.remote_host = remote_host
        self.remote_dir = Path(remote_dir)
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.local_temp_dir = self.local_dir.parent / f"{self.local_dir.name}.tmp"
        rmtree(self.local_temp_dir, ignore_errors=True)
        
        self.ssh_base = [
            "ssh",
            "-oBatchMode=yes",
            "-oServerAliveInterval=15",
            "-oServerAliveCountMax=3",
            self.remote_host,
        ]
        return
    
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

    def prepare_transfer(self) -> tuple[int, list[str], list[str]]:
        queue_paths_rel: list[str] = []
        queue_paths_abs: list[str] = []
        cmd = [*self.ssh_base, "find", str(self.remote_dir), "-type", "f", "-print"]
        out = subprocess.check_output(cmd, text=True)
        abs_remote_paths = sorted([Path(line.strip()) for line in out.splitlines() if line.strip()])

        # Build missing file list 
        for rp in abs_remote_paths:
            rel = rp.relative_to(self.remote_dir)
            lp = self.local_dir / rel
            if not lp.exists():
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
                    for n in iter(lambda: remote_prod.stdout.readinto(buf), 0):
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
    
    def finalize_transfer(self) -> tuple[int, int]:
        """
        Move all files from recordings.tmp into recordings (only if missing).
        Returns (moved_files, skipped_existing).
        """
        moved = 0
        skipped = 0

        for src in self.local_temp_dir.rglob("*"):
            if not src.is_file():
                continue

            rel = src.relative_to(self.local_temp_dir)
            dst = self.local_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)

            if dst.exists():
                skipped += 1
                continue

            os.replace(src, dst)   # atomic rename on same filesystem
            moved += 1
                    
        rmtree(self.local_temp_dir, ignore_errors=True)
        logging.info(f"Finalize: moved {moved}, skipped_existing {skipped}")
        return moved, skipped
    
    def download(self) -> None:
        total_size, queue_paths_rel, queue_paths_abs = self.prepare_transfer()
        if not queue_paths_rel:
            logging.info("No new files to download.")
            return
        self.transfer(total_size, queue_paths_rel)
        self.finalize_transfer()
        return