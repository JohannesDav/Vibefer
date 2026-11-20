#!/usr/bin/env python3
"""GPU release regression: a proven GFN-16 prime must use optimized arithmetic.

204152188^65536+1 is recorded as proven in PrimePages:
https://t5k.org/primes/page.php?id=135124
1026^65536+1 is the existing composite proof-links regression fixture.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from verification_failures import run_checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    executable = args.executable.resolve()
    output = args.output.resolve()
    output.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('GFN_', 'GENEFER_'))}
    optimized = re.compile(r'^(CUDA|OpenCL) profile: .+ \((packed|three primes)\)$', re.M)
    checks = []
    proofs = {}
    cases = [
        ('prime-proof', 204152188, '-p', False, False),
        ('prime-proof-checked', 204152188, '-p', True, False),
        ('prime-quick', 204152188, '-q', False, False),
        ('prime-reference', 204152188, '-p', True, True),
        ('composite-proof', 1026, '-p', True, False),
        ('composite-quick', 1026, '-q', False, False),
    ]
    for label, base, mode, extra_checks, reference in cases:
        work = output / label
        work.mkdir()
        command = [str(executable), '-n', '16', '-b', str(base), mode,
                   '-f', 'candidate']
        if extra_checks:
            command += ['--check-certificate', '--check-tail']
        case_env = dict(env)
        if reference:
            case_env['GENEFER_FORCE_OPENCL'] = '1'
        with (work / 'run.log').open('w') as log:
            process = subprocess.run(command, cwd=work, env=case_env,
                                     stdout=log, stderr=subprocess.STDOUT,
                                     timeout=600)
        text = (work / 'run.log').read_text()
        assert process.returncode == 0, (label, process.returncode, text[-2000:])
        result = (work / 'results.txt').read_text()
        verdict = 'is a probable prime' if base == 204152188 else 'is composite'
        assert verdict in result, (label, result)
        assert ('is composite' if base == 204152188 else 'is a probable prime') not in result
        backend = optimized.search(text)
        if reference:
            assert backend is None, (label, 'Reference unexpectedly used optimized arithmetic')
        else:
            assert backend is not None, (label, 'Did not exercise optimized GPU arithmetic', text)
        if extra_checks:
            assert 'Extra certificate verification passed' in text, label
            assert 'Extra tail recomputation passed' in text, label
        row = dict(name=label, base=base, exponent=16, status='PASS',
                   backend=backend.group(0) if backend else 'original OpenCL')
        if mode == '-p':
            digest = hashlib.sha256((work / 'candidate.proof').read_bytes()).hexdigest()
            proofs[label] = digest
            row['proof_sha256'] = digest
        checks.append(row)
        print(label + ': PASS', flush=True)
    assert len({proofs[x] for x in ['prime-proof', 'prime-proof-checked', 'prime-reference']}) == 1
    assert proofs['composite-proof'] == 'cf499d43d54abc4ce0a33ff13c9882cb2051306bad13484cee719edceb01b986'
    invalid_files = run_checks(executable, output / 'prime-proof/candidate.proof',
                               output / 'invalid-files', 204152188, 16)
    (output / 'result.json').write_text(json.dumps(dict(
        status='PASS', prime_source='https://t5k.org/primes/page.php?id=135124',
        checks=checks, proofs=proofs, invalid_files=invalid_files), indent=2) + '\n')
    print('PASS: optimized known-prime and composite tests, matching proofs, certificate and tail checks', flush=True)


if __name__ == '__main__':
    main()
