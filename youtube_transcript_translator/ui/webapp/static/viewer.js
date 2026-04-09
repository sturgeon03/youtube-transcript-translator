const bootstrap = window.VIEWER_BOOTSTRAP || {};
const overlay = document.getElementById("subtitle-overlay");

let player = null;
let cues = [];
let currentCueIndex = -1;
let rafId = 0;

function parseTimecode(raw) {
  const normalized = raw.trim().replace(",", ".");
  const [hours, minutes, seconds] = normalized.split(":");
  return Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds);
}

function parseSrt(text) {
  return text
    .replace(/\r/g, "")
    .trim()
    .split(/\n{2,}/)
    .map((block) => block.split("\n"))
    .map((lines) => {
      if (lines.length < 3) {
        return null;
      }
      const match = lines[1].match(
        /(\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}[,.]\d{3})/
      );
      if (!match) {
        return null;
      }
      return {
        start: parseTimecode(match[1]),
        end: parseTimecode(match[2]),
        text: lines.slice(2).join("\n").trim(),
      };
    })
    .filter(Boolean);
}

function findCueIndex(timeSeconds) {
  if (!cues.length) {
    return -1;
  }

  if (
    currentCueIndex >= 0 &&
    currentCueIndex < cues.length &&
    cues[currentCueIndex].start <= timeSeconds &&
    timeSeconds <= cues[currentCueIndex].end
  ) {
    return currentCueIndex;
  }

  let low = 0;
  let high = cues.length - 1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const cue = cues[mid];
    if (timeSeconds < cue.start) {
      high = mid - 1;
    } else if (timeSeconds > cue.end) {
      low = mid + 1;
    } else {
      return mid;
    }
  }

  return -1;
}

function renderCue(index) {
  if (index < 0) {
    overlay.textContent = "";
    overlay.classList.remove("ready");
    currentCueIndex = -1;
    return;
  }

  const cue = cues[index];
  if (!cue) {
    return;
  }

  if (index !== currentCueIndex) {
    overlay.textContent = cue.text;
    overlay.classList.add("ready");
    currentCueIndex = index;
  }
}

function syncLoop() {
  if (!player || typeof player.getCurrentTime !== "function") {
    rafId = window.requestAnimationFrame(syncLoop);
    return;
  }

  const state = typeof player.getPlayerState === "function" ? player.getPlayerState() : -1;
  if (state === YT.PlayerState.PLAYING || state === YT.PlayerState.PAUSED || state === YT.PlayerState.BUFFERING) {
    const time = player.getCurrentTime();
    renderCue(findCueIndex(time));
  }

  rafId = window.requestAnimationFrame(syncLoop);
}

async function loadSubtitles() {
  const response = await fetch(bootstrap.subtitleArtifactUrl, { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error(`Failed to load subtitles: ${response.status}`);
  }
  const text = await response.text();
  cues = parseSrt(text);
  if (!cues.length) {
    overlay.textContent = "생성된 자막을 찾지 못했습니다.";
    overlay.classList.add("ready");
  }
}

function buildPlayer() {
  player = new YT.Player("player", {
    width: "100%",
    height: "100%",
    videoId: bootstrap.videoId,
    playerVars: {
      playsinline: 1,
      rel: 0,
      modestbranding: 1,
      cc_load_policy: 0,
    },
    events: {
      onReady() {
        overlay.textContent = "재생을 시작하면 한국어 자막이 표시됩니다.";
        overlay.classList.add("ready");
      },
    },
  });
}

window.onYouTubeIframeAPIReady = async function onYouTubeIframeAPIReady() {
  try {
    await loadSubtitles();
    buildPlayer();
    syncLoop();
  } catch (error) {
    overlay.textContent = error instanceof Error ? error.message : "자막 뷰어를 초기화하지 못했습니다.";
    overlay.classList.add("ready");
  }
};

window.addEventListener("beforeunload", () => {
  if (rafId) {
    window.cancelAnimationFrame(rafId);
  }
});
