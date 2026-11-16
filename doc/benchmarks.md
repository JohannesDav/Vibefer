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
| GTX 1080 Ti | 117.8 → 93.0 (21.1%) | 334.0 → 265.3 (20.6%) | 1612.9 → 1070.7 (33.6%) | 5369.4 → 3946.7 (26.5%) |
| RTX 2060 | 58.2 → 45.9 (21.1%) | 186.4 → 148.1 (20.5%) | — | — |
| RTX 2080 Ti | 40.7 → 32.0 (21.4%) | 119.0 → 88.9 (25.3%) | 366.9 → 247.8 (32.5%) | 1519.5 → 815.8 (46.3%) |
| RTX 3060 12GB | 57.4 → 39.0 (32.1%) | 171.6 → 118.8 (30.8%) | 663.6 → 375.0 (43.5%) | 2830.1 → 1594.6 (43.7%) |
| RTX 3070 | 46.7 → 29.8 (36.2%) | 140.2 → 94.1 (32.9%) | 442.6 → 251.0 (43.3%) | — |
| RTX 3080 | 48.7 → 33.6 (31.0%) | 137.6 → 95.9 (30.3%) | — | — |
| RTX 3090 | 48.0 → 32.2 (32.9%) | 136.9 → 89.0 (35.0%) | 372.4 → 222.6 (40.2%) | 1464.2 → 746.2 (49.0%) |
| RTX 4060 Ti 16GB | 39.7 → 28.1 (29.2%) | 126.3 → 87.3 (30.9%) | 354.9 → 215.4 (39.3%) | 1183.2 → 683.9 (42.2%) |
| RTX 4070 | 38.9 → 25.3 (35.0%) | 107.3 → 74.5 (30.6%) | — | 945.8 → 542.3 (42.7%) |
| RTX 4090 | 41.1 → 18.8 (54.3%) | 81.1 → 42.9 (47.1%) | 166.7 → 92.4 (44.6%) | 451.5 → 263.3 (41.7%) |
| RTX 5070 | 35.4 → 21.4 (39.5%) | 77.2 → 57.8 (25.1%) | 241.6 → 159.4 (34.0%) | 844.0 → 499.9 (40.8%) |
| RTX 5080 | 46.9 → 19.6 (58.2%) | 91.8 → 50.1 (45.4%) | — | — |
| RTX 5090 | 37.2 → 17.6 (52.7%) | 80.4 → 39.9 (50.4%) | 159.7 → 86.9 (45.6%) | 361.3 → 234.5 (35.1%) |
| Tesla V100 | 58.6 → 40.7 (30.5%) | 146.9 → 95.1 (35.3%) | — | — |

| GPU | GFN-20 | GFN-21 | GFN-22 |
|---|---:|---:|---:|
| GTX 1080 Ti | 19710.0 → 12210.6 (38.0%) | — | — |
| RTX 2080 Ti | 6336.9 → 3167.4 (50.0%) | — | — |
| RTX 3060 12GB | 9483.9 → 5087.8 (46.4%) | — | — |
| RTX 3080 | 7412.5 → 3771.5 (49.1%) | — | — |
| RTX 3090 | 4431.6 → 2135.7 (51.8%) | 31500.4 → 12147.2 (61.4%) | — |
| RTX 4060 Ti 16GB | 4419.9 → 2222.5 (49.7%) | 22186.9 → 8769.6 (60.5%) | — |
| RTX 4090 | 1580.7 → 854.8 (45.9%) | 5605.7 → 2735.0 (51.2%) | 19801.8 → 8631.3 (56.4%) |
| RTX 5070 | 3083.0 → 1616.4 (47.6%) | 13223.3 → 5761.2 (56.4%) | — |
| RTX 5080 | — | 9268.6 → 3894.3 (58.0%) | — |
| RTX 5090 | 1122.6 → 669.2 (40.4%) | 5304.4 → 2306.2 (56.5%) | 14611.3 → 6840.8 (53.2%) |
