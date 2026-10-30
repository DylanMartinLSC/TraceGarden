# Third-party components

TraceGarden's MIT license applies to its own source. It does not replace dependency licenses. The portable bundle retains installed metadata and licenses where collected. A generated dependency license inventory is included beside this notice.

- VTracer 0.6.15 — MIT, https://github.com/visioncortex/vtracer (the current upstream development version may have different licensing/version behavior; this app pins the stable engine).
- Pillow — HPND, https://python-pillow.org/
- FastAPI, Starlette, Uvicorn — BSD/MIT family, respective project distributions.
- ReportLab — BSD, https://www.reportlab.com/
- svglib — LGPL-3.0-or-later; dynamically imported, unmodified, https://github.com/deeplook/svglib . Source available at that URL and on PyPI; users may replace the installed module. LGPL notices and license texts must accompany redistributed bundles.
- ezdxf — MIT, https://github.com/mozman/ezdxf
- svgpathtools — MIT, https://github.com/mathandy/svgpathtools
- NumPy, SciPy and bundled numerical libraries — BSD and accompanying third-party notices in distributions.
- Python and PyInstaller runtime — retain their distributed license notices. PyInstaller's bootloader exception permits application bundling.

See distribution metadata for complete transitive dependency terms. Before publishing a binary release, review the generated license inventory and shipped license files; this document is not a legal certification.
