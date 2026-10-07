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
    el.messageInput.focus();
  }

  init();
})();
