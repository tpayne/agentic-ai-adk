// Process Architect web client
//
// A static, backend-agnostic chat UI for the ADK and neuro-san
// ProcessEngineering samples' REST API:
//   GET    /status                 -> { status: "live" }
//   POST   /chat                   { query, session_id?, files? } -> { status, session_id, query, response }
//   DELETE /chat/<session_id>      -> { status, session_id, cleared }
// "files" (optional): [{ name, mime_type, data_base64 }, ...] -- see
// addAttachments/attachmentsForRequest below for how the composer builds
// this. The two backends use attached files differently: the ADK sample
// passes them to Gemini as genuine multimodal content (an attached image
// is actually seen); the neuro-san port extracts them to text instead
// (its underlying framework's own multimodal plumbing is a stub in the
// installed version) -- either way, this page's own request/response
// shape is identical, so it doesn't need to know which backend it's
// talking to.
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
  const SESSION_HISTORY_KEY = "processArchitect.webClient.sessionHistory.v1";
  const SESSION_HISTORY_MAX_ENTRIES = 50;
  const SESSION_PURGE_MAX_AGE_MS = 3 * 24 * 60 * 60 * 1000; // 3 days, matches the server's own default purge window
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

    // Scoped to the sidebar -- the Base URL preset buttons are the only
    // ".preset-btn" elements left (the Artefact Browser tab uses a plain
    // <select>, not this class).
    presetBtns: Array.from(document.querySelectorAll("#sidebar .preset-btn")),
    baseUrlInput: document.getElementById("baseUrlInput"),
    apiKeyInput: document.getElementById("apiKeyInput"),
    toggleKeyVisibility: document.getElementById("toggleKeyVisibility"),
    connectBtn: document.getElementById("connectBtn"),
    connectionStatus: document.getElementById("connectionStatus"),
    topbarStatus: document.getElementById("topbarStatus"),

    sessionIdLabel: document.getElementById("sessionIdLabel"),
    newChatBtn: document.getElementById("newChatBtn"),
    deleteSessionBtn: document.getElementById("deleteSessionBtn"),
    sessionHistoryList: document.getElementById("sessionHistoryList"),
    sessionHistoryEmpty: document.getElementById("sessionHistoryEmpty"),
    purgeOldSessionsBtn: document.getElementById("purgeOldSessionsBtn"),

    themeToggleBtn: document.getElementById("themeToggleBtn"),
    themeToggleIcon: document.getElementById("themeToggleIcon"),
    themeToggleLabel: document.getElementById("themeToggleLabel"),

    muteToggleBtn: document.getElementById("muteToggleBtn"),
    muteToggleIcon: document.getElementById("muteToggleIcon"),
    muteToggleLabel: document.getElementById("muteToggleLabel"),
    volumeSlider: document.getElementById("volumeSlider"),
    faviconLink: document.getElementById("faviconLink"),

    chatScroll: document.getElementById("chatScroll"),
    chatContainer: document.getElementById("chatContainer"),
    emptyState: document.getElementById("emptyState"),
    jumpToLatestBtn: document.getElementById("jumpToLatestBtn"),

    composerForm: document.getElementById("composerForm"),
    messageInput: document.getElementById("messageInput"),
    sendBtn: document.getElementById("sendBtn"),
    stopBtn: document.getElementById("stopBtn"),
    toolbarBtns: Array.from(document.querySelectorAll(".toolbar-btn[data-command]")),
    saveChatBtn: document.getElementById("saveChatBtn"),
    attachFileBtn: document.getElementById("attachFileBtn"),
    attachFileInput: document.getElementById("attachFileInput"),
    composerAttachments: document.getElementById("composerAttachments"),
    micBtn: document.getElementById("micBtn"),

    tabBtns: Array.from(document.querySelectorAll(".tab-btn")),
    chatTabPanel: document.getElementById("chatTabPanel"),
    networkTabPanel: document.getElementById("networkTabPanel"),
    networkTabBadge: document.getElementById("networkTabBadge"),
    networkCount: document.getElementById("networkCount"),
    networkExportBtn: document.getElementById("networkExportBtn"),
    networkCanvasWrap: document.getElementById("networkCanvasWrap"),
    networkEmpty: document.getElementById("networkEmpty"),
    networkSvg: document.getElementById("networkSvg"),
    netHoverTooltip: document.getElementById("netHoverTooltip"),
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
    artifactSelect: document.getElementById("artifactSelect"),
    artifactRefreshBtn: document.getElementById("artifactRefreshBtn"),
    artifactDownloadJsonBtn: document.getElementById("artifactDownloadJsonBtn"),
    artifactsStatus: document.getElementById("artifactsStatus"),
    artifactsEmpty: document.getElementById("artifactsEmpty"),
    artifactTree: document.getElementById("artifactTree"),
    artifactDetail: document.getElementById("artifactDetail"),
    artifactDetailTitle: document.getElementById("artifactDetailTitle"),
    artifactDetailPath: document.getElementById("artifactDetailPath"),
    artifactDetailContext: document.getElementById("artifactDetailContext"),
    artifactDetailList: document.getElementById("artifactDetailList"),
    artifactDetailCloseBtn: document.getElementById("artifactDetailCloseBtn"),
    documentsBtn: document.getElementById("documentsBtn"),
    documentsPopover: document.getElementById("documentsPopover"),
    documentsPopoverCloseBtn: document.getElementById("documentsPopoverCloseBtn"),
    documentsPopoverList: document.getElementById("documentsPopoverList"),

    cloudarchTabPanel: document.getElementById("cloudarchTabPanel"),
    cloudarchRefreshBtn: document.getElementById("cloudarchRefreshBtn"),
    cloudarchExportBtn: document.getElementById("cloudarchExportBtn"),
    cloudarchDownloadXmlBtn: document.getElementById("cloudarchDownloadXmlBtn"),
    cloudarchDownloadIacBtn: document.getElementById("cloudarchDownloadIacBtn"),
    cloudarchStatus: document.getElementById("cloudarchStatus"),
    cloudarchCanvasWrap: document.getElementById("cloudarchCanvasWrap"),
    cloudarchEmpty: document.getElementById("cloudarchEmpty"),
    cloudarchSvg: document.getElementById("cloudarchSvg"),
    cloudarchZoomInBtn: document.getElementById("cloudarchZoomInBtn"),
    cloudarchZoomOutBtn: document.getElementById("cloudarchZoomOutBtn"),
    cloudarchResetViewBtn: document.getElementById("cloudarchResetViewBtn"),

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
    voiceMuted: false,
    voiceVolume: 100,
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

  // The Cloud Architecture tab's data -- the connected backend's current
  // output/cloudarch_drawio.xml (GET /artifacts/cloudarch), rendered as an
  // actual diagram (see renderCloudArchDiagram). Runtime only, same as
  // dataExplorer above; `raw` holds the XML text itself, not a parsed
  // DOM -- re-parsed fresh on every render so a resize/zoom/pan never
  // needs to re-fetch.
  state.cloudarch = {
    raw: null,
    loading: false,
    error: null,
    view: { x: 0, y: 0, scale: 1 },
    autoFit: true,
    // The full diagram's own native pixel size (independent of the
    // current on-screen zoom/pan) -- set by renderCloudArchDiagram,
    // used by exportCloudArchPng.
    contentWidth: null,
    contentHeight: null,
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
  // Voice output (speak a reply on request) -- window.speechSynthesis,
  // built into every modern browser, so (like everything else in this
  // file) this needs no server round trip and no external dependency.
  // ---------------------------------------------------------------
  const SPEECH_SUPPORTED = "speechSynthesis" in window;

  function applyVoiceSettings() {
    if (!SPEECH_SUPPORTED) {
      el.muteToggleBtn.disabled = true;
      el.muteToggleBtn.title = "Voice output isn't supported in this browser.";
      el.muteToggleLabel.textContent = "Voice: unavailable";
      el.volumeSlider.disabled = true;
      return;
    }
    const muted = !!state.voiceMuted;
    el.muteToggleIcon.textContent = muted ? "\u{1F507}" : "\u{1F50A}";
    el.muteToggleLabel.textContent = muted ? "Voice: Off" : "Voice: On";
    el.volumeSlider.value = state.voiceVolume != null ? state.voiceVolume : 100;
    el.volumeSlider.disabled = muted;
    if (muted) stopSpeaking();
  }

  el.muteToggleBtn.addEventListener("click", () => {
    state.voiceMuted = !state.voiceMuted;
    saveState({ voiceMuted: state.voiceMuted });
    applyVoiceSettings();
  });

  el.volumeSlider.addEventListener("input", () => {
    state.voiceVolume = Number(el.volumeSlider.value);
    saveState({ voiceVolume: state.voiceVolume });
  });

  // Renders `html` into a detached element and reads back .textContent --
  // a cheap, robust way to get the plain-text reading of a string that's
  // actually (or might contain) HTML, without a second hand-written
  // "strip tags" regex. Used below both for speech (via renderMarkdownLite
  // first) and for the Cloud Architecture tab's edge labels (which are
  // already plain HTML straight out of the diagram XML, no markdown step
  // needed).
  function htmlToText(html) {
    const scratch = document.createElement("div");
    scratch.innerHTML = html || "";
    return scratch.textContent || "";
  }

  // Renders `markdownText` through the same markdown-lite pipeline used
  // for display, then strips it to plain text via htmlToText -- cheaper
  // and far more robust than a second, hand-written "strip markdown
  // syntax" regex, and guarantees speech and on-screen text never drift
  // out of sync (tables/lists/headings all collapse to sensible plain
  // text for free).
  function plainTextForSpeech(markdownText) {
    return htmlToText(renderMarkdownLite(markdownText || ""));
  }

  // The message-action button (if any) currently showing "Cancel" --
  // only one utterance ever plays at a time, so at most one button is
  // ever in this state. See speakText/stopSpeaking below.
  let activeSpeakBtn = null;

  function setSpeakButtonIdle(btn) {
    btn.textContent = "Speak";
    btn.classList.remove("speaking");
  }

  // Stops whatever is currently speaking (if anything) and reverts
  // whichever button was showing "Cancel" back to "Speak". Safe to call
  // unconditionally, speaking or not -- every other place speech can
  // stop (muting, sending a new message, clicking the active Cancel
  // button itself) goes through this one function, so the button label
  // can never drift out of sync with whether anything is actually
  // playing.
  function stopSpeaking() {
    if (!SPEECH_SUPPORTED) return;
    window.speechSynthesis.cancel();
    if (activeSpeakBtn) {
      setSpeakButtonIdle(activeSpeakBtn);
      activeSpeakBtn = null;
    }
  }

  // Speaks `text` on request (a message's own "Speak" button, which
  // becomes a "Cancel" button -- `btn` -- for as long as this utterance
  // is playing) -- never automatic/on-done, per the feature request.
  // Only one reply speaks at a time: a fresh click (on this message or
  // another) cancels whatever was already playing rather than queuing
  // or overlapping. Clicking the SAME button again while it's the one
  // currently playing cancels it instead of restarting it.
  function speakText(text, btn) {
    if (!SPEECH_SUPPORTED) {
      toast("Text-to-speech isn't supported in this browser.");
      return;
    }
    if (state.voiceMuted) {
      toast("Voice output is muted — unmute it in the sidebar to hear replies.");
      return;
    }
    if (activeSpeakBtn === btn) {
      stopSpeaking();
      return;
    }

    stopSpeaking(); // reverts whichever OTHER button was mid-speech, if any
    const utterance = new SpeechSynthesisUtterance(plainTextForSpeech(text));
    utterance.volume = (state.voiceVolume != null ? state.voiceVolume : 100) / 100;
    // Covers both a natural finish and a genuine synthesis error -- either
    // way this utterance is done, and the button must not stay stuck
    // showing "Cancel" for speech that isn't actually playing anymore.
    // Guarded on `activeSpeakBtn === btn` since stopSpeaking() (a NEWER
    // click, elsewhere) may already have reverted and cleared this one.
    utterance.onend = utterance.onerror = () => {
      if (activeSpeakBtn === btn) {
        setSpeakButtonIdle(btn);
        activeSpeakBtn = null;
      }
    };
    window.speechSynthesis.speak(utterance);

    activeSpeakBtn = btn;
    btn.textContent = "Cancel";
    btn.classList.add("speaking");
  }

  // ---------------------------------------------------------------
  // Turn-completion notification -- gated on the SAME voice on/off
  // toggle as speech output (state.voiceMuted): an audible chime always
  // plays when a turn finishes, and -- only if this tab isn't the one
  // currently focused -- a desktop notification fires and the favicon/
  // title get a small "reply's ready" badge until the tab regains focus.
  //
  // A page has no access to the OS's own actual notification sound or to
  // a real dock-icon bounce/taskbar-flash (those are OS/browser-chrome
  // capabilities, not something web content can trigger directly) --
  // this is the closest cross-platform equivalent achievable from a
  // browser tab: Web Audio for the chime (every modern browser, every
  // OS), the Notification API for an OS-native notification banner/toast
  // (which on most desktop OSes IS the thing that draws attention to the
  // app/tab -- e.g. bouncing/badging the dock icon on macOS, a toast on
  // Windows, a desktop notification on Linux -- entirely up to that OS's
  // own notification settings, not something this page controls), and a
  // favicon/title swap as a visible fallback wherever notifications are
  // denied or unsupported.
  // ---------------------------------------------------------------
  function playCompletionChime() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    try {
      const ctx = new Ctx();
      const now = ctx.currentTime;
      const gain = ctx.createGain();
      gain.connect(ctx.destination);
      const peak = ((state.voiceVolume != null ? state.voiceVolume : 100) / 100) * 0.2; // deliberately subtle, scaled by the user's own volume setting
      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(peak, now + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.4);

      // A short two-note rising chime -- the standard shape for a
      // pleasant, unobtrusive "done" cue.
      [880, 1320].forEach((freq, i) => {
        const osc = ctx.createOscillator();
        osc.type = "sine";
        osc.frequency.value = freq;
        osc.connect(gain);
        const start = now + i * 0.12;
        osc.start(start);
        osc.stop(start + 0.22);
      });
      setTimeout(() => ctx.close(), 600);
    } catch {
      // Best-effort -- a chime failure must never affect the actual turn.
    }
  }

  // Mic-start cue -- a short, single-tone beep when voice input actually
  // starts listening, so pressing the mic button gives the same kind of
  // immediate audible confirmation a voice assistant's "I'm listening"
  // beep gives. Deliberately NOT gated on state.voiceMuted -- that toggle
  // only governs whether AGENT REPLIES are spoken aloud (voice OUTPUT),
  // an unrelated setting from whether the user's own mic is now active
  // (voice INPUT) -- but still scaled by state.voiceVolume for the same
  // "respects the user's general app volume" consistency every other
  // sound on this page has. Deliberately a SINGLE short tone, not
  // playCompletionChime's two-note rising shape just above, so the two
  // are never confused for each other.
  function playMicStartChime() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    try {
      const ctx = new Ctx();
      const now = ctx.currentTime;
      const gain = ctx.createGain();
      gain.connect(ctx.destination);
      const peak = ((state.voiceVolume != null ? state.voiceVolume : 100) / 100) * 0.2;
      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(peak, now + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);

      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = 1100;
      osc.connect(gain);
      osc.start(now);
      osc.stop(now + 0.15);
      setTimeout(() => ctx.close(), 300);
    } catch {
      // Best-effort -- a chime failure must never block recording from starting.
    }
  }

  const DEFAULT_PAGE_TITLE = document.title;
  let completionBadgeActive = false;
  let notificationPermissionRequested = false;

  // Minimal inline SVG, no bundled image asset -- mirrors the sidebar's
  // own "PA" brand mark. `badge` adds a small red dot, the tab-icon
  // equivalent of a bounced dock icon / flashed taskbar entry.
  function faviconDataUri(badge) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">`
      + `<rect width="64" height="64" rx="14" fill="#4285F4"/>`
      + `<text x="32" y="43" font-family="system-ui,sans-serif" font-size="27" font-weight="700" `
      + `text-anchor="middle" fill="#ffffff">PA</text>`
      + (badge ? `<circle cx="50" cy="14" r="11" fill="#ea4335" stroke="#ffffff" stroke-width="2"/>` : "")
      + `</svg>`;
    return `data:image/svg+xml,${encodeURIComponent(svg)}`;
  }

  function setCompletionBadge(active) {
    completionBadgeActive = active;
    el.faviconLink.setAttribute("href", faviconDataUri(active));
    document.title = active ? `🔔 Reply ready — ${DEFAULT_PAGE_TITLE}` : DEFAULT_PAGE_TITLE;
  }

  function clearCompletionBadge() {
    if (completionBadgeActive) setCompletionBadge(false);
  }

  // Clears the badge the moment the user actually looks at the tab again
  // -- covers both switching back to this tab (visibilitychange) and
  // this window/tab regaining OS focus while already the visible one
  // (e.g. alt-tab back on a single-monitor setup where it was never
  // technically "hidden").
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) clearCompletionBadge();
  });
  window.addEventListener("focus", clearCompletionBadge);

  // Only ever SHOWS a notification -- never requests permission itself.
  // Browsers require Notification.requestPermission() to be called
  // synchronously within a genuine user gesture (a click/keypress
  // handler), never from inside an async callback -- this used to be
  // called from here, deep inside notifyTurnComplete()'s own async chain
  // (a server response arriving well after the user's original click had
  // stopped counting as "active"), which Chrome/Safari both reject with
  // "Notification prompting can only be done from a user gesture." See
  // maybeRequestNotificationPermission below for where the request itself
  // now happens instead.
  function showTurnCompleteNotification() {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    try {
      const n = new Notification("Process Architect", { body: "Your reply is ready." });
      n.onclick = () => { window.focus(); n.close(); };
    } catch {
      // Best-effort -- e.g. some browsers refuse this without a service
      // worker in certain contexts; the favicon/title badge still covers it.
    }
  }

  // Called synchronously from the composer's own "submit" handler (a real
  // user gesture) -- the only place in this file a genuine click/keypress
  // is still on the call stack. Only ever asks ONCE per page load
  // (notificationPermissionRequested), and only the first time a message
  // is actually sent -- never on page load itself, which is the kind of
  // upfront permission prompt most people reflexively deny.
  function maybeRequestNotificationPermission() {
    if (!("Notification" in window)) return;
    if (notificationPermissionRequested) return;
    if (Notification.permission !== "default") return;
    notificationPermissionRequested = true;
    Notification.requestPermission();
  }

  // Called once per turn, regardless of outcome (done/stopped/error) --
  // see sendMessage's own finally block below.
  function notifyTurnComplete() {
    if (state.voiceMuted) return;
    playCompletionChime();
    if (document.hidden || !document.hasFocus()) {
      setCompletionBadge(true);
      showTurnCompleteNotification();
    }
  }

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

  // GET /artifacts/* routes (viewing/downloading process/design/
  // requirements/proposal-response/cloudarch data, generated documents)
  // have no JSON body of their own the way
  // POST /chat does, so the session id this client tracks in state.sessionId
  // (set from POST /chat's own response -- see setSessionId) has to travel
  // as a query parameter instead. The backend's own session cookie is NOT
  // a reliable fallback here: this client is typically served from a
  // different origin than the backend API, and a cross-origin fetch()
  // never sends or receives cookies unless BOTH sides opt into
  // credentials -- this client doesn't, and deliberately so (see either
  // backend's own _add_cors_headers). A URL with no active session yet
  // (state.sessionId is null before the first chat turn) is returned
  // unchanged -- the backend then falls back to flat output/, exactly as
  // it did before per-session isolation existed.
  function withSessionIdParam(url) {
    if (!state.sessionId) return url;
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}session_id=${encodeURIComponent(state.sessionId)}`;
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
  // Deliberately does NOT sync to session history itself -- it's called
  // from several places (including restoring a session on page load,
  // BEFORE that session's saved transcript has been replayed back into
  // state.transcript) where syncing here would overwrite a real history
  // entry with an empty one. recordTranscript's own sync call (on every
  // finalized turn) is what actually keeps history current.
  function setSessionId(id) {
    state.sessionId = id || null;
    el.sessionIdLabel.textContent = id || "none";
    el.sessionIdLabel.title = id ? summarizeSessionForTooltip(state.transcript) : "";
    el.deleteSessionBtn.disabled = !state.sessionId;
    saveState({ sessionId: state.sessionId });
  }

  // Shared by newChat/deleteSession below -- clears everything runtime-only
  // and local to THIS client (transcript, network graph, usage history),
  // never persisted across a reload anyway (see loadState/saveState). Does
  // NOT touch the server; callers are responsible for that first.
  function clearLocalChatState() {
    setSessionId(null);
    el.chatContainer.innerHTML = "";
    el.chatContainer.appendChild(el.emptyState);
    el.emptyState.style.display = "";
    state.transcript = [];
    resetNetwork();
    resetUsage();
  }

  // "+ New chat" deliberately does NOT delete the old session anymore --
  // it stays alive server-side and in the sidebar history list below, so
  // it can be reopened later. Only the explicit "Delete session" button,
  // or "Clear chats older than 3 days", ever removes a session.
  function newChat() {
    clearLocalChatState();
    renderSessionHistoryList();
    toast("Started a new chat.");
  }

  el.newChatBtn.addEventListener("click", newChat);

  // Explicit "Delete session" -- the whole point of this action IS the
  // server-side delete (unlike newChat above), so a failure here is
  // reported rather than silently swallowed.
  async function deleteSession() {
    if (!state.sessionId) return;
    const confirmed = window.confirm(
      "Delete this session's chat history and every file it generated on the server? This cannot be undone."
    );
    if (!confirmed) return;

    const baseUrl = currentBaseUrl();
    const sessionId = state.sessionId;
    if (!baseUrl) {
      toast("Set a backend Base URL first.");
      return;
    }
    el.deleteSessionBtn.disabled = true;
    try {
      const response = await fetch(`${baseUrl}/chat/${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
        headers: { ...authHeaders() },
      });
      if (!response.ok) {
        throw new Error(`Server responded ${response.status}`);
      }
      removeSessionHistoryEntry(sessionId);
      clearLocalChatState();
      toast("Session deleted.");
    } catch (err) {
      toast(`Could not delete session: ${err.message || err}`);
      el.deleteSessionBtn.disabled = !state.sessionId;
    }
  }

  el.deleteSessionBtn.addEventListener("click", deleteSession);

  // ---------------------------------------------------------------
  // Session history -- a sidebar list of past chats kept client-side
  // (localStorage) so a chat that "+ New chat" no longer deletes can be
  // reopened later, with its transcript actually re-rendered rather than
  // just resumed blind. Separate storage key from the small settings blob
  // above (STORAGE_KEY) since this one can grow meaningfully larger.
  // ---------------------------------------------------------------
  function loadSessionHistory() {
    try {
      const raw = localStorage.getItem(SESSION_HISTORY_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function saveSessionHistory(sessions) {
    // Keep only the most recently active N entries -- bounds localStorage
    // usage regardless of how many chats accumulate over time.
    const trimmed = [...sessions].sort((a, b) => b.lastActiveAt - a.lastActiveAt).slice(0, SESSION_HISTORY_MAX_ENTRIES);
    try {
      localStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(trimmed));
    } catch {
      // Quota exceeded or unavailable -- drop the older half and retry
      // once; otherwise give up silently, same philosophy as saveState.
      try {
        localStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(trimmed.slice(0, Math.ceil(trimmed.length / 2))));
      } catch {
        /* history just won't persist this time */
      }
    }
    return trimmed;
  }

  function truncateText(text, maxLen) {
    const clean = (text || "").replace(/\s+/g, " ").trim();
    return clean.length > maxLen ? `${clean.slice(0, maxLen - 1)}…` : clean;
  }

  // Hover-tooltip summary for a session: its opening request plus a
  // snippet of the first reply -- a few sentences on what the chat is
  // about, derived purely from the transcript already on hand.
  function summarizeSessionForTooltip(transcript) {
    const firstUser = (transcript || []).find((t) => t.role === "user");
    const firstAgent = (transcript || []).find((t) => t.role === "agent");
    const parts = [];
    if (firstUser) parts.push(truncateText(firstUser.text, 320));
    if (firstAgent) parts.push(truncateText(firstAgent.text, 220));
    return parts.join(" — ") || "No messages yet.";
  }

  // Keeps the CURRENTLY active session's history entry (title/transcript/
  // lastActiveAt) up to date -- called from recordTranscript (every
  // finalized turn) and setSessionId (the moment a session id becomes
  // known, which for a brand-new chat happens slightly AFTER the first
  // user message is already recorded).
  function syncCurrentSessionToHistory() {
    if (!state.sessionId) return;
    const sessions = loadSessionHistory();
    const existing = sessions.find((s) => s.sessionId === state.sessionId);
    const firstUser = state.transcript.find((t) => t.role === "user");
    const entry = {
      sessionId: state.sessionId,
      title: firstUser ? truncateText(firstUser.text, 60) : (existing && existing.title) || "New chat",
      createdAt: (existing && existing.createdAt) || Date.now(),
      lastActiveAt: Date.now(),
      transcript: state.transcript.map((t) => ({ role: t.role, text: t.text, timestamp: t.timestamp })),
    };
    const next = sessions.filter((s) => s.sessionId !== state.sessionId);
    next.push(entry);
    saveSessionHistory(next);
    renderSessionHistoryList();
  }

  function removeSessionHistoryEntry(sessionId) {
    saveSessionHistory(loadSessionHistory().filter((s) => s.sessionId !== sessionId));
    renderSessionHistoryList();
  }

  // Named distinctly from the existing formatRelativeTime(isoString) below
  // (different signature -- epoch ms, not an ISO string -- and this one
  // adds an absolute-date fallback past 7 days) to avoid colliding with
  // it: two function declarations sharing a name in the same scope would
  // silently let whichever is defined later in the file win for ALL
  // callers of that name, which is exactly the kind of bug that's invisible
  // until something quietly calls the wrong one.
  function formatSessionRelativeTime(epochMs) {
    const diffMs = Date.now() - epochMs;
    const minute = 60 * 1000;
    const hour = 60 * minute;
    const day = 24 * hour;
    if (diffMs < minute) return "just now";
    if (diffMs < hour) return `${Math.floor(diffMs / minute)}m ago`;
    if (diffMs < day) return `${Math.floor(diffMs / hour)}h ago`;
    if (diffMs < 7 * day) return `${Math.floor(diffMs / day)}d ago`;
    return new Date(epochMs).toLocaleDateString();
  }

  function renderSessionHistoryList() {
    const sessions = loadSessionHistory().sort((a, b) => b.lastActiveAt - a.lastActiveAt);
    el.sessionHistoryList.querySelectorAll(".session-history-item").forEach((node) => node.remove());
    el.sessionHistoryEmpty.hidden = sessions.length > 0;

    sessions.forEach((entry) => {
      // A plain div, not a <button> -- it contains its OWN delete
      // <button>, and nesting a button inside a button is invalid HTML
      // (browsers silently mangle/auto-close it). role="button" +
      // tabIndex + the keydown handler below keep it keyboard-accessible
      // without that nesting.
      const item = document.createElement("div");
      item.setAttribute("role", "button");
      item.tabIndex = 0;
      item.className = "session-history-item" + (entry.sessionId === state.sessionId ? " active" : "");
      item.title = summarizeSessionForTooltip(entry.transcript || []);

      const main = document.createElement("span");
      main.className = "session-history-item-main";
      const title = document.createElement("span");
      title.className = "session-history-item-title";
      title.textContent = entry.title || "New chat";
      const time = document.createElement("span");
      time.className = "session-history-item-time";
      time.textContent = formatSessionRelativeTime(entry.lastActiveAt);
      main.appendChild(title);
      main.appendChild(time);
      item.appendChild(main);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "session-history-item-delete";
      del.title = "Remove from history";
      del.setAttribute("aria-label", "Remove from history");
      del.textContent = "✕";
      del.addEventListener("click", (evt) => {
        evt.stopPropagation();
        removeSessionHistoryEntry(entry.sessionId);
      });
      item.appendChild(del);

      item.addEventListener("click", () => switchToSession(entry.sessionId));
      item.addEventListener("keydown", (evt) => {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          switchToSession(entry.sessionId);
        }
      });
      el.sessionHistoryList.appendChild(item);
    });
  }

  // Shared by switchToSession/restoreSessionOnLoad below: replays a saved
  // transcript into the (already-cleared) chat view, then sets
  // state.transcript directly, with ORIGINAL timestamps preserved, rather
  // than letting addMessage's own recordTranscript stamp each one with
  // "now" (skipRecord=true on every call below avoids double-appending).
  function replayTranscriptIntoView(transcript) {
    if (!transcript || transcript.length === 0) return;
    el.emptyState.style.display = "none";
    transcript.forEach((turn) => {
      addMessage(turn.role, turn.text, { isMarkdown: turn.role === "agent", skipRecord: true });
    });
    state.transcript = transcript.map((t) => ({ role: t.role, text: t.text, timestamp: new Date(t.timestamp) }));
    // setSessionId (called just before this, by both callers) already set
    // the hover tooltip -- but from the EMPTY transcript at that point,
    // before this replay populated it. Refresh it now with the real one.
    el.sessionIdLabel.title = summarizeSessionForTooltip(state.transcript);
  }

  // Reopens a past chat: restores its session id (so new messages
  // continue that same server-side conversation) and replays its saved
  // transcript back into the chat view.
  function switchToSession(sessionId) {
    if (sessionId === state.sessionId) return;
    const entry = loadSessionHistory().find((s) => s.sessionId === sessionId);
    if (!entry) return;

    clearLocalChatState();
    setSessionId(sessionId);
    replayTranscriptIntoView(entry.transcript || []);
    renderSessionHistoryList();
  }

  // Called once at startup (see init() below) when a session id survived
  // a page reload (state.sessionId is restored from the small settings
  // blob, but the transcript itself never is -- that lives only in the
  // session-history store keyed by id). Mirrors switchToSession's replay
  // but without its "already on this session" early-return, since at
  // init time state.sessionId is already set to this same id (loadState()
  // merged it in before setSessionId is ever called).
  function restoreSessionOnLoad(sessionId) {
    const entry = loadSessionHistory().find((s) => s.sessionId === sessionId);
    setSessionId(sessionId);
    if (entry) {
      replayTranscriptIntoView(entry.transcript || []);
    }
    renderSessionHistoryList();
  }

  // "Clear chats older than 3 days" -- matches the server's own default
  // session-purge window (SESSIONMAXAGEDAYS). Removes matching entries
  // from the local history list and best-effort deletes them server-side
  // too, same "don't block on this" philosophy as newChat's old cleanup.
  function purgeOldSessions() {
    const cutoff = Date.now() - SESSION_PURGE_MAX_AGE_MS;
    const sessions = loadSessionHistory();
    const stale = sessions.filter((s) => s.lastActiveAt < cutoff && s.sessionId !== state.sessionId);
    if (stale.length === 0) {
      toast("No chats older than 3 days to clear.");
      return;
    }

    const staleIds = new Set(stale.map((s) => s.sessionId));
    saveSessionHistory(sessions.filter((s) => !staleIds.has(s.sessionId)));
    renderSessionHistoryList();

    const baseUrl = currentBaseUrl();
    if (baseUrl) {
      stale.forEach((entry) => {
        fetch(`${baseUrl}/chat/${encodeURIComponent(entry.sessionId)}`, {
          method: "DELETE",
          headers: { ...authHeaders() },
        }).catch(() => {});
      });
    }
    toast(`Cleared ${stale.length} chat${stale.length === 1 ? "" : "s"} older than 3 days.`);
  }

  el.purgeOldSessionsBtn.addEventListener("click", purgeOldSessions);

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

  // GFM pipe table helpers -- shared by the header/separator/body row
  // handling in renderMarkdownLite below.
  function splitTableRow(line) {
    let cells = line.split("|");
    // Drop one leading/trailing empty cell from the row's optional outer pipes.
    if (cells.length && cells[0].trim() === "") cells = cells.slice(1);
    if (cells.length && cells[cells.length - 1].trim() === "") cells = cells.slice(0, -1);
    return cells.map((c) => c.trim());
  }

  function isTableSeparatorRow(line) {
    if (!/\|/.test(line)) return false;
    const cells = splitTableRow(line);
    return cells.length > 0 && cells.every((c) => /^:?-+:?$/.test(c));
  }

  function renderMarkdownLite(raw) {
    const text = (raw || "").replace(/\r\n/g, "\n");
    const lines = text.split("\n");
    const html = [];
    let i = 0;

    // Stack of currently-open lists, outermost first -- each frame is
    // { indent, type: 'ul'|'ol', items: [htmlSoFar, ...] }. A deeper
    // indent than the current top opens a NESTED list inside the top
    // frame's own last item (a real <ol>/<ul> nested inside that <li>'s
    // own content) rather than closing the outer list -- the earlier,
    // flat-buffer version treated every indented sub-bullet as "end the
    // current list, start an unrelated one," which silently split one
    // numbered list into several single-item <ol>s (each rendering "1."
    // via the browser's own per-list auto-numbering) the moment any
    // numbered item had an indented sub-bullet under it.
    let listStack = [];

    function lineIndent(line) {
      const match = line.match(/^(\s*)/);
      return match ? match[1].length : 0;
    }

    function closeListFramesDeeperThanOrEqualTo(indent, type) {
      while (
        listStack.length &&
        (listStack[listStack.length - 1].indent > indent ||
          (listStack[listStack.length - 1].indent === indent && listStack[listStack.length - 1].type !== type))
      ) {
        const finished = listStack.pop();
        const finishedHtml = `<${finished.type}>${finished.items.map((it) => `<li>${it}</li>`).join("")}</${finished.type}>`;
        if (listStack.length) {
          const parent = listStack[listStack.length - 1];
          parent.items[parent.items.length - 1] += finishedHtml;
        } else {
          html.push(finishedHtml);
        }
      }
    }

    function flushList() {
      closeListFramesDeeperThanOrEqualTo(-1, null);
    }

    function pushListItem(type, indent, itemText) {
      closeListFramesDeeperThanOrEqualTo(indent, type);
      const top = listStack[listStack.length - 1];
      if (!top || top.indent < indent) {
        listStack.push({ indent, type, items: [] });
      }
      listStack[listStack.length - 1].items.push(renderInline(itemText));
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
        pushListItem("ul", lineIndent(line), ul[1]);
        i += 1;
        continue;
      }

      // Ordered list item.
      const ol = line.match(/^\s*\d+\.\s+(.*)$/);
      if (ol) {
        pushListItem("ol", lineIndent(line), ol[1]);
        i += 1;
        continue;
      }

      // GFM pipe table: a row containing "|" immediately followed by a
      // separator row ("| :--- | ---: |" etc.) marks the start of a
      // table -- a bare "|" in ordinary prose has no such separator line
      // after it and falls through to paragraph handling below instead.
      if (/\|/.test(line) && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1])) {
        flushList();
        const headerCells = splitTableRow(line);
        const aligns = splitTableRow(lines[i + 1]).map((c) => {
          const left = c.startsWith(":");
          const right = c.endsWith(":");
          if (left && right) return "center";
          if (right) return "right";
          if (left) return "left";
          return "";
        });
        i += 2;
        const bodyRows = [];
        while (i < lines.length && /\|/.test(lines[i]) && lines[i].trim() !== "") {
          bodyRows.push(splitTableRow(lines[i]));
          i += 1;
        }
        const alignAttr = (idx) => (aligns[idx] ? ` style="text-align:${aligns[idx]}"` : "");
        const headHtml = headerCells.map((c, idx) => `<th${alignAttr(idx)}>${renderInline(c)}</th>`).join("");
        const bodyHtml = bodyRows
          .map((row) => `<tr>${row.map((c, idx) => `<td${alignAttr(idx)}>${renderInline(c)}</td>`).join("")}</tr>`)
          .join("");
        html.push(`<table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`);
        continue;
      }

      // Blank line -- paragraph separator, UNLESS a blank line (or run of
      // blank lines) sits between two sibling list items ("loose list"
      // spacing, e.g. an LLM response with a blank line after every
      // numbered item). Peek past the blank run; if the next real line
      // still starts a list item, swallow the blank line(s) and keep the
      // list open rather than closing it -- otherwise one 4-item <ol>
      // would split into four single-item <ol>s, each restarting its own
      // "1." (the exact symptom reported: every item showing as "1.").
      if (line.trim() === "") {
        let j = i + 1;
        while (j < lines.length && lines[j].trim() === "") j += 1;
        const nextLine = j < lines.length ? lines[j] : "";
        const nextContinuesList =
          listStack.length > 0 && (/^\s*[-*]\s+/.test(nextLine) || /^\s*\d+\.\s+/.test(nextLine));
        if (!nextContinuesList) {
          flushList();
        }
        i += 1;
        continue;
      }

      flushList();

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
    el.cloudarchTabPanel.hidden = name !== "cloudarch";
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
    } else if (name === "cloudarch") {
      // Same "first open auto-loads" convention as the artifacts tab
      // above, and same "SVG was sized 0x0 while hidden" re-render need
      // as the network tab if a diagram was already loaded before this
      // tab was last switched away from.
      if (state.cloudarch.raw === null && !state.cloudarch.loading && !state.cloudarch.error) {
        loadCloudArchDiagram();
      } else if (state.cloudarch.raw !== null) {
        renderCloudArchDiagram();
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
        // A node the user has dragged (see startNodeDrag/moveNodeDrag
        // further down) keeps its own last-dropped position instead of
        // the computed grid slot -- recomputed every render regardless,
        // so a newly-grown graph's own layout doesn't fight a dragged
        // node's placement, it's just skipped for any node already moved.
        const x = n.manualX != null ? n.manualX : startX + i * nodeSpacing;
        const finalY = n.manualY != null ? n.manualY : y;
        positioned.push({ ...n, x, y: finalY, radius });
      });
    });

    // The real content bounds, which a dragged node can extend past the
    // natural grid's own width/height -- zoom-to-fit and PNG export both
    // need this, or a node dragged further out than the grid would be
    // clipped/cropped by both.
    const labelPadding = 28; // room below each node for its own label text
    const contentWidth = Math.max(width, ...positioned.map((n) => n.x + n.radius + marginX));
    const contentHeight = Math.max(height, ...positioned.map((n) => n.y + n.radius + labelPadding + marginY));

    return { nodes: positioned, width: contentWidth, height: contentHeight };
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
    // Stashed for Export PNG, same pattern as state.cloudarch.contentWidth/
    // contentHeight -- the FULL graph's own natural (now drag-aware) size,
    // not whatever's currently zoomed/panned into view.
    state.network.contentWidth = width;
    state.network.contentHeight = height;

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
      // Drag-to-reposition AND click-to-open-details share the same
      // pointerdown -- see startNodeDrag's own docstring for why this
      // replaces a plain "click" listener entirely rather than living
      // alongside one.
      g.addEventListener("pointerdown", (event) => startNodeDrag(event, node));
      g.addEventListener("pointerenter", (event) => scheduleInstructionsHover(node, event.clientX, event.clientY));
      g.addEventListener("pointermove", (event) => repositionHoverTooltipIfShowing(node, event.clientX, event.clientY));
      g.addEventListener("pointerleave", () => cancelInstructionsHover(node.id));
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

  const NETWORK_EXPORT_SCALE = 2; // 2x pixel density, matching the Cloud Architecture tab's own export

  // Deliberately LIGHT-THEME LITERALS, not this page's current resolved
  // CSS variables -- same reasoning as the Cloud Architecture tab's own
  // cloudArchExportStyle (see its comment): the background painted below
  // is a fixed light color regardless of theme, so text/line colors must
  // match that fixed background unconditionally too, not whatever the
  // live theme (e.g. dark mode, where --text resolves to near-white)
  // happens to currently be.
  function networkExportStyle() {
    const fontFamily = getComputedStyle(document.documentElement).getPropertyValue("--font").trim() || "sans-serif";
    return `
      .net-edge { stroke-width: 1.6; fill: none; }
      .net-edge-hierarchy { stroke: #4f5eff; opacity: 0.6; }
      .net-edge-flow { stroke: #9299a8; stroke-dasharray: 4 4; }
      .net-arrow-hierarchy { fill: #4f5eff; }
      .net-arrow-flow { fill: #9299a8; }
      .net-node-circle { fill: #ffffff; stroke: #d2d5dc; stroke-width: 1.6; }
      .net-node.net-node-active .net-node-circle { stroke: #4f5eff; fill: #eef0ff; }
      .net-node.net-node-selected .net-node-circle { stroke: #4f5eff; stroke-width: 2.4; }
      .net-node-pulse { display: none; } /* a live "currently active" animation has no meaning in a static export */
      .net-node-label { font-size: 10.5px; font-weight: 650; fill: #1b1d22; font-family: ${fontFamily}; }
      .net-node-count { font-size: 9px; font-weight: 700; fill: #ffffff; font-family: ${fontFamily}; }
    `;
  }

  // Exports the FULL graph (not whatever's currently zoomed/panned into
  // view, and including any manually dragged node positions -- see
  // computeNetworkLayout's own content-bounds comment) as a PNG. Mirrors
  // exportCloudArchPng further down exactly -- clones the live SVG rather
  // than re-rendering from scratch, so the export always matches what's
  // on screen (minus zoom/pan) with zero duplicated drawing logic.
  async function exportNetworkPng() {
    const { contentWidth, contentHeight } = state.network;
    if (!contentWidth || !contentHeight || el.networkSvg.hasAttribute("hidden")) {
      toast("No agents invoked yet.");
      return;
    }

    const clone = el.networkSvg.cloneNode(true);
    clone.removeAttribute("hidden");
    clone.setAttribute("viewBox", `0 0 ${contentWidth} ${contentHeight}`);
    clone.setAttribute("width", String(contentWidth));
    clone.setAttribute("height", String(contentHeight));

    const viewport = clone.querySelector("#networkViewport");
    if (viewport) viewport.setAttribute("transform", "translate(0, 0) scale(1)");

    const bg = document.createElementNS(SVG_NS, "rect");
    bg.setAttribute("width", String(contentWidth));
    bg.setAttribute("height", String(contentHeight));
    bg.setAttribute("fill", "#f5f6f8");
    clone.insertBefore(bg, clone.firstChild);

    const styleEl = document.createElementNS(SVG_NS, "style");
    styleEl.textContent = networkExportStyle();
    clone.insertBefore(styleEl, clone.firstChild);

    const svgText = new XMLSerializer().serializeToString(clone);
    const img = new Image();
    try {
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = () => reject(new Error("Could not render the graph for export."));
        img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgText)}`;
      });
    } catch (err) {
      toast((err && err.message) || "Export failed.");
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(contentWidth * NETWORK_EXPORT_SCALE);
    canvas.height = Math.round(contentHeight * NETWORK_EXPORT_SCALE);
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#f5f6f8";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(async (blob) => {
      if (!blob) {
        toast("Export failed.");
        return;
      }
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      const filename = `agent-network-${stamp}.png`;
      const result = await saveFile(blob, filename, { description: "PNG image", accept: { "image/png": [".png"] } });
      if (result === "picker") toast("Graph exported.");
      else if (result === "download") toast("Graph downloaded.");
    }, "image/png");
  }

  el.networkExportBtn.addEventListener("click", exportNetworkPng);

  el.networkCanvasWrap.addEventListener("wheel", (event) => {
    if (state.network.nodes.size === 0) return;
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? 1.12 : 1 / 1.12);
  }, { passive: false });

  let panPointerId = null;
  let panStart = null;

  el.networkSvg.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".net-node")) return; // let node drags through, not a pan start
    if (state.network.nodes.size === 0) return;
    panPointerId = event.pointerId;
    panStart = { clientX: event.clientX, clientY: event.clientY, viewX: state.network.view.x, viewY: state.network.view.y };
    el.networkSvg.setPointerCapture(event.pointerId);
    el.networkSvg.classList.add("panning");
  });
  el.networkSvg.addEventListener("pointermove", (event) => {
    if (nodeDrag && nodeDrag.pointerId === event.pointerId) {
      moveNodeDrag(event);
      return;
    }
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
    if (nodeDrag && nodeDrag.pointerId === event.pointerId) {
      endNodeDrag(event);
      return;
    }
    if (panPointerId !== event.pointerId) return;
    panPointerId = null;
    panStart = null;
    el.networkSvg.classList.remove("panning");
  }
  el.networkSvg.addEventListener("pointerup", endPan);
  el.networkSvg.addEventListener("pointercancel", endPan);

  // ---------------------------------------------------------------
  // Drag-to-reposition a node. Shares #networkSvg's OWN pointer capture
  // (set on that stable element, never torn down/recreated) rather than
  // capturing on the node's own <g> -- renderNetwork() rebuilds every <g>
  // from scratch on each call (including the ones triggered mid-drag by
  // moveNodeDrag below), so a capture held by the <g> itself would be
  // silently released the instant that element gets replaced, cutting the
  // drag off mid-gesture. #networkSvg's existing pan pointermove/pointerup
  // listeners just above dispatch into this instead of their own pan logic
  // whenever a node drag is in progress (see both functions' own checks),
  // so there's exactly one pointer-capture owner at a time, never both.
  //
  // Doubles as click-to-open-details: a pointerdown+pointerup with no real
  // movement (see the MOVE_THRESHOLD check in moveNodeDrag) opens the node
  // detail drawer instead of having left a dragged position -- this
  // replaces the plain "click" listener a node's <g> used to have, since a
  // browser's native click fires on ANY pointerdown+pointerup pair landing
  // on the same element regardless of how far the pointer traveled in
  // between, which would have also fired after a genuine drag.
  // ---------------------------------------------------------------
  const NODE_DRAG_MOVE_THRESHOLD = 3; // px, in content space -- below this, treat as a click, not a drag
  let nodeDrag = null;

  function startNodeDrag(event, node) {
    event.stopPropagation(); // never let #networkSvg's own pointerdown listener also start a pan
    cancelInstructionsHover(node.id); // a tooltip mid-drag would just be visual noise
    nodeDrag = {
      pointerId: event.pointerId, nodeId: node.id,
      startClientX: event.clientX, startClientY: event.clientY,
      startX: node.x, startY: node.y, moved: false,
    };
    el.networkSvg.setPointerCapture(event.pointerId);
  }

  function moveNodeDrag(event) {
    const scale = state.network.view.scale || 1;
    const dx = (event.clientX - nodeDrag.startClientX) / scale;
    const dy = (event.clientY - nodeDrag.startClientY) / scale;
    if (!nodeDrag.moved && (Math.abs(dx) > NODE_DRAG_MOVE_THRESHOLD || Math.abs(dy) > NODE_DRAG_MOVE_THRESHOLD)) {
      nodeDrag.moved = true;
      state.network.autoFit = false; // a re-fit mid-drag would fight the user's own drag with a competing view change
    }
    if (!nodeDrag.moved) return;
    const stored = state.network.nodes.get(nodeDrag.nodeId);
    if (!stored) return;
    const minCoord = 40; // keeps a dragged node from crossing into negative content-space coordinates, which this SVG's own 0,0-anchored canvas has no way to render
    stored.manualX = Math.max(minCoord, nodeDrag.startX + dx);
    stored.manualY = Math.max(minCoord, nodeDrag.startY + dy);
    renderNetwork();
  }

  function endNodeDrag(event) {
    el.networkSvg.releasePointerCapture(event.pointerId);
    const wasMoved = nodeDrag.moved;
    const nodeId = nodeDrag.nodeId;
    nodeDrag = null;
    if (wasMoved) {
      renderNetwork(); // final settle, in case the triggering move event's own render was superseded by a later one
    } else {
      showNodeDetail(nodeId);
    }
  }

  // ---------------------------------------------------------------
  // Hover-to-preview a node's real agent instructions (its HOCON/ADK
  // system prompt) -- GET /agents/<name>/instructions, backed by this
  // project's own cli.py Flask route, which resolves the name against
  // every registries/*.hocon file. `node.label` (the LAST segment of a
  // node's dotted id, e.g. "CloudArch_Agent" out of
  // "CloudArch_Pipeline.CloudArch_Agent") is what that route expects --
  // agent names are unique across this project's own registries, so the
  // short name alone is enough, no need to resolve the full dotted path.
  //
  // Results are cached by name for the rest of this page's lifetime --
  // an agent's own instructions don't change while this tab is open, so
  // re-fetching on every single hover of the same node would be wasted
  // work. A short hover-intent delay (HOVER_DELAY_MS) avoids firing a
  // fetch for every node the pointer merely passes over while moving
  // toward somewhere else on the canvas.
  // ---------------------------------------------------------------
  const HOVER_DELAY_MS = 250;
  const agentInstructionsCache = new Map(); // name -> {status: "ok"|"error", instructions, description, sourceFile, error}
  let hoverTimer = null;
  let hoveredNodeId = null;

  function scheduleInstructionsHover(node, clientX, clientY) {
    if (nodeDrag) return; // mid-drag -- a tooltip popping up would just be noise
    hoveredNodeId = node.id;
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => showInstructionsTooltip(node, clientX, clientY), HOVER_DELAY_MS);
  }

  function repositionHoverTooltipIfShowing(node, clientX, clientY) {
    if (hoveredNodeId !== node.id || el.netHoverTooltip.hidden) return;
    positionHoverTooltip(clientX, clientY);
  }

  function cancelInstructionsHover(nodeId) {
    if (nodeId != null && hoveredNodeId !== nodeId) return; // a stale leave from a node that isn't the current one
    hoveredNodeId = null;
    clearTimeout(hoverTimer);
    el.netHoverTooltip.hidden = true;
    el.netHoverTooltip.removeAttribute("data-node-label");
  }

  function positionHoverTooltip(clientX, clientY) {
    const tooltip = el.netHoverTooltip;
    const margin = 14;
    let left = clientX + margin;
    let top = clientY + margin;
    const maxLeft = window.innerWidth - tooltip.offsetWidth - margin;
    const maxTop = window.innerHeight - tooltip.offsetHeight - margin;
    if (left > maxLeft) left = Math.max(margin, clientX - tooltip.offsetWidth - margin);
    if (top > maxTop) top = Math.max(margin, maxTop);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  function renderHoverTooltipContent(name, result) {
    const tooltip = el.netHoverTooltip;
    const nameEl = document.createElement("div");
    nameEl.className = "net-hover-tooltip-name";
    nameEl.textContent = name;
    tooltip.innerHTML = "";
    tooltip.appendChild(nameEl);

    if (result.status === "loading") {
      const body = document.createElement("div");
      body.className = "net-hover-tooltip-body";
      body.textContent = "Loading instructions…";
      tooltip.appendChild(body);
      return;
    }
    if (result.status === "error") {
      const body = document.createElement("div");
      body.className = "net-hover-tooltip-body net-hover-tooltip-error";
      body.textContent = result.error;
      tooltip.appendChild(body);
      return;
    }
    if (result.description) {
      const desc = document.createElement("div");
      desc.className = "net-hover-tooltip-desc";
      desc.textContent = result.description;
      tooltip.appendChild(desc);
    }
    const body = document.createElement("div");
    body.className = "net-hover-tooltip-body";
    body.textContent = result.instructions;
    tooltip.appendChild(body);

    if (result.sourceFile) {
      const meta = document.createElement("div");
      meta.className = "net-hover-tooltip-meta";
      meta.textContent = result.sourceFile;
      tooltip.appendChild(meta);
    }
  }

  async function showInstructionsTooltip(node, clientX, clientY) {
    if (hoveredNodeId !== node.id) return; // moved on before the hover-intent delay elapsed
    el.netHoverTooltip.dataset.nodeLabel = node.label;
    el.netHoverTooltip.hidden = false;

    const cached = agentInstructionsCache.get(node.label);
    if (cached) {
      renderHoverTooltipContent(node.label, cached);
      positionHoverTooltip(clientX, clientY);
      return;
    }

    renderHoverTooltipContent(node.label, { status: "loading" });
    positionHoverTooltip(clientX, clientY);

    const baseUrl = currentBaseUrl();
    let result;
    if (!baseUrl) {
      result = { status: "error", error: "Set a Base URL and click Connect first." };
    } else {
      try {
        const res = await fetch(`${baseUrl}/agents/${encodeURIComponent(node.label)}/instructions`, {
          method: "GET",
          headers: { ...authHeaders() },
        });
        const body = await res.json().catch(() => ({}));
        result = res.ok
          ? { status: "ok", instructions: body.instructions, description: body.description, sourceFile: body.source_file }
          : { status: "error", error: body.error || `Request failed (${res.status}).` };
      } catch (err) {
        result = { status: "error", error: (err && err.message) || String(err) };
      }
    }
    agentInstructionsCache.set(node.label, result);
    // Only paint this result if the pointer is still over the SAME node --
    // a fast mouse could have already moved to a different node, or off
    // the graph entirely, before this resolved.
    if (el.netHoverTooltip.dataset.nodeLabel === node.label && hoveredNodeId === node.id) {
      renderHoverTooltipContent(node.label, result);
      positionHoverTooltip(clientX, clientY);
    }
  }

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
  // Data explorer -- hierarchical viewer for the Artefact Browser tab's
  // GET /artifacts/<name> ("process", "design", "requirements", or
  // "proposal_response", picked via the tab's own dropdown), a read-only
  // snapshot of this project's own output/process_data.json /
  // output/design_data.json / output/requirements_summary.json /
  // output/proposal_response.json on whichever backend is connected.
  // Rendered as an expandable tree
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
      const res = await fetch(withSessionIdParam(`${baseUrl}/artifacts/${name}`), {
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
        body.textContent = "Pick an artefact from the dropdown above, then click the refresh icon " +
          "to load that pipeline's current saved output from the connected backend.";
      }
      return;
    }

    renderArtifactTree();
  }

  function renderArtifactTree() {
    el.artifactTree.innerHTML = "";
    const { raw, artifact } = state.dataExplorer;
    if (raw === null) return;
    const rootLabel = ["design", "requirements", "proposal_response"].includes(artifact) ? artifact : "process";
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

  el.artifactSelect.addEventListener("change", () => {
    const name = el.artifactSelect.value;
    if (name === state.dataExplorer.artifact) return; // already the active one
    state.dataExplorer.artifact = name;
    loadArtifact(name);
  });

  el.artifactRefreshBtn.addEventListener("click", () => loadArtifact(state.dataExplorer.artifact));

  // Downloads the real process_data.json/design_data.json/
  // requirements_summary.json/proposal_response.json file (vs. the tree
  // view loadArtifact above renders from) -- re-attaching this exact
  // file to a later chat turn (the composer's own "attach file" button)
  // restores it verbatim as the active process/design/requirements
  // summary/proposal response, without re-running the pipeline -- see
  // both backends' Process_Import_Agent/Design_Import_Agent for how a
  // re-uploaded process_data.json/design_data.json is recognized by name
  // and restored rather than re-extracted, and Requirements_Summary_Agent's/
  // Proposal_Response_Pipeline's own literal-restore STEPs for
  // requirements_summary.json/proposal_response.json.
  const ARTIFACT_FILENAMES = {
    requirements: "requirements_summary.json",
    proposal_response: "proposal_response.json",
  };

  async function downloadArtifactJson() {
    const artifact = state.dataExplorer.artifact; // "process", "design", "requirements", or "proposal_response"
    const blob = await fetchArtifactBlob(`/artifacts/${artifact}/download`);
    if (!blob) return;
    // requirements_summary.json/proposal_response.json have no "_data.json"
    // suffix, unlike process/design -- the real on-disk filename, not a
    // derived pattern.
    const filename = ARTIFACT_FILENAMES[artifact] || `${artifact}_data.json`;
    const result = await saveFile(blob, filename, {
      description: "JSON file", accept: { "application/json": [".json"] },
    });
    if (result === "picker") toast(`${filename} saved.`);
    else if (result === "download") toast(`${filename} downloaded.`);
  }
  el.artifactDownloadJsonBtn.addEventListener("click", downloadArtifactJson);

  // ---------------------------------------------------------------
  // Generated documents download popover -- GET /artifacts/documents
  // lists every .docx currently in output/ (there's no fixed filename
  // for these: each one is named after whatever process/design was
  // actually generated, see cli.py's own _list_output_documents), and
  // each row's download button fetches the real bytes via GET
  // /artifacts/documents/<filename>/download and hands them to
  // saveFile -- a plain <a download> wouldn't carry the Authorization/
  // X-API-Key header a configured backend requires, so the bytes have
  // to come through fetch() like every other authenticated call this
  // page makes, not a direct browser navigation.
  // ---------------------------------------------------------------
  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatRelativeTime(isoString) {
    const diffMs = Date.now() - new Date(isoString).getTime();
    const diffMin = Math.round(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.round(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    return `${Math.round(diffHr / 24)}d ago`;
  }

  // Fetches `path` (e.g. "/artifacts/documents/Foo.docx/download") as a
  // Blob, surfacing the backend's own JSON {"error": "..."} on a non-2xx
  // response instead of a generic failure -- shared by every download
  // button on this page (documents popover + the CloudArch tab's own
  // "Download XML" button below).
  async function fetchArtifactBlob(path) {
    const baseUrl = currentBaseUrl();
    if (!baseUrl) {
      toast("Set a Base URL and click Connect first.");
      return null;
    }
    try {
      const res = await fetch(withSessionIdParam(`${baseUrl}${path}`), { method: "GET", headers: { ...authHeaders() } });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        toast(body.error || `Download failed (${res.status}).`);
        return null;
      }
      return await res.blob();
    } catch (err) {
      toast((err && err.message) || "Download failed.");
      return null;
    }
  }

  async function downloadDocument(filename) {
    const blob = await fetchArtifactBlob(`/artifacts/documents/${encodeURIComponent(filename)}/download`);
    if (!blob) return;
    const result = await saveFile(blob, filename, {
      description: "Word document",
      accept: { "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"] },
    });
    if (result === "picker") toast("Document saved.");
    else if (result === "download") toast("Document downloaded.");
  }

  function renderDocumentsPopover(documents) {
    el.documentsPopoverList.innerHTML = "";
    if (documents.length === 0) {
      const empty = document.createElement("div");
      empty.className = "documents-popover-empty";
      empty.textContent = "No generated documents yet.";
      el.documentsPopoverList.appendChild(empty);
      return;
    }
    documents.forEach((doc) => {
      const row = document.createElement("div");
      row.className = "document-row";

      const icon = document.createElement("div");
      icon.className = "document-row-icon";
      icon.innerHTML = `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 1.5h5.5L12.5 4.5V14.5h-8.5z"></path><path d="M9.5 1.5V4.5H12.5"></path>
      </svg>`;

      const info = document.createElement("div");
      info.className = "document-row-info";
      const name = document.createElement("div");
      name.className = "document-row-name";
      name.textContent = doc.filename;
      name.title = doc.filename;
      const meta = document.createElement("div");
      meta.className = "document-row-meta";
      meta.textContent = `${formatBytes(doc.size_bytes)} · ${formatRelativeTime(doc.modified)}`;
      info.append(name, meta);

      const downloadBtn = document.createElement("button");
      downloadBtn.type = "button";
      downloadBtn.className = "document-row-download";
      downloadBtn.title = `Download ${doc.filename}`;
      downloadBtn.setAttribute("aria-label", `Download ${doc.filename}`);
      downloadBtn.innerHTML = `<svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 3v10M10 13l-4-4M10 13l4-4"></path><path d="M4 15.5v1a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-1"></path>
      </svg>`;
      downloadBtn.addEventListener("click", async () => {
        downloadBtn.disabled = true;
        try {
          await downloadDocument(doc.filename);
        } finally {
          downloadBtn.disabled = false;
        }
      });

      row.append(icon, info, downloadBtn);
      el.documentsPopoverList.appendChild(row);
    });
  }

  async function loadDocumentsPopover() {
    el.documentsPopoverList.innerHTML = "";
    const loading = document.createElement("div");
    loading.className = "documents-popover-empty";
    loading.textContent = "Loading…";
    el.documentsPopoverList.appendChild(loading);

    const baseUrl = currentBaseUrl();
    if (!baseUrl) {
      el.documentsPopoverList.innerHTML = "";
      const empty = document.createElement("div");
      empty.className = "documents-popover-empty";
      empty.textContent = "Set a Base URL and click Connect first.";
      el.documentsPopoverList.appendChild(empty);
      return;
    }
    try {
      const res = await fetch(withSessionIdParam(`${baseUrl}/artifacts/documents`), { method: "GET", headers: { ...authHeaders() } });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || `Request failed (${res.status}).`);
      renderDocumentsPopover(body.documents || []);
    } catch (err) {
      el.documentsPopoverList.innerHTML = "";
      const errorEl = document.createElement("div");
      errorEl.className = "documents-popover-empty";
      errorEl.textContent = (err && err.message) || "Could not load documents.";
      el.documentsPopoverList.appendChild(errorEl);
    }
  }

  function openDocumentsPopover() {
    el.documentsPopover.hidden = false;
    el.documentsBtn.setAttribute("aria-expanded", "true");
    loadDocumentsPopover();
    document.addEventListener("pointerdown", onDocumentsPopoverOutsideClick);
    document.addEventListener("keydown", onDocumentsPopoverEscape);
  }

  function closeDocumentsPopover() {
    el.documentsPopover.hidden = true;
    el.documentsBtn.setAttribute("aria-expanded", "false");
    document.removeEventListener("pointerdown", onDocumentsPopoverOutsideClick);
    document.removeEventListener("keydown", onDocumentsPopoverEscape);
  }

  function onDocumentsPopoverOutsideClick(event) {
    if (el.documentsPopover.contains(event.target) || el.documentsBtn.contains(event.target)) return;
    closeDocumentsPopover();
  }

  function onDocumentsPopoverEscape(event) {
    if (event.key === "Escape") closeDocumentsPopover();
  }

  el.documentsBtn.addEventListener("click", () => {
    if (el.documentsPopover.hidden) openDocumentsPopover();
    else closeDocumentsPopover();
  });
  el.documentsPopoverCloseBtn.addEventListener("click", closeDocumentsPopover);

  // ---------------------------------------------------------------
  // Cloud Architecture tab -- renders output/cloudarch_drawio.xml (GET
  // /artifacts/cloudarch) as an actual diagram: real positions/sizes/
  // colors parsed straight out of the mxGraph XML's own <mxCell>/
  // <mxGeometry> elements, unlike the Agent Network tab's graph (which has
  // no real diagram to draw from and lays itself out from scratch). Real
  // AWS/Azure/GCP provider icons are NOT rendered -- no stencil library is
  // bundled, consistent with this page's own no-external-dependency rule
  // (see the top of this file) -- each icon cell instead draws as a small
  // neutral placeholder in its own already-correct reserved slot, so box
  // proportions and overall layout still look right even without the
  // exact glyph.
  // ---------------------------------------------------------------

  // Parses a semicolon-separated mxGraph style string ("rounded=1;
  // fillColor=#FFFFFF;...") into a plain object. A bare token with no
  // "=value" (e.g. "swimlane") maps to `true`.
  function parseMxStyle(styleStr) {
    const out = {};
    (styleStr || "").split(";").forEach((part) => {
      if (!part) return;
      const eq = part.indexOf("=");
      if (eq === -1) out[part] = true;
      else out[part.slice(0, eq)] = part.slice(eq + 1);
    });
    return out;
  }

  // Parses the raw mxGraph XML text into { vertices, edges }, each
  // carrying its own ABSOLUTE page position -- resolved by walking up its
  // "parent" chain and summing offsets, since this project's own layout
  // engine (process_toolkit.cloudarch.layout) parents zones-in-zones,
  // components-in-zones, and icons-in-components with geometry relative
  // to THEIR OWN parent cell's origin (standard mxGraph container
  // nesting), not flat/absolute coordinates throughout.
  function parseDrawioXml(xmlText) {
    const doc = new DOMParser().parseFromString(xmlText, "text/xml");
    if (doc.querySelector("parsererror")) {
      throw new Error("Could not parse the diagram XML.");
    }

    const cellsById = new Map();
    doc.querySelectorAll("mxCell").forEach((cellEl) => {
      const id = cellEl.getAttribute("id");
      if (id == null) return;
      const geomEl = cellEl.querySelector("mxGeometry");
      const offsetEl = geomEl ? geomEl.querySelector('mxPoint[as="offset"]') : null;
      cellsById.set(id, {
        id,
        parent: cellEl.getAttribute("parent"),
        value: cellEl.getAttribute("value") || "",
        style: parseMxStyle(cellEl.getAttribute("style")),
        isVertex: cellEl.getAttribute("vertex") === "1",
        isEdge: cellEl.getAttribute("edge") === "1",
        source: cellEl.getAttribute("source"),
        target: cellEl.getAttribute("target"),
        x: geomEl ? Number(geomEl.getAttribute("x") || 0) : 0,
        y: geomEl ? Number(geomEl.getAttribute("y") || 0) : 0,
        width: geomEl ? Number(geomEl.getAttribute("width") || 0) : 0,
        height: geomEl ? Number(geomEl.getAttribute("height") || 0) : 0,
        points: geomEl
          ? Array.from(geomEl.querySelectorAll('Array[as="points"] > mxPoint')).map((p) => ({
              x: Number(p.getAttribute("x") || 0),
              y: Number(p.getAttribute("y") || 0),
            }))
          : [],
        offset: offsetEl
          ? { x: Number(offsetEl.getAttribute("x") || 0), y: Number(offsetEl.getAttribute("y") || 0) }
          : null,
      });
    });

    const absoluteCache = new Map();
    function absolutePosition(cell) {
      if (!cell) return { x: 0, y: 0 };
      if (absoluteCache.has(cell.id)) return absoluteCache.get(cell.id);
      const parentId = cell.parent;
      const parentCell = parentId && parentId !== "0" && parentId !== "1" ? cellsById.get(parentId) : null;
      const base = parentCell ? absolutePosition(parentCell) : { x: 0, y: 0 };
      const resolved = { x: base.x + cell.x, y: base.y + cell.y };
      absoluteCache.set(cell.id, resolved);
      return resolved;
    }

    const vertices = [];
    const edges = [];
    cellsById.forEach((cell) => {
      if (cell.id === "0" || cell.id === "1") return; // the two bookkeeping root cells, no real geometry
      if (cell.isVertex) {
        const abs = absolutePosition(cell);
        vertices.push({ ...cell, absX: abs.x, absY: abs.y });
      } else if (cell.isEdge) {
        edges.push(cell);
      }
    });
    return { vertices, edges };
  }

  // Resolves an edge's connection point on `vertex`'s own box, from its
  // style's exitX/exitY (or entryX/entryY) fraction -- mirrors exactly
  // how process_toolkit.cloudarch.layout computed and set those same
  // style keys when it generated this XML. Falls back to the box's
  // center (0.5, 0.5) if the style doesn't pin an explicit point.
  function mxEdgeAnchor(vertex, style, xKey, yKey) {
    const fx = style[xKey] != null ? Number(style[xKey]) : 0.5;
    const fy = style[yKey] != null ? Number(style[yKey]) : 0.5;
    return { x: vertex.absX + fx * vertex.width, y: vertex.absY + fy * vertex.height };
  }

  // A component's own icon child cell carries a drawio stencil reference
  // in its style -- no stencil library is bundled (see this tab's own
  // README section), so the exact provider pictogram can't be drawn.
  // Instead, classify the REAL service token into a small set of generic
  // SERVICE-CATEGORY glyphs (compute, database, storage, ...) that are at
  // least visually distinct and recognizable, rather than every service
  // rendering as an identical flat colored box. Order matters -- more
  // specific patterns are checked before generic catch-alls (e.g.
  // "gateway" is checked after "api_gateway"-style patterns so an API
  // Gateway doesn't get misclassified as a generic network gateway).
  //
  // The token to classify is resIcon if present, else shape (see
  // classifyShapeToken's own docstring) -- confirmed directly against a
  // real generated AWS diagram's icon cells, e.g.
  // style="...shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.aurora;"
  // -- using `shape` there would classify EVERY AWS4 icon as the same
  // generic "resourceIcon" wrapper token, never the real service
  // (confirmed: that diagram's waf/alb/ec2/aurora/kms/etc. icons all
  // share that one wrapper shape; only resIcon actually varies).
  const CLOUDARCH_ICON_CATEGORIES = [
    // Leading \b only, deliberately never trailing -- the real AWS4 icon
    // set uses numbered variants for many icons (confirmed directly:
    // "endpoint_2" in a real generated diagram), and "_" counts as a
    // \w word character, so a trailing \b (e.g. \bkms\b) would silently
    // never match "kms_2" or similar. Leading \b is kept so these short,
    // easily-coincidental substrings (ec2, s3, iam, ...) don't also match
    // inside an unrelated longer word.
    { test: /lambda|cloud_functions|cloud_run|app_engine|azure_functions|logic_apps|function/, key: "function" },
    { test: /\bec2|compute_engine|virtual_machines|\binstance|app_service|container_instances/, key: "compute" },
    {
      test: /\brds|cloud_sql|sql_database|dynamodb|bigtable|cosmos_db|firestore|\baurora|elasticache|redshift|documentdb|database/,
      key: "database",
    },
    { test: /\bs3|cloud_storage|blob_storage|\bstorage/, key: "storage" },
    { test: /load_balanc|application_gateway/, key: "loadbalancer" },
    { test: /\bsqs|\bsns|pubsub|pub_sub|service_bus|event_hub|\bqueue|\btopic/, key: "queue" },
    { test: /api_gateway|\bapim|api_management/, key: "gateway" },
    { test: /cloudwatch|\bmonitor|\binsights/, key: "monitoring" },
    { test: /secrets_manager|\bsecret|\bvault|firewall|security|\bwaf|key_vault|\bkms|\biam/, key: "security" },
    { test: /cloudfront|\bcdn|front_door|\binternet/, key: "cdn" },
    { test: /route53|cloud_dns|\bdns/, key: "dns" },
    { test: /\bvpc|virtual_network|\bvnet|\bendpoint|\bnetwork|\bvpn/, key: "network" },
    { test: /kubernetes|\beks|\bgke|\baks|container/, key: "container" },
    { test: /\buser|\bclient|browser|mobile|person/, key: "user" },
    { test: /gateway/, key: "gateway" },
  ];

  // Prefers resIcon over shape -- see CLOUDARCH_ICON_CATEGORIES's own
  // comment on why.
  function classifyShapeToken(style) {
    const lower = (style.resIcon || style.shape || "").toLowerCase();
    const match = CLOUDARCH_ICON_CATEGORIES.find((c) => c.test.test(lower));
    return match ? match.key : "generic";
  }

  // Draws one glyph into `g` (an already-positioned/sized SVG <g>), scaled
  // to the icon cell's own square box (`size` x `size` -- ICON_SIZE in the
  // generator, always square by construction) and colored with the
  // REAL icon_color the generator chose for this specific component.
  // Deliberately built from only circle/ellipse/rect/line/polygon (no
  // hand-computed bezier/arc paths) -- simple primitives whose rendering
  // can't go subtly wrong the way a mistyped arc-flag or control point
  // could, which matters here since this couldn't be visually test-driven
  // in a real browser while writing it.
  function appendCloudArchGlyph(g, category, size, color) {
    const s = size;
    const cx = s / 2;
    const cy = s / 2;
    g.setAttribute("fill", "none");
    g.setAttribute("stroke", color);
    g.setAttribute("stroke-width", String(Math.max(1.5, s * 0.055)));
    g.setAttribute("stroke-linecap", "round");
    g.setAttribute("stroke-linejoin", "round");

    function shape(tag, attrs) {
      const node = document.createElementNS(SVG_NS, tag);
      Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, String(v)));
      g.appendChild(node);
    }

    switch (category) {
      case "compute":
        [0, 1, 2].forEach((i) => {
          const y = s * 0.18 + i * s * 0.24;
          shape("rect", { x: s * 0.18, y, width: s * 0.64, height: s * 0.16, rx: s * 0.03 });
          shape("circle", { cx: s * 0.26, cy: y + s * 0.08, r: s * 0.02, fill: color, stroke: "none" });
        });
        break;
      case "database":
        shape("ellipse", { cx, cy: s * 0.26, rx: s * 0.3, ry: s * 0.11 });
        shape("ellipse", { cx, cy: s * 0.74, rx: s * 0.3, ry: s * 0.11 });
        shape("line", { x1: cx - s * 0.3, y1: s * 0.26, x2: cx - s * 0.3, y2: s * 0.74 });
        shape("line", { x1: cx + s * 0.3, y1: s * 0.26, x2: cx + s * 0.3, y2: s * 0.74 });
        break;
      case "storage":
        shape("polygon", {
          points: `${s * 0.2},${s * 0.3} ${s * 0.8},${s * 0.3} ${s * 0.7},${s * 0.78} ${s * 0.3},${s * 0.78}`,
        });
        shape("line", { x1: s * 0.32, y1: s * 0.3, x2: s * 0.32, y2: s * 0.2 });
        shape("line", { x1: s * 0.68, y1: s * 0.3, x2: s * 0.68, y2: s * 0.2 });
        break;
      case "function":
        shape("polygon", {
          points: `${s * 0.56},${s * 0.14} ${s * 0.3},${s * 0.56} ${s * 0.46},${s * 0.56} ` +
            `${s * 0.4},${s * 0.86} ${s * 0.7},${s * 0.42} ${s * 0.52},${s * 0.42}`,
          fill: color, stroke: "none",
        });
        break;
      case "loadbalancer":
        shape("circle", { cx, cy, r: s * 0.09, fill: color, stroke: "none" });
        [[s * 0.2, s * 0.2], [s * 0.8, s * 0.2], [s * 0.2, s * 0.8], [s * 0.8, s * 0.8]].forEach(([x, y]) => {
          shape("line", { x1: cx, y1: cy, x2: x, y2: y });
          shape("circle", { cx: x, cy: y, r: s * 0.06 });
        });
        break;
      case "queue":
        [0, 1, 2].forEach((i) => {
          shape("rect", { x: s * 0.16 + i * s * 0.1, y: s * 0.3, width: s * 0.48, height: s * 0.4, rx: s * 0.04 });
        });
        break;
      case "gateway":
        shape("line", { x1: s * 0.3, y1: s * 0.18, x2: s * 0.3, y2: s * 0.82 });
        shape("line", { x1: s * 0.7, y1: s * 0.18, x2: s * 0.7, y2: s * 0.82 });
        shape("line", { x1: s * 0.15, y1: cy, x2: s * 0.78, y2: cy });
        shape("polygon", {
          points: `${s * 0.7},${s * 0.4} ${s * 0.86},${cy} ${s * 0.7},${s * 0.6}`,
          fill: color, stroke: "none",
        });
        break;
      case "network":
        [[cx, s * 0.2], [s * 0.22, s * 0.68], [s * 0.78, s * 0.68]].forEach(([x, y]) => {
          shape("circle", { cx: x, cy: y, r: s * 0.09 });
        });
        shape("line", { x1: cx, y1: s * 0.2, x2: s * 0.22, y2: s * 0.68 });
        shape("line", { x1: cx, y1: s * 0.2, x2: s * 0.78, y2: s * 0.68 });
        shape("line", { x1: s * 0.22, y1: s * 0.68, x2: s * 0.78, y2: s * 0.68 });
        break;
      case "container":
        shape("polygon", {
          points: [[0.5, 0.12], [0.85, 0.3], [0.85, 0.7], [0.5, 0.88], [0.15, 0.7], [0.15, 0.3]]
            .map(([x, y]) => `${s * x},${s * y}`).join(" "),
        });
        break;
      case "security":
        shape("polygon", {
          points: [[0.5, 0.13], [0.82, 0.26], [0.82, 0.55], [0.5, 0.88], [0.18, 0.55], [0.18, 0.26]]
            .map(([x, y]) => `${s * x},${s * y}`).join(" "),
        });
        break;
      case "cdn":
        shape("circle", { cx, cy, r: s * 0.32 });
        shape("ellipse", { cx, cy, rx: s * 0.14, ry: s * 0.32 });
        shape("line", { x1: cx - s * 0.32, y1: cy, x2: cx + s * 0.32, y2: cy });
        break;
      case "dns":
        shape("circle", { cx, cy, r: s * 0.32 });
        shape("line", { x1: cx - s * 0.3, y1: cy - s * 0.1, x2: cx + s * 0.3, y2: cy - s * 0.1 });
        shape("line", { x1: cx - s * 0.3, y1: cy + s * 0.1, x2: cx + s * 0.3, y2: cy + s * 0.1 });
        break;
      case "user":
        shape("circle", { cx, cy: s * 0.32, r: s * 0.16 });
        shape("polygon", {
          points: `${s * 0.22},${s * 0.84} ${s * 0.78},${s * 0.84} ${s * 0.68},${s * 0.58} ${s * 0.32},${s * 0.58}`,
        });
        break;
      case "monitoring":
        [0.25, 0.45, 0.65].forEach((h, i) => {
          shape("rect", { x: s * (0.22 + i * 0.2), y: s * (0.82 - h), width: s * 0.12, height: s * h });
        });
        break;
      default: // generic cloud -- three overlapping circles approximate a cloud silhouette
        shape("circle", { cx: s * 0.38, cy: s * 0.56, r: s * 0.2 });
        shape("circle", { cx: s * 0.6, cy: s * 0.46, r: s * 0.24 });
        shape("circle", { cx: s * 0.76, cy: s * 0.58, r: s * 0.16 });
    }
  }

  function renderCloudArchDiagram() {
    const { loading, raw } = state.cloudarch;
    // A parse failure is folded into the same "error" bucket as a fetch
    // failure (both cleared on the next successful load/parse) --
    // discovered here rather than in loadCloudArchDiagram itself, since
    // the XML only actually gets parsed at render time (re-parsed fresh
    // on every render -- see state.cloudarch's own comment).
    let error = state.cloudarch.error;
    let vertices = [];
    let edges = [];
    if (!error && !loading && raw !== null) {
      try {
        ({ vertices, edges } = parseDrawioXml(raw));
      } catch (err) {
        error = (err && err.message) || "Could not parse the diagram.";
      }
    }

    if (loading) {
      el.cloudarchStatus.textContent = "Loading…";
    } else if (error) {
      el.cloudarchStatus.textContent = "Error";
    } else if (raw !== null) {
      el.cloudarchStatus.textContent = `${vertices.length} shape${vertices.length === 1 ? "" : "s"}, ` +
        `${edges.length} connection${edges.length === 1 ? "" : "s"}`;
    } else {
      el.cloudarchStatus.textContent = "Not loaded";
    }

    const hasData = raw !== null && !loading && !error && vertices.length > 0;
    el.cloudarchSvg.toggleAttribute("hidden", !hasData);
    el.cloudarchEmpty.style.display = hasData ? "none" : "";

    if (!hasData) {
      state.cloudarch.contentWidth = null;
      state.cloudarch.contentHeight = null;
      el.cloudarchSvg.innerHTML = "";
      const heading = el.cloudarchEmpty.querySelector("h2");
      const body = el.cloudarchEmpty.querySelector("p");
      if (loading) {
        heading.textContent = "Loading…";
        body.textContent = "Fetching the current cloud architecture diagram from the connected backend…";
      } else if (error) {
        heading.textContent = "Couldn't load the diagram";
        body.textContent = error;
      } else if (raw !== null && vertices.length === 0) {
        heading.textContent = "Diagram is empty";
        body.textContent = "output/cloudarch_drawio.xml exists but contains no shapes.";
      } else {
        heading.textContent = "No diagram loaded";
        body.textContent = "Click the refresh icon to load the connected backend's current " +
          "output/cloudarch_drawio.xml cloud architecture diagram.";
      }
      return;
    }

    const byId = new Map(vertices.map((v) => [v.id, v]));

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    vertices.forEach((v) => {
      minX = Math.min(minX, v.absX);
      minY = Math.min(minY, v.absY);
      maxX = Math.max(maxX, v.absX + v.width);
      maxY = Math.max(maxY, v.absY + v.height);
    });
    const contentWidth = Math.max(1, maxX - minX);
    const contentHeight = Math.max(1, maxY - minY);
    // Stashed for Export PNG, which renders the FULL diagram at its own
    // native size regardless of whatever zoom/pan the on-screen view
    // currently has -- see exportCloudArchPng.
    state.cloudarch.contentWidth = contentWidth;
    state.cloudarch.contentHeight = contentHeight;

    const wrapWidth = el.cloudarchCanvasWrap.clientWidth || 600;
    const wrapHeight = el.cloudarchCanvasWrap.clientHeight || 400;
    el.cloudarchSvg.setAttribute("viewBox", `0 0 ${wrapWidth} ${wrapHeight}`);
    el.cloudarchSvg.innerHTML = "";

    const defs = document.createElementNS(SVG_NS, "defs");
    defs.innerHTML = `
      <marker id="cloudarchArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 Z" class="cloudarch-arrow"></path>
      </marker>
    `;
    el.cloudarchSvg.appendChild(defs);

    const viewport = document.createElementNS(SVG_NS, "g");
    viewport.setAttribute("id", "cloudarchViewport");

    // Vertices BEFORE edges -- matches real mxGraph z-order: a cell's
    // children paint on top of it, and edges (always parent="1", always
    // emitted LAST in the generator's own document order -- see
    // process_toolkit.cloudarch.layout's own edge-emitting loop, which
    // runs after every zone/component loop) are therefore always the
    // topmost layer, over every zone/component regardless of nesting
    // depth. Getting this backwards (edges first, as an earlier version
    // of this function did) looked fine for a cross-zone edge crossing
    // open space, but any edge fully CONTAINED within one zone's own
    // bounding box -- i.e. exactly what "an internal connection between
    // two things in the same zone" looks like -- was then completely
    // painted over by that zone's own opaque background rect, which
    // renders as part of the vertex pass; confirmed directly against a
    // real generated diagram where every such same-zone edge (e.g. an
    // EC2 instance to its own NAT Gateway, both inside one Availability
    // Zone swimlane) was invisible for exactly this reason.
    const vertexGroup = document.createElementNS(SVG_NS, "g");
    vertices.forEach((v) => {
      const style = v.style;
      const g = document.createElementNS(SVG_NS, "g");
      g.setAttribute("class", "cloudarch-node");
      g.setAttribute("transform", `translate(${v.absX - minX}, ${v.absY - minY})`);

      // A component's own icon child cell (style="shape=mxgraph.<provider>.
      // <name>;fillColor=...;...") -- draw a recognizable service-category
      // glyph instead of a flat colored box; see appendCloudArchGlyph's own
      // docstring. Gated on an EMPTY value, not just style.shape alone --
      // a real VPC/VNet zone container also sets shape (e.g.
      // "shape=mxgraph.aws4.group") but carries a real label ("<b>AWS
      // VPC</b>") and a full zone-sized box, confirmed against a real
      // generated diagram -- routing that into the icon-glyph branch
      // would draw one giant, wrongly-scaled glyph instead of the zone's
      // own border+label. An icon cell's own value is always "" (also
      // confirmed directly), so this reliably tells the two apart.
      if (style.shape && !v.value) {
        appendCloudArchGlyph(g, classifyShapeToken(style), Math.min(v.width, v.height), style.fillColor || "#5f6368");
        vertexGroup.appendChild(g);
        return;
      }

      const isImagePlaceholder = style.image != null; // the rare Azure VNet "badge" cell -- no fillColor/strokeColor of its own
      const rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("width", String(v.width));
      rect.setAttribute("height", String(v.height));
      const arcSize = style.arcSize ? Number(style.arcSize) : 4;
      rect.setAttribute("rx", style.rounded === "1" ? String(Math.min(v.width, v.height) * arcSize / 100) : "0");
      rect.setAttribute("fill", isImagePlaceholder ? "var(--accent-soft)" : (style.fillColor || "#ffffff"));
      rect.setAttribute("stroke", isImagePlaceholder ? "var(--accent)" : (style.strokeColor || "#9aa0a6"));
      rect.setAttribute("stroke-width", style.strokeWidth || "1");
      if (style.dashed === "1") rect.setAttribute("stroke-dasharray", "4,3");
      g.appendChild(rect);

      const isSwimlane = !!style.swimlane;
      const headerHeight = isSwimlane ? Number(style.startSize || 20) : v.height;
      if (isSwimlane && v.height > headerHeight) {
        const divider = document.createElementNS(SVG_NS, "line");
        divider.setAttribute("x1", "0");
        divider.setAttribute("x2", String(v.width));
        divider.setAttribute("y1", String(headerHeight));
        divider.setAttribute("y2", String(headerHeight));
        divider.setAttribute("stroke", style.strokeColor || "#9aa0a6");
        g.appendChild(divider);
      }

      // The cell's own `value` is this project's own layout-engine-authored
      // HTML ("<b>Title</b><br/>bullet one<br/>bullet two") -- the exact
      // same trust tier as an agent reply's markdown-lite HTML, which this
      // file already renders via innerHTML elsewhere (see addMessage/
      // renderMarkdownLite) -- so a foreignObject + innerHTML here is
      // consistent with that existing precedent, not a new risk class.
      // (Contrast the Process/Design tree viewer and Agent Network graph,
      // which render arbitrary JSON/identifier DATA and deliberately stick
      // to textContent -- there is no such HTML-label convention there.)
      if (v.value && v.width > 4 && headerHeight > 4) {
        // spacingTop/spacingLeft -- how far the generator pushed this
        // label's own text away from the box's top/left edge (e.g. 74px
        // for a component WITH an icon, reserving exactly the icon's own
        // slot so the two don't overlap -- see
        // process_toolkit.cloudarch.layout.SPACING_TOP_WITH_ICON). Ignoring
        // these previously meant every label started right at the box's
        // top edge regardless, overlapping any icon drawn there.
        const spacingTop = Math.min(headerHeight - 4, Number(style.spacingTop || 0));
        const spacingLeft = Math.min(v.width - 4, Number(style.spacingLeft || 0));
        const fo = document.createElementNS(SVG_NS, "foreignObject");
        fo.setAttribute("x", String(2 + spacingLeft));
        fo.setAttribute("y", String(2 + spacingTop));
        fo.setAttribute("width", String(Math.max(0, v.width - 4 - spacingLeft)));
        fo.setAttribute("height", String(Math.max(0, headerHeight - 4 - spacingTop)));
        const label = document.createElement("div");
        label.className = "cloudarch-cell-label";
        label.style.textAlign = style.align === "left" ? "left" : style.align === "right" ? "right" : "center";
        label.style.justifyContent = style.verticalAlign === "top" ? "flex-start" : "center";
        label.style.color = style.fontColor || "#202124";
        label.style.fontSize = `${style.fontSize || 11}px`;
        label.innerHTML = v.value;
        fo.appendChild(label);
        g.appendChild(fo);
      }

      vertexGroup.appendChild(g);
    });
    viewport.appendChild(vertexGroup);

    const edgeGroup = document.createElementNS(SVG_NS, "g");
    edges.forEach((edge) => {
      const src = byId.get(edge.source);
      const tgt = byId.get(edge.target);
      if (!src || !tgt) return; // dangling reference -- skip rather than draw a broken edge

      const exit = mxEdgeAnchor(src, edge.style, "exitX", "exitY");
      const entry = mxEdgeAnchor(tgt, edge.style, "entryX", "entryY");
      const pathPts = [exit, ...edge.points, entry];

      const polyline = document.createElementNS(SVG_NS, "polyline");
      polyline.setAttribute("points", pathPts.map((p) => `${p.x - minX},${p.y - minY}`).join(" "));
      polyline.setAttribute("class", "cloudarch-edge");
      polyline.setAttribute("stroke", edge.style.strokeColor || "#5f6368");
      if (edge.style.dashed === "1") polyline.setAttribute("stroke-dasharray", "5,4");
      polyline.setAttribute("marker-end", "url(#cloudarchArrow)");
      edgeGroup.appendChild(polyline);

      const labelText = htmlToText(edge.value);
      if (labelText) {
        // The generator's own label placement (a fraction along the path,
        // plus a collision-avoidance pixel offset -- see
        // process_toolkit.cloudarch.layout's own edge-emitting code) isn't
        // reconstructed here; the path's own midpoint is a close enough
        // stand-in for a readable rendering.
        const mid = pathPts[Math.floor(pathPts.length / 2)];
        const label = document.createElementNS(SVG_NS, "text");
        label.setAttribute("x", String(mid.x - minX));
        label.setAttribute("y", String(mid.y - minY - 4));
        label.setAttribute("text-anchor", "middle");
        label.setAttribute("class", "cloudarch-edge-label");
        label.textContent = labelText;
        edgeGroup.appendChild(label);
      }
    });
    viewport.appendChild(edgeGroup);

    el.cloudarchSvg.appendChild(viewport);

    if (state.cloudarch.autoFit) {
      computeCloudArchFitView(contentWidth, contentHeight, wrapWidth, wrapHeight);
    }
    applyCloudArchTransform();
  }

  async function loadCloudArchDiagram() {
    const baseUrl = currentBaseUrl();
    if (!baseUrl) {
      toast("Set a Base URL and click Connect first.");
      return;
    }
    state.cloudarch.loading = true;
    state.cloudarch.error = null;
    renderCloudArchDiagram();
    try {
      const res = await fetch(withSessionIdParam(`${baseUrl}/artifacts/cloudarch`), {
        method: "GET",
        headers: { ...authHeaders() },
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.error || `Request failed (${res.status}).`);
      }
      state.cloudarch.raw = body.data;
      state.cloudarch.autoFit = true;
    } catch (err) {
      state.cloudarch.raw = null;
      state.cloudarch.error = (err && err.message) || String(err);
    } finally {
      state.cloudarch.loading = false;
      renderCloudArchDiagram();
    }
  }

  el.cloudarchRefreshBtn.addEventListener("click", loadCloudArchDiagram);

  const CLOUDARCH_EXPORT_SCALE = 2; // 2x pixel density, so exported text/icons stay crisp rather than blown up from a small on-screen view

  // The exported SVG is serialized into a STANDALONE document with no
  // access to this page's own stylesheet/CSS variables, so the handful
  // of classes the live rendering actually depends on (cloudarch-edge/
  // -arrow/-edge-label/-cell-label) need their values inlined explicitly.
  //
  // Deliberately LIGHT-THEME LITERALS, not this page's CURRENT resolved
  // --text/--text-faint (the previous version's approach) -- the export
  // canvas below always paints a solid #ffffff background regardless of
  // theme (see exportCloudArchPng's own comment on why), so text colors
  // must match that fixed white background unconditionally too. Reading
  // the live theme's CSS variables instead was confirmed to produce a
  // genuinely unreadable export: in dark mode, --text/--text-faint
  // resolve to near-white (#eceef3 / #6b7082), rendered straight onto
  // this always-white background -- exactly a real report of edge/arrow
  // labels being "white on white" in an exported PNG.
  function cloudArchExportStyle() {
    const cs = getComputedStyle(document.documentElement);
    const textFaint = "#9299a8"; // light theme's own --text-faint (style.css :root)
    const text = "#1b1d22"; // light theme's own --text (style.css :root)
    const fontFamily = cs.getPropertyValue("--font").trim() || "sans-serif";
    return `
      .cloudarch-edge { stroke-width: 1.6; fill: none; }
      .cloudarch-arrow { fill: ${textFaint}; }
      .cloudarch-edge-label { font-size: 10.5px; font-weight: 650; fill: ${text}; }
      .cloudarch-cell-label {
        width: 100%; height: 100%; display: flex; flex-direction: column;
        justify-content: center; overflow: hidden; line-height: 1.3; font-family: ${fontFamily};
      }
    `;
  }

  // Exports the FULL diagram (not whatever's currently zoomed/panned
  // into view) as a PNG, at CLOUDARCH_EXPORT_SCALE x its own native
  // pixel size so text/icons stay legible rather than scaling up a tiny
  // on-screen thumbnail. Clones the live SVG rather than re-rendering
  // from scratch, so the export always matches exactly what's on screen
  // (minus zoom/pan) with zero duplicated drawing logic.
  async function exportCloudArchPng() {
    const { contentWidth, contentHeight } = state.cloudarch;
    if (!contentWidth || !contentHeight || el.cloudarchSvg.hasAttribute("hidden")) {
      toast("Load a diagram first.");
      return;
    }

    const clone = el.cloudarchSvg.cloneNode(true);
    clone.removeAttribute("hidden");
    clone.setAttribute("viewBox", `0 0 ${contentWidth} ${contentHeight}`);
    clone.setAttribute("width", String(contentWidth));
    clone.setAttribute("height", String(contentHeight));

    // Reset to the FULL, un-zoomed/un-panned view -- an export should
    // show the whole diagram, not whatever crop/zoom level the user
    // happens to be looking at right now.
    const viewport = clone.querySelector("#cloudarchViewport");
    if (viewport) viewport.setAttribute("transform", "translate(0, 0) scale(1)");

    // A solid white background (matching the diagram XML's own
    // background="#FFFFFF" -- see process_toolkit.cloudarch.layout --
    // rather than this page's current theme) since the live on-screen
    // SVG has no background of its own (it relies on its CSS canvas
    // wrapper) and a transparent PNG background looks broken in most
    // viewers.
    const bg = document.createElementNS(SVG_NS, "rect");
    bg.setAttribute("width", String(contentWidth));
    bg.setAttribute("height", String(contentHeight));
    bg.setAttribute("fill", "#ffffff");
    clone.insertBefore(bg, clone.firstChild);

    const styleEl = document.createElementNS(SVG_NS, "style");
    styleEl.textContent = cloudArchExportStyle();
    clone.insertBefore(styleEl, clone.firstChild);

    const svgText = new XMLSerializer().serializeToString(clone);
    const img = new Image();
    try {
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = () => reject(new Error("Could not render the diagram for export."));
        img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgText)}`;
      });
    } catch (err) {
      toast((err && err.message) || "Export failed.");
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(contentWidth * CLOUDARCH_EXPORT_SCALE);
    canvas.height = Math.round(contentHeight * CLOUDARCH_EXPORT_SCALE);
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(async (blob) => {
      if (!blob) {
        toast("Export failed.");
        return;
      }
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      const filename = `cloud-architecture-${stamp}.png`;
      const result = await saveFile(blob, filename, { description: "PNG image", accept: { "image/png": [".png"] } });
      if (result === "picker") toast("Diagram exported.");
      else if (result === "download") toast("Diagram downloaded.");
    }, "image/png");
  }

  el.cloudarchExportBtn.addEventListener("click", exportCloudArchPng);

  // Downloads the real output/cloudarch_drawio.xml file (vs. the on-screen
  // SVG re-rendering exportCloudArchPng above draws from) -- for opening
  // directly in a real draw.io client, not just a PNG snapshot of this
  // page's own best-effort approximation (see this tab's own disclaimer).
  async function downloadCloudArchXml() {
    const blob = await fetchArtifactBlob("/artifacts/cloudarch/download");
    if (!blob) return;
    const result = await saveFile(blob, "cloudarch_drawio.xml", {
      description: "XML file", accept: { "application/xml": [".xml"] },
    });
    if (result === "picker") toast("Diagram XML saved.");
    else if (result === "download") toast("Diagram XML downloaded.");
  }
  el.cloudarchDownloadXmlBtn.addEventListener("click", downloadCloudArchXml);

  // Downloads the generated Infrastructure-as-Code zip (see
  // CloudArch_IaC_Pipeline, both ports) -- a 404 here just means the IaC
  // pipeline hasn't been run yet this session; fetchArtifactBlob already
  // surfaces that server-reported message via toast.
  async function downloadCloudArchIacZip() {
    const blob = await fetchArtifactBlob("/artifacts/cloudarch_iac/download");
    if (!blob) return;
    const result = await saveFile(blob, "cloudarch_iac.zip", {
      description: "ZIP archive", accept: { "application/zip": [".zip"] },
    });
    if (result === "picker") toast("IaC ZIP saved.");
    else if (result === "download") toast("IaC ZIP downloaded.");
  }
  el.cloudarchDownloadIacBtn.addEventListener("click", downloadCloudArchIacZip);

  // Zoom / pan -- identical mechanics to the Agent Network tab's own
  // section further up (state.cloudarch.view instead of state.network.view,
  // #cloudarchViewport instead of #networkViewport); duplicated rather than
  // shared, the same way the Token Usage tab's own copy of this exact
  // pattern already is in this file.
  function computeCloudArchFitView(contentWidth, contentHeight, wrapWidth, wrapHeight) {
    const padding = 32;
    const scale = Math.min(
      1.15,
      Math.max(MIN_SCALE, Math.min(
        (wrapWidth - padding * 2) / contentWidth,
        (wrapHeight - padding * 2) / contentHeight,
      )),
    );
    state.cloudarch.view = {
      scale,
      x: (wrapWidth - contentWidth * scale) / 2,
      y: (wrapHeight - contentHeight * scale) / 2,
    };
  }

  function applyCloudArchTransform() {
    const viewport = document.getElementById("cloudarchViewport");
    if (!viewport) return;
    const { x, y, scale } = state.cloudarch.view;
    viewport.setAttribute("transform", `translate(${x}, ${y}) scale(${scale})`);
  }

  function zoomCloudArchBy(factor) {
    if (state.cloudarch.raw === null) return;
    const wrapWidth = el.cloudarchCanvasWrap.clientWidth || 600;
    const wrapHeight = el.cloudarchCanvasWrap.clientHeight || 400;
    const view = state.cloudarch.view;
    const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
    const cx = wrapWidth / 2;
    const cy = wrapHeight / 2;
    const contentCx = (cx - view.x) / view.scale;
    const contentCy = (cy - view.y) / view.scale;
    state.cloudarch.view = {
      scale: newScale,
      x: cx - contentCx * newScale,
      y: cy - contentCy * newScale,
    };
    state.cloudarch.autoFit = false;
    applyCloudArchTransform();
  }

  function resetCloudArchView() {
    state.cloudarch.autoFit = true;
    renderCloudArchDiagram();
  }

  el.cloudarchZoomInBtn.addEventListener("click", () => zoomCloudArchBy(ZOOM_STEP));
  el.cloudarchZoomOutBtn.addEventListener("click", () => zoomCloudArchBy(1 / ZOOM_STEP));
  el.cloudarchResetViewBtn.addEventListener("click", resetCloudArchView);

  el.cloudarchCanvasWrap.addEventListener("wheel", (event) => {
    if (state.cloudarch.raw === null) return;
    event.preventDefault();
    zoomCloudArchBy(event.deltaY < 0 ? 1.12 : 1 / 1.12);
  }, { passive: false });

  let cloudarchPanPointerId = null;
  let cloudarchPanStart = null;

  el.cloudarchSvg.addEventListener("pointerdown", (event) => {
    if (state.cloudarch.raw === null) return;
    cloudarchPanPointerId = event.pointerId;
    cloudarchPanStart = {
      clientX: event.clientX, clientY: event.clientY,
      viewX: state.cloudarch.view.x, viewY: state.cloudarch.view.y,
    };
    el.cloudarchSvg.setPointerCapture(event.pointerId);
    el.cloudarchSvg.classList.add("panning");
  });
  el.cloudarchSvg.addEventListener("pointermove", (event) => {
    if (cloudarchPanPointerId !== event.pointerId || !cloudarchPanStart) return;
    state.cloudarch.view = {
      ...state.cloudarch.view,
      x: cloudarchPanStart.viewX + (event.clientX - cloudarchPanStart.clientX),
      y: cloudarchPanStart.viewY + (event.clientY - cloudarchPanStart.clientY),
    };
    state.cloudarch.autoFit = false;
    applyCloudArchTransform();
  });
  function endCloudArchPan(event) {
    if (cloudarchPanPointerId !== event.pointerId) return;
    cloudarchPanPointerId = null;
    cloudarchPanStart = null;
    el.cloudarchSvg.classList.remove("panning");
  }
  el.cloudarchSvg.addEventListener("pointerup", endCloudArchPan);
  el.cloudarchSvg.addEventListener("pointercancel", endCloudArchPan);

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

  // Copilot/Teams-style floating "jump to latest message" button -- shown
  // once the user has scrolled up away from the bottom of the transcript,
  // so they can skip straight back down without manually scrolling.
  const JUMP_TO_LATEST_THRESHOLD_PX = 80;

  function isNearChatBottom() {
    const { scrollTop, scrollHeight, clientHeight } = el.chatScroll;
    return scrollHeight - scrollTop - clientHeight <= JUMP_TO_LATEST_THRESHOLD_PX;
  }

  function updateJumpToLatestVisibility() {
    el.jumpToLatestBtn.hidden = isNearChatBottom();
  }

  // Auto-follow helper, MS Teams "New messages" style: callers capture
  // `isNearChatBottom()` BEFORE mutating the DOM (growing scrollHeight),
  // then pass that snapshot in here AFTER the mutation. Only scrolls if
  // the user was already following the bottom -- someone who has
  // scrolled up to read earlier history does not get yanked back down
  // by the next streamed delta; they just see the floating button light
  // up instead. Without this, every setProgress/setText/finalize call
  // during an active turn force-scrolled unconditionally, so scrolling
  // away mid-stream was immediately overridden by the next delta --
  // which made the button effectively impossible to trigger.
  function finishScrollUpdate(wasNearBottom) {
    if (wasNearBottom) {
      scrollToBottom();
    }
    updateJumpToLatestVisibility();
  }

  el.chatScroll.addEventListener("scroll", updateJumpToLatestVisibility);
  el.jumpToLatestBtn.addEventListener("click", () => {
    scrollToBottom();
    updateJumpToLatestVisibility();
  });

  function formatTime(date) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // For "Save chat" -- records the FINAL text of a turn (never a partial
  // streaming delta) so the exported transcript reads the same whether a
  // turn streamed live or came back in one shot via the non-streaming
  // fallback. Also keeps this session's entry in the sidebar history list
  // up to date, so a chat is accurately listed even before "+ New chat"
  // is ever clicked.
  function recordTranscript(role, text) {
    state.transcript.push({ role, text, timestamp: new Date() });
    syncCurrentSessionToHistory();
  }

  // Copy + (if supported) Speak buttons for an agent message's meta row --
  // shared by addMessage and createLiveAgentMessage().finalize() below,
  // which previously built the Copy button twice, nearly identically.
  function addMessageActionButtons(meta, text) {
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "copy-btn";
    copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", () => copyText(text));
    meta.appendChild(copyBtn);

    if (SPEECH_SUPPORTED) {
      const speakBtn = document.createElement("button");
      speakBtn.type = "button";
      speakBtn.className = "copy-btn speak-btn";
      speakBtn.textContent = "Speak";
      speakBtn.addEventListener("click", () => speakText(text, speakBtn));
      meta.appendChild(speakBtn);
    }
  }

  function addMessage(role, text, { isMarkdown = false, attachmentNames = [], skipRecord = false } = {}) {
    // skipRecord: true when replaying a past session's saved transcript
    // (see switchToSession) -- the caller restores state.transcript
    // directly afterward, with original timestamps preserved, instead of
    // re-recording each replayed turn as if it just happened now.
    if (!skipRecord) {
      recordTranscript(role, text);
    }
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

    // Static (non-removable) echo of what was attached to THIS turn --
    // distinct from .composer-attachments, which is the live, still-
    // editable pending list shown before sending.
    if (attachmentNames.length) {
      const list = document.createElement("div");
      list.className = "message-attachments";
      attachmentNames.forEach((name) => {
        const chip = document.createElement("span");
        chip.className = "attachment-chip";
        const chipName = document.createElement("span");
        chipName.className = "attachment-chip-name";
        chipName.textContent = name;
        chipName.title = name;
        chip.appendChild(chipName);
        list.appendChild(chip);
      });
      col.appendChild(list);
    }

    const meta = document.createElement("div");
    meta.className = "message-meta";
    const time = document.createElement("span");
    time.textContent = formatTime(new Date());
    meta.appendChild(time);

    if (role === "agent") {
      addMessageActionButtons(meta, text);
    }
    col.appendChild(meta);

    // Sending your own message always jumps you to it (matches Teams/
    // Copilot) -- everything else only auto-follows if you were already
    // at the bottom, so scrolling up to read history doesn't get undone.
    const wasNearBottom = role === "user" || isNearChatBottom();
    row.appendChild(col);
    el.chatContainer.appendChild(row);
    finishScrollUpdate(wasNearBottom);
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

    const wasNearBottomOnOpen = isNearChatBottom();
    row.appendChild(col);
    el.chatContainer.appendChild(row);
    finishScrollUpdate(wasNearBottomOnOpen);

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
        const wasNearBottom = isNearChatBottom();
        thinkingSteps.push({ origin, text });
        progressNote.hidden = false;
        progressNote.textContent = origin ? `${origin} — ${text}` : text;
        finishScrollUpdate(wasNearBottom);
      },

      // Plain text, deliberately NOT markdown-rendered -- a delta is an
      // in-progress fragment (e.g. an unclosed ```code block```), and
      // parsing that as markdown mid-stream renders broken HTML far
      // more often than it renders anything useful. finalize() below
      // applies the real rendering once, to the complete text.
      setText(text) {
        const wasNearBottom = isNearChatBottom();
        progressNote.hidden = true;
        bubble.textContent = text;
        finishScrollUpdate(wasNearBottom);
      },

      finalize(text) {
        const wasNearBottom = isNearChatBottom();
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
          addMessageActionButtons(meta, text);
          col.appendChild(meta);
        }
        finishScrollUpdate(wasNearBottom);
      },

      showError(message) {
        const wasNearBottom = isNearChatBottom();
        replaceProgressNoteWithThinking();
        row.classList.add("error");
        const hasText = bubble.textContent && bubble.textContent.trim().length > 0;
        bubble.textContent = hasText ? `${bubble.textContent}\n\n⚠ ${message}` : message;
        finishScrollUpdate(wasNearBottom);
      },

      // User-initiated stop (see stopCurrentTurn) -- NOT an error, so
      // deliberately not styled like one: whatever partial answer had
      // streamed in by the time the backend's cancellation took effect
      // is kept and rendered normally, just with a small "Stopped" badge
      // instead of the usual timestamp/copy row.
      showStopped(text) {
        const wasNearBottom = isNearChatBottom();
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
        finishScrollUpdate(wasNearBottom);
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
  // Composer attachments -- files picked via the paperclip button, read
  // client-side into base64 and sent alongside the next turn's query.
  // Kept in sync with each backend's own server-side limits (see
  // ATTACHMENT_MAX_FILES/ATTACHMENT_MAX_BYTES in cli.py and agent.py) --
  // these client-side checks are purely for fast feedback; the server
  // re-validates independently regardless (a client is never a trusted
  // boundary). Runtime only, like state.network/state.transcript -- not
  // persisted across a reload (see loadState/saveState).
  // ---------------------------------------------------------------
  const ATTACHMENT_MAX_FILES = 4;
  const ATTACHMENT_MAX_BYTES = 8 * 1024 * 1024;

  state.pendingAttachments = []; // {name, mimeType, size, dataBase64}

  function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  // Some browsers report an empty `file.type` for extensions they don't
  // have a built-in mapping for (confirmed in practice for .md) -- fall
  // back to guessing from the extension for the types this composer's
  // own <input accept> list actually offers, rather than sending the
  // backend a blank/wrong mime_type for an otherwise-valid attachment.
  function guessMimeType(file) {
    if (file.type) return file.type;
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const byExt = {
      md: "text/markdown",
      markdown: "text/markdown",
      txt: "text/plain",
      pdf: "application/pdf",
      docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      xml: "application/xml",
      json: "application/json",
    };
    return byExt[ext] || "application/octet-stream";
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        // reader.result is "data:<mime>;base64,<data>" -- only the part
        // after the comma is the actual payload the backend expects.
        const result = reader.result;
        const commaIndex = result.indexOf(",");
        resolve(commaIndex === -1 ? result : result.slice(commaIndex + 1));
      };
      reader.onerror = () => reject(reader.error || new Error("Failed to read file."));
      reader.readAsDataURL(file);
    });
  }

  function renderAttachmentChips() {
    const container = el.composerAttachments;
    container.innerHTML = "";
    container.hidden = state.pendingAttachments.length === 0;
    state.pendingAttachments.forEach((attachment, index) => {
      const chip = document.createElement("span");
      chip.className = "attachment-chip";

      const name = document.createElement("span");
      name.className = "attachment-chip-name";
      name.textContent = attachment.name;
      name.title = attachment.name;
      chip.appendChild(name);

      const size = document.createElement("span");
      size.className = "attachment-chip-size";
      size.textContent = formatFileSize(attachment.size);
      chip.appendChild(size);

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "attachment-chip-remove";
      removeBtn.setAttribute("aria-label", `Remove ${attachment.name}`);
      removeBtn.textContent = "×";
      removeBtn.addEventListener("click", () => {
        state.pendingAttachments.splice(index, 1);
        renderAttachmentChips();
      });
      chip.appendChild(removeBtn);

      container.appendChild(chip);
    });
  }

  async function addAttachments(fileList) {
    const files = Array.from(fileList || []);
    for (const file of files) {
      if (state.pendingAttachments.length >= ATTACHMENT_MAX_FILES) {
        toast(`You can attach up to ${ATTACHMENT_MAX_FILES} files per message.`);
        break;
      }
      if (file.size > ATTACHMENT_MAX_BYTES) {
        toast(`"${file.name}" is too large (max ${formatFileSize(ATTACHMENT_MAX_BYTES)}).`);
        continue;
      }
      try {
        const dataBase64 = await fileToBase64(file);
        state.pendingAttachments.push({
          name: file.name,
          mimeType: guessMimeType(file),
          size: file.size,
          dataBase64,
        });
      } catch (err) {
        toast(`Couldn't read "${file.name}": ${err.message || err}`);
      }
    }
    renderAttachmentChips();
  }

  function clearAttachments() {
    state.pendingAttachments = [];
    renderAttachmentChips();
  }

  // Shape expected by both backends' POST /chat and /chat/stream "files"
  // field -- see cli.py's / agent.py's own _parse_attachments.
  function attachmentsForRequest() {
    return state.pendingAttachments.map((a) => ({
      name: a.name, mime_type: a.mimeType, data_base64: a.dataBase64,
    }));
  }

  el.attachFileBtn.addEventListener("click", () => el.attachFileInput.click());
  el.attachFileInput.addEventListener("change", async (event) => {
    await addAttachments(event.target.files);
    event.target.value = ""; // allow re-selecting the same file(s) later
  });

  // ---------------------------------------------------------------
  // Sending a turn (with retry/backoff for transient failures)
  // ---------------------------------------------------------------
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function postChat(baseUrl, query, files) {
    let lastError = null;
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt += 1) {
      if (attempt > 0) {
        await sleep(RETRY_BASE_DELAY_MS * 2 ** (attempt - 1));
      }
      try {
        const res = await fetch(`${baseUrl}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({
            query, session_id: state.sessionId || undefined,
            files: files && files.length ? files : undefined,
          }),
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
  async function* streamChat(baseUrl, query, files) {
    const response = await fetch(`${baseUrl}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        query, session_id: state.sessionId || undefined,
        files: files && files.length ? files : undefined,
      }),
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

  async function sendMessage(text, files) {
    const baseUrl = currentBaseUrl();
    if (!baseUrl) {
      toast("Set a Base URL and click Connect first.");
      return;
    }

    stopVoiceInputIfActive();
    stopSpeaking();
    addMessage("user", text, { isMarkdown: true, attachmentNames: (files || []).map((f) => f.name) });
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
      for await (const event of streamChat(baseUrl, text, files)) {
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
          live.finalize(event.response || "(The assistant didn't return a reply for this turn. Please try again.)");
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
          const data = await postChat(baseUrl, text, files);
          if (data.status === "ok") {
            setSessionId(data.session_id);
            addMessage("agent", data.response || "(The assistant didn't return a reply for this turn. Please try again.)", { isMarkdown: true });
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
      notifyTurnComplete();
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
  // Voice input -- record a prompt by speech instead of typing it.
  // window.SpeechRecognition (Chrome/Edge only as of this writing;
  // Firefox/Safari don't implement it) -- like speechSynthesis above,
  // this needs no server round trip and no external dependency, so the
  // mic button is simply disabled with an explanatory title where the
  // API doesn't exist rather than this page needing a cloud STT fallback.
  // ---------------------------------------------------------------
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isRecording = false;

  function setRecordingState(recording) {
    isRecording = recording;
    el.micBtn.classList.toggle("recording", recording);
    el.micBtn.title = recording ? "Stop recording" : "Voice input (click to record)";
    el.micBtn.setAttribute("aria-label", el.micBtn.title);
  }

  function stopVoiceInputIfActive() {
    if (recognition && isRecording) recognition.stop();
  }

  function startVoiceInput() {
    recognition = new SpeechRecognitionCtor();
    recognition.lang = navigator.language || "en-US";
    recognition.continuous = true;
    // Only commit FINAL results into the composer -- interim results
    // change word-by-word as recognition refines its guess, and
    // inserting/removing those live would mean constantly rewriting text
    // right where the user's caret is.
    recognition.interimResults = false;

    recognition.addEventListener("result", (event) => {
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) finalText += event.results[i][0].transcript;
      }
      if (finalText) insertTextAtCursor(finalText);
    });

    recognition.addEventListener("error", (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        toast("Microphone access was denied.");
      } else if (event.error !== "no-speech" && event.error !== "aborted") {
        toast(`Voice input error: ${event.error}`);
      }
    });

    // Fires both on an explicit stop() and if the browser's own
    // implementation ends the session on its own (e.g. a long silence) --
    // either way the button must fall back to its idle state rather than
    // keep showing "recording" for a session that has actually ended.
    // Deliberately does NOT auto-restart: a user who wants to keep
    // dictating just clicks the mic again, which is simpler and avoids a
    // restart loop fighting a browser that keeps ending the session.
    recognition.addEventListener("end", () => setRecordingState(false));

    recognition.start();
    setRecordingState(true);
    playMicStartChime();
  }

  if (!SpeechRecognitionCtor) {
    el.micBtn.disabled = true;
    el.micBtn.title = "Voice input isn't supported in this browser (try Chrome or Edge).";
  } else {
    el.micBtn.addEventListener("click", () => {
      if (isRecording) {
        recognition.stop();
      } else {
        startVoiceInput();
      }
    });
  }

  // Inserts `text` at the composer's current caret position (NOT a full
  // replace -- see setComposerPlainText below for that, used only by
  // history recall) so dictated text can mix naturally with whatever was
  // already typed, across one or several recording sessions.
  function insertTextAtCursor(text) {
    el.messageInput.focus();
    const inserted = document.execCommand("insertText", false, text);
    if (!inserted) {
      // execCommand unsupported/failed (rare) -- append at the end rather
      // than silently dropping the transcript. This path does NOT fire a
      // native "input" event the way execCommand does, so updateEmptyState
      // (wired below) needs an explicit call here.
      const existing = el.messageInput.textContent;
      if (existing && !/\s$/.test(existing)) {
        el.messageInput.appendChild(document.createTextNode(" "));
      }
      el.messageInput.appendChild(document.createTextNode(text));
      updateEmptyState();
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
    maybeRequestNotificationPermission();
    const markdown = richTextToMarkdown(el.messageInput);
    const hasAttachments = state.pendingAttachments.length > 0;
    if (!markdown && !hasAttachments) return;
    // A turn with only attachments and no typed text still needs a
    // non-empty "query" -- both backends require one (see each one's own
    // _parse_attachments/_run_chat_turn) -- substitute a minimal default
    // rather than silently blocking the send.
    const query = markdown || "Please review the attached file(s).";
    // Skip an exact repeat of the immediately-previous entry (bash's own
    // default ignoredups behavior) so resending the same query doesn't
    // clutter history with duplicates.
    if (state.commandHistory[state.commandHistory.length - 1] !== query) {
      state.commandHistory.push(query);
    }
    historyIndex = state.commandHistory.length;
    draftBeforeHistory = "";
    el.messageInput.innerHTML = "";
    updateEmptyState();
    const files = attachmentsForRequest();
    clearAttachments();
    sendMessage(query, files);
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

  // Shared by Save Chat and the Cloud Architecture tab's Export PNG --
  // tries a real "Save As" dialog (File System Access API) first, then
  // falls back to a plain browser download where that API doesn't exist
  // (Firefox, Safari as of this writing) or is blocked. Returns which
  // path actually saved the file ("picker"/"download"), or null if the
  // user cancelled the picker, so callers can show their own
  // appropriately-worded toast.
  async function saveFile(blob, filename, { description, accept } = {}) {
    if (window.showSaveFilePicker) {
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: filename,
          types: description && accept ? [{ description, accept }] : undefined,
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        return "picker";
      } catch (err) {
        if (err && err.name === "AbortError") return null; // user cancelled the dialog
        // Fall through to the download fallback below (e.g. a security
        // policy blocked the picker) rather than leaving the user with
        // no way to save at all.
      }
    }

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    return "download";
  }

  async function saveChat() {
    if (state.transcript.length === 0) {
      toast("Nothing to save yet.");
      return;
    }

    const markdown = buildTranscriptMarkdown();
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    const filename = `process-architect-chat-${stamp}.md`;
    const blob = new Blob([markdown], { type: "text/markdown" });

    const result = await saveFile(blob, filename, {
      description: "Markdown", accept: { "text/markdown": [".md"] },
    });
    if (result === "picker") toast("Chat saved.");
    else if (result === "download") toast("Chat downloaded.");
  }

  el.saveChatBtn.addEventListener("click", saveChat);

  // ---------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------
  function init() {
    applyTheme();
    applyVoiceSettings();
    el.faviconLink.setAttribute("href", faviconDataUri(false));
    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
        if (!state.theme) applyTheme();
      });
    }

    el.baseUrlInput.value = state.baseUrl || PRESETS.adk.baseUrl;
    el.apiKeyInput.value = state.apiKey || "";
    setPreset(state.preset && (PRESETS[state.preset] || state.preset === "custom") ? state.preset : "adk");
    if (state.sessionId) {
      restoreSessionOnLoad(state.sessionId);
    } else {
      renderSessionHistoryList();
    }

    setStatus("unknown", "Not connected");
    renderNetwork();
    renderUsageChart();
    el.messageInput.focus();
  }

  init();
})();
