#!/usr/bin/env bash
set -euo pipefail

backend=cuda
if [[ "$GENEFER_VARIANT" == opencl ]]; then backend=gpu; fi
python3 tests/embedded_opencl.py
mkdir -p build/tests
python3 "tools/embed_${backend}_kernels.py" "build/tests/generated/${backend}/embedded_kernels.h"
g++ -std=c++17 -O2 -Isrc "tests/${backend}_parameters_probe.cpp" -lgmp -o build/tests/parameters
python3 "tests/test_${backend}_parameters.py" build/tests/parameters
g++ -std=c++17 -O2 -Isrc -Ibuild/tests/generated "tests/${backend}_profiles.cpp" \
    "src/${backend}/profiles.cpp" -lgmp -o build/tests/profiles
./build/tests/profiles
g++ -std=c++17 -O2 -Isrc -Ibuild/tests/generated "tests/${backend}_handoff.cpp" \
    "src/${backend}/kernel.cpp" -lgmp -o build/tests/handoff
./build/tests/handoff
if [[ "$(g++ -dumpmachine)" == x86_64-* ]]; then
    mkdir -p build/tests/cpu
    cpu_objects=(transform_{sse2,sse4,avx,fma,512,i32}.o)
    make -C build/tests/cpu -f ../../../genefer/makefile_linux_x64 SRC_DIR=../../../src \
        BOINC= CC='g++ -std=c++17 -pthread' -j2 "${cpu_objects[@]}"
    g++ -std=c++17 -O2 -pthread -DTEST_CPU_TRANSFORMS -Isrc tests/cpu_scalar.cpp \
        "${cpu_objects[@]/#/build/tests/cpu/}" -lgmp -o build/tests/cpu-scalar
else
    g++ -std=c++17 -O2 -Isrc tests/cpu_scalar.cpp -lgmp -o build/tests/cpu-scalar
fi
./build/tests/cpu-scalar
