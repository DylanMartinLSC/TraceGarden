"use strict";
const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
let items = [],
  current = 0,
  busy = false,
  selection = new Set(),
  view = "compare";
let cancelled = false,
  activeJob = null,
  penPoints = [],
  nodePoints = [],
  nodeIndex = null,
  nodeMode = "nodes";
let autosaveTimer = null,
  saveGeneration = 0,
  importSequence = 0,
  brushPattern = null,
  brushActive = false,
  painting = false;

function status(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
}
async function request(url, body, method = "POST") {
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok)
    throw Error(
      typeof data.detail === "string"
        ? data.detail
        : "This request could not be completed.",
    );
  return data;
}
function config() {
  const result = {};
  for (const id of [
    "preset",
    "colors",
    "speckle",
    "corner",
    "precision",
    "threshold",
    "max_size",
    "smooth",
    "remove_white",
    "layering",
    "layer_difference",
    "geometry",
    "gradients",
    "rotation",
    "flip",
    "contrast",
  ]) {
    const el = $(id);
    result[id] =
      el.type === "checkbox"
        ? el.checked
        : ["preset", "layering"].includes(id)
          ? el.value
          : Number(el.value);
  }
  result.palette = $("customPalette")
    .value.split(",")
    .map((v) => v.trim())
    .filter(Boolean);
  result.crop = $("cropEnabled").checked
    ? ["cropX", "cropY", "cropW", "cropH"].map((id) => Number($(id).value))
    : null;
  return result;
}
function applyConfig(o) {
  for (const [key, value] of Object.entries(o || {}))
    if ($(key) && !["palette", "crop"].includes(key)) {
      if ($(key).type === "checkbox") $(key).checked = value;
      else $(key).value = value;
    }
  $("customPalette").value = (o?.palette || []).join(", ");
  $("cropEnabled").checked = !!o?.crop;
  if (o?.crop)
    ["cropX", "cropY", "cropW", "cropH"].forEach(
      (id, i) => ($(id).value = o.crop[i]),
    );
  $("colorsValue").textContent = $("colors").value;
}
function exportConfig() {
  return {
    dpi: Number($("dpi").value),
    width_mm: $("width_mm").value ? Number($("width_mm").value) : null,
    color_space: $("color_space").value,
    dxf_mode: $("dxf_mode").value,
    outline: $("outlineExport").checked,
  };
}
function paths() {
  return [
    ...($("vector").querySelector("svg")?.querySelectorAll("path") || []),
  ];
}
function svgElement() {
  return $("vector").querySelector("svg");
}
function selectedIndices() {
  return [...selection].sort((a, b) => a - b);
}
function queue() {
  $("queue").replaceChildren();
  items.forEach((item, i) => {
    const li = document.createElement("li"),
      button = document.createElement("button");
    button.textContent = `${item.result ? "✓ " : ""}${item.file.name}`;
    button.classList.toggle("active", i === current);
    button.disabled = busy;
    button.onclick = () => {
      current = i;
      render();
    };
    li.append(button);
    $("queue").append(li);
  });
  $("convert").disabled = busy || !items.length;
  for (const id of ["files", "demo", "openProject", "recoverProject", "clear"])
    $(id).disabled = busy;
  for (const id of ["brushToggle", "brushUndo"]) $(id).disabled = busy;
  $("editBackground").disabled =
    busy || !items[current]?.result?.background_preview;
  $("cancel").hidden = !busy;
  $("editor").classList.toggle("busy", busy);
}
function add(files) {
  if (busy) return;
  ++importSequence;
  let warning = "";
  for (const file of files) {
    if (items.length >= 20) {
      warning = "A batch can contain up to 20 images.";
      break;
    }
    if (file.size > 100 * 1024 * 1024) {
      warning = `${file.name} is larger than 100 MB.`;
      continue;
    }
    items.push({
      file,
      url: URL.createObjectURL(file),
      history: [],
      future: [],
      brushHistory: [],
    });
  }
  current = Math.max(0, items.length - 1);
  render();
  scheduleSave();
  if (warning) status(warning, true);
}
function setView() {
  document
    .querySelectorAll("[data-view]")
    .forEach((button) =>
      button.setAttribute("aria-pressed", button.dataset.view === view),
    );
  $("originalPane").hidden = view === "vector";
  $("vectorPane").hidden = view === "original";
}
function closeNodes() {
  nodePoints = [];
  nodeIndex = null;
  $("nodePanel").hidden = true;
  svgElement()
    ?.querySelectorAll(".node-handle")
    .forEach((n) => n.remove());
}
function render() {
  selection.clear();
  penPoints = [];
  closeNodes();
  queue();
  setView();
  const item = items[current];
  $("original").hidden = !item;
  $("editor").hidden = !item?.result;
  $("stats").textContent = "";
  $("repair").hidden = !item;
  brushActive = false;
  $("repairCanvas").hidden = true;
  $("brushToggle").textContent = "Enable brush";
  if (!item) {
    $("original").removeAttribute("src");
    $("vector").replaceChildren();
    return;
  }
  $("original").src = item.result?.preview || item.url;
  if (!item.result) {
    $("vector").textContent = "Ready to trace";
    status("Choose a style, then select Vectorize images.");
    return;
  }
  const parsed = new DOMParser().parseFromString(item.svg, "image/svg+xml");
  $("vector").replaceChildren(
    document.importNode(parsed.documentElement, true),
  );
  $("stats").textContent =
    `${item.result.width} × ${item.result.height} · ${paths().length} paths · ${item.result.seconds}s on CPU · ${item.result.geometry || 0} reconstructed shapes · ${item.result.gradients || 0} gradients`;
  palette();
  zoom();
  status("Your vector is ready. Edit the colors or download a file.");
}
function snapshot() {
  const item = items[current];
  item.history.push(item.svg);
  item.future = [];
  if (item.history.length > 30) item.history.shift();
}
function cleanSVG() {
  const clone = svgElement().cloneNode(true);
  clone.removeAttribute("style");
  clone
    .querySelectorAll(".node-handle,.pen-preview")
    .forEach((n) => n.remove());
  clone.querySelectorAll("[class]").forEach((n) => n.removeAttribute("class"));
  return new XMLSerializer().serializeToString(clone);
}
function persist() {
  items[current].svg = cleanSVG();
  scheduleSave();
}
function markSelection() {
  paths().forEach((path, i) =>
    path.classList.toggle("selected", selection.has(i)),
  );
  if (selection.size) {
    const path = paths()[selectedIndices()[0]],
      fill = path.getAttribute("fill");
    if (/^#[a-f0-9]{6}$/i.test(fill)) $("shapeColor").value = fill;
    $("shapeOpacity").value = path.getAttribute("opacity") || "1";
  }
}
function palette() {
  const fills = [...new Set(paths().map((path) => path.getAttribute("fill")))];
  $("palette").replaceChildren();
  for (const fill of fills) {
    if (!/^#[0-9a-f]{6}$/i.test(fill)) continue;
    const label = document.createElement("label"),
      input = document.createElement("input"),
      text = document.createElement("span");
    input.type = "color";
    input.value = fill;
    input.setAttribute("aria-label", `Replace color ${fill}`);
    text.textContent = fill;
    label.append(input, text);
    $("palette").append(label);
    input.onchange = () => {
      snapshot();
      paths()
        .filter((path) => path.getAttribute("fill") === fill)
        .forEach((path) => path.setAttribute("fill", input.value));
      persist();
      palette();
    };
  }
}
function zoom() {
  for (const el of [$("original"), svgElement()])
    if (el) {
      el.style.width = `${Number($("zoom").value) * 100}%`;
      el.parentElement.classList.toggle("zoomed", $("zoom").value !== "1");
    }
}
async function convert() {
  if (busy) return;
  if (
    items.some((item) => item.history.length) &&
    !window.confirm("Tracing again replaces existing vector edits. Continue?")
  )
    return;
  busy = true;
  cancelled = false;
  queue();
  $("progress").hidden = false;
  $("progress").max = items.length;
  let successes = 0;
  const options = config();
  for (let i = 0; i < items.length && !cancelled; i++) {
    const item = items[i];
    status(`Tracing ${i + 1} of ${items.length}: ${item.file.name}`);
    $("progress").value = i;
    try {
      item.error = null;
      const form = new FormData();
      form.append("file", item.file);
      form.append("options", JSON.stringify(options));
      const response = await fetch("/api/jobs", { method: "POST", body: form }),
        job = await response.json();
      if (!response.ok)
        throw Error(
          typeof job.detail === "string"
            ? job.detail
            : "Unable to queue this image.",
        );
      activeJob = job.id;
      while (!cancelled) {
        const state = await request(`/api/jobs/${activeJob}`, undefined, "GET");
        if (state.state === "complete") {
          item.result = state.result;
          item.svg = state.result.svg;
          item.history = [];
          item.future = [];
          item.options = options;
          successes++;
          break;
        }
        if (["failed", "cancelled"].includes(state.state))
          throw Error(state.error || "Conversion cancelled.");
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
    } catch (error) {
      if (!cancelled) item.error = error.message;
    } finally {
      if (activeJob) {
        await request(`/api/jobs/${activeJob}`, undefined, "DELETE").catch(
          () => {},
        );
        activeJob = null;
      }
    }
  }
  busy = false;
  $("progress").value = successes;
  current = Math.max(
    0,
    items.findIndex((item) => item.result),
  );
  render();
  scheduleSave();
  const errors = items
    .filter((item) => item.error)
    .map((item) => `${item.file.name}: ${item.error}`)
    .join(" ");
  status(
    cancelled
      ? "Batch cancelled. Completed results are available."
      : `${successes} of ${items.length} images converted. ${errors}`,
    !!errors,
  );
}
async function editOperation(operation) {
  if (!selection.size) {
    status("Select one or more shapes first.");
    return;
  }
  try {
    const item = items[current],
      original = item.svg;
    const result = await request("/api/edit", {
      svg: original,
      operation,
      indices: selectedIndices(),
      tolerance: 1,
    });
    if (items[current] !== item || item.svg !== original) return;
    snapshot();
    items[current].svg = result.svg;
    render();
    scheduleSave();
  } catch (error) {
    status(error.message, true);
  }
}
function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
async function save(item) {
  const format = $("format").value;
  const response = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ svg: item.svg, format, options: exportConfig() }),
  });
  if (!response.ok) {
    const data = await response.json();
    throw Error(data.detail || "Export failed.");
  }
  downloadBlob(
    await response.blob(),
    item.file.name.replace(/\.[^.]+$/, "") + "." + format,
  );
}
async function saveAll() {
  try {
    const ready = items.filter((item) => item.result);
    status("Preparing your ZIP download…");
    const response = await fetch("/api/export-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        items: ready.map((item) => ({
          svg: item.svg,
          format: $("format").value,
          options: exportConfig(),
        })),
        names: ready.map((item) => item.file.name.replace(/\.[^.]+$/, "")),
      }),
    });
    if (!response.ok)
      throw Error("Batch export failed. Try an individual download.");
    downloadBlob(await response.blob(), "tracegarden-vectors.zip");
    status("ZIP download ready.");
  } catch (error) {
    status(error.message, true);
  }
}
function point(event) {
  const p = svgElement().createSVGPoint();
  p.x = event.clientX;
  p.y = event.clientY;
  const v = p.matrixTransform(svgElement().getScreenCTM().inverse());
  return [Math.round(v.x * 100) / 100, Math.round(v.y * 100) / 100];
}
function drawPen() {
  svgElement()
    ?.querySelectorAll(".pen-preview")
    .forEach((n) => n.remove());
  if (!penPoints.length) return;
  const el = document.createElementNS(NS, "path");
  el.setAttribute("class", "pen-preview");
  el.setAttribute("d", "M" + penPoints.map((p) => p.join(" ")).join(" L"));
  svgElement().append(el);
}
function finishPen() {
  if (penPoints.length < 2) {
    status("Click at least two points on the vector preview.");
    return;
  }
  snapshot();
  const path = document.createElementNS(NS, "path"),
    closed = $("tool").value === "pen";
  path.setAttribute(
    "d",
    "M" + penPoints.map((p) => p.join(" ")).join(" L") + (closed ? " Z" : ""),
  );
  path.setAttribute("fill", closed ? $("penColor").value : "none");
  if (!closed) {
    path.setAttribute("stroke", $("penColor").value);
    path.setAttribute("stroke-width", "1");
  }
  penPoints = [];
  drawPen();
  svgElement().append(path);
  persist();
  $("tool").value = "select";
  render();
}
function nodeText() {
  $("nodes").value = nodePoints
    .map((p) => p.map((v) => v.toFixed(2)).join(", "))
    .join("\n");
}
function drawHandles() {
  svgElement()
    .querySelectorAll(".node-handle")
    .forEach((n) => n.remove());
  const radius = Number(svgElement().getAttribute("width")) / 120;
  nodePoints.forEach(([x, y], i) => {
    const handle = document.createElementNS(NS, "circle");
    handle.setAttribute("class", "node-handle");
    handle.setAttribute("cx", x);
    handle.setAttribute("cy", y);
    handle.setAttribute("r", radius);
    handle.addEventListener("pointerdown", (event) => {
      event.stopPropagation();
      handle.setPointerCapture(event.pointerId);
      handle.onpointermove = (move) => {
        const wasClosed =
          nodePoints[0][0] === nodePoints.at(-1)[0] &&
          nodePoints[0][1] === nodePoints.at(-1)[1];
        nodePoints[i] = point(move);
        if (nodeMode === "curves") {
          if (i % 4 === 0 && i > 0) nodePoints[i - 1] = [...nodePoints[i]];
          if (i % 4 === 3 && i + 1 < nodePoints.length)
            nodePoints[i + 1] = [...nodePoints[i]];
          if (wasClosed && i === 0)
            nodePoints[nodePoints.length - 1] = [...nodePoints[i]];
          if (wasClosed && i === nodePoints.length - 1)
            nodePoints[0] = [...nodePoints[i]];
        }
        svgElement()
          .querySelectorAll(".node-handle")
          .forEach((node, index) => {
            node.setAttribute("cx", nodePoints[index][0]);
            node.setAttribute("cy", nodePoints[index][1]);
          });
        nodeText();
      };
      handle.onpointerup = () => {
        handle.onpointermove = null;
      };
    });
    svgElement().append(handle);
  });
}
async function editNodes(mode = "nodes") {
  if (selection.size !== 1) {
    status("Select one shape to edit its nodes.");
    return;
  }
  try {
    const item = items[current],
      original = item.svg;
    const index = selectedIndices()[0];
    const result = await request("/api/edit", {
      svg: items[current].svg,
      operation: mode,
      indices: [index],
      tolerance: 1,
    });
    if (items[current] !== item || item.svg !== original) return;
    if (mode === "nodes" && result.subpaths.length !== 1)
      throw Error("Split this compound shape before editing nodes.");
    nodeMode = mode;
    nodePoints = mode === "curves" ? result.points : result.subpaths[0];
    nodeIndex = index;
    nodeText();
    $("nodePanel").hidden = false;
    drawHandles();
  } catch (error) {
    status(error.message, true);
  }
}
async function applyNodes() {
  try {
    const item = items[current],
      original = item.svg;
    const points = $("nodes")
      .value.trim()
      .split("\n")
      .map((line) => line.split(",").map(Number));
    const result = await request("/api/edit", {
      svg: items[current].svg,
      operation: nodeMode === "curves" ? "set-curves" : "set-nodes",
      indices: [nodeIndex],
      points,
    });
    if (items[current] !== item || item.svg !== original) return;
    snapshot();
    items[current].svg = result.svg;
    render();
    scheduleSave();
  } catch (error) {
    status(error.message, true);
  }
}
// A single local IndexedDB record. Source bytes and SVG are never sent elsewhere.
function database() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open("TraceGarden", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("projects");
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
async function storeProject(value, generation = saveGeneration) {
  const db = await database();
  if (generation !== saveGeneration) {
    db.close();
    return;
  }
  return new Promise((resolve, reject) => {
    const tx = db.transaction("projects", "readwrite");
    tx.objectStore("projects").put(value, "autosave");
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}
function dataURL(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(blob);
  });
}
async function project() {
  return {
    type: "TraceGarden",
    version: 1,
    options: config(),
    items: await Promise.all(
      items.map(async (item) => ({
        name: item.file.name,
        source: await dataURL(item.file),
        svg: item.svg || null,
        initialSVG: item.result?.svg || null,
        result: item.result ? { ...item.result, svg: undefined } : null,
        options: item.options || null,
        brushOriginal: item.brushOriginal || null,
      })),
    ),
  };
}
function scheduleSave() {
  clearTimeout(autosaveTimer);
  const generation = ++saveGeneration;
  autosaveTimer = setTimeout(async () => {
    try {
      if (items.length) await storeProject(await project(), generation);
    } catch {
      status(
        "Browser autosave is unavailable or full. Save a project file to keep your work.",
        true,
      );
    }
  }, 700);
}
async function restore(doc) {
  if (busy)
    throw Error("Finish the current operation before opening a project.");
  if (
    doc?.type !== "TraceGarden" ||
    doc.version !== 1 ||
    !Array.isArray(doc.items) ||
    doc.items.length > 20
  )
    throw Error("This is not a supported TraceGarden project.");
  busy = true;
  queue();
  const loaded = [];
  try {
    for (const item of doc.items) {
      if (
        typeof item.name !== "string" ||
        typeof item.source !== "string" ||
        !/^data:image\/(png|jpeg|webp|gif|bmp|tiff);base64,[A-Za-z0-9+/=]+$/.test(
          item.source,
        ) ||
        item.source.length > 134 * 1024 * 1024
      )
        throw Error("Invalid image in project.");
      const binary = atob(item.source.split(",")[1]);
      const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
      const blob = new Blob([bytes], {
        type: item.source.slice(5, item.source.indexOf(";")),
      });
      let svg = null;
      if (item.svg) {
        const safe = await request("/api/validate-svg", { svg: item.svg });
        svg = safe.svg;
      }
      let initialSVG = svg;
      if (item.initialSVG)
        initialSVG = (
          await request("/api/validate-svg", { svg: item.initialSVG })
        ).svg;
      if (
        svg &&
        (!item.result ||
          !Number.isFinite(item.result.width) ||
          !Number.isFinite(item.result.height))
      )
        throw Error("Missing vector metadata.");
      if (
        item.result?.preview &&
        !/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(item.result.preview)
      )
        throw Error("Invalid preview in project.");
      if (
        item.brushOriginal &&
        !/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(item.brushOriginal)
      )
        throw Error("Invalid brush source in project.");
      const file = new File([blob], item.name, { type: blob.type });
      loaded.push({
        file,
        url: URL.createObjectURL(file),
        svg,
        result: svg ? { ...item.result, svg: initialSVG } : null,
        history: [],
        future: [],
        brushHistory: [],
        options: item.options,
        brushOriginal: item.brushOriginal || null,
      });
    }
  } catch (error) {
    loaded.forEach((item) => URL.revokeObjectURL(item.url));
    busy = false;
    queue();
    throw error;
  }
  busy = false;
  items.forEach((item) => URL.revokeObjectURL(item.url));
  items = loaded;
  current = 0;
  applyConfig(doc.options);
  render();
  scheduleSave();
  status("Project restored.");
}
async function recover() {
  const sequence = ++importSequence;
  try {
    const db = await database();
    const value = await new Promise((resolve, reject) => {
      const r = db
        .transaction("projects")
        .objectStore("projects")
        .get("autosave");
      r.onsuccess = () => resolve(r.result);
      r.onerror = reject;
    });
    db.close();
    if (sequence !== importSequence) return;
    if (!value) throw Error("No autosave was found in this browser.");
    await restore(value);
  } catch (error) {
    status(error.message, true);
  }
}
async function setupBrush() {
  if (!items.length) return;
  brushActive = !brushActive;
  $("repairCanvas").hidden = !brushActive;
  $("brushToggle").textContent = brushActive ? "Disable brush" : "Enable brush";
  if (!brushActive) return;
  const image = new Image();
  const item = items[current];
  image.src = item.url;
  await image.decode();
  if (items[current] !== item) return;
  const canvas = $("repairCanvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  canvas.getContext("2d").drawImage(image, 0, 0);
  const original = new Image();
  original.src = item.brushOriginal || item.url;
  await original.decode();
  if (items[current] !== item) return;
  brushPattern = canvas.getContext("2d").createPattern(original, "no-repeat");
}
function brushPoint(event) {
  const rect = $("repairCanvas").getBoundingClientRect();
  return [
    ((event.clientX - rect.left) * $("repairCanvas").width) / rect.width,
    ((event.clientY - rect.top) * $("repairCanvas").height) / rect.height,
  ];
}
async function commitBrush() {
  const item = items[current];
  const blob = await new Promise((resolve) =>
    $("repairCanvas").toBlob(resolve),
  );
  URL.revokeObjectURL(item.url);
  item.file = new File(
    [blob],
    item.file.name.replace(/\.[^.]+$/, "") + ".png",
    { type: "image/png" },
  );
  item.url = URL.createObjectURL(item.file);
  item.result = null;
  item.svg = null;
  item.history = [];
  item.future = [];
  $("original").src = item.url;
  $("editor").hidden = true;
  $("vector").textContent =
    "Source corrected. Vectorize again to update the result.";
  queue();
  scheduleSave();
}

$("files").onchange = (e) => {
  add(e.target.files);
  e.target.value = "";
};
$("drop").onkeydown = (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    $("files").click();
  }
};
for (const event of ["dragover", "dragleave", "drop"])
  $("drop").addEventListener(event, (e) => {
    e.preventDefault();
    $("drop").classList.toggle("drag", event === "dragover");
    if (event === "drop") add(e.dataTransfer.files);
  });
document.addEventListener("paste", (e) => {
  const files = [...e.clipboardData.items]
    .filter((i) => i.type.startsWith("image/"))
    .map((i) => i.getAsFile());
  if (files.length) add(files);
});
$("zoom").onchange = zoom;
$("colors").oninput = () => ($("colorsValue").textContent = $("colors").value);
$("preset").onchange = () => {
  const preset = $("preset").value;
  $("colors").value =
    preset === "illustration"
      ? 32
      : ["ink", "centerline"].includes(preset)
        ? 2
        : 16;
  $("colors").oninput();
  $("speckle").value = preset === "pixel" ? 0 : 4;
  $("precision").value = preset === "photo" ? 7 : 4;
};
document.querySelectorAll("[data-view]").forEach(
  (button) =>
    (button.onclick = () => {
      view = button.dataset.view;
      setView();
    }),
);
$("convert").onclick = convert;
$("cancel").onclick = () => {
  cancelled = true;
  if (activeJob)
    request(`/api/jobs/${activeJob}`, undefined, "DELETE").catch(() => {});
};
$("vector").onclick = (event) => {
  if (!svgElement() || busy || event.target.classList.contains("node-handle"))
    return;
  if ($("tool").value !== "select") {
    penPoints.push(point(event));
    drawPen();
    return;
  }
  if (event.target.localName !== "path") return;
  closeNodes();
  const index = paths().indexOf(event.target);
  if (index < 0) return;
  if (!event.shiftKey) selection.clear();
  if (selection.has(index)) selection.delete(index);
  else selection.add(index);
  markSelection();
  status(`${selection.size} shape(s) selected.`);
};
$("delete").onclick = () => {
  if (!selection.size) {
    status("Click a vector shape first.");
    return;
  }
  snapshot();
  const list = paths();
  selectedIndices()
    .reverse()
    .forEach((i) => list[i].remove());
  persist();
  render();
};
$("undo").onclick = () => {
  const item = items[current];
  if (item?.history.length) {
    item.future.push(item.svg);
    item.svg = item.history.pop();
    render();
    scheduleSave();
  }
};
$("redo").onclick = () => {
  const item = items[current];
  if (item?.future.length) {
    item.history.push(item.svg);
    item.svg = item.future.pop();
    render();
    scheduleSave();
  }
};
$("reset").onclick = () => {
  snapshot();
  items[current].svg =
    items[current].result.svg ||
    items[current].initialSVG ||
    items[current].svg;
  render();
  scheduleSave();
};
for (const id of ["shapeColor", "shapeOpacity"])
  $(id).onchange = () => {
    if (!selection.size) return;
    snapshot();
    const list = paths();
    selection.forEach((i) =>
      list[i].setAttribute(
        id === "shapeColor" ? "fill" : "opacity",
        $(id).value,
      ),
    );
    persist();
    palette();
  };
document
  .querySelectorAll("[data-op]")
  .forEach(
    (button) => (button.onclick = () => editOperation(button.dataset.op)),
  );
for (const id of ["front", "back"])
  $(id).onclick = () => {
    if (!selection.size) return;
    snapshot();
    const list = paths();
    selectedIndices().forEach((i) =>
      id === "front"
        ? svgElement().append(list[i])
        : svgElement().insertBefore(list[i], paths()[0]),
    );
    persist();
    render();
  };
$("editNodes").onclick = () => editNodes();
$("editCurves").onclick = () => editNodes("curves");
$("applyNodes").onclick = applyNodes;
$("cancelNodes").onclick = closeNodes;
$("finishPen").onclick = finishPen;
$("cancelPen").onclick = () => {
  penPoints = [];
  drawPen();
};
$("save").onclick = async () => {
  try {
    await save(items[current]);
    status("Download ready. Check your browser downloads.");
  } catch (error) {
    status(error.message, true);
  }
};
$("saveAll").onclick = saveAll;
$("saveProject").onclick = async () => {
  try {
    downloadBlob(
      new Blob([JSON.stringify(await project())], { type: "application/json" }),
      "artwork.tracegarden",
    );
    status("Project file saved.");
  } catch (error) {
    status(error.message, true);
  }
};
$("openProject").onclick = () => $("projectFile").click();
$("projectFile").onchange = async (event) => {
  const sequence = ++importSequence;
  try {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 512 * 1024 * 1024)
      throw Error(
        "Project exceeds 512 MB. Save large batches as separate projects.",
      );
    const doc = JSON.parse(await file.text());
    if (sequence !== importSequence) return;
    await restore(doc);
  } catch (error) {
    status(error.message, true);
  } finally {
    event.target.value = "";
  }
};
$("recoverProject").onclick = recover;
$("clear").onclick = async () => {
  if (busy) return;
  busy = true;
  status("Clearing session…");
  clearTimeout(autosaveTimer);
  ++saveGeneration;
  ++importSequence;
  items.forEach((item) => URL.revokeObjectURL(item.url));
  items = [];
  current = 0;
  render();
  $("progress").hidden = true;
  await storeProject(null).catch(() => {});
  busy = false;
  queue();
  status("Session and autosave cleared.");
};
$("brushToggle").onclick = () =>
  setupBrush().catch((error) => status(error.message, true));
$("editBackground").onclick = async () => {
  const item = items[current],
    result = item?.result;
  if (!result?.background_preview) {
    status("Choose automatic background removal and vectorize first.");
    return;
  }
  try {
    const image = new Image();
    image.src = result.background_preview;
    await image.decode();
    if (items[current] !== item) return;
    item.brushOriginal = result.preview;
    const canvas = $("repairCanvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    canvas.getContext("2d").drawImage(image, 0, 0);
    $("background").value = "keep";
    $("cropEnabled").checked = false;
    $("rotation").value = "0";
    $("flip").checked = false;
    $("symmetry").value = "none";
    await commitBrush();
    brushActive = false;
    await setupBrush();
    $("brushMode").value = "restore";
    status(
      "Brush over pixels to keep them, or choose Remove. Vectorize again when finished.",
    );
  } catch (error) {
    status(error.message, true);
  }
};
$("repairCanvas").onpointerdown = (event) => {
  if (!brushActive || busy) return;
  painting = true;
  const canvas = $("repairCanvas"),
    item = items[current];
  item.brushHistory.push(canvas.toDataURL());
  if (item.brushHistory.length > 10) item.brushHistory.shift();
  canvas.setPointerCapture(event.pointerId);
  const context = canvas.getContext("2d"),
    [x, y] = brushPoint(event);
  const mode = $("brushMode").value;
  context.globalCompositeOperation =
    mode === "remove" ? "destination-out" : "source-over";
  context.strokeStyle =
    mode === "restore" && brushPattern ? brushPattern : $("brushColor").value;
  context.lineWidth = Number($("brushSize").value);
  context.lineCap = "round";
  context.lineJoin = "round";
  context.beginPath();
  context.moveTo(x, y);
  context.lineTo(x + 0.01, y + 0.01);
  context.stroke();
};
$("repairCanvas").onpointermove = (event) => {
  if (!painting) return;
  const [x, y] = brushPoint(event),
    context = $("repairCanvas").getContext("2d");
  context.lineTo(x, y);
  context.stroke();
};
$("repairCanvas").onpointerup = async () => {
  if (painting) {
    painting = false;
    await commitBrush();
  }
};
$("repairCanvas").onpointercancel = $("repairCanvas").onpointerup;
$("brushUndo").onclick = async () => {
  const value = items[current]?.brushHistory.pop();
  if (!value) return;
  const image = new Image();
  image.src = value;
  await image.decode();
  $("repairCanvas")
    .getContext("2d")
    .clearRect(0, 0, $("repairCanvas").width, $("repairCanvas").height);
  $("repairCanvas").getContext("2d").globalCompositeOperation = "source-over";
  $("repairCanvas").getContext("2d").drawImage(image, 0, 0);
  await commitBrush();
};
$("demo").onclick = () => {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 512;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#f4dfaa";
  ctx.fillRect(0, 0, 512, 512);
  ctx.fillStyle = "#315d45";
  ctx.beginPath();
  ctx.arc(256, 242, 155, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#f4dfaa";
  ctx.beginPath();
  ctx.ellipse(232, 220, 48, 100, -0.7, 0, Math.PI * 2);
  ctx.ellipse(295, 206, 40, 78, 0.7, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#f4dfaa";
  ctx.lineWidth = 13;
  ctx.beginPath();
  ctx.moveTo(260, 190);
  ctx.lineTo(260, 350);
  ctx.stroke();
  canvas.toBlob((blob) =>
    add([new File([blob], "garden-mark.png", { type: "image/png" })]),
  );
};
document.addEventListener("keydown", (event) => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) || busy)
    return;
  if ((event.ctrlKey || event.metaKey) && event.key === "z") {
    event.preventDefault();
    $(event.shiftKey ? "redo" : "undo").click();
  }
  if (event.key === "Delete") $("delete").click();
  if (event.key === "Escape") {
    penPoints = [];
    drawPen();
    closeNodes();
    selection.clear();
    markSelection();
  }
});
render();
