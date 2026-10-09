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
  // Token Usage tab -- pricing reference table, USD per 1,000,000 tokens,
  // used ONLY to estimate cost from whatever model the connected backend
  // itself reports (via GET /status for the ADK original's one static
  // model, or per-turn via usage.model for neuro-san) -- there is no
  // manual model picker; the backend's own config is the source of truth
  // for which model is actually running, so this is purely a lookup, not
  // a user-facing selection. Sourced from each provider's own public
  // pricing page (checked 2026-10; see the web client README's "Token
  // Usage tab" section for links) -- NOT fabricated. Promotional/
  // introductory rates (e.g. Gemini 3.x Flash's discounted rate through
  // end of 2026) are the CURRENT real price, not a forecast of what a
  // turn will cost after a price change takes effect -- revisit this
  // table if prices move. `aliases` are other raw model-name strings a
  // backend might report (e.g. ADK's MODEL property can include a
  // "provider/" prefix) that should resolve to the same entry.
  // ---------------------------------------------------------------
  const MODEL_PRICING = [
    { id: "gemini-3.8-flash", input: 0.75, output: 3.75,
      aliases: ["gemini-3.7-flash", "gemini-3.6-flash"] },
    { id: "gemini-3-flash", input: 0.75, output: 3.75 }, // est., same tier as 3.6-3.8
    { id: "gemini-2.5-flash", input: 0.30, output: 2.50 },
    { id: "gemini-2.5-pro", input: 1.25, output: 10.00 }, // <=200k ctx
    { id: "claude-sonnet-5", input: 2.00, output: 10.00,
      aliases: ["anthropic/claude-sonnet-5"] },
    { id: "claude-opus-4-8", input: 5.00, output: 25.00 },
    { id: "claude-haiku-4-5", input: 1.00, output: 5.00 },
    { id: "gpt-4o", input: 2.50, output: 10.00,
      aliases: ["openai/gpt-4o"] },
    { id: "bedrock-claude-sonnet-4-5", input: 3.00, output: 15.00,
      aliases: ["bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"] },
  ];

  function findPricingByModelName(modelName) {
    if (!modelName) return null;
    const lower = modelName.toLowerCase();

    // Exact match first (id or alias).
    const exact = MODEL_PRICING.find((p) => p.id.toLowerCase() === lower
      || (p.aliases || []).some((a) => a.toLowerCase() === lower));
    if (exact) return exact;

    // Fall back to a prefix match either direction -- a real deployment
    // can report a more specific/versioned model string than this table
    // tracks (e.g. "gemini-3.8-flash-002" or "...-preview-09-2026") and
    // would otherwise silently show no cost estimate at all despite a
    // close match clearly existing. Longest matching prefix wins, so a
    // more specific table entry (if one's ever added) beats a shorter,
    // more generic one.
    let best = null;
    let bestLen = 0;
    MODEL_PRICING.forEach((p) => {
      [p.id, ...(p.aliases || [])].forEach((key) => {
        const keyLower = key.toLowerCase();
        if ((lower.startsWith(keyLower) || keyLower.startsWith(lower)) && keyLower.length > bestLen) {
          best = p;
          bestLen = keyLower.length;
        }
      });
    });
    return best;
  }

  function currentPricingRates() {
    const entry = findPricingByModelName(state.usage.autoDetectedModel);
    return entry ? { input: entry.input, output: entry.output } : null;
  }

  // Fixed thresholds (total tokens for ONE turn), not relative to the
  // session's own observed range -- a "red" turn should mean roughly the
  // same thing from one conversation to the next, not be graded on a
  // curve against whatever else happened to run in this session. Tune
  // here if these don't match your own usage patterns.
  const USAGE_THRESHOLDS = { green: 2000, amber: 8000 };

  function usageLevel(totalTokens) {
    if (totalTokens <= USAGE_THRESHOLDS.green) return "green";
    if (totalTokens <= USAGE_THRESHOLDS.amber) return "amber";
    return "red";
  }

  // ---------------------------------------------------------------
  // Element lookups
  // ---------------------------------------------------------------
  const el = {
    app: document.getElementById("app"),
    sidebar: document.getElementById("sidebar"),
    sidebarScrim: document.getElementById("sidebarScrim"),
    sidebarOpenBtn: document.getElementById("sidebarOpenBtn"),
    sidebarCloseBtn: document.getElementById("sidebarCloseBtn"),

    // Scoped to the sidebar -- the Process/Design tab's artifact toggle
    // (below) reuses the same ".preset-btn" class purely for its visual
    // style, via a different selector (".artifacts-toggle .preset-btn"),
    // and must NOT be picked up here or setPreset's own active-state
    // bookkeeping would stomp on it (and vice versa).
    presetBtns: Array.from(document.querySelectorAll("#sidebar .preset-btn")),
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
    stopBtn: document.getElementById("stopBtn"),
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

    artifactsTabPanel: document.getElementById("artifactsTabPanel"),
    artifactToggleBtns: Array.from(document.querySelectorAll(".artifacts-toggle .preset-btn")),
    artifactRefreshBtn: document.getElementById("artifactRefreshBtn"),
    artifactsStatus: document.getElementById("artifactsStatus"),
    artifactsEmpty: document.getElementById("artifactsEmpty"),
    artifactTree: document.getElementById("artifactTree"),
    artifactDetail: document.getElementById("artifactDetail"),
    artifactDetailTitle: document.getElementById("artifactDetailTitle"),
    artifactDetailPath: document.getElementById("artifactDetailPath"),
    artifactDetailContext: document.getElementById("artifactDetailContext"),
    artifactDetailList: document.getElementById("artifactDetailList"),
    artifactDetailCloseBtn: document.getElementById("artifactDetailCloseBtn"),

    usageTabPanel: document.getElementById("usageTabPanel"),
    usageModelValue: document.getElementById("usageModelValue"),
    usageResetBtn: document.getElementById("usageResetBtn"),
    usageStatTurns: document.getElementById("usageStatTurns"),
    usageStatTotalTokens: document.getElementById("usageStatTotalTokens"),
    usageStatLastTokens: document.getElementById("usageStatLastTokens"),
    usageStatCost: document.getElementById("usageStatCost"),
    usageCanvasWrap: document.getElementById("usageCanvasWrap"),
    usageEmpty: document.getElementById("usageEmpty"),
    usageSvg: document.getElementById("usageSvg"),
    usageZoomInBtn: document.getElementById("usageZoomInBtn"),
    usageZoomOutBtn: document.getElementById("usageZoomOutBtn"),
    usageResetViewBtn: document.getElementById("usageResetViewBtn"),
    usageDetail: document.getElementById("usageDetail"),
    usageDetailTitle: document.getElementById("usageDetailTitle"),
    usageDetailPath: document.getElementById("usageDetailPath"),
    usageDetailContext: document.getElementById("usageDetailContext"),
    usageDetailList: document.getElementById("usageDetailList"),
    usageDetailCloseBtn: document.getElementById("usageDetailCloseBtn"),

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

  // Sent-message history for the composer's Up/Down recall (see
  // recallHistory below) -- bash-style, oldest first, newest last. Runtime
  // only, like the transcript above, and deliberately NOT cleared by "+
  // New chat" (unlike transcript/network/usage) -- what you typed is still
  // useful to recall even after starting a fresh chat to try it again.
  state.commandHistory = [];

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

  // The Process/Design tab's data -- a hierarchical view of whichever
  // artifact (output/process_data.json or output/design_data.json) the
  // connected backend's GET /artifacts/<name> currently serves. Runtime
  // only, same as network/transcript above -- re-fetched fresh each time
  // the tab is opened or the artifact changes, not persisted across reloads.
  //   expandedPaths: Set of JSON-path strings ("$", "$.steps[2]", ...)
  //     currently expanded in the tree, so re-rendering after a toggle (or
  //     after a fresh load) preserves what the user had open.
  state.dataExplorer = {
    artifact: "process",
    raw: null,
    expandedPaths: new Set(["$"]),
    selectedPath: null,
    loading: false,
    error: null,
  };

  // The Token Usage tab's data -- one entry per completed turn that
  // reported a "usage" field (see recordUsageTurn, called from
  // sendMessage's "done" handling). Runtime only, like transcript/network
  // above -- cleared by "+ New chat", not persisted across reloads.
  // autoDetectedModel is whatever model name the connected backend itself
  // last reported (via GET /status or a turn's own usage.model) -- there
  // is no manual override; the backend's own config is the source of
  // truth for which model actually ran.
  state.usage = {
    turns: [],
    selectedTurnIndex: null,
    autoDetectedModel: null,
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
        // The ADK backend reports its one statically-configured model here
        // (see GET /status's own docstring); neuro-san does not, since it
        // can genuinely invoke different models per turn -- that case is
        // instead picked up per-turn from usage.model (see recordUsageTurn).
        const body = await res.json().catch(() => ({}));
        if (body && body.model) setDetectedModel(body.model);
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
    resetUsage();
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
    el.artifactsTabPanel.hidden = name !== "artifacts";
    el.usageTabPanel.hidden = name !== "usage";

    if (name !== "network") closeNodeDetail();
    if (name !== "artifacts") closeArtifactDetail();
    if (name !== "usage") closeUsageDetail();

    if (name === "network") {
      // The SVG's viewBox is sized from el.networkCanvasWrap's own
      // clientWidth/clientHeight (see computeNetworkLayout) -- while the
      // panel was hidden that was 0, so the layout has to be redone now
      // that the panel actually has real dimensions to measure.
      renderNetwork();
    } else if (name === "artifacts") {
      // First time this tab is opened (nothing loaded, no error on
      // record yet) -- auto-load the currently selected artifact, same
      // as the Agent Network tab doesn't need an explicit "load" step.
      if (state.dataExplorer.raw === null && !state.dataExplorer.loading && !state.dataExplorer.error) {
        loadArtifact(state.dataExplorer.artifact);
      }
    } else if (name === "usage") {
      // Same reason as the network tab above -- the SVG was sized 0x0
      // while this panel was hidden.
      renderUsageChart();
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
  // Data explorer -- hierarchical viewer for the Process/Design tab's
  // GET /artifacts/<name> ("process" or "design"), a read-only snapshot of
  // this project's own output/process_data.json / output/design_data.json
  // on whichever backend is connected. Rendered as an expandable tree
  // (root top-left, children expanding down-and-right) built via
  // document.createElement/.textContent -- NOT innerHTML string
  // concatenation -- since the JSON content being displayed is arbitrary
  // backend output and could contain HTML-like strings.
  // ---------------------------------------------------------------
  function isExpandable(value) {
    if (Array.isArray(value)) return value.length > 0;
    return value !== null && typeof value === "object" && Object.keys(value).length > 0;
  }

  function describeType(value) {
    if (value === null) return "null";
    if (Array.isArray(value)) return "array";
    return typeof value;
  }

  // Short, single-line preview for a tree row or a detail-panel field --
  // NOT a recursive dump of a container's contents (that's what expanding
  // the row itself, or clicking into a child, is for).
  function valuePreview(value, max) {
    if (value === null) return "null";
    if (Array.isArray(value)) return `Array (${value.length} item${value.length === 1 ? "" : "s"})`;
    if (typeof value === "object") {
      const n = Object.keys(value).length;
      return `Object (${n} field${n === 1 ? "" : "s"})`;
    }
    if (typeof value === "string") {
      const truncated = value.length > max ? `${value.slice(0, max - 1)}…` : value;
      return JSON.stringify(truncated);
    }
    return String(value);
  }

  async function loadArtifact(name) {
    const baseUrl = currentBaseUrl();
    if (!baseUrl) {
      toast("Set a Base URL and click Connect first.");
      return;
    }
    state.dataExplorer.loading = true;
    state.dataExplorer.error = null;
    // A fresh load starts over -- an expand/selection state (and an open
    // detail panel) built against a PREVIOUS artifact's shape (e.g.
    // switching from Process to Design, or re-running the pipeline) has no
    // guaranteed correspondence to the new data's paths. Cleared up front,
    // not just on success below, so a load that ends in an error doesn't
    // leave the drawer open showing the stale, now-unrelated artifact's
    // node.
    state.dataExplorer.expandedPaths = new Set(["$"]);
    state.dataExplorer.selectedPath = null;
    closeArtifactDetail();
    renderArtifactsPanel();
    try {
      const res = await fetch(`${baseUrl}/artifacts/${name}`, {
        method: "GET",
        headers: { ...authHeaders() },
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.error || `Request failed (${res.status}).`);
      }
      state.dataExplorer.raw = body.data;
    } catch (err) {
      state.dataExplorer.raw = null;
      state.dataExplorer.error = (err && err.message) || String(err);
    } finally {
      state.dataExplorer.loading = false;
      renderArtifactsPanel();
    }
  }

  function renderArtifactsPanel() {
    const { loading, error, raw, artifact } = state.dataExplorer;

    if (loading) {
      el.artifactsStatus.textContent = "Loading…";
    } else if (error) {
      el.artifactsStatus.textContent = "Error";
    } else if (raw !== null) {
      const count = Array.isArray(raw) ? raw.length : (raw && typeof raw === "object" ? Object.keys(raw).length : 0);
      const noun = Array.isArray(raw) ? "item" : "field";
      el.artifactsStatus.textContent = `Loaded ${count} top-level ${noun}${count === 1 ? "" : "s"}`;
    } else {
      el.artifactsStatus.textContent = "Not loaded";
    }

    const hasData = raw !== null && !loading && !error;
    el.artifactTree.hidden = !hasData;
    el.artifactsEmpty.style.display = hasData ? "none" : "";

    if (!hasData) {
      const heading = el.artifactsEmpty.querySelector("h2");
      const body = el.artifactsEmpty.querySelector("p");
      if (loading) {
        heading.textContent = "Loading…";
        body.textContent = `Fetching the ${artifact} pipeline's current output from the connected backend…`;
      } else if (error) {
        heading.textContent = "Couldn't load this artifact";
        body.textContent = error;
      } else {
        heading.textContent = "No data loaded";
        body.textContent = "Pick Process or Design above, then click the refresh icon to load " +
          "that pipeline's current output/*_data.json from the connected backend.";
      }
      return;
    }

    renderArtifactTree();
  }

  function renderArtifactTree() {
    el.artifactTree.innerHTML = "";
    const { raw, artifact } = state.dataExplorer;
    if (raw === null) return;
    const rootLabel = artifact === "design" ? "design" : "process";
    buildTreeRow(rootLabel, raw, "$", 0, el.artifactTree);
  }

  function toggleTreePath(path) {
    const expanded = state.dataExplorer.expandedPaths;
    if (expanded.has(path)) {
      expanded.delete(path);
    } else {
      expanded.add(path);
    }
    renderArtifactTree();
  }

  function buildTreeRow(key, value, path, depth, container) {
    const row = document.createElement("div");
    row.className = "tree-row";
    row.style.paddingLeft = `${depth * 18 + 8}px`;
    if (path === state.dataExplorer.selectedPath) row.classList.add("selected");

    const expandable = isExpandable(value);
    const expanded = expandable && state.dataExplorer.expandedPaths.has(path);

    const toggle = document.createElement("span");
    toggle.className = "tree-toggle" + (expandable ? "" : " tree-toggle-empty") + (expanded ? " expanded" : "");
    if (expandable) {
      toggle.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleTreePath(path);
      });
    }
    row.appendChild(toggle);

    const keySpan = document.createElement("span");
    keySpan.className = "tree-key";
    keySpan.textContent = key;
    row.appendChild(keySpan);

    const sep = document.createElement("span");
    sep.className = "tree-sep";
    sep.textContent = ":";
    row.appendChild(sep);

    const valueSpan = document.createElement("span");
    valueSpan.className = "tree-value";
    valueSpan.textContent = valuePreview(value, 70);
    row.appendChild(valueSpan);

    row.addEventListener("click", () => showArtifactDetail(path, key, value));
    container.appendChild(row);

    if (expanded) {
      const children = document.createElement("div");
      if (Array.isArray(value)) {
        value.forEach((item, index) => {
          buildTreeRow(`[${index}]`, item, `${path}[${index}]`, depth + 1, children);
        });
      } else {
        Object.keys(value).forEach((childKey) => {
          buildTreeRow(childKey, value[childKey], `${path}.${childKey}`, depth + 1, children);
        });
      }
      container.appendChild(children);
    }
  }

  // ---------------------------------------------------------------
  // Data explorer -- node detail panel. Shows the clicked node's OWN
  // direct properties (its immediate fields/items with their type and a
  // short preview), not a recursive dump of everything below it -- that's
  // what expanding/clicking into a child row is for.
  // ---------------------------------------------------------------
  function appendArtifactDetailRow(label, valueText) {
    const row = document.createElement("div");
    row.className = "node-detail-entry";

    const meta = document.createElement("div");
    meta.className = "node-detail-entry-meta";
    const labelSpan = document.createElement("span");
    labelSpan.textContent = label;
    meta.appendChild(labelSpan);
    row.appendChild(meta);

    const text = document.createElement("div");
    text.className = "node-detail-entry-text";
    text.textContent = valueText;
    row.appendChild(text);

    el.artifactDetailList.appendChild(row);
  }

  function showArtifactDetail(path, key, value) {
    state.dataExplorer.selectedPath = path;
    renderArtifactTree(); // picks up the .selected highlight on the clicked row

    el.artifactDetailTitle.textContent = key;
    el.artifactDetailPath.textContent = path;

    el.artifactDetailContext.innerHTML = "";
    const typeLine = document.createElement("div");
    typeLine.textContent = `Type: ${describeType(value)}`;
    el.artifactDetailContext.appendChild(typeLine);

    el.artifactDetailList.innerHTML = "";

    if (value === null || typeof value !== "object") {
      appendArtifactDetailRow("Value", value === null ? "null" : String(value));
    } else if (Array.isArray(value)) {
      if (value.length === 0) {
        appendArtifactDetailRow("", "(empty array)");
      } else {
        value.forEach((item, index) => appendArtifactDetailRow(`[${index}]`, valuePreview(item, 90)));
      }
    } else {
      const keys = Object.keys(value);
      if (keys.length === 0) {
        appendArtifactDetailRow("", "(empty object)");
      } else {
        keys.forEach((childKey) => appendArtifactDetailRow(childKey, valuePreview(value[childKey], 90)));
      }
    }

    el.artifactDetail.classList.add("open");
  }

  function closeArtifactDetail() {
    el.artifactDetail.classList.remove("open");
    if (state.dataExplorer.selectedPath) {
      state.dataExplorer.selectedPath = null;
      renderArtifactTree();
    }
  }

  el.artifactDetailCloseBtn.addEventListener("click", closeArtifactDetail);

  el.artifactToggleBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.artifact;
      if (name === state.dataExplorer.artifact) return; // already the active one
      state.dataExplorer.artifact = name;
      el.artifactToggleBtns.forEach((b) => b.classList.toggle("active", b.dataset.artifact === name));
      loadArtifact(name);
    });
  });

  el.artifactRefreshBtn.addEventListener("click", () => loadArtifact(state.dataExplorer.artifact));

  // ---------------------------------------------------------------
  // Token Usage tab -- one bar per completed turn that reported a "usage"
  // field (see recordUsageTurn, called from sendMessage's "done" handling
  // for both the streaming and non-streaming-fallback paths). Bar height
  // is that turn's own total_tokens (so the chart genuinely rises and
  // falls turn to turn, not a monotonic running total), filled a solid
  // green/amber/red by usageLevel's fixed thresholds above. A thin dashed
  // trend line connects each bar's peak. Cost is estimated client-side
  // from the MODEL_PRICING lookup above, keyed off whichever model the
  // connected backend itself reports (see setDetectedModel) -- there is
  // no manual model picker, since the backend's own config is the source
  // of truth for which model actually ran.
  // ---------------------------------------------------------------
  function formatTokens(n) {
    return Number(n || 0).toLocaleString();
  }

  function formatCost(dollars) {
    if (dollars === null || dollars === undefined) return "—";
    if (dollars === 0) return "$0.00";
    if (dollars < 0.01) return "<$0.01";
    return `$${dollars.toFixed(dollars < 1 ? 4 : 2)}`;
  }

  function estimateTurnCost(turn) {
    const rates = currentPricingRates();
    if (!rates) return null;
    return (turn.promptTokens / 1e6) * rates.input + (turn.completionTokens / 1e6) * rates.output;
  }

  function estimateSessionCost() {
    const rates = currentPricingRates();
    if (!rates) return null;
    return state.usage.turns.reduce((sum, t) => sum + (estimateTurnCost(t) || 0), 0);
  }

  // Records whatever model name the connected backend itself just
  // reported (via GET /status for the ADK original's one static model, or
  // a turn's own usage.model for neuro-san's real per-turn model) and
  // refreshes anything depending on it -- the displayed model name, the
  // cost estimate, and an already-open detail panel's cost figure. No
  // user override: the backend's own config is the source of truth for
  // which model actually ran, so this is a readout, not a picker.
  function setDetectedModel(reportedModel) {
    if (!reportedModel || reportedModel === state.usage.autoDetectedModel) return;
    state.usage.autoDetectedModel = reportedModel;
    el.usageModelValue.textContent = findPricingByModelName(reportedModel)
      ? reportedModel
      : `${reportedModel} (no pricing data)`;
    renderUsageStats();
    refreshOpenUsageDetail();
  }

  function recordUsageTurn(usage, query) {
    if (!usage) return; // older backend, or a turn that made no LLM calls
    state.usage.turns.push({
      turnIndex: state.usage.turns.length + 1,
      timestamp: new Date(),
      promptTokens: usage.prompt_tokens || 0,
      completionTokens: usage.completion_tokens || 0,
      totalTokens: usage.total_tokens || 0,
      reportedModel: usage.model || null,
      query: query || "",
    });
    setDetectedModel(usage.model);
    renderUsageChart();
  }

  function renderUsageStats() {
    const turns = state.usage.turns;
    el.usageStatTurns.textContent = String(turns.length);
    const totalTokens = turns.reduce((sum, t) => sum + t.totalTokens, 0);
    el.usageStatTotalTokens.textContent = formatTokens(totalTokens);
    const last = turns[turns.length - 1];
    el.usageStatLastTokens.textContent = last ? formatTokens(last.totalTokens) : "—";

    if (turns.length === 0) {
      el.usageStatCost.textContent = "—";
      el.usageStatCost.title = "";
    } else if (!currentPricingRates()) {
      // No pricing table entry matches the detected model -- say so
      // explicitly rather than showing a bare "—" that looks identical
      // to "nothing happened yet".
      el.usageStatCost.textContent = "—";
      el.usageStatCost.title = state.usage.autoDetectedModel
        ? `No pricing data for "${state.usage.autoDetectedModel}"`
        : "No model detected yet";
    } else {
      el.usageStatCost.textContent = formatCost(estimateSessionCost());
      el.usageStatCost.title = "";
    }
  }

  const USAGE_SVG_NS = "http://www.w3.org/2000/svg";

  // Fixed per-bar footprint (not stretched to fill the canvas width the
  // way an earlier version of this did) -- bars pack together starting at
  // the left margin and the content's own width simply grows as more
  // turns arrive, same philosophy as computeNetworkLayout's "natural
  // size, let zoom/pan handle fitting" above. Content HEIGHT stays fixed
  // (this is a left-to-right timeline, not something that grows
  // vertically) so only width needs to accommodate turn count.
  const USAGE_BAR_WIDTH = 14;
  const USAGE_BAR_GAP = 6;
  const USAGE_PLOT_HEIGHT = 220;
  const USAGE_MARGIN = { left: 54, right: 16, top: 16, bottom: 8 };

  function computeUsageLayout() {
    const turns = state.usage.turns;
    if (turns.length === 0) return { bars: [], width: 0, height: 0, scaleMax: 1 };

    const maxValue = Math.max(...turns.map((t) => t.totalTokens), 1);
    // Headroom so the tallest bar doesn't touch the very top edge.
    const scaleMax = maxValue * 1.15;

    const width = USAGE_MARGIN.left + USAGE_MARGIN.right
      + turns.length * (USAGE_BAR_WIDTH + USAGE_BAR_GAP) - USAGE_BAR_GAP;
    const height = USAGE_MARGIN.top + USAGE_PLOT_HEIGHT + USAGE_MARGIN.bottom;

    const bars = turns.map((turn, index) => {
      const x = USAGE_MARGIN.left + index * (USAGE_BAR_WIDTH + USAGE_BAR_GAP);
      const barHeight = Math.max(2, (turn.totalTokens / scaleMax) * USAGE_PLOT_HEIGHT);
      const y = USAGE_MARGIN.top + USAGE_PLOT_HEIGHT - barHeight;
      return { turn, x, y, height: barHeight };
    });

    return { bars, width, height, scaleMax };
  }

  function renderUsageChart() {
    renderUsageStats();

    const turns = state.usage.turns;
    if (turns.length === 0) {
      el.usageEmpty.style.display = "";
      el.usageSvg.setAttribute("hidden", "");
      el.usageSvg.innerHTML = "";
      return;
    }
    el.usageEmpty.style.display = "none";
    el.usageSvg.removeAttribute("hidden");

    const { bars, width, height, scaleMax } = computeUsageLayout();

    // The SVG's own viewBox is pinned 1:1 to the canvas wrap's actual
    // pixel size -- NOT the content's size -- exactly like the Agent
    // Network tab, so the zoom/pan transform below (applied to
    // #usageViewport, not the viewBox itself) works in plain screen-
    // pixel-equivalent units instead of juggling two coordinate systems.
    const wrapWidth = el.usageCanvasWrap.clientWidth || 600;
    const wrapHeight = el.usageCanvasWrap.clientHeight || 300;
    el.usageSvg.setAttribute("viewBox", `0 0 ${wrapWidth} ${wrapHeight}`);
    el.usageSvg.innerHTML = "";

    const viewport = document.createElementNS(USAGE_SVG_NS, "g");
    viewport.setAttribute("id", "usageViewport");

    // Gridlines + axis labels at 0/50/100% of scaleMax -- drawn the full
    // CONTENT width (not just the visible canvas) so they still line up
    // with the bars once panned/zoomed.
    [0, 0.5, 1].forEach((frac) => {
      const y = USAGE_MARGIN.top + USAGE_PLOT_HEIGHT - frac * USAGE_PLOT_HEIGHT;
      const line = document.createElementNS(USAGE_SVG_NS, "line");
      line.setAttribute("x1", String(USAGE_MARGIN.left));
      line.setAttribute("x2", String(Math.max(width - USAGE_MARGIN.right, USAGE_MARGIN.left)));
      line.setAttribute("y1", String(y));
      line.setAttribute("y2", String(y));
      line.setAttribute("class", "usage-gridline");
      viewport.appendChild(line);

      const label = document.createElementNS(USAGE_SVG_NS, "text");
      label.setAttribute("x", String(USAGE_MARGIN.left - 8));
      label.setAttribute("y", String(y + 3));
      label.setAttribute("text-anchor", "end");
      label.setAttribute("class", "usage-axis-label");
      label.textContent = formatTokens(Math.round(frac * scaleMax));
      viewport.appendChild(label);
    });

    // Bars, one per turn.
    const trendPoints = [];
    bars.forEach(({ turn, x, y, height: barHeight }) => {
      trendPoints.push(`${x + USAGE_BAR_WIDTH / 2},${y}`);

      const level = usageLevel(turn.totalTokens);
      const g = document.createElementNS(USAGE_SVG_NS, "g");
      g.setAttribute("class", `usage-bar usage-bar-${level}${turn.turnIndex === state.usage.selectedTurnIndex ? " usage-bar-selected" : ""}`);
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      g.setAttribute("aria-label", `Turn ${turn.turnIndex}: ${turn.totalTokens} tokens`);
      g.addEventListener("click", () => showUsageDetail(turn.turnIndex));
      g.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          showUsageDetail(turn.turnIndex);
        }
      });

      const rect = document.createElementNS(USAGE_SVG_NS, "rect");
      rect.setAttribute("class", "usage-bar-fill");
      rect.setAttribute("x", String(x));
      rect.setAttribute("y", String(y));
      rect.setAttribute("width", String(USAGE_BAR_WIDTH));
      rect.setAttribute("height", String(barHeight));
      rect.setAttribute("rx", "2");
      g.appendChild(rect);

      const title = document.createElementNS(USAGE_SVG_NS, "title");
      title.textContent = `Turn ${turn.turnIndex}: ${turn.totalTokens.toLocaleString()} tokens — click for details`;
      g.appendChild(title);

      viewport.appendChild(g);
    });

    // Trend line connecting each bar's peak.
    if (trendPoints.length > 1) {
      const polyline = document.createElementNS(USAGE_SVG_NS, "polyline");
      polyline.setAttribute("points", trendPoints.join(" "));
      polyline.setAttribute("class", "usage-trend-line");
      viewport.appendChild(polyline);
    }

    el.usageSvg.appendChild(viewport);

    if (state.usage.autoFit) {
      computeUsageFitView(width, height, wrapWidth, wrapHeight);
    }
    applyUsageTransform();
  }

  // ---------------------------------------------------------------
  // Zoom / pan -- identical model to the Agent Network tab's (see its own
  // comment above computeFitView/applyNetworkTransform/zoomBy): adjusts
  // state.usage.view (x, y, scale) and re-applies it as a transform on
  // #usageViewport; computeUsageLayout's own bar positions never change.
  // autoFit stays true (recomputing a "fit everything" view on every
  // render, so newly streamed-in turns never end up off-screen) until the
  // user manually zooms or pans, at which point their view is left alone
  // until they click Reset.
  // ---------------------------------------------------------------
  function computeUsageFitView(contentWidth, contentHeight, wrapWidth, wrapHeight) {
    const padding = 24;
    const scale = Math.min(
      1.15, // don't blow a 1-2 turn chart up past a sensible size just because the canvas is big
      Math.max(MIN_SCALE, Math.min(
        (wrapWidth - padding * 2) / contentWidth,
        (wrapHeight - padding * 2) / contentHeight,
      )),
    );
    // Left-justified: anchor the content's own left/top edge inside the
    // padding rather than centering it, so a short chart (few turns)
    // starts flush at the left like a timeline, not floating centered.
    state.usage.view = {
      scale,
      x: padding,
      y: (wrapHeight - contentHeight * scale) / 2,
    };
  }

  function applyUsageTransform() {
    const viewport = document.getElementById("usageViewport");
    if (!viewport) return;
    const { x, y, scale } = state.usage.view;
    viewport.setAttribute("transform", `translate(${x}, ${y}) scale(${scale})`);
  }

  function zoomUsageBy(factor) {
    if (state.usage.turns.length === 0) return;
    const wrapWidth = el.usageCanvasWrap.clientWidth || 600;
    const wrapHeight = el.usageCanvasWrap.clientHeight || 300;
    const view = state.usage.view;
    const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
    // Zoom around the canvas's own center, not the content's origin --
    // keeps whatever's currently in the middle of the view in the middle
    // after zooming, instead of the view drifting toward a corner.
    const cx = wrapWidth / 2;
    const cy = wrapHeight / 2;
    const contentCx = (cx - view.x) / view.scale;
    const contentCy = (cy - view.y) / view.scale;
    state.usage.view = {
      scale: newScale,
      x: cx - contentCx * newScale,
      y: cy - contentCy * newScale,
    };
    state.usage.autoFit = false;
    applyUsageTransform();
  }

  function resetUsageView() {
    state.usage.autoFit = true;
    renderUsageChart();
  }

  el.usageZoomInBtn.addEventListener("click", () => zoomUsageBy(ZOOM_STEP));
  el.usageZoomOutBtn.addEventListener("click", () => zoomUsageBy(1 / ZOOM_STEP));
  el.usageResetViewBtn.addEventListener("click", resetUsageView);

  el.usageCanvasWrap.addEventListener("wheel", (event) => {
    if (state.usage.turns.length === 0) return;
    event.preventDefault();
    zoomUsageBy(event.deltaY < 0 ? 1.12 : 1 / 1.12);
  }, { passive: false });

  let usagePanPointerId = null;
  let usagePanStart = null;

  el.usageSvg.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".usage-bar")) return; // let bar clicks through, not a pan start
    if (state.usage.turns.length === 0) return;
    usagePanPointerId = event.pointerId;
    usagePanStart = { clientX: event.clientX, clientY: event.clientY, viewX: state.usage.view.x, viewY: state.usage.view.y };
    el.usageSvg.setPointerCapture(event.pointerId);
    el.usageSvg.classList.add("panning");
  });
  el.usageSvg.addEventListener("pointermove", (event) => {
    if (usagePanPointerId !== event.pointerId || !usagePanStart) return;
    state.usage.view = {
      ...state.usage.view,
      x: usagePanStart.viewX + (event.clientX - usagePanStart.clientX),
      y: usagePanStart.viewY + (event.clientY - usagePanStart.clientY),
    };
    state.usage.autoFit = false;
    applyUsageTransform();
  });
  function endUsagePan(event) {
    if (usagePanPointerId !== event.pointerId) return;
    usagePanPointerId = null;
    usagePanStart = null;
    el.usageSvg.classList.remove("panning");
  }
  el.usageSvg.addEventListener("pointerup", endUsagePan);
  el.usageSvg.addEventListener("pointercancel", endUsagePan);

  function appendUsageDetailRow(label, valueText) {
    const row = document.createElement("div");
    row.className = "node-detail-entry";
    const meta = document.createElement("div");
    meta.className = "node-detail-entry-meta";
    const labelSpan = document.createElement("span");
    labelSpan.textContent = label;
    meta.appendChild(labelSpan);
    row.appendChild(meta);
    const text = document.createElement("div");
    text.className = "node-detail-entry-text";
    text.textContent = valueText;
    row.appendChild(text);
    el.usageDetailList.appendChild(row);
  }

  // Fills in the detail panel's content for one turn -- separated from
  // showUsageDetail below (which also flips selection state and
  // re-renders the chart) so a pricing/rate change can refresh an
  // ALREADY-OPEN panel's "Estimated cost" line without touching
  // selection or risking a render loop through renderUsageChart.
  function renderUsageDetailContent(turn) {
    el.usageDetailTitle.textContent = `Turn ${turn.turnIndex}`;
    el.usageDetailPath.textContent = formatTime(turn.timestamp);

    el.usageDetailContext.innerHTML = "";
    const modelLine = document.createElement("div");
    modelLine.textContent = `Model: ${turn.reportedModel || "(not reported)"}`;
    el.usageDetailContext.appendChild(modelLine);
    const levelLine = document.createElement("div");
    levelLine.textContent = `Burn level: ${usageLevel(turn.totalTokens)}`;
    el.usageDetailContext.appendChild(levelLine);

    el.usageDetailList.innerHTML = "";
    appendUsageDetailRow("Prompt tokens", formatTokens(turn.promptTokens));
    appendUsageDetailRow("Completion tokens", formatTokens(turn.completionTokens));
    appendUsageDetailRow("Total tokens", formatTokens(turn.totalTokens));
    appendUsageDetailRow("Estimated cost", formatCost(estimateTurnCost(turn)));
    if (turn.query) {
      appendUsageDetailRow("Query", turn.query);
    }
  }

  function showUsageDetail(turnIndex) {
    const turn = state.usage.turns.find((t) => t.turnIndex === turnIndex);
    if (!turn) return;

    state.usage.selectedTurnIndex = turnIndex;
    renderUsageChart(); // picks up the .usage-bar-selected outline
    renderUsageDetailContent(turn);
    el.usageDetail.classList.add("open");
  }

  // Re-renders the OPEN detail panel's cost figure after a pricing/rate
  // change -- without this, switching models or editing a custom rate
  // while a turn's detail panel is open would leave it showing a stale
  // cost computed under the previous rate.
  function refreshOpenUsageDetail() {
    if (state.usage.selectedTurnIndex === null) return;
    const turn = state.usage.turns.find((t) => t.turnIndex === state.usage.selectedTurnIndex);
    if (turn) renderUsageDetailContent(turn);
  }

  function closeUsageDetail() {
    el.usageDetail.classList.remove("open");
    if (state.usage.selectedTurnIndex !== null) {
      state.usage.selectedTurnIndex = null;
      renderUsageChart();
    }
  }

  el.usageDetailCloseBtn.addEventListener("click", closeUsageDetail);

  function resetUsage() {
    state.usage.turns = [];
    state.usage.selectedTurnIndex = null;
    state.usage.view = { x: 0, y: 0, scale: 1 };
    state.usage.autoFit = true;
    closeUsageDetail();
    renderUsageChart();
  }

  el.usageResetBtn.addEventListener("click", () => {
    resetUsage();
    toast("Token usage history cleared.");
  });

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

    // Every "progress" SSE event seen during this turn, in order -- kept
    // around (not just the latest one, which is all progressNote itself
    // shows live) so the turn's full thinking/tool-call trace can still be
    // inspected after the fact, collapsed behind the "Thinking" disclosure
    // built in replaceProgressNoteWithThinking below.
    const thinkingSteps = [];

    // Swaps the live progressNote for a collapsed <details> listing every
    // recorded step -- or just drops it if there's nothing to show (e.g.
    // a backend with no progress events at all, or an error before the
    // first one arrived). Built via document.createElement/.textContent,
    // not innerHTML, since origin/text come from the backend's SSE stream
    // and could in principle contain HTML-like text.
    function replaceProgressNoteWithThinking() {
      if (thinkingSteps.length === 0) {
        progressNote.remove();
        return;
      }

      const details = document.createElement("details");
      details.className = "thinking";

      const summary = document.createElement("summary");
      summary.className = "thinking-summary";
      const toggle = document.createElement("span");
      toggle.className = "thinking-toggle";
      summary.appendChild(toggle);
      const label = document.createElement("span");
      label.className = "thinking-label";
      label.textContent = `Thinking (${thinkingSteps.length} step${thinkingSteps.length === 1 ? "" : "s"})`;
      summary.appendChild(label);
      details.appendChild(summary);

      const list = document.createElement("ol");
      list.className = "thinking-steps";
      thinkingSteps.forEach((step) => {
        const item = document.createElement("li");
        item.className = "thinking-step";
        if (step.origin) {
          const originSpan = document.createElement("span");
          originSpan.className = "thinking-step-origin";
          originSpan.textContent = step.origin;
          item.appendChild(originSpan);
        }
        const textSpan = document.createElement("span");
        textSpan.className = "thinking-step-text";
        textSpan.textContent = step.text || "";
        item.appendChild(textSpan);
        list.appendChild(item);
      });
      details.appendChild(list);

      progressNote.replaceWith(details);
    }

    return {
      row,

      setProgress(origin, text) {
        thinkingSteps.push({ origin, text });
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
        replaceProgressNoteWithThinking();
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
        replaceProgressNoteWithThinking();
        row.classList.add("error");
        const hasText = bubble.textContent && bubble.textContent.trim().length > 0;
        bubble.textContent = hasText ? `${bubble.textContent}\n\n⚠ ${message}` : message;
        scrollToBottom();
      },

      // User-initiated stop (see stopCurrentTurn) -- NOT an error, so
      // deliberately not styled like one: whatever partial answer had
      // streamed in by the time the backend's cancellation took effect
      // is kept and rendered normally, just with a small "Stopped" badge
      // instead of the usual timestamp/copy row.
      showStopped(text) {
        recordTranscript("agent", text || "(stopped before generating a response)");
        replaceProgressNoteWithThinking();
        row.classList.add("stopped");
        bubble.innerHTML = text ? renderMarkdownLite(text) : "";
        if (!text) {
          const empty = document.createElement("p");
          empty.textContent = "(Stopped before generating a response.)";
          bubble.appendChild(empty);
        }
        if (!metaAdded) {
          metaAdded = true;
          const meta = document.createElement("div");
          meta.className = "message-meta";
          const badge = document.createElement("span");
          badge.className = "stopped-badge";
          badge.textContent = "Stopped";
          meta.appendChild(badge);
          const time = document.createElement("span");
          time.textContent = formatTime(new Date());
          meta.appendChild(time);
          col.appendChild(meta);
        }
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
    el.sendBtn.hidden = true;
    el.stopBtn.hidden = false;
    el.stopBtn.disabled = false;
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
          recordUsageTurn(event.usage, text);
        } else if (event.status === "stopped") {
          sawDone = true;
          live.showStopped(event.response || "");
          recordUsageTurn(event.usage, text);
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
            recordUsageTurn(data.usage, text);
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
      el.sendBtn.hidden = false;
      el.stopBtn.hidden = true;
      el.messageInput.contentEditable = "true";
      el.messageInput.focus();
    }
  }

  // Best-effort: asks the backend to cancel session_id's currently
  // in-flight turn (see POST /chat/<session_id>/stop on both backends).
  // Deliberately does NOT abort the client's own fetch()/EventSource read
  // of the stream -- the backend's cancellation produces a proper
  // {"status": "stopped", ...} SSE event back over this SAME still-open
  // connection (see sendMessage's own handling of it above), which is a
  // cleaner outcome than the client unilaterally cutting the connection
  // and risking a race against that event actually arriving.
  async function stopCurrentTurn() {
    el.stopBtn.disabled = true; // avoid a duplicate POST on a double-click
    const baseUrl = currentBaseUrl();
    if (!baseUrl || !state.sessionId) return;
    try {
      await fetch(`${baseUrl}/chat/${encodeURIComponent(state.sessionId)}/stop`, {
        method: "POST",
        headers: { ...authHeaders() },
      });
    } catch {
      // Best-effort -- if this fails the turn just runs to completion
      // normally, same as if Stop had never been clicked.
    }
  }

  el.stopBtn.addEventListener("click", stopCurrentTurn);

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

  // ---------------------------------------------------------------
  // Command history recall -- bash-style Up/Down through state.
  // commandHistory (populated on send, see the submit handler below).
  // historyIndex === state.commandHistory.length means "not currently
  // navigating, viewing the live draft"; draftBeforeHistory stashes
  // whatever was being typed the moment history navigation STARTS, so
  // pressing Down back past the newest entry restores it -- same as a
  // real shell.
  // ---------------------------------------------------------------
  let historyIndex = 0;
  let draftBeforeHistory = "";

  // Up/Down should only hijack the caret when it's genuinely at the
  // top/bottom of a (possibly multi-line) draft -- otherwise pressing Up
  // to move up one line of a longer message would instead yank in a
  // whole different history entry. Checked via the caret's own on-screen
  // position (robust to the composer's DOM shape varying with whatever
  // bold/italic/list formatting is active) rather than DOM structure.
  function caretEdgeRect(atStart) {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return null;
    const range = sel.getRangeAt(0).cloneRange();
    range.collapse(atStart);
    const rects = range.getClientRects();
    const rect = rects.length > 0 ? rects[0] : range.getBoundingClientRect();
    // A collapsed range occasionally reports a degenerate all-zero rect on
    // the very next keydown right after the selection was just set
    // programmatically (confirmed directly: immediately after
    // recallHistory's own setComposerPlainText call, before the browser
    // has fully caught up) -- treated as "unknown" here so the caller's
    // own fallback (assume true, i.e. don't block recall) applies instead
    // of this transient glitch wrongly reporting "not at the edge".
    if (rect.top === 0 && rect.bottom === 0 && rect.left === 0 && rect.right === 0) return null;
    return rect;
  }

  // Compared against the CONTENT's own first/last line rects, not the
  // (padded) #messageInput container box -- comparing against the
  // container left a gap no bigger than the box's own top/bottom padding,
  // which was well within typical sub-pixel/line-height rounding and made
  // the old threshold flip unpredictably (confirmed directly: Down arrow
  // silently failed to recall anything because of exactly this).
  function contentEdgeRect(atStart) {
    if (el.messageInput.textContent.trim() === "") return null;
    const range = document.createRange();
    range.selectNodeContents(el.messageInput);
    const rects = range.getClientRects();
    if (rects.length === 0) return null;
    return atStart ? rects[0] : rects[rects.length - 1];
  }

  function caretIsOnFirstLine() {
    const contentRect = contentEdgeRect(true);
    if (!contentRect) return true; // empty composer
    const caretRect = caretEdgeRect(true);
    if (!caretRect) return true;
    return caretRect.top - contentRect.top < 4;
  }

  function caretIsOnLastLine() {
    const contentRect = contentEdgeRect(false);
    if (!contentRect) return true; // empty composer
    const caretRect = caretEdgeRect(false);
    if (!caretRect) return true;
    return contentRect.bottom - caretRect.bottom < 4;
  }

  // Replaces the composer's content with plain text (built from real text
  // nodes/<br>s, not innerHTML, since a recalled entry is untrusted-ish
  // content the user typed earlier) and places the caret at the end --
  // ready to edit further or resend immediately, like a shell prompt.
  // Formatting (bold/italic/lists) from the original turn is NOT
  // reconstructed -- history stores the same plain markdown string
  // actually sent, same as everything else that records a turn (e.g.
  // Save Chat's transcript), not a second, richer representation.
  function setComposerPlainText(text) {
    el.messageInput.innerHTML = "";
    const lines = (text || "").split("\n");
    lines.forEach((line, i) => {
      if (line) el.messageInput.appendChild(document.createTextNode(line));
      if (i < lines.length - 1) el.messageInput.appendChild(document.createElement("br"));
    });
    updateEmptyState();
    el.messageInput.focus();
    const range = document.createRange();
    range.selectNodeContents(el.messageInput);
    range.collapse(false);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function recallHistory(direction) {
    if (state.commandHistory.length === 0) return;
    if (historyIndex === state.commandHistory.length) {
      draftBeforeHistory = richTextToMarkdown(el.messageInput);
    }
    const next = historyIndex + direction;
    if (next < 0 || next > state.commandHistory.length) return; // nothing further to recall
    historyIndex = next;
    setComposerPlainText(
      historyIndex === state.commandHistory.length ? draftBeforeHistory : state.commandHistory[historyIndex]
    );
  }

  el.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "ArrowUp" && !event.shiftKey && !event.altKey && !event.metaKey && caretIsOnFirstLine()) {
      event.preventDefault();
      recallHistory(-1);
      return;
    }
    if (event.key === "ArrowDown" && !event.shiftKey && !event.altKey && !event.metaKey && caretIsOnLastLine()) {
      event.preventDefault();
      recallHistory(1);
      return;
    }
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
    // Skip an exact repeat of the immediately-previous entry (bash's own
    // default ignoredups behavior) so resending the same query doesn't
    // clutter history with duplicates.
    if (state.commandHistory[state.commandHistory.length - 1] !== markdown) {
      state.commandHistory.push(markdown);
    }
    historyIndex = state.commandHistory.length;
    draftBeforeHistory = "";
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
    renderUsageChart();
    el.messageInput.focus();
  }

  init();
})();
