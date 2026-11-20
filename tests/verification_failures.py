#!/usr/bin/env python3
"""Reject damaged proof/certificate files and files for another candidate.

Reuses a completed proof; no new full candidate test is needed.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def run_checks(executable, proof, output, base, exponent):
    executable, proof, output = executable.resolve(), proof.resolve(), output.resolve()
    output.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('GFN_', 'GENEFER_'))}
    env['GENEFER_FORCE_OPENCL'] = '1'
    checks = []

    def run(label, work, mode, b=base, n=exponent, error=None):
        with (work / (label + '.log')).open('w') as log:
            process = subprocess.run(
                [str(executable), '-n', str(n), '-b', str(b), mode, '-f', 'candidate'],
                cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        text = (work / (label + '.log')).read_text()
        if error:
            assert process.returncode == 1, (label, process.returncode, text[-2000:])
            assert error in text, (label, text[-2000:])
            result = (work / 'results.txt').read_text() if (work / 'results.txt').exists() else ''
            assert not result, (label, result)
            assert not re.search(r' is (?:a probable prime|composite|checked)', text), (label, text)
            if mode == '-s':
                assert not (work / 'candidate.cert').exists(), label
        else:
            assert process.returncode == 0, (label, process.returncode, text[-2000:])
        checks.append(dict(name=label, status='PASS', exit_code=process.returncode))
        print(label + ': PASS', flush=True)
        return text

    valid = output / 'valid'
    valid.mkdir()
    shutil.copyfile(proof, valid / 'candidate.proof')
    generated = run('valid-proof', valid, '-s')
    checked = run('valid-certificate', valid, '-c')
    key = re.compile(r'\bckey = ([0-9A-F]{16})')
    assert key.search(generated) and key.search(checked)
    assert key.search(generated).group(1) == key.search(checked).group(1)
    for suffix, mode in [('proof', '-s'), ('cert', '-c')]:
        original = (valid / ('candidate.' + suffix)).read_bytes()
        assert len(original) > 32
        damaged = bytearray(original)
        damaged[-1] ^= 1
        payload = bytearray(original)
        # Header (8 bytes), then the integer's size and base (8 bytes).
        # Change a digit, leaving metadata and the stored checksum intact.
        payload[16] ^= 2
        cases = [
            ('bad-payload', payload, base, exponent, 'bad file (crc32)'),
            ('bad-checksum', damaged, base, exponent, 'bad file (crc32)'),
            ('truncated', original[:-1], base, exponent, 'failure of a read operation'),
            ('wrong-base', original, base + 2, exponent, 'bad file'),
            ('wrong-exponent', original, base, exponent + 1, 'bad file'),
        ]
        for label, data, b, n, error in cases:
            label = suffix + '-' + label
            work = output / label
            work.mkdir()
            (work / ('candidate.' + suffix)).write_bytes(data)
            run(label, work, mode, b, n, error)
    report = dict(status='PASS', checks=checks)
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--proof', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base', type=int, required=True)
    parser.add_argument('--exponent', type=int, required=True)
    args = parser.parse_args()
    run_checks(args.executable, args.proof, args.output, args.base, args.exponent)


if __name__ == '__main__':
    main()
