(async () => {
  const INDEX_URL = chrome.runtime.getURL("subtitles/index.json");
  const PLAYER_SELECTOR = "#movie_player";
  const VIDEO_SELECTOR = "video.html5-main-video";
  const STORAGE_KEY = "codexKoSubtitleOverlaySettings";

  const SIZE_ORDER = ["compact", "comfortable", "large"];
  const POSITION_ORDER = ["bottom", "top"];
  const THEME_ORDER = ["soft", "solid", "outline"];

  const SIZE_PRESETS = {
    compact: {
      fontSize: "clamp(18px, 1.5vw, 25px)",
      maxWidth: "64%",
      padding: "8px 12px",
      lineHeight: "1.3",
    },
    comfortable: {
      fontSize: "clamp(20px, 1.8vw, 29px)",
      maxWidth: "70%",
      padding: "10px 14px",
      lineHeight: "1.35",
    },
    large: {
      fontSize: "clamp(22px, 2.1vw, 33px)",
      maxWidth: "76%",
      padding: "12px 16px",
      lineHeight: "1.38",
    },
  };

  const THEME_PRESETS = {
    soft: {
      background: "rgba(10, 10, 10, 0.40)",
      border: "1px solid rgba(255, 255, 255, 0.10)",
      boxShadow: "0 10px 30px rgba(0, 0, 0, 0.18)",
      backdropFilter: "blur(5px)",
      textShadow: "0 2px 6px rgba(0, 0, 0, 0.95)",
      extraPadding: null,
    },
    solid: {
      background: "rgba(0, 0, 0, 0.68)",
      border: "1px solid rgba(255, 255, 255, 0.14)",
      boxShadow: "0 12px 32px rgba(0, 0, 0, 0.28)",
      backdropFilter: "none",
      textShadow: "0 2px 6px rgba(0, 0, 0, 0.95)",
      extraPadding: null,
    },
    outline: {
      background: "transparent",
      border: "0",
      boxShadow: "none",
      backdropFilter: "none",
      textShadow:
        "0 0 2px rgba(0, 0, 0, 1), 0 2px 8px rgba(0, 0, 0, 0.95), 0 0 16px rgba(0, 0, 0, 0.72)",
      extraPadding: "2px 8px",
    },
  };

  const DEFAULT_SETTINGS = {
    position: "bottom",
    size: "compact",
    theme: "soft",
  };

  const state = {
    currentVideoId: null,
    cues: [],
    overlay: null,
    toolbar: null,
    buttons: {},
    enabled: true,
    index: null,
    currentCueIndex: -1,
    rafId: 0,
    lastUrl: location.href,
    settings: { ...DEFAULT_SETTINGS },
  };

  function getVideoId(url = location.href) {
    try {
      const parsed = new URL(url);
      if (parsed.hostname === "youtu.be") {
        return parsed.pathname.slice(1);
      }
      return parsed.searchParams.get("v");
    } catch {
      return null;
    }
  }

  async function loadIndex() {
    if (state.index) {
      return state.index;
    }
    const response = await fetch(INDEX_URL);
    if (!response.ok) {
      throw new Error(`Failed to load subtitle index: ${response.status}`);
    }
    state.index = await response.json();
    return state.index;
  }

  async function loadSettings() {
    try {
      const stored = await chrome.storage.local.get(STORAGE_KEY);
      state.settings = {
        ...DEFAULT_SETTINGS,
        ...(stored?.[STORAGE_KEY] || {}),
      };
    } catch {
      state.settings = { ...DEFAULT_SETTINGS };
    }
  }

  function saveSettings() {
    chrome.storage.local.set({
      [STORAGE_KEY]: state.settings,
    });
  }

  function parseTimecode(raw) {
    const normalized = raw.trim().replace(",", ".");
    const parts = normalized.split(":");
    if (parts.length !== 3) {
      throw new Error(`Invalid SRT timestamp: ${raw}`);
    }
    const [hours, minutes, seconds] = parts;
    return Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds);
  }

  function balanceIntoTwoLines(text) {
    const words = text.split(/\s+/).filter(Boolean);
    if (words.length < 4) {
      return text;
    }

    let bestIndex = Math.max(1, Math.floor(words.length / 2));
    let bestScore = Infinity;
    for (let index = 1; index < words.length; index += 1) {
      const left = words.slice(0, index).join(" ");
      const right = words.slice(index).join(" ");
      const score = Math.abs(left.length - right.length);
      if (score < bestScore) {
        bestScore = score;
        bestIndex = index;
      }
    }

    return `${words.slice(0, bestIndex).join(" ")}\n${words.slice(bestIndex).join(" ")}`;
  }

  function formatCueText(text) {
    const normalized = text
      .replace(/\r/g, "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .join(" ");

    if (!normalized) {
      return "";
    }

    if (normalized.length <= 28) {
      return normalized;
    }

    return balanceIntoTwoLines(normalized);
  }

  function parseSrt(text) {
    const blocks = text
      .replace(/\r/g, "")
      .trim()
      .split(/\n{2,}/);

    const cues = [];
    for (const block of blocks) {
      const lines = block.split("\n").map((line) => line.trimEnd());
      if (lines.length < 3) {
        continue;
      }

      const timeLine = lines[1];
      const match = timeLine.match(
        /(\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}[,.]\d{3})/
      );
      if (!match) {
        continue;
      }

      cues.push({
        start: parseTimecode(match[1]),
        end: parseTimecode(match[2]),
        text: formatCueText(lines.slice(2).join("\n")),
      });
    }
    return cues;
  }

  function buildButton(text, title) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.title = title;
    Object.assign(button.style, {
      minWidth: "38px",
      height: "32px",
      border: "0",
      borderRadius: "999px",
      background: "rgba(0, 0, 0, 0.64)",
      color: "#fff",
      fontSize: "12px",
      fontWeight: "700",
      cursor: "pointer",
      padding: "0 10px",
      boxShadow: "0 6px 20px rgba(0, 0, 0, 0.22)",
      backdropFilter: "blur(4px)",
    });
    return button;
  }

  function ensureUi() {
    const player = document.querySelector(PLAYER_SELECTOR);
    if (!player) {
      return null;
    }

    let overlay = player.querySelector(".codex-ko-subtitle-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "codex-ko-subtitle-overlay";
      Object.assign(overlay.style, {
        position: "absolute",
        left: "50%",
        transform: "translateX(-50%)",
        color: "#fff",
        fontWeight: "700",
        textAlign: "center",
        whiteSpace: "pre-line",
        wordBreak: "keep-all",
        overflowWrap: "normal",
        pointerEvents: "none",
        zIndex: "60",
        opacity: "0",
        transition: "opacity 120ms ease, top 120ms ease, bottom 120ms ease",
        fontFamily: "'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif",
      });
      player.appendChild(overlay);
    }

    let toolbar = player.querySelector(".codex-ko-subtitle-toolbar");
    if (!toolbar) {
      toolbar = document.createElement("div");
      toolbar.className = "codex-ko-subtitle-toolbar";
      Object.assign(toolbar.style, {
        position: "absolute",
        top: "16px",
        right: "16px",
        display: "flex",
        gap: "8px",
        zIndex: "61",
        pointerEvents: "auto",
      });

      const powerButton = buildButton("KO", "Toggle Korean subtitles");
      const sizeButton = buildButton("S", "Subtitle size");
      const positionButton = buildButton("B", "Subtitle position");
      const themeButton = buildButton("BG", "Subtitle background style");

      powerButton.addEventListener("click", () => {
        state.enabled = !state.enabled;
        applyButtonState();
        renderSubtitle();
      });

      sizeButton.addEventListener("click", () => {
        cycleSetting("size", SIZE_ORDER);
      });

      positionButton.addEventListener("click", () => {
        cycleSetting("position", POSITION_ORDER);
      });

      themeButton.addEventListener("click", () => {
        cycleSetting("theme", THEME_ORDER);
      });

      toolbar.appendChild(powerButton);
      toolbar.appendChild(sizeButton);
      toolbar.appendChild(positionButton);
      toolbar.appendChild(themeButton);
      player.appendChild(toolbar);

      state.buttons = {
        power: powerButton,
        size: sizeButton,
        position: positionButton,
        theme: themeButton,
      };
    }

    state.overlay = overlay;
    state.toolbar = toolbar;
    applyOverlayStyle();
    applyButtonState();
    return overlay;
  }

  function cycleSetting(key, values) {
    const currentIndex = values.indexOf(state.settings[key]);
    const nextIndex = (currentIndex + 1) % values.length;
    state.settings[key] = values[nextIndex];
    saveSettings();
    applyOverlayStyle();
    applyButtonState();
  }

  function applyButtonState() {
    const { power, size, position, theme } = state.buttons;
    if (!power || !size || !position || !theme) {
      return;
    }

    power.style.opacity = state.enabled ? "1" : "0.48";
    size.textContent =
      state.settings.size === "compact"
        ? "S"
        : state.settings.size === "comfortable"
          ? "M"
          : "L";
    size.title = `Subtitle size: ${state.settings.size}`;

    position.textContent = state.settings.position === "bottom" ? "B" : "T";
    position.title = `Subtitle position: ${state.settings.position}`;

    theme.textContent =
      state.settings.theme === "soft"
        ? "BG"
        : state.settings.theme === "solid"
          ? "HD"
          : "OL";
    theme.title = `Subtitle style: ${state.settings.theme}`;
  }

  function applyOverlayStyle() {
    if (!state.overlay) {
      return;
    }

    const sizePreset = SIZE_PRESETS[state.settings.size] || SIZE_PRESETS.compact;
    const themePreset = THEME_PRESETS[state.settings.theme] || THEME_PRESETS.soft;

    Object.assign(state.overlay.style, {
      maxWidth: sizePreset.maxWidth,
      padding: themePreset.extraPadding || sizePreset.padding,
      borderRadius: "14px",
      fontSize: sizePreset.fontSize,
      lineHeight: sizePreset.lineHeight,
      background: themePreset.background,
      border: themePreset.border,
      boxShadow: themePreset.boxShadow,
      backdropFilter: themePreset.backdropFilter,
      textShadow: themePreset.textShadow,
    });

    updateOverlayLayout();
  }

  function updateOverlayLayout() {
    const player = document.querySelector(PLAYER_SELECTOR);
    if (!player || !state.overlay) {
      return;
    }

    const height = player.clientHeight || 0;
    const controlsVisible = !player.classList.contains("ytp-autohide");

    if (state.settings.position === "top") {
      state.overlay.style.top = `${Math.max(Math.round(height * 0.06), 28)}px`;
      state.overlay.style.bottom = "auto";
      return;
    }

    const bottomOffset = controlsVisible ? 108 : 56;
    state.overlay.style.bottom = `${Math.max(Math.round(height * 0.12), bottomOffset)}px`;
    state.overlay.style.top = "auto";
  }

  function findCueIndex(currentTime) {
    const cues = state.cues;
    const currentIndex = state.currentCueIndex;

    if (
      currentIndex >= 0 &&
      currentIndex < cues.length &&
      currentTime >= cues[currentIndex].start &&
      currentTime <= cues[currentIndex].end
    ) {
      return currentIndex;
    }

    if (
      currentIndex + 1 < cues.length &&
      currentTime >= cues[currentIndex + 1].start &&
      currentTime <= cues[currentIndex + 1].end
    ) {
      return currentIndex + 1;
    }

    for (let index = 0; index < cues.length; index += 1) {
      const cue = cues[index];
      if (currentTime >= cue.start && currentTime <= cue.end) {
        return index;
      }
      if (cue.start > currentTime) {
        break;
      }
    }

    return -1;
  }

  function renderSubtitle() {
    const video = document.querySelector(VIDEO_SELECTOR);
    if (!video || !state.overlay) {
      return;
    }

    updateOverlayLayout();

    if (!state.enabled || state.cues.length === 0) {
      state.overlay.style.opacity = "0";
      return;
    }

    const cueIndex = findCueIndex(video.currentTime);
    state.currentCueIndex = cueIndex;
    if (cueIndex === -1) {
      state.overlay.textContent = "";
      state.overlay.style.opacity = "0";
      return;
    }

    state.overlay.textContent = state.cues[cueIndex].text;
    state.overlay.style.opacity = "1";
  }

  async function loadSubtitleTrack(videoId) {
    const index = await loadIndex();
    const entry = index?.videos?.[videoId];
    if (!entry?.file) {
      return [];
    }

    const subtitleUrl = chrome.runtime.getURL(entry.file);
    const response = await fetch(subtitleUrl);
    if (!response.ok) {
      throw new Error(`Failed to load subtitle file: ${response.status}`);
    }
    const subtitleText = await response.text();
    return parseSrt(subtitleText);
  }

  async function refreshVideoContext() {
    const videoId = getVideoId();
    if (!videoId) {
      state.currentVideoId = null;
      state.cues = [];
      state.currentCueIndex = -1;
      if (state.overlay) {
        state.overlay.style.opacity = "0";
      }
      if (state.toolbar) {
        state.toolbar.style.display = "none";
      }
      return;
    }

    if (videoId === state.currentVideoId) {
      ensureUi();
      return;
    }

    state.currentVideoId = videoId;
    state.currentCueIndex = -1;
    ensureUi();

    try {
      state.cues = await loadSubtitleTrack(videoId);
    } catch (error) {
      console.error("[codex-ko-subtitle-overlay]", error);
      state.cues = [];
    }

    if (state.toolbar) {
      state.toolbar.style.display = state.cues.length > 0 ? "flex" : "none";
    }
    if (state.overlay && state.cues.length === 0) {
      state.overlay.textContent = "";
      state.overlay.style.opacity = "0";
    }
  }

  function startRenderLoop() {
    if (state.rafId) {
      cancelAnimationFrame(state.rafId);
    }

    const tick = () => {
      if (location.href !== state.lastUrl) {
        state.lastUrl = location.href;
        refreshVideoContext().catch((error) => {
          console.error("[codex-ko-subtitle-overlay]", error);
        });
      }

      ensureUi();
      renderSubtitle();
      state.rafId = requestAnimationFrame(tick);
    };

    tick();
  }

  document.addEventListener("yt-navigate-finish", () => {
    refreshVideoContext().catch((error) => {
      console.error("[codex-ko-subtitle-overlay]", error);
    });
  });

  await loadSettings();
  await refreshVideoContext();
  startRenderLoop();
})();
