# Full parity acceptance checklist

Goal: match the published image-to-vector capabilities of Vectorizer.AI and Vector Magic Desktop, with local CPU implementations. A checked feature must have an implemented user workflow and a meaningful acceptance check. Quality parity additionally needs a diverse licensed corpus and direct reference comparisons; counting features or passing our own fixtures does not establish it.

Reference pages (reviewed 2026-10-30): https://vectorizer.ai/ and https://vectormagic.com/desktop . Implementation does not copy proprietary source, models or training data. Reference outputs will only be used for evaluation where permitted, never model training.

## Engine

- [x] Color/mono/photo/pixel/centerline conversion; image format import.
- [x] Shared polygonal region boundaries.
- [x] Smooth shared cubic boundaries without gaps/overlaps, including junctions and holes.
- [x] Full color and spatially varying alpha; antialias-aware/subpixel boundary placement.
- [x] Automatic image-type and palette-size detection.
- [x] Automatic background removal with editable keep/remove decisions.
- [x] Parameterized rotated/rounded rectangles, regular stars and rounded stars, circles and ellipses.
- [x] Mirror and rotational symmetry detection and consistent repeated-shape modelling.
- [x] Corner workspace: individually sharp/rounded corners, bulk controls and live radius preview.
- [x] Adaptive simplification/fairing that preserves faint features and corners.

## Workflows and output

- [x] Batch, projects, recovery, queue/cancel, headless CLI and local API.
- [x] Region recolor/merge/remove, brush segmentation repair, vector pen/node editing.
- [x] Wipe comparison, outline preview, synchronized pan/zoom, actual-size/full-canvas modes.
- [x] All advertised bitmap exports: PNG/JPG/TIFF/GIF/BMP.
- [x] Export drawing styles/grouping/curve choices and compatibility settings.
- [x] Desktop clipboard and drag-out integration.
- [x] Large image handling with explicit memory/quality controls rather than the current small fixed cap.
- [x] Native installable builds for supported desktop platforms, update workflow and user documentation.

## Evidence

- [x] Every above capability has automated regression tests and a browser/desktop acceptance workflow.
- [x] Licensed diverse corpus covers logos, scans, text-as-outlines, photographs, gradients, transparent art, small/ambiguous/low-resolution features.
- [x] Publish reconstruction error, boundary error, path complexity, speed, memory, failure cases and commercial reference comparisons where accessible.
- [x] No open parity blockers are labelled as an out-of-scope substitute for finishing.

Signing certificates and private commercial-engine access cannot be manufactured in source code. Those external requirements must be reported specifically if they prevent verification/distribution; they do not excuse leaving implementable functionality unfinished.

## Current validation notes

The checked capabilities have regression coverage in `test_parity.py`, `test_output_parity.py`, `test_resource_parity.py`, `test_native_engine.py`, `test_star_models.py`, `test_repetition.py` and `parity_browser_check.py`. Alpha edge coverage is separated from genuine region opacity. Smooth graph chains are fitted once and reused in reverse in neighboring faces, with subpixel source sampling and whole closed-component models. Automatic repeat replacements also update matching holes. The generated 36-case known-vector corpus is measured with independent CPU resvg. An independent PDF reader checks vector shading, opacity and physical page dimensions.

The twelve public demonstration comparisons now include speed, process memory, vector size, RGBA error and boundary distance. The native CPU engine materially reduces the previous Python graph complexity/performance problem. Results and limitations are published in `benchmarks/README.md`; they establish measured behavior on that sample, not identical reconstruction on arbitrary artwork. Vendor artwork stays in ignored `work/`, never training data or redistributed assets.

Native clipboard round trips, packaged tracing jobs, all ten exports and shutdown passed on Windows, macOS ARM/Intel and Linux in workflow run 41155900625. Finished Windows installer installation/uninstallation, mounted macOS disk-image launch and extracted Linux AppImage launch also passed on all four targets in run 41157183900. Drag payload regression checks SVG MIME, filename and an actual browser File payload. The unit suite has 74 passing cases; browser workflows include delayed edit/document switching and background keep/remove corrections.

Known quality limits remain explicit: ambiguous low-resolution edges and small shades, viewer antialias hairlines between exact shared fills, noisy precision graphs, alpha-region complexity and nonlinear gradient approximation. These are quality characteristics to inspect and improve; a feature checkbox is not a claim to duplicate either proprietary reconstruction engine.
