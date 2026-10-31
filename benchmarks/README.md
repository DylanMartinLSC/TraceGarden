# CPU, memory and reconstruction measurements

## Current 0.3 development comparison

Twelve source/reference pairs are publicly advertised on [Vectorizer.AI](https://vectorizer.ai/). The benchmark downloads those exact public example URLs only when explicitly requested; cached artwork remains in ignored `work/`. No user uploads, accounts, model training or vendor artwork redistribution are involved. The sample set is vendor-selected and consists of illustrated artwork and logos.

Both outputs are rendered by independent CPU resvg at the input dimensions. MAE compares premultiplied RGBA on a 0–1 scale. Boundary distance is the symmetric mean distance between silhouette/color-change pixels (threshold 0.025), in input pixels. These measure agreement with the example output; they do not prove identical quality, perceptual equivalence or superiority. Input error can reward retaining JPEG artifacts. Vendor timing/memory are unavailable.

| Example | CPU seconds | SVG size / reference | RGBA MAE to reference | Boundary distance, px |
|---|---:|---:|---:|---:|
| bubble-tea | 0.237 | 2.85× | 0.0282 | 0.494 |
| bull-mascot | 0.173 | 0.75× | 0.0054 | 0.165 |
| cloud-computing | 0.113 | 0.79× | 0.0119 | 0.329 |
| coffee-fox | 0.134 | 0.66× | 0.0091 | 0.150 |
| coffee-shop | 0.253 | 0.69× | 0.0094 | 0.147 |
| geometric-shapes | 0.105 | 1.53× | 0.0041 | 0.138 |
| leaping-stag | 0.186 | 1.00× | 0.0102 | 0.196 |
| lion-mascot | 0.199 | 0.62× | 0.0124 | 0.168 |
| mountain-supply | 0.249 | 0.75× | 0.0103 | 0.182 |
| national-park | 0.199 | 0.57× | 0.0088 | 0.151 |
| seaside-panther | 0.405 | 2.59× | 0.0182 | 0.433 |
| wolf-mascot | 0.149 | 0.83× | 0.0193 | 0.181 |

Median tracing time is 0.192 seconds; the largest measured whole-process RSS is 179.4 MiB. RSS includes Python, imports and preceding cases, sampled every 2ms during tracing. It is not isolated worker memory or a low-end-machine measurement. Settings, versions, source URLs and SHA-256 hashes are in [reference-results.json](reference-results.json).

A separate run restricted the same process to one logical CPU: median 0.191 seconds, slowest 0.359 seconds, peak whole-process RSS 178.7 MiB. This is one hardware thread on the same fast desktop, not a low-end CPU emulation. See [single-CPU results](reference-single-cpu-results.json); reproduce with `--one-cpu --output benchmarks/reference-single-cpu-results.json`.

The current public-domain NASA photograph workload uses three fresh spawned workers: 0.240 seconds median trace time, 1.192 seconds median total worker wall time, 116.4 MiB peak RSS, 814 paths and normalized RGB MAE 0.04627. [Raw 0.3 photo results](photograph-0.3-results.json) include settings and version information.

## Known-vector reconstruction corpus

[parity-results.json](parity-results.json) contains 36 generated CC0 fixtures: circles, rotated ellipses/rounded rectangles, stars, thin strokes, nested holes, adjacent colors, varying alpha, faint corners, text outlines, scan-like lines and a linear gradient at 64/128/256 pixels. The precision shared-curve mode is evaluated against original vector truth using resvg. This is an acceptance corpus, not a representative sample of all real artwork. The photographic benchmark below uses a public-domain NASA portrait.

Observed limits: low-resolution blended edges remain ambiguous; automatic palettes can approximate small shades; exact shared fills can show antialias hairlines in viewers; noisy shared-curve graphs can become slow and fall back to polygons; full alpha may need many regions; nonlinear gradients remain region approximations. Inspect source/result and choose stacked output or adjust settings when needed. Whole-gradient fitting now rejects foreground detail rather than replacing it with a color plane.

Reproduce with `python benchmarks/parity_corpus.py` and `python benchmarks/reference_compare.py --download-public-examples`. Commercial example assets are not included in the repository. Older measurements below use different engine/settings and must not be combined with current results.

## Historical 0.2 workloads

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

The photograph is scikit-image's bundled NASA portrait of Eileen Collins, documented as public domain by [scikit-image](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut). The benchmark reads its installed local copy and does not fetch it at runtime. No input artwork is committed. One natural photo does not establish general photo quality. Those historical workloads did not include commercial examples. Low-end CPU/memory measurements are still needed.
