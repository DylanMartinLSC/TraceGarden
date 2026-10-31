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
- [ ] Parameterized rotated/rounded rectangles, regular stars and rounded stars, circles and ellipses.
- [ ] Mirror and rotational symmetry detection and consistent repeated-shape modelling.
- [x] Corner workspace: individually sharp/rounded corners, bulk controls and live radius preview.
- [ ] Adaptive simplification/fairing that preserves faint features and corners.

## Workflows and output

- [x] Batch, projects, recovery, queue/cancel, headless CLI and local API.
- [x] Region recolor/merge/remove, brush segmentation repair, vector pen/node editing.
- [x] Wipe comparison, outline preview, synchronized pan/zoom, actual-size/full-canvas modes.
- [x] All advertised bitmap exports: PNG/JPG/TIFF/GIF/BMP.
- [x] Export drawing styles/grouping/curve choices and compatibility settings.
- [ ] Desktop clipboard and drag-out integration.
- [x] Large image handling with explicit memory/quality controls rather than the current small fixed cap.
- [ ] Native installable builds for supported desktop platforms, update workflow and user documentation.

## Evidence

- [ ] Every above capability has automated regression tests and a browser/desktop acceptance workflow.
- [ ] Licensed diverse corpus covers logos, scans, text-as-outlines, photographs, gradients, transparent art, small/ambiguous/low-resolution features.
- [ ] Publish reconstruction error, boundary error, path complexity, speed, memory, failure cases and commercial reference comparisons where accessible.
- [ ] No open parity blockers are labelled as an out-of-scope substitute for finishing.

Signing certificates and private commercial-engine access cannot be manufactured in source code. Those external requirements must be reported specifically if they prevent verification/distribution; they do not excuse leaving implementable functionality unfinished.

## Current validation notes

The newly checked capabilities have regression coverage in `test_parity.py`, `test_output_parity.py`, `test_resource_parity.py` and `parity_browser_check.py`. Alpha edge coverage is separated from genuine region opacity. Smooth graph chains are fitted once and reused in reverse in neighboring faces, with subpixel source sampling and whole closed-component models. The generated 27-case known-vector corpus is measured with the independent CPU resvg renderer.

**Still open:** production complexity/performance on the vendor-selected public demonstration images. Initial comparisons show acceptable agreement on some images but excessive path complexity on others; these are not passing full-parity evidence. The benchmark stores vendor artwork only in ignored `work/`, never as training data or redistributed source assets. Native package and desktop clipboard acceptance are also not complete merely because build code exists.
