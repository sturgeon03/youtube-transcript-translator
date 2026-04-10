from __future__ import annotations

import io
import threading
import traceback
import uuid
import webbrowser
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.requests import Request

from ...app.config import (
    DEFAULT_LOCAL_TRANSCRIPTION_COMPUTE_TYPE,
    DEFAULT_LOCAL_TRANSCRIPTION_DEVICE,
    DEFAULT_LOCAL_TRANSCRIPTION_MODEL,
    DEFAULT_LOCAL_TRANSLATION_DEVICE,
    DEFAULT_LOCAL_TRANSLATION_MAX_INPUT_LENGTH,
    DEFAULT_LOCAL_TRANSLATION_MAX_NEW_TOKENS,
    DEFAULT_LOCAL_TRANSLATION_MODEL,
    DEFAULT_LOCAL_TRANSLATION_NUM_BEAMS,
    DEFAULT_LOCAL_TRANSLATION_SOURCE_LANG,
    DEFAULT_LOCAL_TRANSLATION_TARGET_LANG,
    DEFAULT_MAX_GAP_SECONDS,
    DEFAULT_MAX_GROUP_SECONDS,
    DEFAULT_MAX_GROUP_WORDS,
    DEFAULT_TRANSCRIPT_SOURCE,
    DEFAULT_TRANSLATOR,
    DEFAULT_WRAP_WIDTH,
    OutputConfig,
    PipelineConfig,
    TranscriptConfig,
    TranslationConfig,
)
from ...app.pipeline import PipelineResult, run_pipeline
from ...glossary.loader import GlossaryProfile, list_glossary_profiles
from ...sources.youtube import extract_video_id


APP_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_ROOT / "templates"
STATIC_DIR = APP_ROOT / "static"
DEFAULT_JOB_ROOT = Path.cwd() / "artifacts" / "webui"
DEFAULT_EXTENSION_ROOT = Path(__file__).resolve().parents[1] / "chrome_overlay"
LOCAL_TRANSCRIPTION_MODEL_PRESETS = [
    {
        "value": "small.en",
        "label": "small.en",
        "description": "Fastest local ASR, lower accuracy on long technical lectures.",
    },
    {
        "value": "medium.en",
        "label": "medium.en",
        "description": "Recommended quality baseline for technical English lectures.",
    },
    {
        "value": "large-v3",
        "label": "large-v3",
        "description": "Highest local ASR quality, best on stronger GPUs.",
    },
]


class JobRequest(BaseModel):
    url: str = Field(..., min_length=11)
    transcript_source: str = DEFAULT_TRANSCRIPT_SOURCE
    translator: str = DEFAULT_TRANSLATOR
    glossary_profile: str | None = None
    local_translation_model: str = DEFAULT_LOCAL_TRANSLATION_MODEL
    register_overlay: bool = True
    overlay_label: str | None = None
    local_transcription_model: str = DEFAULT_LOCAL_TRANSCRIPTION_MODEL
    local_transcription_device: str = DEFAULT_LOCAL_TRANSCRIPTION_DEVICE
    local_transcription_compute_type: str = DEFAULT_LOCAL_TRANSCRIPTION_COMPUTE_TYPE
    local_translation_device: str = DEFAULT_LOCAL_TRANSLATION_DEVICE
    local_translation_source_lang: str = DEFAULT_LOCAL_TRANSLATION_SOURCE_LANG
    local_translation_target_lang: str = DEFAULT_LOCAL_TRANSLATION_TARGET_LANG
    local_translation_max_input_length: int = DEFAULT_LOCAL_TRANSLATION_MAX_INPUT_LENGTH
    local_translation_max_new_tokens: int = DEFAULT_LOCAL_TRANSLATION_MAX_NEW_TOKENS
    local_translation_num_beams: int = DEFAULT_LOCAL_TRANSLATION_NUM_BEAMS
    max_group_seconds: float = DEFAULT_MAX_GROUP_SECONDS
    max_group_words: int = DEFAULT_MAX_GROUP_WORDS
    max_gap_seconds: float = DEFAULT_MAX_GAP_SECONDS
    wrap_width: int = DEFAULT_WRAP_WIDTH


@dataclass
class JobRecord:
    id: str
    created_at: str
    request: dict[str, Any]
    workdir: Path
    status: str = "queued"
    phase: str = "queued"
    progress_percent: float = 0.0
    progress_detail: str | None = "Waiting for the job to start"
    logs: list[str] = field(default_factory=list)
    result: dict[str, str] | None = None
    error: str | None = None

    def append_log(self, text: str) -> None:
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
        for line in cleaned.split("\n"):
            if line:
                self.logs.append(line)


class JobLogStream(io.TextIOBase):
    def __init__(self, job: JobRecord, lock: threading.Lock) -> None:
        self.job = job
        self.lock = lock

    def write(self, text: str) -> int:
        if not text:
            return 0
        with self.lock:
            self.job.append_log(text)
        return len(text)

    def flush(self) -> None:
        return None


class JobStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}

    def create(self, request: JobRequest) -> JobRecord:
        job_id = uuid.uuid4().hex[:10]
        workdir = (self.root_dir / job_id).resolve()
        workdir.mkdir(parents=True, exist_ok=True)
        record = JobRecord(
            id=job_id,
            created_at=datetime.now().isoformat(timespec="seconds"),
            request=request.model_dump(),
            workdir=workdir,
        )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> JobRecord:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=f"Unknown job id: {job_id}") from exc

    def update_status(self, job_id: str, status: str) -> JobRecord:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            if status == "queued":
                job.phase = "queued"
            elif status == "completed":
                job.phase = "completed"
                job.progress_percent = 100.0
                job.progress_detail = "Pipeline completed"
            elif status == "failed":
                job.phase = "failed"
                job.progress_detail = job.error or "The job failed."
            return job

    def update_progress(
        self,
        job_id: str,
        *,
        stage: str,
        progress: float | None = None,
        detail: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.status in {"completed", "failed"}:
                return
            job.phase = stage
            if progress is not None:
                job.progress_percent = max(0.0, min(100.0, progress))
            if detail:
                job.progress_detail = detail

    def set_result(self, job_id: str, result: dict[str, str]) -> None:
        with self._lock:
            self._jobs[job_id].result = result

    def set_error(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.error = error

    def append_log(self, job_id: str, text: str) -> None:
        with self._lock:
            self._jobs[job_id].append_log(text)

    def snapshot(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs[job_id]
            return {
                "id": job.id,
                "created_at": job.created_at,
                "status": job.status,
                "phase": job.phase,
                "progress_percent": job.progress_percent,
                "progress_detail": job.progress_detail,
                "logs": list(job.logs),
                "request": dict(job.request),
                "result": dict(job.result) if job.result else None,
                "error": job.error,
            }


def build_pipeline_config(request: JobRequest, *, workdir: Path) -> PipelineConfig:
    video_id = extract_video_id(request.url)
    output_root = workdir / video_id
    output_root.parent.mkdir(parents=True, exist_ok=True)

    return PipelineConfig(
        url=request.url,
        input_path=None,
        max_group_seconds=request.max_group_seconds,
        max_group_words=request.max_group_words,
        max_gap_seconds=request.max_gap_seconds,
        transcript=TranscriptConfig(
            source_mode=request.transcript_source,
            language="en",
            local_model=request.local_transcription_model,
            local_device=request.local_transcription_device,
            local_compute_type=request.local_transcription_compute_type,
        ),
        translation=TranslationConfig(
            backend=request.translator,
            batch_size=8,
            wrap_width=request.wrap_width,
            glossary_path=None,
            glossary_profile=request.glossary_profile,
            glossary_registry_path=None,
            local_model=request.local_translation_model,
            local_device=request.local_translation_device,
            local_source_lang=request.local_translation_source_lang,
            local_target_lang=request.local_translation_target_lang,
            local_max_input_length=request.local_translation_max_input_length,
            local_max_new_tokens=request.local_translation_max_new_tokens,
            local_num_beams=request.local_translation_num_beams,
        ),
        output=OutputConfig(
            output_path=output_root.with_suffix(".ko.grouped.srt"),
            english_output=output_root.with_suffix(".en.srt"),
            english_text_output=output_root.with_suffix(".en.txt"),
            extension_root=DEFAULT_EXTENSION_ROOT if request.register_overlay else None,
            video_id=video_id,
            overlay_label=request.overlay_label,
            review_output=output_root.with_suffix(".review.md"),
            json_output=output_root.with_suffix(".segments.json"),
        ),
    )


def serialize_result(result: PipelineResult, config: PipelineConfig) -> dict[str, str]:
    payload = {
        "input_reference": str(result.input_reference),
        "korean_output": str(result.korean_output_path),
    }
    if config.output.english_output is not None:
        payload["english_srt"] = str(config.output.english_output.resolve())
    if config.output.english_text_output is not None:
        payload["english_txt"] = str(config.output.english_text_output.resolve())
    if config.output.review_output is not None:
        payload["review_md"] = str(config.output.review_output.resolve())
    if config.output.json_output is not None:
        payload["segments_json"] = str(config.output.json_output.resolve())
    if result.overlay_subtitle_path is not None:
        payload["overlay_subtitle"] = str(result.overlay_subtitle_path.resolve())
    payload["quality_issue_count"] = str(result.quality_issue_count)
    return payload


def build_viewer_context(job_store: JobStore, job_id: str) -> dict[str, Any]:
    snapshot = job_store.snapshot(job_id)
    result = snapshot.get("result") or {}
    subtitle_url = result.get("korean_output")
    if not subtitle_url:
        raise HTTPException(status_code=409, detail="This job does not have a completed Korean subtitle output yet.")

    request_payload = snapshot.get("request") or {}
    video_url = request_payload.get("url")
    video_id = extract_video_id(video_url)
    if not video_id:
        raise HTTPException(status_code=400, detail="The completed job does not contain a valid YouTube video id.")

    return {
        "job_id": snapshot["id"],
        "created_at": snapshot["created_at"],
        "video_id": video_id,
        "video_url": video_url,
        "subtitle_artifact_url": f"/api/jobs/{job_id}/artifacts/korean_output",
        "review_artifact_url": f"/api/jobs/{job_id}/artifacts/review_md" if result.get("review_md") else None,
        "quality_issue_count": result.get("quality_issue_count", "0"),
    }


def run_job(job_store: JobStore, job_id: str, request: JobRequest) -> None:
    job = job_store.get(job_id)
    log_stream = JobLogStream(job, job_store._lock)
    config = build_pipeline_config(request, workdir=job.workdir)

    def progress_callback(
        *,
        stage: str,
        progress: float | None = None,
        detail: str | None = None,
    ) -> None:
        job_store.update_progress(
            job_id,
            stage=stage,
            progress=progress,
            detail=detail,
        )

    try:
        job_store.update_status(job_id, "running")
        job_store.update_progress(
            job_id,
            stage="starting",
            progress=1.0,
            detail="Starting pipeline",
        )
        with redirect_stdout(log_stream), redirect_stderr(log_stream):
            result = run_pipeline(
                config,
                target_dir=job.workdir,
                progress_callback=progress_callback,
            )
        job_store.set_result(job_id, serialize_result(result, config))
        job_store.update_status(job_id, "completed")
    except Exception as exc:
        job_store.set_error(job_id, str(exc))
        job_store.append_log(job_id, traceback.format_exc())
        job_store.update_status(job_id, "failed")


def create_app(*, open_browser: bool = False) -> FastAPI:
    app = FastAPI(title="YouTube Transcript Translator UI")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    job_store = JobStore(DEFAULT_JOB_ROOT)
    profiles = list_glossary_profiles()

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.job_store = job_store
    app.state.glossary_profiles = profiles

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "glossary_profiles": profiles,
                "default_translator": DEFAULT_TRANSLATOR,
                "default_local_model": DEFAULT_LOCAL_TRANSLATION_MODEL,
                "default_transcript_source": DEFAULT_TRANSCRIPT_SOURCE,
                "default_local_transcription_model": DEFAULT_LOCAL_TRANSCRIPTION_MODEL,
                "local_transcription_model_presets": LOCAL_TRANSCRIPTION_MODEL_PRESETS,
                "default_extension_root": str(DEFAULT_EXTENSION_ROOT),
            },
        )

    @app.get("/jobs/{job_id}/watch", response_class=HTMLResponse)
    async def watch_job(request: Request, job_id: str) -> HTMLResponse:
        context = build_viewer_context(job_store, job_id)
        return templates.TemplateResponse(
            request,
            "viewer.html",
            context,
        )

    @app.post("/api/jobs")
    async def create_job(payload: JobRequest) -> dict[str, Any]:
        record = job_store.create(payload)
        thread = threading.Thread(
            target=run_job,
            args=(job_store, record.id, payload),
            daemon=True,
            name=f"job-{record.id}",
        )
        thread.start()
        return {"job_id": record.id, "status": record.status}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        return job_store.snapshot(job_id)

    @app.get("/api/jobs/{job_id}/artifacts/{artifact_name}")
    async def get_artifact(job_id: str, artifact_name: str) -> FileResponse:
        snapshot = job_store.snapshot(job_id)
        result = snapshot.get("result") or {}
        path_string = result.get(artifact_name)
        if not path_string:
            raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_name}")
        artifact_path = Path(path_string)
        if not artifact_path.exists():
            raise HTTPException(status_code=404, detail=f"Artifact file missing: {artifact_path}")
        return FileResponse(path=artifact_path, filename=artifact_path.name)

    if open_browser:
        @app.on_event("startup")
        async def _open_browser() -> None:
            webbrowser.open("http://127.0.0.1:8000", new=1)

    return app


app = create_app()
