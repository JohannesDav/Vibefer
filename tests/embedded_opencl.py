#!/usr/bin/env python3
"""Check that the embedded fallback source matches the editable OpenCL source."""

import ast
from pathlib import Path


root = Path(__file__).resolve().parents[1]
header = (root / "src/ocl/kernel.h").read_text(encoding="utf-8")
declaration = "static const char * const src_ocl_kernel ="
_, marker, initializer = header.partition(declaration)
assert marker and initializer.rstrip().endswith(";"), "Missing embedded OpenCL initializer"
embedded = ast.literal_eval("(" + initializer.rstrip()[:-1] + ")")
source = (root / "ocl/kernel.cl").read_text(encoding="utf-8")
assert embedded == source, "src/ocl/kernel.h is out of sync with ocl/kernel.cl"
print("PASS embedded OpenCL source matches ocl/kernel.cl")
