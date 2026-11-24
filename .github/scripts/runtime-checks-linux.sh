#!/usr/bin/env bash
set -euo pipefail

executable=$(realpath "${1:?Pass the unpacked Linux release executable}")
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export POCL_MAX_PTHREAD_COUNT=2

bash .github/scripts/check-banner.sh "$executable"

make -C genefer -f makefile_linux_x64 BOINC= CC='g++ -std=c++17 -pthread' -j2 ../bin/genefer
make -C cyclo -f Makefile_linux -j2
g++ -std=c++17 -O2 tests/gfn_residue.cpp -lgmp -o "$work/gfn-residue"
python3 tests/cpu_regressions.py --genefer bin/genefer --cyclo bin/cyclo \
    --oracle "$work/gfn-residue"
python3 tests/proof_storage.py --executable bin/genefer --output "$work/proof-storage"
python3 tests/legacy_quick_checkpoint.py "$executable"

g++ -std=c++17 -O2 -DGPU -Isrc -IKhronos tests/two_prime_overflow.cpp \
    -lOpenCL -lgmp -o "$work/two-prime-overflow"

# Run outside the checkout so the tests use the embedded fallback kernel.
cd "$work"
timeout 180 ./two-prime-overflow
GENEFER_FORCE_OPENCL=1 timeout 180 "$executable" -n 12 -b 1534 -q -f smoke
grep -F '1534^{2^12} + 1 is a probable prime' results.txt
