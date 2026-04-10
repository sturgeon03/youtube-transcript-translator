const form = document.getElementById("job-form");
const submitButton = document.getElementById("submit-button");
const formStatus = document.getElementById("form-status");
const jobBadge = document.getElementById("job-badge");
const jobMeta = document.getElementById("job-meta");
const logs = document.getElementById("logs");
const resultLinks = document.getElementById("result-links");
const progressPhase = document.getElementById("progress-phase");
const progressDetail = document.getElementById("progress-detail");
const progressPercent = document.getElementById("progress-percent");
const progressFill = document.getElementById("progress-fill");
const terminalProgress = document.getElementById("terminal-progress");

const phaseLabels = {
  queued: "대기 중",
  starting: "작업 시작",
  loading_glossary: "용어집 로드",
  loading_input: "로컬 입력 로드",
  resolving_transcript: "영어 자막 확인",
  checking_youtube_subtitles: "유튜브 자막 확인",
  downloading_audio: "오디오 다운로드",
  loading_asr_model: "전사 모델 로딩",
  transcribing_audio: "로컬 전사",
  english_ready: "영어 자막 준비 완료",
  grouping_subtitles: "자막 그룹화",
  downloading_model: "번역 모델 다운로드",
  loading_model: "번역 모델 로딩",
  translating: "번역",
  quality_checks: "품질 검사",
  rendering_subtitles: "표시용 자막 생성",
  writing_artifacts: "산출물 저장",
  registering_overlay: "오버레이 등록",
  completed: "완료",
  failed: "실패",
};

let currentJobId = null;
let pollTimer = null;
let pollGeneration = 0;

function clampProgress(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}

function humanizePhase(phase) {
  if (!phase) {
    return "대기 중";
  }
  return phaseLabels[phase] || phase.replace(/_/g, " ");
}

function buildTerminalBar(percent, width = 30) {
  const clamped = clampProgress(percent);
  const filled = Math.round((clamped / 100) * width);
  return `${"=".repeat(filled)}${"-".repeat(Math.max(0, width - filled))}`;
}

function setBadge(status) {
  jobBadge.textContent = status;
  jobBadge.className = `badge ${status}`;
}

function appendActionLink({ href, text, newTab = true, className = "" }) {
  const link = document.createElement("a");
  link.href = href;
  link.textContent = text;
  if (newTab) {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }
  if (className) {
    link.classList.add(className);
  }
  resultLinks.appendChild(link);
}

function renderLinks(jobId, result, snapshot) {
  resultLinks.innerHTML = "";
  if (!result) {
    return;
  }

  if (snapshot?.status === "completed") {
    appendActionLink({
      href: `/jobs/${jobId}/watch`,
      text: "Watch with Overlay",
      className: "primary-link",
    });
    if (snapshot.request?.url) {
      appendActionLink({
        href: snapshot.request.url,
        text: "Open YouTube",
      });
    }
  }

  const labels = {
    english_srt: "English SRT",
    english_txt: "English TXT",
    korean_output: "Korean SRT",
    review_md: "Review MD",
    segments_json: "Segments JSON",
    overlay_subtitle: "Overlay SRT",
  };

  Object.entries(labels).forEach(([key, label]) => {
    if (!result[key]) {
      return;
    }
    appendActionLink({
      href: `/api/jobs/${jobId}/artifacts/${key}`,
      text: label,
    });
  });
}

function renderProgress(snapshot) {
  const percent = clampProgress(snapshot.progress_percent);
  const phase = humanizePhase(snapshot.phase);
  const detail = snapshot.progress_detail || "작업 진행 중";
  const bar = buildTerminalBar(percent);

  progressPhase.textContent = phase;
  progressDetail.textContent = detail;
  progressPercent.textContent = `${percent.toFixed(1)}%`;
  progressFill.style.width = `${percent}%`;
  terminalProgress.textContent = `[${bar}] ${percent.toFixed(1).padStart(5)}% | ${snapshot.phase || "idle"} | ${detail}`;
}

function renderJob(snapshot) {
  setBadge(snapshot.status);
  jobMeta.textContent = `job=${snapshot.id} | created=${snapshot.created_at}`;
  renderProgress(snapshot);
  renderLinks(snapshot.id, snapshot.result, snapshot);

  const logLines = [];
  if (snapshot.error) {
    logLines.push(`[error] ${snapshot.error}`);
  }
  logLines.push(...snapshot.logs);
  logs.textContent = logLines.length ? logLines.join("\n") : "아직 로그가 없습니다.";
  logs.scrollTop = logs.scrollHeight;

  if (snapshot.status === "completed") {
    formStatus.textContent = `완료: quality warnings ${snapshot.result?.quality_issue_count ?? "0"}`;
    submitButton.disabled = false;
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  } else if (snapshot.status === "failed") {
    formStatus.textContent = "실패: 로그를 확인하세요.";
    submitButton.disabled = false;
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }
}

async function pollJob(jobId, generation) {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (generation !== pollGeneration || jobId !== currentJobId) {
    return;
  }
  if (!response.ok) {
    formStatus.textContent = "작업 상태 조회에 실패했습니다.";
    submitButton.disabled = false;
    return;
  }
  const snapshot = await response.json();
  if (generation !== pollGeneration || jobId !== currentJobId) {
    return;
  }
  renderJob(snapshot);
  if (snapshot.status === "queued" || snapshot.status === "running") {
    pollTimer = setTimeout(() => pollJob(jobId, generation), 1200);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  pollGeneration += 1;
  submitButton.disabled = true;
  formStatus.textContent = "작업 생성 중...";
  setBadge("queued");
  renderProgress({
    phase: "queued",
    progress_percent: 0,
    progress_detail: "새 작업을 준비하고 있습니다.",
  });
  logs.textContent = "작업을 시작합니다...";
  resultLinks.innerHTML = "";

  const payload = {
    url: document.getElementById("url").value.trim(),
    transcript_source: document.getElementById("transcript_source").value,
    translator: document.getElementById("translator").value,
    glossary_profile: document.getElementById("glossary_profile").value || null,
    local_translation_model: document.getElementById("local_translation_model").value.trim(),
    register_overlay: document.getElementById("register_overlay").checked,
    overlay_label: document.getElementById("overlay_label").value.trim() || null,
    local_transcription_model: document.getElementById("local_transcription_model").value.trim(),
    wrap_width: Number(document.getElementById("wrap_width").value),
  };

  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    formStatus.textContent = "작업 생성 실패";
    logs.textContent = errorText;
    submitButton.disabled = false;
    setBadge("failed");
    renderProgress({
      phase: "failed",
      progress_percent: 0,
      progress_detail: "작업 생성에 실패했습니다.",
    });
    return;
  }

  const created = await response.json();
  currentJobId = created.job_id;
  formStatus.textContent = `작업 시작: ${currentJobId}`;
  pollJob(currentJobId, pollGeneration);
});
