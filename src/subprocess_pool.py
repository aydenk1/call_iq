from tqdm import tqdm
import os
import shutil
import subprocess
from dataclasses import dataclass
import time
from typing import Iterable, Optional

@dataclass
class ProcResult:
    cmd: list[str]
    rc: int
    stdout: str
    stderr: str

class SubprocessPool:
    def __init__(
        self,
        max_workers: int = 4,
        capture_stdout: bool = False,
        capture_stderr: bool = True,
        text: bool = True,
        nice: Optional[int] = None,
        show_progress: bool = True,
        desc: str = "Jobs",
    ) -> None:
        self.max_workers = max(1, int(max_workers))
        self.capture_stdout = capture_stdout
        self.capture_stderr = capture_stderr
        self.text = text
        self.nice = nice
        self.show_progress = show_progress
        self.desc = desc

    def _maybe_nice(self, cmd: list[str]) -> list[str]:
        if self.nice is None:
            return cmd
        if os.name != "posix":
            return cmd
        nice_path = shutil.which("nice")
        if not nice_path:
            return cmd
        return [nice_path, "-n", str(self.nice), *cmd]

    def run(self, commands: Iterable[list[str]]) -> list[ProcResult]:
        cmds = list(commands)
        results: list[ProcResult] = []
        running: dict[subprocess.Popen, list[str]] = {}
        i = 0

        def start(cmd: list[str]) -> subprocess.Popen:
            cmd2 = self._maybe_nice(cmd)
            return subprocess.Popen(
                cmd2,
                stdout=subprocess.PIPE if self.capture_stdout else subprocess.DEVNULL,
                stderr=subprocess.PIPE if self.capture_stderr else subprocess.DEVNULL,
                text=self.text,
            )

        pbar = tqdm(total=len(cmds), desc=self.desc, unit="job") if self.show_progress else None
        try:
            while i < len(cmds) or running:
                # Fill slots
                while i < len(cmds) and len(running) < self.max_workers:
                    cmd = cmds[i]
                    i += 1
                    proc = start(cmd)
                    running[proc] = cmd

                # Try to reap any finished proc without blocking
                finished_proc = None
                for proc in list(running.keys()):
                    if proc.poll() is not None:
                        finished_proc = proc
                        break

                # If none finished yet, briefly sleep and re-check to avoid blocking.
                if finished_proc is None:
                    time.sleep(0.1)
                    continue

                rc = finished_proc.poll()  # already finished

                cmd = running.pop(finished_proc)

                out = finished_proc.stdout.read() if (finished_proc.stdout and self.capture_stdout) else ""
                err = finished_proc.stderr.read() if (finished_proc.stderr and self.capture_stderr) else ""

                results.append(ProcResult(cmd=cmd, rc=rc if rc is not None else 0, stdout=out, stderr=err))
                if pbar:
                    pbar.update(1)

        finally:
            if pbar:
                pbar.close()

            # If something blows up mid-run, kill anything still running
            for proc in running.keys():
                try:
                    proc.kill()
                except Exception:
                    pass

        return results
