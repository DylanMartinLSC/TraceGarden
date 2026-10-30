# Feature coverage and release gaps

Commercial reference pages reviewed October 28, 2026: [Vectorizer.AI](https://vectorizer.ai/), [Vector Magic Desktop](https://vectormagic.com/desktop), [Vector Magic features](https://vectormagic.com/). Claims here reflect published workflows, not a head-to-head test.

| Capability | TraceGarden 0.1 |
|---|---|
| Local, CPU conversion without account | Implemented |
| Drag/drop, paste, file picker | Implemented |
| Color, monochrome, polygon and spline paths | Implemented through presets |
| Batch processing and ZIP download | Implemented, sequential, 20-file batch |
| SVG, PDF, EPS | Implemented, vector paths |
| DXF | Sampled polylines only, unitless; not exact Bezier/arc geometry |
| PNG preview export | Implemented, raster |
| Side-by-side preview and zoom | Implemented |
| Transparent input / near-white removal | Implemented with alpha limitations in README |
| Palette editing, remove shape, undo/reset | Implemented |
| Real circles/ellipses/arcs reconstruction | Not implemented |
| Shared topology / guaranteed nonoverlapping cut paths | Not implemented; stacked tracing can overlap |
| Manual node editing, pen, join/split and segmentation brush | Not implemented; open SVG in a full vector editor |
| True gradients / meshes | Not implemented |
| Editable text / font recognition | Not implemented |
| Centerline tracing | Not implemented; ink traces filled outlines |
| Native AI format | Not implemented; SVG/PDF can be imported by design tools |
| CMYK / ICC-managed print workflow | Not implemented; input converted to RGB without ICC profile conversion |
| Crop / rotation tools | Not implemented; EXIF orientation is applied |
| Persistent project documents | Not implemented |
| Cancel, background job recovery | Not implemented |
| Signed installer and automatic updates | Not implemented; portable Windows bundle only |

## Next release priorities

1. Diverse real-image corpus with consent/licensing, raster reconstruction metrics, human ratings and peak-RSS benchmarks on low-end CPUs.
2. Cutout topology and geometric primitives; cutting-tool compatibility tests before recommending manufacturing use.
3. Gradient/photo improvements, segmentation brushes and node editing; undoable cropping and rotation.
4. Persistent projects, cancellation through isolated worker processes, crash recovery.
5. Signed Windows installer, tested macOS/Linux packages, keyboard/screen-reader user testing and localization.

The current app is functional for common flat-art tracing, but these gaps prevent an honest assertion of full paid-service parity or a finished public release.
