# Comparison figure provenance

These figures compare the original raster, the public Vectorizer.AI reference SVG, and TraceGarden's corresponding output for twelve vendor-selected public examples. Individual source URLs, source/reference SHA-256 hashes, settings and measurements are recorded in [reference-results.json](../../benchmarks/reference-results.json). The [paired report](../../benchmarks/COMPARISONS.md) explains the comparison's limits.

The original artwork and reference SVGs come from the public examples linked on https://vectorizer.ai/. Third-party artwork and reference outputs retain their owners' rights; they are not relicensed under TraceGarden's MIT source-code license or the generated fixture corpus's CC0 dedication. These are comparative evaluation figures, not standalone artwork assets.

The charts were generated from the cached measured outputs using Matplotlib and CPU resvg. Overview panels use equal source-pixel dimensions and nearest-neighbor display. Close-ups render vectors at four times source resolution and enlarge original raster pixels without smoothing; crops match in source coordinates. The PDF contains three overview pages covering all twelve examples and one page of selected close-ups.

Input MAE measures pixel error against the original raster, not perceptual quality. No Vector Magic comparison or commercial speed/memory measurement is included. Example selection and the displayed crop regions are not an independently sampled quality study.

To regenerate from the measured local cache in the development environment:

```sh
python -m pip install matplotlib
python benchmarks/visual_charts.py --output docs/comparisons
```

Populate the cache first with `python benchmarks/reference_compare.py --download-public-examples` if needed. Matplotlib is a chart-generation dependency, not a runtime dependency of the vector studio.
