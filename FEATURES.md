# Version 0.3 workflow coverage

References: [Vectorizer.AI](https://vectorizer.ai/) and [Vector Magic Desktop](https://vectormagic.com/desktop), reviewed October 30, 2026. This inventory describes implemented functionality. Reconstruction results differ between engines; measured comparisons and limits are in [benchmarks](benchmarks/README.md). Acceptance evidence is tracked in [PARITY.md](PARITY.md).

| Workflow | Implementation and evidence |
|---|---|
| Local CPU conversion | Native Rust engine plus Python precision geometry; isolated jobs, cancellation, queue and timeout tests |
| Image import and batch | Picker/drop/paste, PNG/JPEG/WebP/GIF/BMP/TIFF, batch ZIP, CLI/API; browser workflows |
| Automatic artwork/palette detection | Flat-interior palette analysis with small-accent regression; manual presets/custom palettes |
| Shared boundaries | Native and precision shared cubic curves, junctions/holes, polygon coverage; no-overlap/gap regressions |
| Transparency and antialias coverage | Separate RGB+A regions, subpixel precision fitting and alpha coverage; rendered-alpha regressions |
| Whole geometry | Circles/ellipses, rotated rounded rectangles, regular/rounded/stretched stars, polygons; model and raster tests |
| Corners | Individual/all-corner sharpening/rounding, radius preview, apply/discard; browser and geometry tests |
| Symmetry and repeats | Mirror/rotational detection, automatic repeat families, manual match/normalize; shared-hole preservation tests |
| Background/segmentation correction | Automatic border removal, keep/restore-original and transparent removal brushes, color paint and brush undo |
| Vector editing | Recolor/opacity, multiselect, join/subtract/intersect/split, delete, simplify, reverse, layer order, pen, nodes and Bezier controls |
| Inspection | Side-by-side/wipe/outlines, synchronized pan/zoom, actual-size and fullscreen; desktop/mobile browser checks |
| Projects/recovery | Portable source+vector projects, local IndexedDB autosave/recovery, stale-response protection; browser checks |
| Gradients | Conditional linear-region fitting, preserved foreground detail, SVG/PDF/EPS vector gradients; reconstruction and independent PDF checks |
| SVG/PDF/EPS/AI | Editable SVG, vector PDF/EPS and PDF-compatible AI; EPS has no transparency; AI has no native Illustrator authoring metadata |
| DXF | Exact circular/elliptical arcs, cubic splines, modern or R12 polylines; independent ezdxf reader tests |
| Bitmap export | PNG/JPG/GIF/BMP/TIFF, physical dimensions/DPI and alpha where supported; independent Pillow reads |
| Export controls | Group by color, fill/stroke styles, cubic/quadratic/polyline compatibility, physical width and generic CMYK PDF |
| Clipboard/drag | Native Windows/macOS/Linux SVG clipboard with system fallbacks; real CI round trips; browser SVG file drag payload |
| Large inputs/resources | 100 MB/100 MP source limit, JPEG draft decoding, configurable memory/detail/time budgets; large-JPEG regression |
| Native distribution | Windows Setup/portable, macOS ARM/Intel DMG, Linux AppImage; packaged tracing/export/shutdown checks and installer acceptance |
| Updates | Explicit public GitHub release lookup and download link; no automatic network requests during conversion |

The source is MIT licensed. Dependencies retain their own FOSS licenses; notices are included. Signing certificates and native authoring metadata are not supplied. No editable-text OCR is advertised: lettering is traced into outlines. Nonlinear gradients can remain color-region approximations.
