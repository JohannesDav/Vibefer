# Benchmark results

Each comparison runs a complete test of the same candidate on the same machine, once with the original genefer22 and once with this fork. Times include proof generation.

- The original version was compiled from Gallot’s commit `56905b2339b3fed056fc0c24d2e331d588d028bb`.
- Both versions ran Gallot’s Gerbicz–Li error check. This fork’s optional `--check-certificate` and `--check-tail` checks were off.
- Each subproject used the same candidate on every GPU, with a round base near PrimeGrid’s search range in November 2026, according to its [project status page](https://www.primegrid.com/server_status_subprojects.php): 620,000,000 for GFN-16, 520,000,000 for GFN-17-Mega, 100,000,000 for GFN-18, 30,000,000 for GFN-19, 8,000,000 for GFN-20, 2,800,000 for GFN-21 and 660,000 for GFN-22.

In every comparison, the two versions wrote identical proof files, and each proof passed Gallot’s certificate check.

Each cell shows the time in seconds with the original version → with this fork (time saved). A dash means we skipped that comparison because of the time and cost involved, not because the combination is unsupported.

Times are for a complete test, as a PrimeGrid task would run it. For GFN-16 and GFN-17, they include compiling the kernels specific to the candidate's base, which each new task requires. For larger sizes, this compilation takes under 1% of the test time and is not included.

Results can differ noticeably between machines with the same GPU, depending for example on drivers, power limits and the rest of the system.

| GPU | GFN-16 | GFN-17 | GFN-18 | GFN-19 |
|---|---:|---:|---:|---:|
| RTX 2080 Ti | 43.0 → 35.9 (16.5%) | 131.8 → 101.4 (23.1%) | 375.9 → 253.9 (32.5%) | 1501.3 → 842.3 (43.9%) |
| RTX 3090 | 47.1 → 38.7 (17.8%) | 122.7 → 91.7 (25.3%) | 298.6 → 208.2 (30.3%) | 985.3 → 580.8 (41.1%) |
| RTX 4060 Ti | 40.5 → 33.1 (18.3%) | 117.5 → 89.7 (23.7%) | 353.6 → 232.4 (34.3%) | 1209.6 → 720.1 (40.5%) |
| RTX 5070 | 35.2 → 29.7 (15.6%) | 73.7 → 58.3 (20.9%) | 240.7 → 166.9 (30.7%) | 834.8 → 500.1 (40.1%) |
| RTX 5090 | 30.0 → 26.5 (11.7%) | 86.2 → 70.0 (18.8%) | 137.9 → 110.8 (19.6%) | 383.6 → 261.1 (32.0%) |

| GPU | GFN-20 | GFN-21 | GFN-22 | GFN-23 |
|---|---:|---:|---:|---:|
| RTX 2080 Ti | — | — | — | — |
| RTX 3090 | 4043.6 → 2007.6 (50.4%) | — | — | — |
| RTX 4060 Ti | 4376.0 → 2282.6 (47.8%) | — | — | — |
| RTX 5070 | 3017.9 → 1594.2 (47.2%) | — | — | — |
| RTX 5090 | 1378.7 → 870.9 (36.8%) | 5308.9 → 2547.7 (52.0%) | 15157.8 → 7961.4 (47.5%) | — |

## Comparison with CUDA

Each cell shows the time this OpenCL version saves as a percentage of the time the [CUDA version](https://github.com/JohannesDav/vibefer) saves, both compared with the original genefer22. **100% means both save the same amount of time.** Lower values show where the OpenCL version falls behind.

The OpenCL and CUDA measurements used different rented machines, drivers and power settings, so small differences are not meaningful.

| GPU | GFN-16 | GFN-17 | GFN-18 | GFN-19 | GFN-20 | GFN-21 | GFN-22 | GFN-23 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| RTX 2080 Ti | 77% | 91% | 100% | 95% | — | — | — | — |
| RTX 3090 | 54% | 72% | 75% | 84% | 97% | — | — | — |
| RTX 4060 Ti | 63% | 77% | 87% | 96% | 96% | — | — | — |
| RTX 5070 | 40% | 83% | 90% | 98% | 99% | — | — | — |
| RTX 5090 | 22% | 37% | 43% | 91% | 91% | 92% | 89% | — |
