"use strict";
const originalConfig = config;
config = function () {
  const value = originalConfig();
  for (const id of ["background", "background_color", "symmetry"])
    value[id] = $(id).value;
  for (const id of [
    "background_tolerance",
    "symmetry_order",
    "memory_limit_mib",
    "timeout_seconds",
  ])
    value[id] = Number($(id).value);
  return value;
};
const originalExportConfig = exportConfig;
exportConfig = function () {
  const value = originalExportConfig();
  for (const id of ["grouping", "draw_style", "curve_mode", "compatibility"])
    value[id] = $(id).value;
  return value;
};
const originalSetView = setView;
setView = function () {
  originalSetView();
  $("previews").classList.toggle("wipe-mode", view === "wipe");
  $("previews").classList.toggle("outline-view", view === "outlines");
  $("wipeControl").hidden = view !== "wipe";
  if (view === "outlines") {
    $("originalPane").hidden = true;
    $("vectorPane").hidden = false;
  }
  $("vectorPane").style.clipPath =
    view === "wipe" ? `inset(0 0 0 ${$("compareSplit").value}%)` : "";
};
$("compareSplit").oninput = setView;
$("fullCanvas").onclick = () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else
    $("previews")
      .requestFullscreen()
      .catch((error) => status(error.message, true));
};
$("actualSize").onclick = () => {
  for (const element of [$("original"), svgElement()])
    if (element) {
      element.style.width = `${items[current]?.result?.width || element.naturalWidth}px`;
      element.style.maxHeight = "none";
      element.parentElement.classList.add("zoomed");
    }
};
let syncingScroll = false,
  pan = null,
  wasPan = false;
document.querySelectorAll(".viewport").forEach((viewport) => {
  viewport.addEventListener("scroll", () => {
    if (syncingScroll) return;
    syncingScroll = true;
    document.querySelectorAll(".viewport").forEach((other) => {
      if (other !== viewport) {
        other.scrollLeft = viewport.scrollLeft;
        other.scrollTop = viewport.scrollTop;
      }
    });
    syncingScroll = false;
  });
  viewport.addEventListener("pointerdown", (event) => {
    wasPan = false;
    if (event.button !== 1 && !event.altKey) return;
    event.preventDefault();
    pan = {
      viewport,
      x: event.clientX,
      y: event.clientY,
      left: viewport.scrollLeft,
      top: viewport.scrollTop,
    };
    viewport.setPointerCapture(event.pointerId);
  });
  viewport.addEventListener("pointermove", (event) => {
    if (pan?.viewport !== viewport) return;
    wasPan = true;
    viewport.scrollLeft = pan.left + pan.x - event.clientX;
    viewport.scrollTop = pan.top + pan.y - event.clientY;
  });
  viewport.addEventListener("pointerup", () => {
    pan = null;
  });
});
const previousVectorClick = $("vector").onclick;
$("vector").onclick = (event) => {
  if (!wasPan) previousVectorClick(event);
};
const previousRender = render;
render = function () {
  cornerBase = null;
  cornerPreview = null;
  ++cornerSequence;
  previousRender();
  if ($("parityFeedback")) {
    const result = items[current]?.result;
    const parts = [];
    if (result?.analysis?.preset)
      parts.push(
        `Automatic: ${result.analysis.preset}, ${result.analysis.colors} colors`,
      );
    if (result?.background?.pixels)
      parts.push(
        `Removed ${result.background.pixels} border-background pixels`,
      );
    if (result?.symmetry?.length)
      parts.push(`Symmetry: ${result.symmetry.join(", ")}`);
    if (result?.full_alpha) parts.push("Spatially varying alpha preserved");
    $("parityFeedback").textContent = parts.join(" · ");
  }
};
let cornerBase = null,
  cornerPreview = null,
  cornerIndices = [],
  cornerSequence = 0,
  cornerTimer;
$("loadCorners").onclick = async () => {
  if (selection.size !== 1) {
    status("Select one shape to load its corners.");
    return;
  }
  try {
    cornerBase = items[current].svg;
    cornerIndices = selectedIndices();
    const result = await request("/api/edit", {
      svg: cornerBase,
      operation: "corner-info",
      indices: cornerIndices,
    });
    $("cornerChoice").replaceChildren(new Option("All corners", "all"));
    for (const corner of result.corners)
      $("cornerChoice").append(
        new Option(
          `Corner ${corner.index + 1} (${Math.round(corner.x)}, ${Math.round(corner.y)})`,
          String(corner.index),
        ),
      );
    status(
      `${result.corners.length} corners loaded. Change the radius to preview.`,
    );
  } catch (error) {
    status(error.message, true);
  }
};
async function previewCorners() {
  if (!cornerBase) {
    status("Load the selected shape’s corners first.");
    return;
  }
  const sequence = ++cornerSequence;
  try {
    const result = await request("/api/edit", {
      svg: cornerBase,
      operation: "round-corners",
      indices: cornerIndices,
      radius: Number($("cornerRadius").value),
      corner_indices:
        $("cornerChoice").value === "all"
          ? null
          : [Number($("cornerChoice").value)],
    });
    if (sequence !== cornerSequence) return;
    cornerPreview = result.svg;
    const parsed = new DOMParser().parseFromString(
      cornerPreview,
      "image/svg+xml",
    );
    $("vector").replaceChildren(
      document.importNode(parsed.documentElement, true),
    );
    zoom();
    status("Corner preview. Apply to keep it, or discard.");
  } catch (error) {
    status(error.message, true);
  }
}
$("cornerRadius").oninput = () => {
  $("cornerRadiusValue").textContent = $("cornerRadius").value;
  clearTimeout(cornerTimer);
  cornerTimer = setTimeout(previewCorners, 150);
};
$("cornerChoice").onchange = previewCorners;
$("sharpCorners").onclick = () => {
  $("cornerRadius").value = "0";
  $("cornerRadiusValue").textContent = "0";
  previewCorners();
};
$("applyCorners").onclick = () => {
  if (!cornerPreview) return;
  snapshot();
  items[current].svg = cornerPreview;
  cornerPreview = null;
  cornerBase = null;
  render();
  scheduleSave();
};
$("discardCorners").onclick = () => {
  ++cornerSequence;
  clearTimeout(cornerTimer);
  cornerPreview = null;
  cornerBase = null;
  render();
};
$("applyShape").onclick = async () => {
  if (!selection.size) {
    status("Select a shape to replace first.");
    return;
  }
  try {
    const result = await request("/api/edit", {
      svg: items[current].svg,
      operation: "shape",
      indices: selectedIndices(),
      shape_type: $("paramKind").value,
      center: [Number($("paramX").value), Number($("paramY").value)],
      size: [Number($("paramW").value), Number($("paramH").value)],
      rotation: Number($("paramRotate").value),
      radius: Number($("paramRadius").value),
      sides: Number($("paramSides").value),
      inner_ratio: Number($("paramInner").value),
    });
    snapshot();
    items[current].svg = result.svg;
    render();
    scheduleSave();
    status('Shape geometry applied.');
  } catch (error) {
    status(error.message, true);
  }
};
$("copyVector").onclick = async () => {
  try {
    await navigator.clipboard.writeText(items[current].svg);
    status("Editable SVG copied to the clipboard.");
  } catch (error) {
    status("Clipboard access failed. Download SVG instead.", true);
  }
};
$("dragVector").onclick = (event) => event.preventDefault();
$("dragVector").ondragstart = (event) => {
  if (!items[current]?.svg) {
    event.preventDefault();
    return;
  }
  const name = items[current].file.name.replace(/\.[^.]+$/, "") + ".svg";
  const url = URL.createObjectURL(
    new Blob([items[current].svg], { type: "image/svg+xml" }),
  );
  event.dataTransfer.setData("DownloadURL", `image/svg+xml:${name}:${url}`);
  event.dataTransfer.setData("image/svg+xml", items[current].svg);
  setTimeout(() => URL.revokeObjectURL(url), 60000);
};
render();

$("copyNative").onclick = async () => {
  try {
    const result = await request("/api/clipboard", { svg: items[current].svg });
    status("Copied: " + result.formats.join(", "));
  } catch (error) {
    status(error.message, true);
  }
};

$("selectSimilar").onclick = async () => {
  if (!selection.size) {
    status("Select a repeat template first.");
    return;
  }
  try {
    const result = await request("/api/edit", {
      svg: items[current].svg,
      operation: "similar",
      indices: [selectedIndices()[0]],
    });
    selection = new Set(result.matches.map((match) => match.index));
    markSelection();
    status(`${selection.size} matching shapes selected.`);
  } catch (error) {
    status(error.message, true);
  }
};
$("normalizeRepeats").onclick = () => editOperation("repeat");
$("checkUpdates").onclick = async () => {
  status("Checking published releases�");
  try {
    const result = await request("/api/updates", {});
    status(
      result.available
        ? `Version ${result.latest} is available. Download from the project�s Releases page.`
        : `You have ${result.current}; no newer published version was found.`,
    );
    if (result.available) {
      const link = document.createElement("a");
      link.href = result.url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "Open release downloads";
      $("status").append(" ", link);
    }
  } catch (error) {
    status(error.message, true);
  }
};
$("quitApp").onclick = async () => {
  if (busy && !confirm("Stop the current conversion and quit?")) return;
  try {
    await request("/api/shutdown", {});
    status("TraceGarden stopped. You may close this tab.");
  } catch (error) {
    status(error.message, true);
  }
};
