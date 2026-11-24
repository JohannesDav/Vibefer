#!/usr/bin/env python3
"""Resume a version -1 three-register GPU checkpoint through CPU OpenCL."""

import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

from cpu_regressions import with_checksum


def test(executable):
    base, exponent = 1534, 12
    size = 1 << exponent
    bits = pow(base, size).bit_length()
    first_bit = bits - 1
    block = first_bit // (2 << ((bits.bit_length() - 1) // 2)) + 1

    def register(digit):
        # Two-prime NTT stores each normalized digit in both channels.
        return (struct.pack("=I", digit) + bytes((size - 1) * 4)) * 2

    # After the leading bit, register 0 is 2. Register 2 is scratch.
    header = struct.pack("=iiidi", -1, 0, first_bit - 1, 5.0, 6)  # NTT2
    data = header + register(2) + register(2 if first_bit % block == 0 else 1) + register(0)
    with tempfile.TemporaryDirectory(prefix="legacy-quick-") as directory:
        work = Path(directory)
        (work / "candidate.ctx").write_bytes(with_checksum(data))
        result = subprocess.run(
            [str(executable), "-q", "-n", str(exponent), "-b", str(base), "-f", "candidate"],
            cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env=dict(os.environ, GENEFER_FORCE_OPENCL="1"), timeout=180,
        )
        assert result.returncode == 0 and "Resuming from a checkpoint." in result.stdout, result.stdout
        assert "1534^{2^12} + 1 is a probable prime" in (work / "results.txt").read_text()
        print("PASS upstream three-register quick checkpoint resumes", flush=True)


if __name__ == "__main__":
    test(Path(sys.argv[1]).resolve())
