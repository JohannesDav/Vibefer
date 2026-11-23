#!/usr/bin/env python3
"""Exercise BOINC proof storage, per-task budgets and live disk fallback."""

import argparse
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

from boinc_ipc import Episode, sha


RAM = re.compile(r"^Proof checkpoints: RAM \((\d+) MiB\)\.$", re.M)
DISK_MEMORY = re.compile(r"^Proof checkpoints: disk \(needs (\d+) MiB, (\d+) MiB available\)\.$", re.M)
DISK = "Proof checkpoints: disk ("
SPILL = "Memory pressure: switched proof checkpoints to disk ("
PRESSURE = "<heartbeat/><wss>67108864</wss><max_wss>33554432</max_wss>"
GFN16_PROOF = "cf499d43d54abc4ce0a33ff13c9882cb2051306bad13484cee719edceb01b986"


def launch(args, slot, label, **options):
    return Episode(
        slot, slot, args.initializer, "p", label, candidate=1026,
        check_certificate=False, check_tail=False, **options,
    )


def prepare_slot(args, label):
    slot = args.output / label
    slot.mkdir()
    shutil.copy2(args.executable, slot / "renamed executable")
    return slot


def log(slot):
    stderr = slot / "stderr.txt"
    return stderr.read_text() if stderr.exists() else ""


def assert_proof(slot, digest=GFN16_PROOF):
    assert (slot / "boinc_finish_called").read_text().strip() == "0"
    assert (slot / "results.txt").is_file()
    assert sha(slot / "gproof.proof") == digest


def run_case(args, exponent, digest, quit_during_proof):
    slot = prepare_slot(args, f"gfn{exponent}")

    episode = launch(args, slot, f"gfn{exponent}-pressure", exponent=exponent)
    try:
        episode.wait(lambda: RAM.search(log(slot)))
        initially_needed = int(RAM.search(log(slot))[1])
        if quit_during_proof:
            episode.wait(lambda: (slot / "gproof.proof").exists(), 1200)
            episode.control("<suspend/>")
            episode.wait(lambda: "Boinc client is suspended." in log(slot))
        else:
            episode.delay(2)
        assert not list(slot.glob("*.ckpt")), "RAM mode wrote proof checkpoints"
        episode.heartbeat = PRESSURE
        episode.wait(lambda: SPILL in log(slot), 15)
        assert list(slot.glob("*.ckpt")), "spill did not persist proof checkpoints"
        if quit_during_proof:
            episode.control("<quit/>")
        assert episode.finish(120)["returncode"] == 0
    finally:
        if episode.process.poll() is None:
            episode.process.kill()
            episode.process.wait()
    assert log(slot).count(SPILL) == 1
    assert "BOINC budget 32.0 MiB per task across 1 task" in log(slot)

    if quit_during_proof:
        assert not (slot / "boinc_finish_called").exists()
        assert not (slot / "results.txt").exists()
        with (slot / "gproof.ctx").open("rb") as context:
            _, phase, next_bit = struct.unpack("=iii", context.read(12))
        assert (phase, next_bit) == (0, -1), "did not save completed PRP state"
        episode = launch(args, slot, f"gfn{exponent}-resume", exponent=exponent)
        try:
            assert episode.finish(120)["returncode"] == 0
        finally:
            if episode.process.poll() is None:
                episode.process.kill()
                episode.process.wait()
        assert "Resuming from a checkpoint." in log(slot)

    assert_proof(slot, digest)
    print(f"PASS: GFN-{exponent} memory spill, proof {digest}", flush=True)
    return initially_needed


def parallel_start(args, count, limit, storage):
    episodes, gates = [], []
    try:
        for i in range(count):
            label = f"parallel-{count}-{i}"
            slot = prepare_slot(args, label)
            gate = args.output / f"{label}.start"
            gates.append(gate)
            episodes.append(launch(args, slot, label, exponent=16,
                                   memory_limit_mib=limit, start_gate=gate))
        gates[0].touch()
        if count == 2:
            # Keep both tasks visible to the census while serializing RAM allocation.
            first = episodes[0]
            first.wait(lambda: storage.search(log(first.slot)))
        for gate in gates[1:]:
            gate.touch()
        deadline = time.monotonic() + 120
        while any(episode.process.poll() is None for episode in episodes):
            assert time.monotonic() < deadline, "parallel tasks did not finish"
            for episode in episodes:
                episode.tick()
        for episode in episodes:
            assert episode.finish(120)["returncode"] == 0
            text = log(episode.slot)
            match = storage.search(text)
            assert match, text
            if storage is DISK_MEMORY:
                needed, available = map(int, match.groups())
                assert needed > available and available <= limit / count + 0.5, text
            assert SPILL not in text, text
            assert_proof(episode.slot)
    finally:
        for episode in episodes:
            if episode.process.poll() is None:
                episode.process.kill()
                episode.process.wait()
    mode = "RAM" if storage is RAM else "disk"
    print(f"PASS: {count} parallel tasks chose {mode} at {limit} MiB total", flush=True)


def added_peers(args, count, limit, peer_mib=0):
    label = "heavy-peer" if peer_mib else "added-tasks"
    slot = prepare_slot(args, label)
    episode = launch(args, slot, label, exponent=16, memory_limit_mib=limit)
    peers = []
    try:
        episode.wait(lambda: RAM.search(log(slot)))
        for index in range(count - 1):
            ready = args.output / f"{label}-{index}.ready"
            process = subprocess.Popen([
                sys.executable, "-c",
                "import pathlib, sys, time; memory = bytearray(b'.') * (int(sys.argv[1])*1024**2); "
                "pathlib.Path(sys.argv[2]).touch(); time.sleep(120)",
                str(peer_mib), str(ready),
            ])
            peers.append(process)
            episode.wait(ready.exists)
        episode.wait(lambda: SPILL in log(slot), 15)
        switch = next(line for line in log(slot).splitlines() if line.startswith(SPILL))
        match = re.search(r"BOINC budget ([\d.]+) MiB per task across (\d+) tasks", switch)
        assert match and int(match[2]) == count, switch
        if peer_mib:
            assert float(match[1]) < limit / count - 1, switch
        assert episode.finish(120)["returncode"] == 0
        assert_proof(slot)
    finally:
        for process in [*peers, episode.process]:
            if process.poll() is None:
                process.kill()
                process.wait()
    print("PASS: " + switch, flush=True)


def disk_only(args, label, reason, **options):
    slot = prepare_slot(args, label)
    episode = launch(args, slot, label, exponent=16, **options)
    try:
        assert episode.finish(120)["returncode"] == 0
        assert f"{DISK}{reason})." in log(slot)
        assert_proof(slot)
    finally:
        if episode.process.poll() is None:
            episode.process.kill()
            episode.process.wait()
    print(f"PASS: {label} completed on disk", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--initializer", type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--output", type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    args.output.mkdir()
    needed = run_case(args, 16, GFN16_PROOF, quit_during_proof=False)
    # Leave room for GPU startup allocations with two tasks, while the share
    # for four tasks stays below the measured initial requirement.
    limit = math.ceil(needed * 3.4)
    parallel_start(args, 2, limit, RAM)
    parallel_start(args, 4, limit, DISK_MEMORY)
    added_peers(args, 4, limit)
    added_peers(args, 2, limit, math.ceil(limit - needed / 2))
    disk_only(args, "forced-disk", "--proof-storage=disk", memory_limit_mib=1, force_disk=True)
    disk_only(args, "unknown-budget", "BOINC task memory budget unavailable", client_pid=0)
    run_case(args, 19, "f2baad1af5c6e3a484eff198e3d5d8754dbd2c40872928a7731953de994a5edd",
             quit_during_proof=True)


if __name__ == "__main__":
    main()
