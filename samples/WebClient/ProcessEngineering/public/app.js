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
    let out = escapeHtml(text);
    // Links: [text](url) -- escaped url's quotes already neutralized by escapeHtml above.
    out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    // Inline code.
    out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
    // Bold then italic (order matters so **x** isn't eaten by the italic rule first).
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
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

      // Paragraph: gather consecutive non-blank, non-special lines.
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
      html.push(`<p>${renderInline(paraLines.join(" "))}</p>`);
    }

    flushList();
    return html.join("") || escapeHtml(text);
  }

  // ---------------------------------------------------------------
  // Chat transcript rendering
  // ---------------------------------------------------------------
  function scrollToBottom() {
    el.chatScroll.scrollTop = el.chatScroll.scrollHeight;
  }

  function formatTime(date) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function addMessage(role, text, { isMarkdown = false } = {}) {
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

  function addTypingIndicator() {
    el.emptyState.style.display = "none";
    const row = document.createElement("div");
    row.className = "message-row agent";
    row.innerHTML = `
      <div class="avatar">PA</div>
      <div class="message-col">
        <div class="bubble"><div class="typing-indicator"><span></span><span></span><span></span></div></div>
      </div>`;
    el.chatContainer.appendChild(row);
    scrollToBottom();
    return row;
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

  async function sendMessage(text) {
    const baseUrl = currentBaseUrl();
    if (!baseUrl) {
      toast("Set a Base URL and click Connect first.");
      return;
    }

    addMessage("user", text);
    const typingRow = addTypingIndicator();
    el.sendBtn.disabled = true;
    el.messageInput.disabled = true;

    try {
      const data = await postChat(baseUrl, text);
      typingRow.remove();
      if (data.status === "ok") {
        setSessionId(data.session_id);
        addMessage("agent", data.response || "(empty response)", { isMarkdown: true });
      } else {
        addMessage("error", data.error || "The backend returned an error.");
      }
    } catch (err) {
      typingRow.remove();
      addMessage("error", `Couldn't reach the backend: ${err.message || err}`);
    } finally {
      el.sendBtn.disabled = false;
      el.messageInput.disabled = false;
      el.messageInput.focus();
    }
  }

  // ---------------------------------------------------------------
  // Composer
  // ---------------------------------------------------------------
  function autoGrow() {
    el.messageInput.style.height = "auto";
    el.messageInput.style.height = `${Math.min(el.messageInput.scrollHeight, 160)}px`;
  }

  el.messageInput.addEventListener("input", autoGrow);

  el.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      el.composerForm.requestSubmit();
    }
  });

  el.composerForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = el.messageInput.value.trim();
    if (!text) return;
    el.messageInput.value = "";
    autoGrow();
    sendMessage(text);
  });

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
    el.messageInput.focus();
  }

  init();
})();
