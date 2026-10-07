// Process Architect web client
//
// A static, backend-agnostic chat UI for the ADK and neuro-san
// ProcessEngineering samples' REST API:
//   GET    /status                 -> { status: "live" }
//   POST   /chat                   { query, session_id? } -> { status, session_id, query, response }
//   DELETE /chat/<session_id>      -> { status, session_id, cleared }
// Both backends expose an identical contract (see each project's own
// cli.py / process_agents/common/agent.py), so this single page works
// against either one -- just point "Base URL" at whichever is running.
//
// No framework, no build step, no external CDN dependency -- everything
// needed to render (including markdown-lite formatting) lives in this
// file, so the page keeps working even with no internet access beyond
// the REST calls themselves.

(() => {
  "use strict";

  const STORAGE_KEY = "processArchitect.webClient.v1";
  const RETRYABLE_STATUS = new Set([429, 502, 503, 504]);
  const MAX_RETRIES = 2;
  const RETRY_BASE_DELAY_MS = 600;

  // Both backends default to HTTPS on :443 / HTTP on :8080 when run with
  // just "-d" (ADK: `agent.py -d`) or "-d --flask" (neuro-san: `cli.py -d
  // --flask`) -- distinct, non-colliding ports here so both can run (and
  // be compared) side by side locally without one needing `-p` to move
  // off the other's port. --http avoids a self-signed-cert browser
  // warning for the common "just try it locally" path; swap to https://
  // and the real port if the backend is running with a real cert.
  const PRESETS = {
    adk: { baseUrl: "http://127.0.0.1:8080", label: "ADK" },
    ns: { baseUrl: "http://127.0.0.1:8081", label: "Neuro-SAN" },
  };

  // ---------------------------------------------------------------
  // Element lookups
  // ---------------------------------------------------------------
  const el = {
    app: document.getElementById("app"),
    sidebar: document.getElementById("sidebar"),
    sidebarScrim: document.getElementById("sidebarScrim"),
    sidebarOpenBtn: document.getElementById("sidebarOpenBtn"),
    sidebarCloseBtn: document.getElementById("sidebarCloseBtn"),

    presetBtns: Array.from(document.querySelectorAll(".preset-btn")),
    baseUrlInput: document.getElementById("baseUrlInput"),
    apiKeyInput: document.getElementById("apiKeyInput"),
    toggleKeyVisibility: document.getElementById("toggleKeyVisibility"),
    connectBtn: document.getElementById("connectBtn"),
    connectionStatus: document.getElementById("connectionStatus"),
    topbarStatus: document.getElementById("topbarStatus"),

    sessionIdLabel: document.getElementById("sessionIdLabel"),
    newChatBtn: document.getElementById("newChatBtn"),

    themeToggleBtn: document.getElementById("themeToggleBtn"),
    themeToggleIcon: document.getElementById("themeToggleIcon"),
    themeToggleLabel: document.getElementById("themeToggleLabel"),

    chatScroll: document.getElementById("chatScroll"),
    chatContainer: document.getElementById("chatContainer"),
    emptyState: document.getElementById("emptyState"),

    composerForm: document.getElementById("composerForm"),
    messageInput: document.getElementById("messageInput"),
    sendBtn: document.getElementById("sendBtn"),
    toolbarBtns: Array.from(document.querySelectorAll(".toolbar-btn[data-command]")),
    saveChatBtn: document.getElementById("saveChatBtn"),

    tabBtns: Array.from(document.querySelectorAll(".tab-btn")),
    chatTabPanel: document.getElementById("chatTabPanel"),
    networkTabPanel: document.getElementById("networkTabPanel"),
    networkTabBadge: document.getElementById("networkTabBadge"),
    networkCount: document.getElementById("networkCount"),
    networkCanvasWrap: document.getElementById("networkCanvasWrap"),
    networkEmpty: document.getElementById("networkEmpty"),
    networkSvg: document.getElementById("networkSvg"),
    networkZoomInBtn: document.getElementById("networkZoomInBtn"),
    networkZoomOutBtn: document.getElementById("networkZoomOutBtn"),
    networkResetViewBtn: document.getElementById("networkResetViewBtn"),

    nodeDetail: document.getElementById("nodeDetail"),
    nodeDetailTitle: document.getElementById("nodeDetailTitle"),
    nodeDetailPath: document.getElementById("nodeDetailPath"),
    nodeDetailContext: document.getElementById("nodeDetailContext"),
    nodeDetailStats: document.getElementById("nodeDetailStats"),
    nodeDetailList: document.getElementById("nodeDetailList"),
    nodeDetailCloseBtn: document.getElementById("nodeDetailCloseBtn"),

    toast: null,
  };

  // ---------------------------------------------------------------
  // Persisted state
  // ---------------------------------------------------------------
  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      return JSON.parse(raw) || {};
    } catch {
      return {};
    }
  }

  function saveState(patch) {
    const next = { ...loadState(), ...patch };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* localStorage unavailable (private browsing, quota, ...) -- state
         just won't survive a reload; everything else still works. */
    }
    return next;
  }

  let state = {
    baseUrl: "",
    apiKey: "",
    preset: "adk",
    sessionId: null,
    theme: null, // null = follow system preference
    ...loadState(),
  };

  // Finalized (non-streaming-partial) turns, for "Save chat" -- runtime
  // only, like the visible transcript itself (neither survives a reload,
  // see loadState/saveState above -- only connection settings do).
  state.transcript = [];

  // The Agent Network tab's data -- built ENTIRELY from "progress" SSE
  // events (see streamChat/sendMessage), since those are the only events
  // that carry an "origin". Runtime only, same as the transcript above.
  //   nodes: id -> { id, label, depth, count, invocations: [...] }
  //   edges: "from|to|type" -> { from, to, type, count }
  // A node's own id is its FULL dotted path up to and including itself
  // (e.g. "cloudarch.CloudArch_Pipeline"), not just its last segment --
  // two different branches can otherwise have same-named leaves.
  state.network = {
    nodes: new Map(),
    edges: new Map(),
    lastLeaf: null,
    activeLeaf: null,
    selectedNode: null,
    turnIndex: 0,
    currentQuery: "",
    view: { x: 0, y: 0, scale: 1 },
    autoFit: true,
  };

  // ---------------------------------------------------------------
  // Theme
  // ---------------------------------------------------------------
  function applyTheme() {
    const root = document.documentElement;
    if (state.theme === "dark" || state.theme === "light") {
      root.setAttribute("data-theme", state.theme);
    } else {
      root.removeAttribute("data-theme");
    }
    const systemDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = state.theme ? state.theme === "dark" : systemDark;
    el.themeToggleIcon.textContent = isDark ? "☀" : "☽";
    el.themeToggleLabel.textContent = isDark ? "Light mode" : "Dark mode";
  }

  el.themeToggleBtn.addEventListener("click", () => {
    const systemDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const currentlyDark = state.theme ? state.theme === "dark" : systemDark;
    state.theme = currentlyDark ? "light" : "dark";
    saveState({ theme: state.theme });
    applyTheme();
  });

  // ---------------------------------------------------------------
  // Sidebar (mobile)
  // ---------------------------------------------------------------
  function openSidebar() { el.app.classList.add("sidebar-visible"); }
  function closeSidebar() { el.app.classList.remove("sidebar-visible"); }
  el.sidebarOpenBtn.addEventListener("click", openSidebar);
  el.sidebarCloseBtn.addEventListener("click", closeSidebar);
  el.sidebarScrim.addEventListener("click", closeSidebar);

  // ---------------------------------------------------------------
  // Toast
  // ---------------------------------------------------------------
  function toast(message) {
    if (!el.toast) {
      el.toast = document.createElement("div");
      el.toast.id = "toast";
      document.body.appendChild(el.toast);
    }
    el.toast.textContent = message;
    el.toast.classList.add("visible");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.toast.classList.remove("visible"), 2200);
  }

  // ---------------------------------------------------------------
  // Connection settings
  // ---------------------------------------------------------------
  function setPreset(name) {
    state.preset = name;
    el.presetBtns.forEach((btn) => btn.classList.toggle("active", btn.dataset.preset === name));
    if (name !== "custom" && PRESETS[name]) {
      el.baseUrlInput.value = PRESETS[name].baseUrl;
    }
  }

  el.presetBtns.forEach((btn) => {
    btn.addEventListener("click", () => setPreset(btn.dataset.preset));
  });

  el.baseUrlInput.addEventListener("input", () => {
    // Manually editing the URL always implies "custom", regardless of
    // which preset button was last clicked.
    const matchesPreset = Object.entries(PRESETS).find(([, p]) => p.baseUrl === el.baseUrlInput.value);
    setPreset(matchesPreset ? matchesPreset[0] : "custom");
  });

  el.toggleKeyVisibility.addEventListener("click", () => {
    el.apiKeyInput.type = el.apiKeyInput.type === "password" ? "text" : "password";
  });

  function currentBaseUrl() {
    return (el.baseUrlInput.value || "").trim().replace(/\/+$/, "");
  }

  function authHeaders() {
    const key = el.apiKeyInput.value.trim();
    if (!key) return {};
    return { Authorization: `Bearer ${key}` };
  }

  function setStatusPill(pillEl, kind, text) {
    pillEl.classList.remove("status-unknown", "status-connected", "status-error", "status-checking");
    pillEl.classList.add(`status-${kind}`);
    pillEl.querySelector(".status-text").textContent = text;
  }

  function setStatus(kind, text) {
    setStatusPill(el.connectionStatus, kind, text);
    setStatusPill(el.topbarStatus, kind, text);
  }

  async function connect() {
    const baseUrl = currentBaseUrl();
    if (!baseUrl) {
      toast("Enter a Base URL first.");
      return;
    }
    setStatus("checking", "Checking…");
    el.connectBtn.disabled = true;
    try {
      const res = await fetch(`${baseUrl}/status`, { method: "GET" });
      if (res.ok) {
        setStatus("connected", "Connected");
        saveState({ baseUrl, apiKey: el.apiKeyInput.value, preset: state.preset });
      } else {
        setStatus("error", `Unreachable (${res.status})`);
      }
    } catch (err) {
      setStatus("error", "Unreachable");
    } finally {
      el.connectBtn.disabled = false;
    }
  }

  el.connectBtn.addEventListener("click", connect);

  // ---------------------------------------------------------------
  // Session
  // ---------------------------------------------------------------
  function setSessionId(id) {
    state.sessionId = id || null;
    el.sessionIdLabel.textContent = id || "none";
    saveState({ sessionId: state.sessionId });
  }

  async function newChat() {
    const baseUrl = currentBaseUrl();
    if (state.sessionId && baseUrl) {
      try {
        await fetch(`${baseUrl}/chat/${encodeURIComponent(state.sessionId)}`, {
          method: "DELETE",
          headers: { ...authHeaders() },
        });
      } catch {
        // Best-effort -- the server-side session will simply age out /
        // stay around until process restart if this fails; either way
        // the client forgets it below.
      }
    }
    setSessionId(null);
    el.chatContainer.innerHTML = "";
    el.chatContainer.appendChild(el.emptyState);
    el.emptyState.style.display = "";
    state.transcript = [];
    resetNetwork();
    toast("Started a new chat.");
  }

  el.newChatBtn.addEventListener("click", newChat);

  // ---------------------------------------------------------------
  // Markdown-lite rendering (no external dependency)
  // ---------------------------------------------------------------
  function escapeHtml(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderInline(text) {
    // Pull out backslash-escaped literals FIRST (e.g. a user typed a
    // literal "*" in the composer, which richTextToMarkdown below escapes
    // as "\*" so it round-trips as a literal character instead of being
    // misread as bold/italic syntax here) -- placeholders survive
    // escapeHtml and the markdown regexes below unaffected (neither
    // control characters nor digits match any of them), then get
    // restored as literal (HTML-escaped) text at the very end.
    const escapes = [];
    const withPlaceholders = text.replace(/\\([*_`\\])/g, (_m, ch) => {
      escapes.push(ch);
      return `\u0000${escapes.length - 1}\u0000`;
    });

    let out = escapeHtml(withPlaceholders);
    // Links: [text](url) -- escaped url's quotes already neutralized by escapeHtml above.
    out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    // Inline code.
    out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
    // Bold then italic (order matters so **x** isn't eaten by the italic rule first).
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");

    out = out.replace(/\u0000(\d+)\u0000/g, (_m, i) => escapeHtml(escapes[Number(i)]));
    return out;
  }

  function renderMarkdownLite(raw) {
    const text = (raw || "").replace(/\r\n/g, "\n");
    const lines = text.split("\n");
    const html = [];
    let i = 0;
    let listBuffer = null; // { type: 'ul'|'ol', items: [] }

    function flushList() {
      if (!listBuffer) return;
      const tag = listBuffer.type;
      html.push(`<${tag}>` + listBuffer.items.map((it) => `<li>${renderInline(it)}</li>`).join("") + `</${tag}>`);
      listBuffer = null;
    }

    while (i < lines.length) {
      const line = lines[i];

      // Fenced code block.
      if (/^```/.test(line)) {
        flushList();
        const codeLines = [];
        i += 1;
        while (i < lines.length && !/^```/.test(lines[i])) {
          codeLines.push(lines[i]);
          i += 1;
        }
        i += 1; // skip closing fence
        html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        continue;
      }

      // Headings.
      const heading = line.match(/^(#{1,3})\s+(.*)$/);
      if (heading) {
        flushList();
        const level = heading[1].length;
        html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
        i += 1;
        continue;
      }

      // Unordered list item.
      const ul = line.match(/^\s*[-*]\s+(.*)$/);
      if (ul) {
        if (!listBuffer || listBuffer.type !== "ul") {
          flushList();
          listBuffer = { type: "ul", items: [] };
        }
        listBuffer.items.push(ul[1]);
        i += 1;
        continue;
      }

      // Ordered list item.
      const ol = line.match(/^\s*\d+\.\s+(.*)$/);
      if (ol) {
        if (!listBuffer || listBuffer.type !== "ol") {
          flushList();
          listBuffer = { type: "ol", items: [] };
        }
        listBuffer.items.push(ol[1]);
        i += 1;
        continue;
      }

      flushList();

      // Blank line -- paragraph separator, nothing to emit.
      if (line.trim() === "") {
        i += 1;
        continue;
      }

      // Paragraph: gather consecutive non-blank, non-special lines. A
      // line ending in two or more trailing spaces is the standard
      // markdown "hard break" marker (this is what the composer's own
      // richTextToMarkdown emits for a user's Shift+Enter) -- rendered
      // as an actual <br>, not collapsed into the flowing paragraph text
      // the way an ordinary soft-wrapped line is. Each line is run
      // through renderInline SEPARATELY (not after joining the raw
      // markdown first) so formatting that closes before a break and
      // reopens after it -- exactly what richTextToMarkdown produces --
      // renders correctly either way.
      const paraLines = [line];
      i += 1;
      while (
        i < lines.length &&
        lines[i].trim() !== "" &&
        !/^```/.test(lines[i]) &&
        !/^#{1,3}\s+/.test(lines[i]) &&
        !/^\s*[-*]\s+/.test(lines[i]) &&
        !/^\s*\d+\.\s+/.test(lines[i])
      ) {
        paraLines.push(lines[i]);
        i += 1;
      }
      let paragraph = renderInline(paraLines[0].replace(/ {2,}$/, ""));
      for (let j = 1; j < paraLines.length; j += 1) {
        const joiner = / {2,}$/.test(paraLines[j - 1]) ? "<br>" : " ";
        paragraph += joiner + renderInline(paraLines[j].replace(/ {2,}$/, ""));
      }
      html.push(`<p>${paragraph}</p>`);
    }

    flushList();
    return html.join("") || escapeHtml(text);
  }

  // ---------------------------------------------------------------
  // Tabs
  // ---------------------------------------------------------------
  function switchTab(name) {
    el.tabBtns.forEach((btn) => {
      const isActive = btn.dataset.tab === name;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-selected", String(isActive));
    });
    el.chatTabPanel.hidden = name !== "chat";
    el.networkTabPanel.hidden = name !== "network";
    if (name === "network") {
      // The SVG's viewBox is sized from el.networkCanvasWrap's own
      // clientWidth/clientHeight (see computeNetworkLayout) -- while the
      // panel was hidden that was 0, so the layout has to be redone now
      // that the panel actually has real dimensions to measure.
      renderNetwork();
    } else {
      closeNodeDetail();
    }
  }

  el.tabBtns.forEach((btn) => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

  // ---------------------------------------------------------------
  // Agent Network -- built entirely from "progress" SSE events (the only
  // ones carrying an "origin"; see streamChat/sendMessage below), tracking
  // which agents/pipelines/tools have been invoked in this session and
  // how they relate to each other, live as the conversation moves on.
  // ---------------------------------------------------------------
  function resetNetwork() {
    state.network = {
      nodes: new Map(),
      edges: new Map(),
      lastLeaf: null,
      activeLeaf: null,
      selectedNode: null,
      turnIndex: 0,
      currentQuery: "",
      view: { x: 0, y: 0, scale: 1 },
      autoFit: true,
    };
    closeNodeDetail();
    renderNetwork();
  }

  // Called once per sendMessage, before the turn's events start arriving,
  // so every invocation recorded during this turn can be traced back to
  // the query that triggered it (shown in the node detail drawer).
  function beginNetworkTurn(query) {
    state.network.turnIndex += 1;
    state.network.currentQuery = query;
  }

  function recordInvocation(origin, text) {
    if (!origin) return;
    const path = origin.split(".").map((s) => s.trim()).filter(Boolean);
    if (path.length === 0) return;

    const net = state.network;
    let id = "";
    for (let depth = 0; depth < path.length; depth += 1) {
      const parentId = id;
      id = id ? `${id}.${path[depth]}` : path[depth];
      if (!net.nodes.has(id)) {
        net.nodes.set(id, { id, label: path[depth], depth, count: 0, invocations: [] });
      }
      if (depth > 0) {
        const edgeKey = `${parentId}|${id}|hierarchy`;
        const edge = net.edges.get(edgeKey) || { from: parentId, to: id, type: "hierarchy", count: 0 };
        edge.count += 1;
        net.edges.set(edgeKey, edge);
      }
    }

    const leaf = id;
    const leafNode = net.nodes.get(leaf);
    leafNode.count += 1;
    leafNode.invocations.push({
      text: text || "",
      timestamp: new Date(),
      turnIndex: net.turnIndex,
      query: net.currentQuery,
    });

    // A "flow"/handoff edge from whichever node was last active to this
    // one -- the only signal available for a backend whose origin has no
    // dotted hierarchy at all (ADK's is a single flat agent name; see
    // _stream_chat_turn's own docstring), and still useful alongside the
    // hierarchy edges above for neuro-san's multi-segment origins, since
    // it captures control actually MOVING to a sibling/unrelated branch,
    // not just nesting. Skipped when the direct parent in THIS path is
    // already the last-active node, so a plain step deeper into the same
    // branch doesn't draw a redundant second edge on top of the
    // hierarchy one that already connects them.
    const directParent = path.length > 1 ? id.slice(0, id.length - path[path.length - 1].length - 1) : null;
    if (net.lastLeaf && net.lastLeaf !== leaf && net.lastLeaf !== directParent) {
      const edgeKey = `${net.lastLeaf}|${leaf}|flow`;
      const edge = net.edges.get(edgeKey) || { from: net.lastLeaf, to: leaf, type: "flow", count: 0 };
      edge.count += 1;
      net.edges.set(edgeKey, edge);
    }
    net.lastLeaf = leaf;
    net.activeLeaf = leaf;
  }

  // Called when a turn ends (done/error/connection lost) so the pulsing
  // "currently active" highlight reflects a turn actually in progress,
  // not whichever node happened to go last.
  function endNetworkTurn() {
    state.network.activeLeaf = null;
    renderNetwork();
  }

  function computeNetworkLayout() {
    const nodes = Array.from(state.network.nodes.values());
    if (nodes.length === 0) return { nodes: [], width: 0, height: 0 };

    const byDepth = new Map();
    nodes.forEach((n) => {
      if (!byDepth.has(n.depth)) byDepth.set(n.depth, []);
      byDepth.get(n.depth).push(n);
    });

    const levelHeight = 110;
    // This project's own agent names run long (CloudArch_Reviewer_Agent,
    // Requirements_Summary_Agent, ...) -- wide enough spacing that
    // truncateLabel's own (also widened) limit doesn't still have to
    // chop most of them down to a couple of words.
    const nodeSpacing = 190;
    const marginX = 80;
    const marginY = 50;

    const maxCols = Math.max(...Array.from(byDepth.values()).map((arr) => arr.length));
    // The NATURAL size of the graph's own content -- not padded up to
    // fill the canvas wrap the way an earlier version of this did. Zoom/
    // pan (see applyNetworkTransform) handles fitting/filling the canvas
    // now, so this only needs to be big enough that a 1-2 node graph
    // doesn't collapse to a single point.
    const width = Math.max(360, marginX * 2 + Math.max(0, maxCols - 1) * nodeSpacing);
    const depths = Array.from(byDepth.keys()).sort((a, b) => a - b);
    const height = Math.max(240, marginY * 2 + Math.max(0, depths.length - 1) * levelHeight);

    const positioned = [];
    depths.forEach((depth) => {
      const rowNodes = byDepth.get(depth); // stable: Map iteration = insertion = first-seen order
      const rowWidth = Math.max(0, rowNodes.length - 1) * nodeSpacing;
      const startX = (width - rowWidth) / 2;
      const y = depths.length === 1 ? height / 2 : marginY + depth * levelHeight;
      rowNodes.forEach((n, i) => {
        const radius = Math.min(26, 15 + Math.log2(n.count + 1) * 4);
        positioned.push({ ...n, x: startX + i * nodeSpacing, y, radius });
      });
    });

    return { nodes: positioned, width, height };
  }

  function truncateLabel(label, max = 24) {
    return label.length > max ? `${label.slice(0, max - 1)}…` : label;
  }

  function edgeEndpoint(from, to, radius) {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    return { x: from.x + (dx / dist) * radius, y: from.y + (dy / dist) * radius };
  }

  const SVG_NS = "http://www.w3.org/2000/svg";

  function renderNetwork() {
    const nodeCount = state.network.nodes.size;
    el.networkTabBadge.hidden = nodeCount === 0;
    el.networkTabBadge.textContent = String(nodeCount);
    el.networkCount.textContent = nodeCount === 0
      ? "No agents invoked yet"
      : `${nodeCount} agent${nodeCount === 1 ? "" : "s"} invoked`;

    if (nodeCount === 0) {
      el.networkEmpty.style.display = "";
      el.networkSvg.setAttribute("hidden", "");
      el.networkSvg.innerHTML = ""; // defense-in-depth: no stale graph content even if hiding it fails
      return;
    }
    el.networkEmpty.style.display = "none";
    // The "hidden" IDL property doesn't reliably reflect onto a
    // namespaced SVG element in every engine the way it does for plain
    // HTML elements (confirmed directly: el.networkSvg.hidden = false
    // left the content attribute in place) -- toggle the attribute
    // itself instead, which has no such ambiguity.
    el.networkSvg.removeAttribute("hidden");

    const { nodes, width, height } = computeNetworkLayout();
    const byId = new Map(nodes.map((n) => [n.id, n]));

    // The SVG's own viewBox is pinned 1:1 to the canvas wrap's actual
    // pixel size -- NOT the graph content's size -- so the zoom/pan
    // transform below (applied to #networkViewport, not the viewBox
    // itself) can work in plain screen-pixel-equivalent units instead of
    // juggling two different coordinate systems.
    const wrapWidth = el.networkCanvasWrap.clientWidth || 600;
    const wrapHeight = el.networkCanvasWrap.clientHeight || 400;
    el.networkSvg.setAttribute("viewBox", `0 0 ${wrapWidth} ${wrapHeight}`);
    el.networkSvg.innerHTML = "";

    const defs = document.createElementNS(SVG_NS, "defs");
    defs.innerHTML = `
      <marker id="netArrowHierarchy" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 Z" class="net-arrow-hierarchy"></path>
      </marker>
      <marker id="netArrowFlow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 Z" class="net-arrow-flow"></path>
      </marker>
    `;
    el.networkSvg.appendChild(defs);

    const viewport = document.createElementNS(SVG_NS, "g");
    viewport.setAttribute("id", "networkViewport");

    const edgeGroup = document.createElementNS(SVG_NS, "g");
    for (const edge of state.network.edges.values()) {
      const from = byId.get(edge.from);
      const to = byId.get(edge.to);
      if (!from || !to) continue;
      const start = edgeEndpoint(from, to, from.radius);
      const end = edgeEndpoint(to, from, to.radius + 6);
      const line = document.createElementNS(SVG_NS, "line");
      line.setAttribute("x1", String(start.x));
      line.setAttribute("y1", String(start.y));
      line.setAttribute("x2", String(end.x));
      line.setAttribute("y2", String(end.y));
      line.setAttribute("class", `net-edge net-edge-${edge.type}`);
      line.setAttribute("marker-end", edge.type === "hierarchy" ? "url(#netArrowHierarchy)" : "url(#netArrowFlow)");
      edgeGroup.appendChild(line);
    }
    viewport.appendChild(edgeGroup);

    const nodeGroup = document.createElementNS(SVG_NS, "g");
    for (const node of nodes) {
      const isActive = node.id === state.network.activeLeaf;
      const isSelected = node.id === state.network.selectedNode;
      const classes = ["net-node"];
      if (isActive) classes.push("net-node-active");
      if (isSelected) classes.push("net-node-selected");

      const g = document.createElementNS(SVG_NS, "g");
      g.setAttribute("class", classes.join(" "));
      g.setAttribute("transform", `translate(${node.x}, ${node.y})`);
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      g.setAttribute("aria-label", `${node.label}, invoked ${node.count} time${node.count === 1 ? "" : "s"}`);
      g.addEventListener("click", () => showNodeDetail(node.id));
      g.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          showNodeDetail(node.id);
        }
      });

      if (isActive) {
        const pulse = document.createElementNS(SVG_NS, "circle");
        pulse.setAttribute("r", String(node.radius));
        pulse.setAttribute("class", "net-node-pulse");
        g.appendChild(pulse);
      }

      const circle = document.createElementNS(SVG_NS, "circle");
      circle.setAttribute("r", String(node.radius));
      circle.setAttribute("class", "net-node-circle");
      g.appendChild(circle);

      const title = document.createElementNS(SVG_NS, "title");
      title.textContent = `${node.id}\nInvoked ${node.count} time${node.count === 1 ? "" : "s"} — click for details`;
      g.appendChild(title);

      if (node.count > 1) {
        const countLabel = document.createElementNS(SVG_NS, "text");
        countLabel.setAttribute("class", "net-node-count");
        countLabel.setAttribute("text-anchor", "middle");
        countLabel.setAttribute("dy", "3.5");
        countLabel.textContent = String(node.count);
        g.appendChild(countLabel);
      }

      const label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("class", "net-node-label");
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("dy", String(node.radius + 16));
      label.textContent = truncateLabel(node.label);
      g.appendChild(label);

      nodeGroup.appendChild(g);
    }
    viewport.appendChild(nodeGroup);
    el.networkSvg.appendChild(viewport);

    if (state.network.autoFit) {
      computeFitView(width, height, wrapWidth, wrapHeight);
    }
    applyNetworkTransform();
  }

  // ---------------------------------------------------------------
  // Zoom / pan -- the +/-/reset controls and drag-to-pan/wheel-zoom this
  // section implements all just adjust state.network.view (x, y, scale)
  // and re-apply it as a transform on #networkViewport; the graph's own
  // node positions (computeNetworkLayout) never change. autoFit stays
  // true (recomputing a "fit everything" view on every render, so newly
  // streamed-in nodes never end up off-screen) until the user manually
  // zooms or pans, at which point their view is left alone until they
  // click Reset.
  // ---------------------------------------------------------------
  const ZOOM_STEP = 1.3;
  const MIN_SCALE = 0.2;
  const MAX_SCALE = 3;

  function computeFitView(contentWidth, contentHeight, wrapWidth, wrapHeight) {
    const padding = 32;
    const scale = Math.min(
      1.15, // don't blow a 1-2 node graph up past a sensible size just because the canvas is big
      Math.max(MIN_SCALE, Math.min(
        (wrapWidth - padding * 2) / contentWidth,
        (wrapHeight - padding * 2) / contentHeight,
      )),
    );
    state.network.view = {
      scale,
      x: (wrapWidth - contentWidth * scale) / 2,
      y: (wrapHeight - contentHeight * scale) / 2,
    };
  }

  function applyNetworkTransform() {
    const viewport = document.getElementById("networkViewport");
    if (!viewport) return;
    const { x, y, scale } = state.network.view;
    viewport.setAttribute("transform", `translate(${x}, ${y}) scale(${scale})`);
  }

  function zoomBy(factor) {
    if (state.network.nodes.size === 0) return;
    const wrapWidth = el.networkCanvasWrap.clientWidth || 600;
    const wrapHeight = el.networkCanvasWrap.clientHeight || 400;
    const view = state.network.view;
    const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
    // Zoom around the canvas's own center, not the content's origin --
    // keeps whatever's currently in the middle of the view in the middle
    // after zooming, instead of the view drifting toward a corner.
    const cx = wrapWidth / 2;
    const cy = wrapHeight / 2;
    const contentCx = (cx - view.x) / view.scale;
    const contentCy = (cy - view.y) / view.scale;
    state.network.view = {
      scale: newScale,
      x: cx - contentCx * newScale,
      y: cy - contentCy * newScale,
    };
    state.network.autoFit = false;
    applyNetworkTransform();
  }

  function resetNetworkView() {
    state.network.autoFit = true;
    renderNetwork();
  }

  el.networkZoomInBtn.addEventListener("click", () => zoomBy(ZOOM_STEP));
  el.networkZoomOutBtn.addEventListener("click", () => zoomBy(1 / ZOOM_STEP));
  el.networkResetViewBtn.addEventListener("click", resetNetworkView);

  el.networkCanvasWrap.addEventListener("wheel", (event) => {
    if (state.network.nodes.size === 0) return;
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? 1.12 : 1 / 1.12);
  }, { passive: false });

  let panPointerId = null;
  let panStart = null;

  el.networkSvg.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".net-node")) return; // let node clicks through, not a pan start
    if (state.network.nodes.size === 0) return;
    panPointerId = event.pointerId;
    panStart = { clientX: event.clientX, clientY: event.clientY, viewX: state.network.view.x, viewY: state.network.view.y };
    el.networkSvg.setPointerCapture(event.pointerId);
    el.networkSvg.classList.add("panning");
  });
  el.networkSvg.addEventListener("pointermove", (event) => {
    if (panPointerId !== event.pointerId || !panStart) return;
    state.network.view = {
      ...state.network.view,
      x: panStart.viewX + (event.clientX - panStart.clientX),
      y: panStart.viewY + (event.clientY - panStart.clientY),
    };
    state.network.autoFit = false;
    applyNetworkTransform();
  });
  function endPan(event) {
    if (panPointerId !== event.pointerId) return;
    panPointerId = null;
    panStart = null;
    el.networkSvg.classList.remove("panning");
  }
  el.networkSvg.addEventListener("pointerup", endPan);
  el.networkSvg.addEventListener("pointercancel", endPan);

  // ---------------------------------------------------------------
  // Node detail drawer -- "what did this agent/pipeline/tool actually do
  // in this session" for debugging a chat: every recorded invocation
  // (timestamp, the progress note seen, which turn, and the user query
  // that triggered it), not just the aggregate count shown on the node.
  // ---------------------------------------------------------------
  function showNodeDetail(nodeId) {
    const node = state.network.nodes.get(nodeId);
    if (!node) return;

    state.network.selectedNode = nodeId;
    renderNetwork(); // picks up the .net-node-selected ring on the clicked node

    el.nodeDetailTitle.textContent = node.label;
    el.nodeDetailPath.textContent = node.id;

    const baseUrl = currentBaseUrl() || "(not set)";
    el.nodeDetailContext.innerHTML = "";
    const sessionLine = document.createElement("div");
    sessionLine.innerHTML = `Session <code>${escapeHtml(state.sessionId || "none")}</code>`;
    const backendLine = document.createElement("div");
    backendLine.innerHTML = `Backend <code>${escapeHtml(baseUrl)}</code>`;
    el.nodeDetailContext.append(sessionLine, backendLine);

    const firstTurn = node.invocations[0]?.turnIndex;
    const lastInvocation = node.invocations[node.invocations.length - 1];
    el.nodeDetailStats.innerHTML = "";
    const stats = [
      ["Invocations", String(node.count)],
      ["First turn", firstTurn ? `#${firstTurn}` : "—"],
      ["Last seen", lastInvocation ? formatTime(lastInvocation.timestamp) : "—"],
    ];
    for (const [label, value] of stats) {
      const stat = document.createElement("div");
      stat.className = "node-detail-stat";
      stat.innerHTML = `<span class="node-detail-stat-value">${escapeHtml(value)}</span><span class="node-detail-stat-label">${escapeHtml(label)}</span>`;
      el.nodeDetailStats.appendChild(stat);
    }

    el.nodeDetailList.innerHTML = "";
    if (node.invocations.length === 0) {
      const empty = document.createElement("div");
      empty.className = "node-detail-empty";
      empty.textContent = "No recorded activity for this node yet.";
      el.nodeDetailList.appendChild(empty);
    } else {
      // Most recent first -- what you'd want when debugging "what just happened".
      for (const invocation of [...node.invocations].reverse()) {
        const entry = document.createElement("div");
        entry.className = "node-detail-entry";

        const meta = document.createElement("div");
        meta.className = "node-detail-entry-meta";
        meta.innerHTML = `<span>Turn #${invocation.turnIndex}</span><span>${formatTime(invocation.timestamp)}</span>`;
        entry.appendChild(meta);

        const text = document.createElement("div");
        text.className = "node-detail-entry-text";
        text.textContent = invocation.text || "(no progress text)";
        entry.appendChild(text);

        if (invocation.query) {
          const query = document.createElement("div");
          query.className = "node-detail-entry-query";
          query.innerHTML = `<b>Query:</b> ${escapeHtml(invocation.query)}`;
          entry.appendChild(query);
        }

        el.nodeDetailList.appendChild(entry);
      }
    }

    el.nodeDetail.classList.add("open");
  }

  function closeNodeDetail() {
    el.nodeDetail.classList.remove("open");
    if (state.network.selectedNode) {
      state.network.selectedNode = null;
      renderNetwork();
    }
  }

  el.nodeDetailCloseBtn.addEventListener("click", closeNodeDetail);

  // ---------------------------------------------------------------
  // Chat transcript rendering
  // ---------------------------------------------------------------
  function scrollToBottom() {
    el.chatScroll.scrollTop = el.chatScroll.scrollHeight;
  }

  function formatTime(date) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // For "Save chat" -- records the FINAL text of a turn (never a partial
  // streaming delta) so the exported transcript reads the same whether a
  // turn streamed live or came back in one shot via the non-streaming
  // fallback.
  function recordTranscript(role, text) {
    state.transcript.push({ role, text, timestamp: new Date() });
  }

  function addMessage(role, text, { isMarkdown = false } = {}) {
    recordTranscript(role, text);
    el.emptyState.style.display = "none";

    const row = document.createElement("div");
    row.className = `message-row ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = role === "user" ? "You" : role === "error" ? "!" : "PA";
    row.appendChild(avatar);

    const col = document.createElement("div");
    col.className = "message-col";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (isMarkdown) {
      bubble.innerHTML = renderMarkdownLite(text);
    } else {
      bubble.textContent = text;
    }
    col.appendChild(bubble);

    const meta = document.createElement("div");
    meta.className = "message-meta";
    const time = document.createElement("span");
    time.textContent = formatTime(new Date());
    meta.appendChild(time);

    if (role === "agent") {
      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "copy-btn";
      copyBtn.textContent = "Copy";
      copyBtn.addEventListener("click", () => copyText(text));
      meta.appendChild(copyBtn);
    }
    col.appendChild(meta);

    row.appendChild(col);
    el.chatContainer.appendChild(row);
    scrollToBottom();
    return row;
  }

  // A message row that starts as a typing indicator and is updated in
  // place as a streamed turn progresses -- see streamChat/sendMessage.
  // Kept deliberately separate from addMessage (which is one-shot: full
  // text, rendered once) since a streaming turn needs to mutate the
  // SAME bubble repeatedly as progress/delta events arrive.
  function createLiveAgentMessage() {
    el.emptyState.style.display = "none";

    const row = document.createElement("div");
    row.className = "message-row agent";

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = "PA";
    row.appendChild(avatar);

    const col = document.createElement("div");
    col.className = "message-col";

    const progressNote = document.createElement("div");
    progressNote.className = "progress-note";
    progressNote.hidden = true;
    col.appendChild(progressNote);

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
    col.appendChild(bubble);

    row.appendChild(col);
    el.chatContainer.appendChild(row);
    scrollToBottom();

    let metaAdded = false;

    return {
      row,

      setProgress(origin, text) {
        progressNote.hidden = false;
        progressNote.textContent = origin ? `${origin} — ${text}` : text;
        scrollToBottom();
      },

      // Plain text, deliberately NOT markdown-rendered -- a delta is an
      // in-progress fragment (e.g. an unclosed ```code block```), and
      // parsing that as markdown mid-stream renders broken HTML far
      // more often than it renders anything useful. finalize() below
      // applies the real rendering once, to the complete text.
      setText(text) {
        progressNote.hidden = true;
        bubble.textContent = text;
        scrollToBottom();
      },

      finalize(text) {
        recordTranscript("agent", text);
        progressNote.remove();
        bubble.innerHTML = renderMarkdownLite(text);
        if (!metaAdded) {
          metaAdded = true;
          const meta = document.createElement("div");
          meta.className = "message-meta";
          const time = document.createElement("span");
          time.textContent = formatTime(new Date());
          meta.appendChild(time);
          const copyBtn = document.createElement("button");
          copyBtn.type = "button";
          copyBtn.className = "copy-btn";
          copyBtn.textContent = "Copy";
          copyBtn.addEventListener("click", () => copyText(text));
          meta.appendChild(copyBtn);
          col.appendChild(meta);
        }
        scrollToBottom();
      },

      showError(message) {
        progressNote.remove();
        row.classList.add("error");
        const hasText = bubble.textContent && bubble.textContent.trim().length > 0;
        bubble.textContent = hasText ? `${bubble.textContent}\n\n⚠ ${message}` : message;
        scrollToBottom();
      },
    };
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      toast("Copied to clipboard.");
    } catch {
      toast("Could not copy.");
    }
  }

  // ---------------------------------------------------------------
  // Sending a turn (with retry/backoff for transient failures)
  // ---------------------------------------------------------------
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function postChat(baseUrl, query) {
    let lastError = null;
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt += 1) {
      if (attempt > 0) {
        await sleep(RETRY_BASE_DELAY_MS * 2 ** (attempt - 1));
      }
      try {
        const res = await fetch(`${baseUrl}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ query, session_id: state.sessionId || undefined }),
        });

        if (res.ok) {
          return res.json();
        }

        const body = await res.json().catch(() => ({}));
        const message = body.error || `Request failed (${res.status}).`;

        if (RETRYABLE_STATUS.has(res.status) && attempt < MAX_RETRIES) {
          lastError = new Error(message);
          continue; // backoff and retry
        }
        throw new Error(message);
      } catch (err) {
        if (err instanceof TypeError && attempt < MAX_RETRIES) {
          // Network-level failure (connection refused, DNS, CORS
          // preflight rejection, offline) -- worth a retry in case it
          // was transient; a misconfigured Base URL will just exhaust
          // the retries and surface the same error afterward.
          lastError = err;
          continue;
        }
        throw err;
      }
    }
    throw lastError || new Error("Request failed after retrying.");
  }

  // Async generator over POST /chat/stream's text/event-stream body: one
  // parsed JSON object per `data: {...}\n\n` frame. Deliberately NOT the
  // browser's native EventSource -- EventSource is GET-only and can't
  // send custom headers, so there's no way to attach Authorization/
  // X-API-Key to it when an API key is configured. fetch() + manually
  // reading response.body's ReadableStream works the same way EventSource
  // would from the caller's point of view (just `for await` the events)
  // without that limitation.
  async function* streamChat(baseUrl, query) {
    const response = await fetch(`${baseUrl}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ query, session_id: state.sessionId || undefined }),
    });

    if (!response.ok || !response.body) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `Request failed (${response.status}).`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      let separatorIndex;
      while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);
        const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data:"));
        if (!dataLine) continue;
        try {
          yield JSON.parse(dataLine.slice(5).trim());
        } catch {
          // Malformed frame -- skip it rather than abort the whole turn
          // over one bad chunk.
        }
      }
    }
  }

  async function sendMessage(text) {
    const baseUrl = currentBaseUrl();
    if (!baseUrl) {
      toast("Set a Base URL and click Connect first.");
      return;
    }

    addMessage("user", text, { isMarkdown: true });
    beginNetworkTurn(text);
    el.sendBtn.disabled = true;
    el.messageInput.contentEditable = "false";

    const live = createLiveAgentMessage();
    let gotAnyEvent = false;
    let sawDone = false;

    try {
      for await (const event of streamChat(baseUrl, text)) {
        gotAnyEvent = true;
        if (event.session_id) setSessionId(event.session_id);

        if (event.status === "progress") {
          live.setProgress(event.origin, event.text || "");
          recordInvocation(event.origin, event.text);
          renderNetwork();
        } else if (event.status === "delta") {
          live.setText(event.text || "");
        } else if (event.status === "done") {
          sawDone = true;
          live.finalize(event.response || "(empty response)");
        } else if (event.status === "error") {
          live.showError(event.error || "The backend returned an error.");
        }
      }
      if (!sawDone) {
        // The stream closed without ever sending "done" -- leaves no
        // indication anything went wrong otherwise (no exception is
        // thrown just because the body ended), so the live bubble would
        // otherwise be stuck showing a half-finished answer forever.
        live.showError("The connection ended unexpectedly.");
      }
    } catch (err) {
      if (!gotAnyEvent) {
        // Nothing arrived at all -- likely an older backend without
        // /chat/stream, or a network hiccup before the stream even
        // started. Fall back to the non-streaming endpoint (which has
        // its own retry/backoff) instead of leaving the user looking at
        // a dead typing indicator.
        live.row.remove();
        try {
          const data = await postChat(baseUrl, text);
          if (data.status === "ok") {
            setSessionId(data.session_id);
            addMessage("agent", data.response || "(empty response)", { isMarkdown: true });
          } else {
            addMessage("error", data.error || "The backend returned an error.");
          }
        } catch (fallbackErr) {
          addMessage("error", `Couldn't reach the backend: ${fallbackErr.message || fallbackErr}`);
        }
      } else {
        // Died mid-stream after already showing partial text -- don't
        // silently retry (could duplicate a billable LLM call); show
        // what arrived plus an inline error instead.
        live.showError(`Connection lost: ${err.message || err}`);
      }
    } finally {
      endNetworkTurn();
      el.sendBtn.disabled = false;
      el.messageInput.contentEditable = "true";
      el.messageInput.focus();
    }
  }

  // ---------------------------------------------------------------
  // Composer -- a contenteditable div (not a <textarea>) so bold/italic/
  // bullet formatting actually has somewhere to live while typing.
  // Auto-expands by itself via CSS (min-height/max-height/overflow-y on
  // .composer-input) -- unlike a <textarea>, a block-level contenteditable
  // naturally grows with its own content, so there's no scrollHeight
  // bookkeeping needed here the way a <textarea> would require.
  // ---------------------------------------------------------------
  function updateEmptyState() {
    const isEmpty = el.messageInput.textContent.trim() === "" && !el.messageInput.querySelector("img");
    el.messageInput.classList.toggle("is-empty", isEmpty);
  }

  function updateToolbarActiveStates() {
    el.toolbarBtns.forEach((btn) => {
      try {
        btn.classList.toggle("active", document.queryCommandState(btn.dataset.command));
      } catch {
        // queryCommandState can throw for a command the browser doesn't
        // recognize -- leave that button's active state alone rather
        // than letting one bad command break the others.
      }
    });
  }

  el.toolbarBtns.forEach((btn) => {
    // Without this, clicking a toolbar button first steals focus (and
    // therefore the text selection execCommand needs to act on) away
    // from the composer before the click handler below even runs.
    btn.addEventListener("mousedown", (event) => event.preventDefault());
    btn.addEventListener("click", () => {
      document.execCommand(btn.dataset.command, false, null);
      el.messageInput.focus();
      updateEmptyState();
      updateToolbarActiveStates();
    });
  });

  document.addEventListener("selectionchange", () => {
    if (document.activeElement === el.messageInput) updateToolbarActiveStates();
  });

  el.messageInput.addEventListener("input", updateEmptyState);

  el.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      // Inside an active bullet/numbered list, let Enter behave
      // natively (new list item, or exit the list on an empty one) --
      // only intercept it for "send" OUTSIDE a list. Without this check
      // there'd be no way to add a second bullet without the first
      // Enter immediately sending the message.
      if (document.queryCommandState("insertUnorderedList") || document.queryCommandState("insertOrderedList")) {
        return;
      }
      event.preventDefault();
      el.composerForm.requestSubmit();
      return;
    }
    if (event.key === "Enter" && event.shiftKey) {
      // Force a soft line break (<br>) rather than whatever block-
      // splitting behavior (a new <div>/<p>) some browsers default to
      // for a bare Enter in a contenteditable -- keeps the editor's own
      // DOM shape predictable for richTextToMarkdown below regardless of
      // browser.
      event.preventDefault();
      document.execCommand("insertLineBreak");
      return;
    }
    const meta = event.ctrlKey || event.metaKey;
    if (meta && event.key.toLowerCase() === "b") {
      event.preventDefault();
      document.execCommand("bold");
      updateToolbarActiveStates();
    } else if (meta && event.key.toLowerCase() === "i") {
      event.preventDefault();
      document.execCommand("italic");
      updateToolbarActiveStates();
    }
  });

  // Converts the composer's rich-text DOM into a markdown-equivalent
  // string -- sent to the backend as `query` AND re-rendered for the
  // user's own message bubble via the same renderMarkdownLite used for
  // agent replies, so "what you typed" and "what's displayed" are driven
  // by one formatting pipeline rather than two.
  function richTextToMarkdown(root) {
    function escapeLiteral(text) {
      // So a literal "*"/"_"/"`"/"\" the user actually typed (not
      // produced via the bold/italic toolbar) round-trips as that exact
      // character through renderMarkdownLite instead of being misread
      // as formatting syntax -- see renderInline's matching unescape step.
      return text.replace(/([*_`\\])/g, "\\$1");
    }

    // Flattened first into {text, bold, italic} / {break: true} tokens,
    // THEN merged and wrapped -- NOT wrapped per DOM text node directly.
    // Confirmed directly or wrapping per text node breaks the moment the
    // browser's own contenteditable output splits one visually-uniform
    // bold/italic span across multiple text nodes/elements (observed: a
    // bold toggle immediately before a line break left a stray single-
    // space <strong> nested inside an <em>; wrapping that AS ITS OWN
    // "**...**" produced "*emphasis**\n**rest*" -- invalid, unparseable
    // markdown at the boundary where two unrelated "**" pairs collide).
    const tokens = [];

    function pushText(text, marks) {
      if (!text) return;
      // execCommand("insertLineBreak") inserts a literal "\n" CHARACTER
      // into the text node in some browsers (confirmed directly) rather
      // than an actual <br> element -- split on it into its own break
      // token, same as a real <br> gets below, instead of silently
      // embedding a raw newline inside a bold/italic run (which would
      // otherwise desync from renderInline's own italic regex, which
      // deliberately stops at a newline and would leave the run's
      // closing "*" dangling on the wrong side of it).
      const parts = text.split("\n");
      parts.forEach((part, i) => {
        if (part) tokens.push({ text: escapeLiteral(part), bold: !!marks.bold, italic: !!marks.italic });
        // hard: true -- a genuine user-typed line break (Shift+Enter),
        // rendered as a visible <br> on round-trip. Distinct from the
        // structural (list-item/paragraph) breaks below, which are
        // already their own separate lines by construction and don't
        // need the hard-break marker to render correctly.
        if (i < parts.length - 1) tokens.push({ brk: true, hard: true });
      });
    }

    function walk(node, marks) {
      if (node.nodeType === Node.TEXT_NODE) {
        pushText(node.textContent, marks);
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;

      const tag = node.tagName.toLowerCase();
      if (tag === "br") {
        tokens.push({ brk: true, hard: true });
        return;
      }
      if (tag === "li") {
        tokens.push({ text: "- ", bold: false, italic: false });
        Array.from(node.childNodes).forEach((c) => walk(c, marks));
        tokens.push({ brk: true });
        return;
      }
      if (tag === "ul" || tag === "ol") {
        tokens.push({ brk: true });
        Array.from(node.childNodes).forEach((c) => walk(c, marks));
        return;
      }

      const nextMarks = { ...marks };
      if (tag === "b" || tag === "strong") nextMarks.bold = true;
      if (tag === "i" || tag === "em") nextMarks.italic = true;

      Array.from(node.childNodes).forEach((c) => walk(c, nextMarks));

      // Some browsers wrap each line of a contenteditable in its own
      // <div>/<p> on Enter (rather than using a plain text node + <br>)
      // -- treated as a hard break, same as the explicit Shift+Enter
      // handling in the keydown listener above produces.
      if (tag === "div" || tag === "p") tokens.push({ brk: true, hard: true });
    }

    Array.from(root.childNodes).forEach((c) => walk(c, {}));

    // Merge adjacent text tokens that share the EXACT same bold/italic
    // state into one run before wrapping, so a visually-uniform span
    // that happened to arrive as several DOM text nodes still gets wrapped
    // in exactly one "**...**"/"*...*" pair, not one per fragment.
    const merged = [];
    for (const token of tokens) {
      const last = merged[merged.length - 1];
      if (!token.brk && last && !last.brk && last.bold === token.bold && last.italic === token.italic) {
        last.text += token.text;
      } else {
        merged.push({ ...token });
      }
    }

    const raw = merged
      .map((token) => {
        // Two trailing spaces before the newline is the standard
        // markdown "hard break" marker -- renderMarkdownLite's own
        // paragraph-joining step (see its own comment) renders a line
        // ending this way as an actual <br> instead of collapsing it
        // into the flowing paragraph text the way an ordinary soft-
        // wrapped line is. Without this, a user's own Shift+Enter would
        // round-trip as an invisible space instead of a line break.
        // Structural breaks (list items, paragraphs) skip the marker --
        // they're already their own line by construction, and the extra
        // trailing spaces would otherwise show up as literal characters
        // at the end of e.g. a list item's own text.
        if (token.brk) return token.hard ? "  \n" : "\n";
        if (token.bold && token.italic) return `***${token.text}***`;
        if (token.bold) return `**${token.text}**`;
        if (token.italic) return `*${token.text}*`;
        return token.text;
      })
      .join("");

    // A div-per-line structure can otherwise leave a ragged trail of
    // blank lines between paragraphs -- collapse 3+ consecutive newlines
    // down to one blank line (2 newlines), matching normal markdown
    // paragraph spacing.
    return raw.replace(/\n{3,}/g, "\n\n").trim();
  }

  el.composerForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const markdown = richTextToMarkdown(el.messageInput);
    if (!markdown) return;
    el.messageInput.innerHTML = "";
    updateEmptyState();
    sendMessage(markdown);
  });

  // ---------------------------------------------------------------
  // Save chat
  // ---------------------------------------------------------------
  function buildTranscriptMarkdown() {
    const lines = [
      "# Process Architect — Chat Transcript",
      "",
      `_Exported ${new Date().toLocaleString()}_`,
      "",
    ];
    const roleLabel = { user: "You", agent: "Process Architect", error: "Error" };
    for (const entry of state.transcript) {
      lines.push(`### ${roleLabel[entry.role] || entry.role} — ${formatTime(entry.timestamp)}`, "", entry.text, "");
    }
    return lines.join("\n");
  }

  async function saveChat() {
    if (state.transcript.length === 0) {
      toast("Nothing to save yet.");
      return;
    }

    const markdown = buildTranscriptMarkdown();
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    const filename = `process-architect-chat-${stamp}.md`;

    if (window.showSaveFilePicker) {
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: filename,
          types: [{ description: "Markdown", accept: { "text/markdown": [".md"] } }],
        });
        const writable = await handle.createWritable();
        await writable.write(markdown);
        await writable.close();
        toast("Chat saved.");
        return;
      } catch (err) {
        if (err && err.name === "AbortError") return; // user cancelled the dialog
        // Fall through to the download fallback below (e.g. a security
        // policy blocked the picker) rather than leaving the user with
        // no way to save at all.
      }
    }

    // Fallback for browsers without the File System Access API (Firefox,
    // Safari as of this writing) -- triggers a normal browser download
    // rather than a true "Save As" dialog, but gets the file saved either way.
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    toast("Chat downloaded.");
  }

  el.saveChatBtn.addEventListener("click", saveChat);

  // ---------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------
  function init() {
    applyTheme();
    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
        if (!state.theme) applyTheme();
      });
    }

    el.baseUrlInput.value = state.baseUrl || PRESETS.adk.baseUrl;
    el.apiKeyInput.value = state.apiKey || "";
    setPreset(state.preset && (PRESETS[state.preset] || state.preset === "custom") ? state.preset : "adk");
    if (state.sessionId) {
      setSessionId(state.sessionId);
    }

    setStatus("unknown", "Not connected");
    renderNetwork();
    el.messageInput.focus();
  }

  init();
})();
