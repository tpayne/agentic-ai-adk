// --- Globals ---
let processModel = null;
let currentLevel = 1;
let currentParentStep = null;

let lanes = [];

function buildLanesFromProcess(processModel) {
  const laneSet = new Set();

  // Level 1
  (processModel.level1_steps || []).forEach((step) => {
    const r = normalizeResponsible(step.responsible_party);
    if (r) laneSet.add(r);
  });

  // Level 2
  Object.values(processModel.subprocess_index || {}).forEach((substeps) => {
    substeps.forEach((sub) => {
      const r = normalizeResponsible(sub.responsible_party);
      if (r) laneSet.add(r);
    });
  });

  // Convert to array
  lanes = Array.from(laneSet);

  // Fallback if JSON has no responsible_party fields
  if (lanes.length === 0) {
    lanes = ["Process"];
  }
}

let zoomScale = 1;
let panX = 0;
let panY = 0;
let isPanning = false;
let panStart = { x: 0, y: 0 };

let activeLaneVisibility = {};

// --- Utility: SVG creation ---
function createSvgElement(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

function normalizeResponsible(responsible) {
  if (!responsible) return null;
  if (Array.isArray(responsible)) return responsible[0];
  return responsible;
}

// --- Load process model ---
async function loadProcess() {
  const res = await fetch("/api/process");
  processModel = await res.json();
  buildLanesFromProcess(processModel);
  document.getElementById("process-title").textContent =
    processModel.process_name || "Process";
  renderLevel1();
  enableZoomPan();
  enableSearch();
  enableLaneFilters();
  enableDarkModeToggle();
}

// --- Clear diagram ---
function clearDiagram() {
  const viewport = document.getElementById("viewport");
  while (viewport.firstChild) viewport.removeChild(viewport.firstChild);
}

// --- Layout engine: compute node positions based on text width ---
function measureTextWidth(text, fontSize = 14, fontFamily = "system-ui") {
  const canvas =
    measureTextWidth._canvas ||
    (measureTextWidth._canvas = document.createElement("canvas"));
  const ctx = canvas.getContext("2d");
  ctx.font = `${fontSize}px ${fontFamily}`;
  return ctx.measureText(text).width;
}

function layoutSteps(steps, laneHeight, baseMarginX) {
  const nodes = [];
  const minWidth = 180;
  const maxWidth = 380;
  const hGap = 60;

  let currentX = baseMarginX;

  steps.forEach((step, idx) => {
    const label = step.step_name || step.substep_name || "Step";
    const laneName = normalizeResponsible(step.responsible_party) || "Process";
    const laneIndex = lanes.indexOf(laneName);
    const laneIdx = laneIndex >= 0 ? laneIndex : 3;

    const textWidth = measureTextWidth(label, 14);
    const width = Math.min(maxWidth, Math.max(minWidth, textWidth + 40));
    const height = 70;

    const yCenter = laneIdx * laneHeight + laneHeight / 2;
    const x = currentX;
    const y = yCenter - height / 2;

    nodes.push({
      step,
      label,
      laneName,
      laneIndex: laneIdx,
      x,
      y,
      width,
      height,
      centerX: x + width / 2,
      centerY: yCenter,
    });

    currentX += width + hGap;
  });

  return nodes;
}

// --- Draw lanes ---
function drawLanes(viewport, width, laneHeight) {
  lanes.forEach((lane, i) => {
    const y = i * laneHeight;
    const laneRect = createSvgElement("rect", {
      x: 0,
      y,
      width,
      height: laneHeight,
      fill: i % 2 === 0 ? "var(--bg-lane-even)" : "var(--bg-lane-odd)",
      stroke: "var(--border)",
    });
    viewport.appendChild(laneRect);

    const label = createSvgElement("text", {
      x: 10,
      y: y + 20,
      class: "lane-label",
    });
    label.textContent = lane;
    viewport.appendChild(label);
  });
}

// --- Draw curved arrow between nodes ---
function drawArrow(viewport, fromNode, toNode) {
  const x1 = fromNode.x + fromNode.width;
  const y1 = fromNode.centerY;
  const x2 = toNode.x;
  const y2 = toNode.centerY;

  const dx = (x2 - x1) / 2;
  const control1X = x1 + dx;
  const control1Y = y1;
  const control2X = x2 - dx;
  const control2Y = y2;

  const pathData = `M ${x1} ${y1} C ${control1X} ${control1Y}, ${control2X} ${control2Y}, ${x2} ${y2}`;

  const path = createSvgElement("path", {
    d: pathData,
    fill: "none",
    stroke: "#888",
    "stroke-width": 2,
    "marker-end": "url(#arrowhead)",
  });

  viewport.appendChild(path);
}

// --- Draw node ---
function drawNode(viewport, node, level) {
  const { x, y, width, height, label, step } = node;
  const duration = step.estimated_duration || "";
  const inputs = step.inputs || [];
  const outputs = step.deliverables || step.outputs || [];

  const group = createSvgElement("g", {
    class: "node",
    "data-label": label,
    "data-lane": node.laneName,
  });

  group.addEventListener("dblclick", () => {
    if (level === 1) renderLevel2(label);
  });

  const rect = createSvgElement("rect", {
    x,
    y,
    width,
    height,
    rx: 6,
    ry: 6,
  });
  group.appendChild(rect);

  const text = createSvgElement("text", {
    x: x + 10,
    y: y + 24,
    "font-size": "14px",
  });
  text.textContent = label;
  group.appendChild(text);

  if (duration) {
    const durText = createSvgElement("text", {
      x: x + 10,
      y: y + 44,
      class: "duration-text",
    });
    durText.textContent = `Duration: ${duration}`;
    group.appendChild(durText);
  }

  inputs.forEach((inp, idx) => {
    const t = createSvgElement("text", {
      x: x + width / 2,
      y: y - 10 - idx * 12,
      "text-anchor": "middle",
      class: "io-text-input",
    });
    t.textContent = `↑ ${inp}`;
    group.appendChild(t);
  });

  outputs.forEach((out, idx) => {
    const t = createSvgElement("text", {
      x: x + width / 2,
      y: y + height + 14 + idx * 12,
      "text-anchor": "middle",
      class: "io-text-output",
    });
    t.textContent = `${out} ↓`;
    group.appendChild(t);
  });

  // Position the icon relative to the box's top-right corner
  const infoGroup = createSvgElement("g", {
    transform: `translate(${x + width - 22}, ${y + 18})`,
    style: "pointer-events: all; cursor: pointer;",
  });

  const hitbox = createSvgElement("rect", {
    x: 0,
    y: -13,
    width: 15,
    height: 15,
    fill: "transparent",
  });

  infoGroup.appendChild(hitbox);

  // The icon itself
  const infoText = createSvgElement("text", {
    x: 0,
    y: 0,
    class: "info-icon",
  });
  infoText.textContent = "ℹ️";
  infoGroup.appendChild(infoText);

  infoGroup.addEventListener("click", (e) => {
    e.stopPropagation();
    showInfo(step, label);
  });

  group.appendChild(infoGroup);
  viewport.appendChild(group);
}
// --- Breadcrumb ---
function updateBreadcrumb(level, parentStep = null) {
  const c1 = document.getElementById("crumb-level1");
  const sep = document.getElementById("crumb-sep");
  const cStep = document.getElementById("crumb-step");

  if (level === 1) {
    sep.style.display = "none";
    cStep.style.display = "none";
  } else {
    sep.style.display = "inline";
    cStep.style.display = "inline";
    cStep.textContent = parentStep;
  }
}

document.getElementById("modal-close").onclick = closeModal;
document.getElementById("crumb-level1").onclick = () => {
  renderLevel1();
};

document.getElementById("crumb-step").onclick = () => {
  if (currentParentStep) renderLevel2(currentParentStep);
};

// --- Modal ---
function showInfo(step, title) {
  const modalTitle = document.getElementById("modal-title");
  const modalBody = document.getElementById("modal-body");

  modalTitle.textContent = title;

  // Clear modal body
  modalBody.innerHTML = "";

  // --- Create tab bar ---
  const tabBar = document.createElement("div");
  tabBar.style.display = "flex";
  tabBar.style.gap = "12px";
  tabBar.style.marginBottom = "10px";

  const tabFormatted = document.createElement("button");
  tabFormatted.textContent = "Formatted";
  tabFormatted.style.padding = "4px 8px";
  tabFormatted.style.cursor = "pointer";
  tabFormatted.style.fontSize = "13px";
  tabFormatted.style.border = "1px solid var(--border)";
  tabFormatted.style.background = "var(--bg-panel)";
  tabFormatted.style.color = "var(--text)";
  tabFormatted.dataset.active = "true";

  const tabRaw = document.createElement("button");
  tabRaw.textContent = "Raw JSON";
  tabRaw.style.padding = "4px 8px";
  tabRaw.style.cursor = "pointer";
  tabRaw.style.fontSize = "13px";
  tabRaw.style.border = "1px solid var(--border)";
  tabRaw.style.background = "var(--bg-panel)";
  tabRaw.style.color = "var(--text)";
  tabRaw.dataset.active = "false";

  tabBar.appendChild(tabFormatted);
  tabBar.appendChild(tabRaw);
  modalBody.appendChild(tabBar);

  // --- Content containers ---
  const formattedContainer = document.createElement("div");
  const rawContainer = document.createElement("div");
  rawContainer.style.display = "none";

  modalBody.appendChild(formattedContainer);
  modalBody.appendChild(rawContainer);

  // --- Recursive renderer with collapsible sections ---
  function renderValue(value) {
    // Null / undefined
    if (value === null || value === undefined) {
      return "<i>None</i>";
    }

    // Primitive
    if (typeof value !== "object") {
      return String(value);
    }

    // Array
    if (Array.isArray(value)) {
      if (value.length === 0) return "<i>Empty list</i>";

      // Array of primitives
      if (value.every(v => typeof v !== "object")) {
        return `
          <ul style="margin:0; padding-left:18px;">
            ${value.map(v => `<li>${renderValue(v)}</li>`).join("")}
          </ul>
        `;
      }

      // Array of objects → collapsible per item
      return value
        .map((obj, idx) => {
          const id = "col-" + Math.random().toString(36).slice(2);
          return `
            <div style="margin-bottom:6px;">
              <div style="cursor:pointer; user-select:none;"
                   onclick="document.getElementById('${id}').style.display =
                            document.getElementById('${id}').style.display === 'none' ? 'block' : 'none';
                            this.querySelector('.arrow').textContent =
                            document.getElementById('${id}').style.display === 'none' ? '▶' : '▼';">
                <span class="arrow">▶</span>
                <strong>Item ${idx + 1}</strong>
              </div>
              <div id="${id}" style="display:none; margin-left:14px; border-left:2px solid var(--border); padding-left:8px;">
                ${renderValue(obj)}
              </div>
            </div>
          `;
        })
        .join("");
    }

    // Object → collapsible table
    const id = "col-" + Math.random().toString(36).slice(2);

    const rows = Object.entries(value)
      .map(([k, v]) => {
        return `
          <tr>
            <td style="padding:4px; border:1px solid var(--border); vertical-align:top; width:30%;">
              <strong>${k}</strong>
            </td>
            <td style="padding:4px; border:1px solid var(--border); vertical-align:top;">
              ${renderValue(v)}
            </td>
          </tr>
        `;
      })
      .join("");

    return `
      <div style="margin-bottom:6px;">
        <div style="cursor:pointer; user-select:none;"
             onclick="document.getElementById('${id}').style.display =
                      document.getElementById('${id}').style.display === 'none' ? 'block' : 'none';
                      this.querySelector('.arrow').textContent =
                      document.getElementById('${id}').style.display === 'none' ? '▶' : '▼';">
          <span class="arrow">▶</span>
          <strong>Details</strong>
        </div>

        <div id="${id}" style="display:none; margin-left:14px; border-left:2px solid var(--border); padding-left:8px;">
          <table style="width:100%; border-collapse:collapse; font-size:12px; margin:4px 0;">
            ${rows}
          </table>
        </div>
      </div>
    `;
  }
  // --- FIELD ORDER (same as your original) ---
  const FIELD_ORDER = [
    "step_name",
    "substep_name",
    "description",
    "estimated_duration",
    "responsible_party",
    "inputs",
    "deliverables",
    "outputs",
    "dependencies",
    "success_criteria",
  ];

  // --- Build formatted table ---
  function buildFormattedTable(step) {
    let html = `
      <table style="
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        table-layout: fixed;
      ">
        <thead>
          <tr style="background: var(--border); color: var(--bg-panel);">
            <th style="padding: 6px; border: 1px solid #ccc; text-align: left;">Key</th>
            <th style="padding: 6px; border: 1px solid #ccc; text-align: left;">Value</th>
          </tr>
        </thead>
        <tbody>
    `;

    let rowIndex = 0;

    function addRow(key, valueHtml) {
      const bg = rowIndex % 2 === 0 ? "var(--bg-panel)" : "var(--bg-lane-odd)";
      html += `
        <tr style="background:${bg};">
          <td style="padding:6px; border:1px solid var(--border); vertical-align:top; word-wrap:break-word;">
            ${key}
          </td>
          <td style="padding:6px; border:1px solid var(--border); vertical-align:top; word-wrap:break-word;">
            ${valueHtml}
          </td>
        </tr>
      `;
      rowIndex++;
    }

    // Render fields in defined order
    FIELD_ORDER.forEach((key) => {
      if (key in step) {
        addRow(key, renderValue(step[key]));
      }
    });

    // Render remaining fields
    Object.entries(step).forEach(([key, value]) => {
      if (!FIELD_ORDER.includes(key)) {
        addRow(key, renderValue(value));
      }
    });

    html += `</tbody></table>`;
    return html;
  }

  // Insert formatted table into container
  formattedContainer.innerHTML = buildFormattedTable(step);
  // --- RAW JSON VIEW ---

  // Simple syntax highlighter (no external libs)
  function syntaxHighlight(json) {
    if (typeof json !== "string") {
      json = JSON.stringify(json, null, 2);
    }

    json = json
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    return json.replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      function (match) {
        let cls = "json-number";
        if (/^"/.test(match)) {
          if (/:$/.test(match)) {
            cls = "json-key";
          } else {
            cls = "json-string";
          }
        } else if (/true|false/.test(match)) {
          cls = "json-boolean";
        } else if (/null/.test(match)) {
          cls = "json-null";
        }
        return `<span class="${cls}">${match}</span>`;
      }
    );
  }

  // Inject minimal inline styles for syntax highlighting
  const style = document.createElement("style");
  style.textContent = `
    .json-key { color: #c792ea; }
    .json-string { color: #a5e844; }
    .json-number { color: #f78c6c; }
    .json-boolean { color: #82aaff; }
    .json-null { color: #ff5370; }
  `;
  document.head.appendChild(style);

  // Build raw JSON block
  const rawJson = JSON.stringify(step, null, 2);

  const copyBtn = document.createElement("button");
  copyBtn.textContent = "Copy JSON";
  copyBtn.style.marginBottom = "8px";
  copyBtn.style.padding = "4px 8px";
  copyBtn.style.cursor = "pointer";
  copyBtn.style.fontSize = "12px";
  copyBtn.style.border = "1px solid var(--border)";
  copyBtn.style.background = "var(--bg-panel)";
  copyBtn.style.color = "var(--text)";

  copyBtn.onclick = () => {
    navigator.clipboard.writeText(rawJson);
    copyBtn.textContent = "Copied!";
    setTimeout(() => (copyBtn.textContent = "Copy JSON"), 1200);
  };

  const pre = document.createElement("pre");
  pre.style.background = "var(--bg-lane-odd)";
  pre.style.padding = "10px";
  pre.style.fontSize = "12px";
  pre.style.overflowX = "auto";
  pre.innerHTML = syntaxHighlight(rawJson);

  rawContainer.appendChild(copyBtn);
  rawContainer.appendChild(pre);
  // --- TAB SWITCHING LOGIC ---

  function activateTab(which) {
    if (which === "formatted") {
      formattedContainer.style.display = "block";
      rawContainer.style.display = "none";

      tabFormatted.dataset.active = "true";
      tabRaw.dataset.active = "false";

      tabFormatted.style.background = "var(--accent)";
      tabFormatted.style.color = "#fff";

      tabRaw.style.background = "var(--bg-panel)";
      tabRaw.style.color = "var(--text)";
    } else {
      formattedContainer.style.display = "none";
      rawContainer.style.display = "block";

      tabFormatted.dataset.active = "false";
      tabRaw.dataset.active = "true";

      tabRaw.style.background = "var(--accent)";
      tabRaw.style.color = "#fff";

      tabFormatted.style.background = "var(--bg-panel)";
      tabFormatted.style.color = "var(--text)";
    }
  }

  tabFormatted.onclick = () => activateTab("formatted");
  tabRaw.onclick = () => activateTab("raw");

  // Default tab
  activateTab("formatted");

  // --- OPEN MODAL ---
  document.getElementById("modal-backdrop").style.display = "flex";
}

function closeModal() {
  document.getElementById("modal-backdrop").style.display = "none";
}
window.closeModal = closeModal;

// --- Render Level 1 ---
function renderLevel1() {
  currentLevel = 1;
  currentParentStep = null;
  clearDiagram();
  updateBreadcrumb(1);
  resetZoom();

  const svg = document.getElementById("diagram");
  const viewport = document.getElementById("viewport");
  // ⭐ Force layout so svg.clientHeight is real 
  svg.getBoundingClientRect();
  const width = svg.clientWidth || 1000;
  const height = svg.clientHeight || 600;

  const minLaneHeight = 170;
  const laneHeight = Math.max(minLaneHeight, height / lanes.length);
  drawLanes(viewport, width, laneHeight);

  const steps = processModel.level1_steps || [];
  const visibleSteps = steps.filter((step) => {
    const laneName = normalizeResponsible(step.responsible_party) || "Process";
    return activeLaneVisibility[laneName] !== false;
  });

  const nodes = layoutSteps(visibleSteps, laneHeight, 160);

  nodes.forEach((node) => drawNode(viewport, node, 1));

  for (let i = 0; i < nodes.length - 1; i++) {
    drawArrow(viewport, nodes[i], nodes[i + 1]);
  }

  updateMinimap();
}

// --- Render Level 2 ---
function renderLevel2(parentStepName) {
  currentLevel = 2;
  currentParentStep = parentStepName;
  clearDiagram();
  updateBreadcrumb(2, parentStepName);
  resetZoom();

  const svg = document.getElementById("diagram");
  const viewport = document.getElementById("viewport");
  // ⭐ Force layout so svg.clientHeight is real 
  svg.getBoundingClientRect();
  const width = svg.clientWidth || 1000;
  const height = svg.clientHeight || 600;

  const minLaneHeight = 170;
  const laneHeight = Math.max(minLaneHeight, height / lanes.length);
  drawLanes(viewport, width, laneHeight);

  const flow = processModel.subprocess_index[parentStepName] || [];
  const visibleSteps = flow.filter((step) => {
    const laneName = normalizeResponsible(step.responsible_party) || "Process";
    return activeLaneVisibility[laneName] !== false;
  });

  const nodes = layoutSteps(visibleSteps, laneHeight, 160);

  nodes.forEach((node) => drawNode(viewport, node, 2));

  for (let i = 0; i < nodes.length - 1; i++) {
    drawArrow(viewport, nodes[i], nodes[i + 1]);
  }
  // ⭐ Auto‑pan to the first Level‑2 node 
  if (nodes.length > 0) { 
    panX = 0; 
    panY = -nodes[0].y + 200; 
    updateTransform(); 
  }
  updateMinimap();
}

// --- Zoom & Pan ---
function enableZoomPan() {
  const svg = document.getElementById("diagram");

  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const scaleAmount = e.deltaY * -0.001;
    zoomScale = Math.min(Math.max(0.2, zoomScale + scaleAmount), 3);
    updateTransform();
    updateMinimap();
  });

  // Zoom In button
  document.getElementById("zoom-in-btn").addEventListener("click", () => {
    zoomScale = Math.min(zoomScale + 0.1, 3);
    updateTransform();
    updateMinimap();
  });

  // Zoom Out button
  document.getElementById("zoom-out-btn").addEventListener("click", () => {
    zoomScale = Math.max(zoomScale - 0.1, 0.2);
    updateTransform();
    updateMinimap();
  });

  svg.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    isPanning = true;
    panStart = { x: e.clientX - panX, y: e.clientY - panY };
  });

  svg.addEventListener("mousemove", (e) => {
    if (!isPanning) return;
    panX = e.clientX - panStart.x;
    panY = e.clientY - panStart.y;
    updateTransform();
    updateMinimap();
  });

  svg.addEventListener("mouseup", () => {
    isPanning = false;
  });
  svg.addEventListener("mouseleave", () => {
    isPanning = false;
  });

  document
    .getElementById("reset-zoom-btn")
    .addEventListener("click", resetZoom);
}

function updateTransform() {
  const viewport = document.getElementById("viewport");
  viewport.setAttribute(
    "transform",
    `translate(${panX},${panY}) scale(${zoomScale})`
  );
}

function resetZoom() {
  zoomScale = 1;
  panX = 0;
  panY = 0;
  updateTransform();
  updateMinimap();
}

// --- Minimap ---
function updateMinimap() {
  const minimap = document.getElementById("minimap");
  const mmContent = document.getElementById("minimap-content");
  const mmViewport = document.getElementById("minimap-viewport");

  while (mmContent.firstChild) mmContent.removeChild(mmContent.firstChild);

  const viewport = document.getElementById("viewport");
  const clone = viewport.cloneNode(true);
  clone.removeAttribute("transform");
  clone.setAttribute("transform", "scale(0.1)");
  mmContent.appendChild(clone);

  mmViewport.setAttribute("x", -panX * 0.1);
  mmViewport.setAttribute("y", -panY * 0.1);
  mmViewport.setAttribute("width", (minimap.clientWidth * 0.1) / zoomScale);
  mmViewport.setAttribute("height", (minimap.clientHeight * 0.1) / zoomScale);
}

// --- Search ---
function enableSearch() {
  const box = document.getElementById("search-box");
  box.addEventListener("input", () => {
    const query = box.value.toLowerCase();
    const rects = document.querySelectorAll(".node rect");
    rects.forEach((r) => r.classList.remove("highlight"));

    if (!query) return;

    const matches = [];
    document.querySelectorAll(".node").forEach((node) => {
      const label = (node.getAttribute("data-label") || "").toLowerCase();
      if (label.includes(query)) {
        const rect = node.querySelector("rect");
        rect.classList.add("highlight");
        matches.push(node);
      }
    });

    if (matches.length > 0) {
      const rect = matches[0].querySelector("rect");
      const x = parseFloat(rect.getAttribute("x"));
      const y = parseFloat(rect.getAttribute("y"));
      panX = -x + 200;
      panY = -y + 200;
      updateTransform();
      updateMinimap();
    }
  });
}

// --- Lane filters ---
function enableLaneFilters() {
  const container = document.getElementById("lane-filters");
  container.innerHTML = "<strong>Show lanes:</strong>";

  lanes.forEach((lane) => {
    const id = "lane-" + lane.replace(/\s+/g, "-");
    const label = document.createElement("label");
    label.innerHTML = `
                    <input type="checkbox" id="${id}" data-lane="${lane}" checked>
                    ${lane}
                `;
    container.appendChild(label);
  });

  container.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.addEventListener("change", () => {
      const lane = cb.getAttribute("data-lane");
      activeLaneVisibility[lane] = cb.checked;
      if (currentLevel === 1) renderLevel1();
      else if (currentLevel === 2 && currentParentStep)
        renderLevel2(currentParentStep);
    });
  });
}

// --- Dark mode ---
function enableDarkModeToggle() {
  const btn = document.getElementById("dark-toggle-btn");
  btn.addEventListener("click", () => {
    const root = document.documentElement;
    const isDark = root.classList.toggle("dark");
    btn.textContent = isDark ? "Light mode" : "Dark mode";
  });
}

// --- Init ---
window.addEventListener("load", loadProcess);
