#!/usr/bin/env bash
set -euo pipefail

executable=${1:?Pass the built Vibefer executable}
banner=$("$executable" -v | tr -d '\r')
if [[ "${GITHUB_REF:-}" == refs/tags/v* ]]; then
    grep -Fx "Vibefer ${GITHUB_REF#refs/tags/v} (https://github.com/JohannesDav/Vibefer)" <<<"$banner"
else
    grep -Ex 'Vibefer [^[:space:]]+ \(https://github\.com/JohannesDav/Vibefer\)' <<<"$banner"
fi
