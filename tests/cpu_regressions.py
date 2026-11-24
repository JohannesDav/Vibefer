#!/usr/bin/env python3
"""Known answers and failure regressions for the Linux CPU executables."""

import argparse
from functools import lru_cache
import os
from pathlib import Path
import pty
import re
import resource
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import zlib
import time


PRIME = 1534
COMPOSITE = 1538


def command(executable, base, mode):
    return [str(executable), mode, "-n", "12", "-b", str(base),
            "-f", "candidate", "-t", "1"]


def run(args, work, **kwargs):
    return subprocess.run(args, cwd=work, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, timeout=120, **kwargs)


def verdict(work, base, expected):
    results = (work / "results.txt").read_text()
    lines = [line for line in results.splitlines() if line.startswith(f"{base}^{{2^12}} + 1 is ")]
    assert len(lines) == 1 and re.match(rf".+ is {expected}\b", lines[0]), results
    return results, lines[0]


def known_answers(executable, oracle, root):
    @lru_cache(maxsize=None)
    def residue(base, witness, divisor=1):
        text = subprocess.check_output(
            [str(oracle), str(base), str(witness), str(divisor)], text=True, timeout=60)
        is_one, low64 = text.split()
        return is_one == "1", int(low64, 16)

    for base in (PRIME, COMPOSITE):
        is_prime = base == PRIME
        is_prp, low64 = residue(base, 2)
        assert is_prp == is_prime
        for mode in ("-p", "-q", "-e"):
            work = root / f"{base}{mode}"
            work.mkdir()
            result = run(command(executable, base, mode), work)
            assert result.returncode == 0, result.stdout
            expected = ("prime" if mode == "-e" else "a probable prime") if is_prime else "composite"
            results, line = verdict(work, base, expected)
            if mode == "-p":
                assert (work / "candidate.proof").stat().st_size > 0
            if mode != "-e" and not is_prime:
                assert f"res64 = {low64:016X}" in line, line
            if mode == "-e":
                # Deterministic mode reports witness comparisons, not res64.
                witnesses = re.findall(r"^(\d+)\^\{\(N - 1\)(?:/(\d+))?\} (!?=) 1\.$",
                                       results, re.M)
                assert witnesses
                for witness, divisor, comparison in witnesses:
                    is_one, _ = residue(base, int(witness), int(divisor or 1))
                    assert is_one == (comparison == "="), (base, witness, divisor, comparison)
            print(f"PASS known answer {base} {mode}", flush=True)


def checkpoint_fixture(executable, work, mode="-e", base=COMPOSITE):
    # A terminal makes the application's startup line visible before exit.
    master, terminal = pty.openpty()
    try:
        process = subprocess.Popen(command(executable, base, mode), cwd=work,
                                   stdout=terminal, stderr=terminal)
        os.close(terminal)
        terminal = None
        try:
            output = bytearray()
            deadline = time.monotonic() + 10
            while b"thread(s)" not in output:
                remaining = max(0, deadline - time.monotonic())
                assert select.select([master], [], [], remaining)[0], output
                output.extend(os.read(master, 4096))
            process.send_signal(signal.SIGINT)
            assert process.wait(timeout=10) == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    finally:
        if terminal is not None:
            os.close(terminal)
        os.close(master)
    return (work / ("candidate.ctxp" if mode == "-e" else "candidate.ctx")).read_bytes()


def checkpoint_recovery(executable, root):
    work = root / "interrupted"
    work.mkdir()
    fixture = checkpoint_fixture(executable, work)
    damaged = fixture[:-1] + bytes([fixture[-1] ^ 1])
    for label, base, data, backup, rejection in (
        ("wrong-candidate", PRIME, fixture, False, "invalid context"),
        ("bad-checksum", COMPOSITE, damaged, False, "bad file (crc32)"),
        ("use-backup", COMPOSITE, damaged, True, "bad file (crc32)"),
    ):
        work = root / label
        work.mkdir()
        (work / "candidate.ctxp").write_bytes(data)
        if backup:
            (work / "candidate.ctxp.old").write_bytes(fixture)
        result = run(command(executable, base, "-e"), work)
        assert result.returncode == 0 and rejection in result.stdout, result.stdout
        assert ("Resuming from a checkpoint." in result.stdout) == backup, result.stdout
        verdict(work, base, "prime" if base == PRIME else "composite")
        print(f"PASS deterministic checkpoint {label}", flush=True)


def with_checksum(data):
    checksum = (~zlib.crc32(data) ^ 0xA23777AC) & 0xFFFFFFFF
    return data + checksum.to_bytes(4, sys.byteorder)


def ordinary_checkpoint_candidate(executable, root):
    work = root / "ordinary-checkpoint"
    work.mkdir()
    fixture = checkpoint_fixture(executable, work, "-q")
    assert struct.unpack_from("=i", fixture) == (3,)
    assert struct.unpack_from("=II", fixture, 20) == (COMPOSITE, 12)
    legacy = with_checksum(struct.pack("=i", 1) + fixture[4:20] + fixture[28:-4])
    for label, base, data, resume in (
        ("same-base", COMPOSITE, fixture, True),
        ("wrong-base", PRIME, fixture, False),
        ("wrong-size", COMPOSITE, with_checksum(fixture[:24] + struct.pack("=I", 13) + fixture[28:-4]), False),
        ("legacy", COMPOSITE, legacy, True),
    ):
        work = root / f"ordinary-{label}"
        work.mkdir()
        (work / "candidate.ctx").write_bytes(data)
        if label == "wrong-base":
            (work / "candidate.ctx.old").write_bytes(legacy)
        result = run(command(executable, base, "-q"), work)
        assert result.returncode == 0, result.stdout
        assert ("Resuming from a checkpoint." in result.stdout) == resume, result.stdout
        assert ("invalid context" in result.stdout) != resume, result.stdout
        verdict(work, base, "a probable prime" if base == PRIME else "composite")
        print(f"PASS ordinary checkpoint {label}", flush=True)


def proof_verdict_mismatch(executable, root):
    work = root / "proof-verdict-mismatch"
    work.mkdir()
    results = work / "results.txt"
    results.mkdir()
    args = command(executable, COMPOSITE, "-p") + ["--proof-storage=disk"]
    original = run(args, work)
    assert "Cannot write 'results.txt' file" in original.stdout, original.stdout
    results.rmdir()

    # A completed context retains the original verdict. Change one digit in
    # the saved proof residue while keeping both the composite flag and CRC valid.
    point = work / "candidate_0.ckpt"
    original_digits = point.read_bytes()[:-4]
    byte_in_digit = 0 if sys.byteorder == "little" else 3
    for field, offset in (("res64", 8), ("old64", len(original_digits) - 4)):
        digits = bytearray(original_digits)
        digits[offset + byte_in_digit] ^= 1
        point.write_bytes(with_checksum(digits))
        result = run(args, work)
        assert result.returncode == 1 and "Reported verdict or residue disagrees" in result.stdout, result.stdout
        assert not results.exists()
        print(f"PASS proof rejects a changed composite {field}", flush=True)


def failed_validation(executable, root):
    work = root / "failed-validation"
    work.mkdir()
    results = work / "results.txt"
    results.mkdir()
    args = command(executable, COMPOSITE, "-q") + ["-x", "i32"]
    original = run(args, work)
    assert "Cannot write 'results.txt' file" in original.stdout, original.stdout
    results.rmdir()
    checkpoint = work / "candidate.ctx"
    saved = checkpoint.read_bytes()
    assert struct.unpack_from("=i", saved, 8) == (-1,)
    # Replace the saved Gerbicz–Li accumulator with the final PRP residue.
    registers = saved[32:-4]
    assert len(registers) % 2 == 0
    final = registers[:len(registers) // 2]
    checkpoint.write_bytes(with_checksum(saved[:32] + final + final))
    result = run(args, work)
    assert result.returncode == 1 and "validation failed!" in result.stdout, result.stdout
    assert " is composite" not in result.stdout
    print("PASS failed Gerbicz–Li validation returns failure", flush=True)


def failure_cases(executable, cyclo, root):
    work = root / "cyclo"
    work.mkdir()
    for args, message in (
        (["-e"], "-e is not supported by cyclo"),
        (["-q", "-x", "i32"], "-x i32 is not supported by cyclo"),
        (["-q", "-xi32"], "-x i32 is not supported by cyclo"),
    ):
        result = run([str(cyclo), *args, "-n", "12", "-b", str(PRIME)], work)
        assert result.returncode != 0 and message in result.stdout, result.stdout
        assert not list(work.iterdir())
    print("PASS cyclo rejects unsupported options", flush=True)

    work = root / "result-write-failure"
    work.mkdir()
    contents = b"x" * (1024 * 1024)
    path = work / "results.txt"
    path.write_bytes(contents)

    def limit_file_size():
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (len(contents), len(contents)))

    result = run(command(executable, COMPOSITE, "-p"), work, preexec_fn=limit_file_size)
    assert result.returncode != 0 and "Cannot write 'results.txt' file" in result.stdout, result.stdout
    assert path.read_bytes() == contents
    print("PASS failed result write returns failure", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("genefer", "cyclo", "oracle"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="gfn-regressions-") as directory:
        root = Path(directory)
        known_answers(args.genefer.resolve(), args.oracle.resolve(), root)
        checkpoint_recovery(args.genefer.resolve(), root)
        ordinary_checkpoint_candidate(args.genefer.resolve(), root)
        proof_verdict_mismatch(args.genefer.resolve(), root)
        failed_validation(args.genefer.resolve(), root)
        failure_cases(args.genefer.resolve(), args.cyclo.resolve(), root)


if __name__ == "__main__":
    main()
