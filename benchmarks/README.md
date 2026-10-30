# CPU, memory and reconstruction measurements

Measured October 30, 2026 on Windows 11, AMD Ryzen 9 9900X (12 cores/24 threads), Python 3.12.8. No GPU or remote processing. Each case uses three fresh spawned workers. Median trace time includes decoding/preprocessing/tracing/SVG serialization but excludes interpreter/module startup. Process wall time includes startup and quality rendering. Peak RSS is sampled every 10ms across the worker and includes imports and quality rendering; short peaks can be missed. These are local workload measurements, not a scalability or commercial-parity guarantee.

| Case | Pixels | Median trace | Peak RSS | Normalized RGB MAE |
|---|---|---:|---:|---:|
| Flat logo + geometry | 1024 × 1024 | 0.2003 s | 229.0 MiB | 0.00128 |
| Linear gradient | 1024 × 1024 | 0.1800 s | 234.9 MiB | 0.00077 |
| Shared-boundary regions | 1024 × 1024 | 0.1108 s | 204.9 MiB | 0.00107 |
| Centerlines | 1024 × 1024 | 0.1817 s | 174.4 MiB | 0.20289* |
| Seeded synthetic texture | 1024 × 1024 | 5.2273 s | 384.4 MiB | 0.06347 |
| NASA astronaut photograph | 512 × 512 | 0.2294 s | 136.1 MiB | 0.05353 |

*Centerline tracing intentionally reduces thick marks to one-pixel strokes; its whole-image MAE is not comparable to filled-region tracing. MAE is mean absolute RGB error on a 0–1 scale against a white-composited rasterization. It is not a perceptual or human rating. Fast tracing can still discard important details. The texture fixture creates 32,160 paths / 11.4 MB SVG; its complete worker wall time, including quality rendering, was 17.2665 s. Typical logo/photo worker wall time was about 1–1.6 seconds because startup/imports are included.

Raw settings, results and measurement notes: [studio-results.json](studio-results.json), [photograph-results.json](photograph-results.json). Reproduce with `python benchmarks/studio.py` and `python benchmarks/photograph.py` in the development environment. Original 0.1 synthetic measurements remain in `results.json`; they use different settings and are not a direct apples-to-apples speed comparison.

The photograph is scikit-image's bundled NASA portrait of Eileen Collins, documented as public domain by [scikit-image](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut). The benchmark reads its installed local copy and does not fetch it at runtime. No input artwork is committed. One natural photo does not establish general photo quality. No paid engine was benchmarked, and low-end CPU/memory measurements are still needed.
