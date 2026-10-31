"""Generate attributed comparison figures; requires matplotlib, Pillow and resvg-py."""

import argparse
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import resvg_py
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
report = json.loads(
    Path("benchmarks/reference-results.json").read_text(encoding="utf-8")
)
rows = report["results"]
cache = Path("work/reference-examples")
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "text.color": "#18392f",
        "axes.titlecolor": "#18392f",
        "figure.facecolor": "#f6f5ef",
        "savefig.facecolor": "#f6f5ef",
    }
)


def render(row, scale=1, crop=None):
    name = row["case"]
    w, h = row["size"]
    pictures = []
    original = Image.open(cache / f"{name}.jpg").convert("RGBA")
    pictures.append(original)
    for file in [cache / f"{name}.svg", cache / f"{name}-tracegarden.svg"]:
        image = Image.open(
            io.BytesIO(
                resvg_py.svg_to_bytes(
                    svg_string=file.read_text(encoding="utf-8"),
                    width=w * scale,
                    height=h * scale,
                    skip_system_fonts=True,
                )
            )
        ).convert("RGBA")
        pictures.append(image)
    if crop:
        rect = tuple(round(v * d) for v, d in zip(crop, [w, h, w, h]))
        pictures[0] = (
            pictures[0]
            .crop(rect)
            .resize(
                ((rect[2] - rect[0]) * scale, (rect[3] - rect[1]) * scale),
                Image.Resampling.NEAREST,
            )
        )
        for i in [1, 2]:
            pictures[i] = pictures[i].crop(tuple(x * scale for x in rect))
    return pictures


def page(group, detail=False):
    fig = plt.figure(figsize=(14, 17))
    grid = fig.add_gridspec(
        4,
        3,
        left=0.055,
        right=0.975,
        top=0.875,
        bottom=0.075,
        wspace=0.035,
        hspace=0.34,
    )
    fig.text(
        0.055,
        0.963,
        "VISUAL COMPARISON" + (" / MATCHED CLOSE-UPS" if detail else ""),
        size=22,
        weight="bold",
    )
    fig.text(
        0.055,
        0.936,
        "Original input   /   public Vectorizer.AI reference   /   TraceGarden 0.3 output",
        size=12,
    )
    fig.text(
        0.055,
        0.912,
        "12 vendor-selected public examples. No Vector Magic or commercial speed/memory benchmark.",
        size=10,
        color="#52665c",
    )
    for c, label in enumerate(
        ["ORIGINAL RASTER", "VECTORIZER.AI REFERENCE", "TRACEGARDEN"]
    ):
        fig.text(0.055 + c * (0.92 / 3), 0.89, label, size=10, weight="bold")
    for r, row in enumerate(group):
        crop = CROPS.get(row["case"]) if detail else None
        images = render(row, 4 if detail else 1, crop)
        for c, image in enumerate(images):
            ax = fig.add_subplot(grid[r, c])
            ax.set_facecolor("white")
            matte = Image.new("RGBA", image.size, "white")
            matte.alpha_composite(image)
            ax.imshow(matte.convert("RGB"), interpolation="nearest")
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_color("#ccd4ca")
                spine.set_linewidth(0.65)
            if c == 0:
                ax.set_title(
                    row["case"].replace("-", " ").title(),
                    loc="left",
                    size=11,
                    pad=10,
                    weight="bold",
                )
            if not detail:
                if c == 0:
                    label = f"{row['size'][0]} x {row['size'][1]} pixels"
                elif c == 1:
                    label = f"SVG {row['reference_svg_bytes']:,} bytes | input MAE {row['vendor_mae_vs_input']:.4f}"
                else:
                    label = f"SVG {row['svg_bytes']:,} bytes | input MAE {row['mae_vs_input']:.4f}"
                ax.set_xlabel(label, size=9, labelpad=9)
            elif c == 0:
                ax.set_xlabel("Matched source-space crop", size=9, labelpad=9)
    fig.text(
        0.055,
        0.038,
        "Close-ups: vectors rendered at 4x; input pixels enlarged without smoothing."
        if detail
        else "All three overview panels use the same source-pixel dimensions and nearest-neighbor display.",
        size=9,
        color="#52665c",
    )
    fig.text(
        0.055,
        0.022,
        "Input MAE is pixel error, not a perceptual quality score. Source links, hashes and settings: benchmarks/reference-results.json.",
        size=9,
        color="#52665c",
    )
    return fig


CROPS = {
    "bubble-tea": (0.12, 0.10, 0.84, 0.40),
    "cloud-computing": (0.05, 0.02, 0.68, 0.40),
    "lion-mascot": (0.18, 0.02, 0.9, 0.43),
    "seaside-panther": (0.42, 0.14, 0.94, 0.65),
}
with PdfPages(
    args.output / "TraceGarden-visual-comparisons.pdf",
    metadata={
        "Title": "TraceGarden and Vectorizer.AI: twelve public example comparisons",
        "Author": "TraceGarden evaluation",
        "Subject": "Public reference-output comparison; not proof of general quality parity",
    },
) as pdf:
    for index in range(3):
        fig = page(rows[index * 4 : index * 4 + 4])
        fig.savefig(args.output / f"Visual-comparison-{index + 1:02d}.png", dpi=150)
        pdf.savefig(fig)
        plt.close(fig)
    fig = page([next(r for r in rows if r["case"] == name) for name in CROPS], True)
    fig.savefig(args.output / "Visual-comparison-closeups.png", dpi=170)
    pdf.savefig(fig)
    plt.close(fig)
print("Created three four-case overview charts, matched close-ups and a four-page PDF.")
