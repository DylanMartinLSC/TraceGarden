"""Publish explicit paired metrics; build a private, offline visual gallery.

No third-party artwork is committed. The HTML is generated from the ignored
reference cache populated by reference_compare.py --download-public-examples.
"""

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path


def markdown(report):
    lines = [
        "# Actual comparison coverage",
        "",
        "The commercial comparison is limited to **12 public Vectorizer.AI example pairs**. "
        "We have **not benchmarked Vector Magic Desktop**, commercial service latency, "
        "commercial CPU usage or commercial memory use. TraceGarden timing/memory figures "
        "elsewhere in this folder measure TraceGarden alone. These results do not establish "
        "general commercial quality parity.",
        "",
        "Each row below includes the original input and the vendor-provided SVG reference. "
        "Both SVGs are rendered at the input dimensions using resvg. Sizes are uncompressed "
        "SVG bytes. MAE is premultiplied RGBA error against the original input on a 0–1 scale. "
        "Lower input MAE can reward retaining JPEG noise or blur; it is not a perceptual "
        "quality ranking. The source set was selected by the vendor, not sampled independently.",
        "",
        "| Example / original | Vectorizer.AI reference | Vectorizer.AI SVG bytes | TraceGarden SVG bytes | Vectorizer.AI input MAE | TraceGarden input MAE |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in report["results"]:
        lines.append(
            f"| [{row['case']}]({row['urls']['jpg']}) | [View SVG]({row['urls']['svg']}) "
            f"| {row['reference_svg_bytes']:,} | {row['svg_bytes']:,} "
            f"| {row['vendor_mae_vs_input']:.6f} | {row['mae_vs_input']:.6f} |"
        )
    rows = report["results"]
    smaller = sum(r["svg_bytes"] < r["reference_svg_bytes"] for r in rows)
    lower_error = sum(r["mae_vs_input"] < r["vendor_mae_vs_input"] for r in rows)
    lines += [
        "",
        f"On these {len(rows)} examples, TraceGarden produces smaller SVGs on {smaller} "
        f"and lower input MAE on {lower_error}. Neither statistic establishes better visual quality.",
        "",
        "## Visual comparison",
        "",
        "Generate an offline gallery with original raster, Vectorizer.AI reference, and "
        "TraceGarden output shown together. It includes synchronized zoom/scroll and paired metrics. "
        "Third-party artwork remains in the local cache and generated gallery, outside the published source.",
        "",
        "```sh",
        "python benchmarks/reference_compare.py --download-public-examples",
        "python benchmarks/comparison_report.py",
        "# Open work/reference-comparison.html in a browser.",
        "```",
        "",
        "The gallery uses browser SVG rendering; numeric metrics use resvg. Raw results, "
        "source URLs, input/reference SHA-256 hashes, settings and environment details are in "
        "[reference-results.json](reference-results.json). The [main report](README.md) "
        "also lists error between the two outputs and measured TraceGarden resource use.",
    ]
    return "\n".join(lines) + "\n"


def gallery(report, cache):
    cards = []
    for row in report["results"]:
        name = row["case"]
        original = (cache / f"{name}.jpg").read_bytes()
        reference = (cache / f"{name}.svg").read_bytes()
        actual = (cache / f"{name}-tracegarden.svg").read_text(encoding="utf-8")
        for kind, data in [("jpg", original), ("svg", reference)]:
            if hashlib.sha256(data).hexdigest() != row["sha256"][kind]:
                raise ValueError(f"{name}: cached {kind} differs from measured source.")
        if len(actual.encode()) != row["svg_bytes"]:
            raise ValueError(
                f"{name}: output size differs from report; regenerate the benchmark."
            )
        images = []
        for label, mime, data in [
            ("Original input", "image/jpeg", original),
            ("Vectorizer.AI reference", "image/svg+xml", reference),
            ("TraceGarden", "image/svg+xml", actual.encode()),
        ]:
            encoded = base64.b64encode(data).decode()
            images.append(
                f'<figure><figcaption>{label}</figcaption><div class="viewport">'
                f'<div class="image" style="aspect-ratio:{row["size"][0]}/{row["size"][1]}">'
                f'<img alt="{html.escape(name)} — {label}" src="data:{mime};base64,{encoded}">'
                "</div></div></figure>"
            )
        cards.append(
            f'<section><h2>{html.escape(name)}</h2><div class="row">{"".join(images)}</div>'
            f"<p>SVG bytes: Vectorizer.AI <b>{row['reference_svg_bytes']:,}</b>; "
            f"TraceGarden <b>{row['svg_bytes']:,}</b>. Input MAE: "
            f"Vectorizer.AI <b>{row['vendor_mae_vs_input']:.6f}</b>; "
            f"TraceGarden <b>{row['mae_vs_input']:.6f}</b>.</p>"
            f'<p><a href="{html.escape(row["urls"]["jpg"])}">Original source</a> · '
            f'<a href="{html.escape(row["urls"]["svg"])}">Vendor reference source</a></p></section>'
        )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TraceGarden / Vectorizer.AI — visual comparisons</title>
<style>body{font:16px system-ui;max-width:1600px;margin:24px auto;padding:0 20px;color:#17382d;background:#f7f6f1}
header{position:sticky;top:0;background:#f7f6f1;z-index:1;padding:12px;border-bottom:1px solid #bbb}
section{padding:20px 0;border-bottom:1px solid #bbb}.row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
figure{margin:0;min-width:0}figcaption{font-weight:700;padding:8px}.viewport{height:420px;overflow:auto;background:repeating-conic-gradient(#fff 0% 25%,#eee 0% 50%) 0/20px 20px;border:1px solid #ccc}
.image{width:calc(100% * var(--zoom,1));position:relative}img{display:block;width:100%;height:100%}a{color:#175cb0}input{vertical-align:middle}
@media(max-width:700px){.row{grid-template-columns:1fr}.viewport{height:350px}}</style>
<header><h1>TraceGarden / Vectorizer.AI</h1><p>12 public example pairs. No Vector Magic comparison or commercial speed/memory measurements.</p>
<label>Zoom all images <input id="zoom" type="range" min="1" max="4" step=".25" value="1"><output id="level">1×</output></label></header>
<p>These are public vendor-selected examples, not an independent quality ranking. Input error can reward JPEG artifacts. Browser previews may differ slightly from the resvg renderer used for metrics. This gallery is self-contained and makes no network requests unless you open a source link.</p>
"""
        + "".join(cards)
        + """<script>
document.getElementById('zoom').oninput=e=>{document.documentElement.style.setProperty('--zoom',e.target.value);document.getElementById('level').textContent=e.target.value+'×'};
document.querySelectorAll('.row').forEach(row=>{let active=false;row.querySelectorAll('.viewport').forEach(view=>view.onscroll=()=>{if(active)return;active=true;row.querySelectorAll('.viewport').forEach(other=>{if(other!==view){other.scrollTop=view.scrollTop;other.scrollLeft=view.scrollLeft}});requestAnimationFrame(()=>active=false)})});
</script></html>"""
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report", type=Path, default=Path("benchmarks/reference-results.json")
    )
    parser.add_argument("--cache", type=Path, default=Path("work/reference-examples"))
    parser.add_argument(
        "--html", type=Path, default=Path("work/reference-comparison.html")
    )
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    Path("benchmarks/COMPARISONS.md").write_text(
        markdown(report), encoding="utf-8", newline="\n"
    )
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.html.write_text(gallery(report, args.cache), encoding="utf-8", newline="\n")
    print(f"Wrote paired comparison table and {args.html}")
