# Published 0.2 workflow coverage

This table describes the published 0.2 release. Current full-parity development is tracked in [PARITY.md](PARITY.md), with tests and evidence; it remains an active, unfinished objective.

Reference workflows: [Vectorizer.AI](https://vectorizer.ai/) and [Vector Magic Desktop](https://vectormagic.com/desktop), reviewed October 30, 2026. This is a capability inventory, not proof that proprietary reconstruction quality has been matched.

| Capability | TraceGarden 0.2 | Verification / qualification |
|---|---|---|
| Local CPU image conversion | Implemented | All runtime processing local; no GPU |
| Drop, paste, picker, batch and ZIP | Implemented | Browser suite |
| Color, mono, pixel, smooth tracing | Implemented | Preset regression tests |
| Side-by-side and zoom | Implemented | Browser suite; no draggable wipe comparator |
| Palette selection and replacement | Implemented | Custom quantization + editing |
| Transparency | Per-region opacity | Uniform-alpha test; variable alpha approximated |
| Crop, rotate, mirror, contrast, profile handling | Implemented | Transform/palette tests; crop before rotation |
| Manual segmentation corrections | Raster brush | Join/separate/remove marks before retracing |
| Ellipses, circles, rectangles, rounded rectangles, polygon outlines | Conditional fitting | Circular-arc reconstruction and DXF test; rounded rectangles axis-aligned |
| Shared boundaries | Coverage mode | No-area-overlap/gap and nested-island tests; polygonal boundaries |
| Gradients | Two-stop linear | Rendered RGB error and PDF/EPS gradient tests |
| SVG/PDF/EPS | Vector export | Tests; EPS has no opacity |
| AI | PDF-compatible export | Not Illustrator-native metadata |
| DXF | Curves or polylines | Exact circular arcs, cubic splines; ellipse approximation |
| PNG | Alpha-aware raster preview | Physical-size and alpha tests |
| Print controls | Width, DPI, generic CMYK PDF | No press-profile proofing |
| Shape edits | Color/opacity/delete/order, Boolean ops, splitting, simplify, reverse | Area and browser tests |
| Node/curve tools | Polygon nodes and Bezier controls | Coordinate editor and draggable handles; compound contours require split |
| Pen tool | Polygons and open strokes | Browser pointer test |
| Undo/redo | Vector and brush histories | Browser tests; history resets on project import |
| Save and recovery | Portable projects + browser autosave | Reload and file roundtrip tests |
| Cancel and recovery from stalls | Worker isolation and 120s timeout | Lifecycle/cancellation tests |
| Pipeline access | CLI and localhost API | Headless batch command and API suite |
| Public release packaging | Portable Windows build | Unsigned; native macOS/Linux installers absent |
| Benchmarks | Speed, sampled RSS, rendered MAE | Synthetic fixtures + one NASA photograph; no vendor comparison |

## Remaining limits

This version covers the common local tracing/edit/export workflow substantially more broadly than 0.1. It does not establish full quality or exact feature parity with every paid service. Shared-boundary mode is polygonal; smooth shared splines need further work. Nonlinear gradients/meshes, editable text/OCR, native Illustrator document data, arbitrary rounded-shape fitting, signed distribution and automatic updates are outside the current implementation. A broad licensed real-image corpus, human evaluation, low-end hardware measurements, manufacturing compatibility trials and accessibility/localization testing remain release-quality work.

A test fixture passing is evidence for that fixture, not a universal geometric or quality guarantee. API validation and job isolation help local robustness; the application is not a public multi-tenant hosting server.
