#!/usr/bin/env python3
"""Check host-RAM proof storage and recovery with a Linux CPU build."""

import argparse
import errno
import fcntl
import os
from pathlib import Path
import pty
import resource
import select
import signal
import shutil
import struct
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    executable = args.executable.resolve()
    output = args.output.resolve()
    output.mkdir()
    command = [executable, "-n", "12", "-b", "1534", "-x", "i32", "-f", "candidate"]
    disk = ["--proof-storage=disk"]
    ram = "Proof checkpoints: RAM (3 MiB)."
    checkpoint = "candidate.ctx"
    proof = "candidate.proof"

    def limit_file_size():
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (4096, 4096))

    def run(work, label, switches=(), stop=None, fail_save=False, mode="-p"):
        log = work / (label + ".log")
        argv = command + [mode, *switches]
        if stop is None:
            with log.open("w") as stream:
                proc = subprocess.run(argv, cwd=work, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
            assert proc.returncode == 0, log.read_text()
            return log.read_text()

        # A terminal flushes the status lines even for the statically linked CI build.
        master, slave = pty.openpty()
        with log.open("wb") as stream, os.fdopen(master, "rb", 0) as terminal, os.fdopen(slave, "wb", 0) as output:
            proc = subprocess.Popen(
                argv, cwd=work, stdout=output, stderr=subprocess.STDOUT,
                preexec_fn=limit_file_size if fail_save else None,
            )
            output.close()
            try:
                sent_quit = False
                deadline = time.monotonic() + 120
                while True:
                    assert time.monotonic() < deadline, log.read_text()
                    if select.select([terminal], [], [], 0.01)[0]:
                        try:
                            chunk = terminal.read(4096)
                        except OSError as error:
                            if error.errno != errno.EIO:  # Linux closes the PTY this way.
                                raise
                            break
                        if not chunk:
                            break
                        stream.write(chunk)
                        stream.flush()
                    if not sent_quit and stop(work, log):
                        proc.terminate()
                        sent_quit = True
                assert sent_quit, log.read_text()
                assert proc.wait(timeout=10) == int(fail_save), log.read_text()
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
        return log.read_text()

    def after_start(work, log):
        if ram not in log.read_text():
            return False
        time.sleep(0.5)
        assert not (work / checkpoint).exists()
        assert not list(work.glob("*.ckpt"))
        return True

    def during_proof(work, _log):
        if not (work / proof).exists():
            return False
        assert not (work / checkpoint).exists()
        assert not list(work.glob("*.ckpt"))
        return True

    def after_resume(_work, log):
        if "Resuming from a checkpoint." not in log.read_text():
            return False
        time.sleep(0.5)
        return True

    assert "Proof checkpoints: disk (--proof-storage=disk)." in run(output, "reference", disk)
    expected = (output / proof).read_bytes()
    for label, stop, resume_args in (
        ("prp-to-disk", after_start, disk),
        ("proof-to-ram", during_proof, []),
    ):
        work = output / label
        work.mkdir()
        text = run(work, "quit", stop=stop)
        assert ram in text
        assert "terminated." in text and not (work / "results.txt").exists()
        saved_context = (work / checkpoint).read_bytes()
        saved_bit = struct.unpack_from("=i", saved_context, 8)[0]
        points = len(list(work.glob("*.ckpt")))
        if label == "prp-to-disk":
            assert saved_bit > 0 and 0 < points < 128
            text = run(work, "failed-save", stop=after_resume, fail_save=True)
            assert "failure of a write operation" in text
            assert (work / checkpoint).read_bytes() == saved_context
            print("PASS failed save leaves the previous checkpoint usable", flush=True)
        else:
            assert saved_bit == -1 and points == 128
        if label == "proof-to-ram":
            for damage in ("truncated", "bad-checksum"):
                damaged = output / damage
                shutil.copytree(work, damaged)
                point = damaged / "candidate_0.ckpt"
                data = point.read_bytes()
                point.write_bytes(data[:-1] if damage == "truncated" else data[:-1] + bytes([data[-1] ^ 1]))
                text = run(damaged, "restart", resume_args)
                assert "Proof checkpoints are missing or invalid; restarting from the beginning." in text
                assert "Resuming from a checkpoint." not in text
                assert "is a probable prime" in (damaged / "results.txt").read_text()
                assert (damaged / proof).read_bytes() == expected
                print(f"PASS {damage} proof checkpoint restarts the run", flush=True)
        text = run(work, "resume", resume_args)
        assert "Resuming from a checkpoint." in text
        assert (work / proof).read_bytes() == expected
        print("PASS", label, flush=True)

    # A concurrent allocation can cause automatic selection of disk storage.
    work = output / "busy-lock"
    work.mkdir()
    lock_path = Path("/tmp") / f"vibefer-proof-buffer-{os.getuid()}"
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert "Proof checkpoints: disk (proof memory reservation unavailable)." in run(work, "auto")
    assert (work / proof).read_bytes() == expected
    print("PASS automatic disk fallback", flush=True)

    def after_quick_start(_work, log):
        if "Using i32 implementation" not in log.read_text():
            return False
        time.sleep(0.5)
        return True

    work = output / "quick-to-proof"
    work.mkdir()
    text = run(work, "quick-quit", stop=after_quick_start, mode="-q")
    assert "terminated." in text and not list(work.glob("*.ckpt"))
    assert (work / checkpoint).is_file()
    text = run(work, "proof-restart")
    assert "Proof checkpoints are missing or invalid; restarting from the beginning." in text
    assert "Resuming from a checkpoint." not in text
    assert "is a probable prime" in (work / "results.txt").read_text()
    assert (work / proof).read_bytes() == expected
    print("PASS quick checkpoint restarts proof from the beginning", flush=True)


if __name__ == "__main__":
    main()
