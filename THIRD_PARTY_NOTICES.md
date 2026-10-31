# Third-party components

TraceGarden source is MIT. Dependency licenses remain their own and are included in `third-party-licenses` and the portable package. The dependency inventory is generated from installed distribution metadata; some development-only libraries are included. It is not a legal certification.

- VTracer 1.0.0a4 — MIT OR Apache-2.0; distributed under the MIT option, https://github.com/visioncortex/vtracer/tree/1.0.0-alpha.4 . The native API is pinned and tested on supported platforms. The wheel omits license files, so the exact tagged upstream LICENSE is included in `third-party-licenses/vtracer/LICENSE`.
- resvg-py / resvg — MIT and bundled Rust dependency terms; included distribution license, https://github.com/baseplate-admin/resvg-py and https://github.com/RazrFalcon/resvg .
- Pillow — HPND and bundled codec notices, https://python-pillow.org/
- FastAPI / Starlette / Uvicorn — MIT / BSD licenses in distributions.
- NumPy / SciPy / scikit-image — BSD family plus included third-party numerical and algorithm notices.
- OpenCV — Apache-2.0 and bundled notices; headless CPU build.
- Shapely — BSD; GEOS is LGPL-2.1-or-later, dynamically linked and unmodified. Users may replace the shared GEOS libraries. Source: https://libgeos.org/ and https://github.com/libgeos/geos . Preserve its LGPL license and corresponding source/relinking rights when redistributing.
- ReportLab — BSD; retain bundled font notices. TraceGarden's export path uses vector geometry, not the optional bundled display fonts.
- ezdxf / svgpathtools — MIT.
- defusedxml — Python Software Foundation license.
- psutil — BSD.
- Python and PyInstaller runtime — retain Python licensing and PyInstaller's bootloader exception.

Version 0.1 used svglib and rl-renderPM. Version 0.2 no longer imports either; leftover environment notices may still be present in the inventory. See actual distribution metadata for full transitive terms. Review generated notices before publishing binary releases.
