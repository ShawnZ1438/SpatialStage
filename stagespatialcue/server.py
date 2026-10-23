"""Loopback-only operator API and static app."""
from __future__ import annotations

import os
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .audio import StageController, audio_duration
from .http_safety import RequestSizeLimit
from .autocal import AutoCalConfig, AutoCalManager, geometry_signature
from .models import Cue, Project
from .spatial import calibration_preview
from .storage import AUDIO_EXT, ProjectStore

MAX_UPLOAD_BYTES = 150 * 1024 * 1024
STATIC_DIR = Path(__file__).parent / "static"


class NamePayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ArmPayload(BaseModel):
    project_id: str
    index: int = Field(default=0, ge=0)
    cue_id: str | None = None


class ProjectPayload(BaseModel):
    project_id: str


class GoPayload(ProjectPayload):
    cut: bool = False


class DevicePayload(BaseModel):
    device_index: int = Field(ge=0)


class MasterPayload(BaseModel):
    mute: bool
    db: float = Field(ge=-90, le=6)


class TestPayload(BaseModel):
    channel: int = Field(ge=1, le=4)


class CapturePayload(BaseModel):
    recording: bool


class MonitorPayload(BaseModel):
    gains: list[float] = Field(min_length=4, max_length=4)


class AutoCalStartPayload(BaseModel):
    hardware_ready: bool = False


class AutoCalApplyPayload(BaseModel):
    confirm: str = ""


def filename_key(cue: Cue):
    match = re.match(r"^(\d{1,5})[-_ ]", cue.filename)
    return (0, int(match.group(1)), cue.filename.lower()) if match else (1, cue.filename.lower(), "")


def create_app(data_root: Path | None = None) -> FastAPI:
    root = Path(data_root or os.environ.get("STAGE_SPATIAL_DATA", "~/.spatialstage/projects"))
    store = ProjectStore(root)
    stage = StageController(store)
    autocal = AutoCalManager(store, stage)
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        stage.status()  # flush buffered render events from the audio callback
        autocal.cancel()
        stage.shutdown()

    app = FastAPI(title="SpatialStage", version=__version__, lifespan=lifespan)
    app.add_middleware(RequestSizeLimit)
    app.state.store = store
    app.state.stage = stage
    app.state.autocal = autocal

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        origin = request.headers.get("origin", "")
        host = request.headers.get("host", "")
        if host not in {"127.0.0.1:8765", "localhost:8765"}:
            return Response("Only loopback hosts are allowed", status_code=403)
        if origin and origin not in {"http://127.0.0.1:8765", "http://localhost:8765"}:
            return Response("Only the SpatialStage browser origin on port 8765 is allowed", status_code=403)
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {"version": __version__, "mode": "local", "sample_rate": 48000}

    @app.get("/api/projects")
    def projects():
        return store.all()

    @app.post("/api/projects")
    def create_project(payload: NamePayload):
        return store.create(payload.name)

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        return store.get(project_id)

    @app.put("/api/projects/{project_id}")
    def replace_project(project_id: str, project: Project):
        if project.id != project_id:
            raise HTTPException(status_code=400, detail="Project ID cannot change")
        if not (store.directory(project_id) / "project.json").exists():
            raise HTTPException(status_code=404, detail="Project missing")
        for cue in project.cues:
            if cue.media_relpath:
                store.media_path(project_id, cue.media_relpath)  # validate only; missing file allowed in editor
        stage.can_update(project)
        previous = store.get(project_id)
        # Never let a general project editor bypass deliberate AutoCal approval.
        project.active_calibration_id = previous.active_calibration_id
        project.calibration_enabled = previous.calibration_enabled
        # Any geometry/routing/trim modification invalidates acoustic measurement.
        if (geometry_signature(project.speakers) != geometry_signature(previous.speakers)
                or project.distance_compensation != previous.distance_compensation):
            project.active_calibration_id = None
            project.calibration_enabled = False
        project.schema_version = 3
        saved = store.save(project)
        stage.sync(saved)
        stage.log("project_saved", cue_count=len(saved.cues))
        return saved

    @app.post("/api/projects/{project_id}/upload")
    async def upload_audio(project_id: str, files: list[UploadFile] = File(...)):
        project = store.get(project_id)
        if len(files) > 250:
            raise HTTPException(status_code=413, detail="Maximum 250 files per upload")
        added, ignored = [], []
        for source in files:
            name = Path((source.filename or "").replace("\\", "/")).name
            if Path(name).suffix.lower() not in AUDIO_EXT or name.startswith("._"):
                ignored.append(name)
                continue
            written = 0
            with tempfile.NamedTemporaryFile(prefix="stageupload-", delete=False) as temp:
                temp_path = Path(temp.name)
                try:
                    while chunk := await source.read(1024 * 1024):
                        written += len(chunk)
                        if written > MAX_UPLOAD_BYTES:
                            raise HTTPException(status_code=413, detail=f"File exceeds 150 MiB: {name}")
                        temp.write(chunk)
                    temp.flush()
                    relative, display_name = store.add_file(project_id, temp_path, name)
                finally:
                    temp.close()  # Windows cannot unlink an open upload file.
                    temp_path.unlink(missing_ok=True)
            full = store.media_path(project_id, relative)
            match = re.match(r"^\d{1,5}[-_ ](.+)$", Path(display_name).stem)
            title = match.group(1).replace("_", " ") if match else Path(display_name).stem.replace("_", " ")
            cue = Cue(title=title, filename=display_name, media_relpath=relative, duration_s=audio_duration(full))
            added.append(cue)
        # Decoding/upload awaits may overlap ordinary saves. Re-read current fields.
        project = store.get(project_id)
        project.cues.extend(sorted(added, key=filename_key))
        store.save(project)
        stage.sync(project)
        stage.log("media_import", added=len(added), ignored=len(ignored))
        return {"added": len(added), "ignored": ignored, "project": project}

    @app.post("/api/projects/{project_id}/cues/{cue_id}/replace-media")
    async def replace_cue_media(project_id: str, cue_id: str, file: UploadFile = File(...)):
        project = store.get(project_id)
        cue = next((c for c in project.cues if c.id == cue_id), None)
        if cue is None:
            raise HTTPException(status_code=404, detail="Cue not found")
        name = Path((file.filename or "").replace("\\", "/")).name
        if Path(name).suffix.lower() not in AUDIO_EXT:
            raise HTTPException(status_code=400, detail="Unsupported audio format")
        with tempfile.NamedTemporaryFile(prefix="spatialstage-media-", delete=False) as temp:
            path = Path(temp.name)
            size = 0
            try:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="Audio exceeds 150 MiB")
                    temp.write(chunk)
                temp.flush()
                relative, display = store.add_file(project_id, path, name)
            finally:
                temp.close()  # Windows cannot unlink an open upload file.
                path.unlink(missing_ok=True)
        duration = audio_duration(store.media_path(project_id, relative))
        project = store.get(project_id)
        cue = next((c for c in project.cues if c.id == cue_id), None)
        if cue is None:
            raise HTTPException(status_code=404, detail="Cue was deleted during media upload")
        cue.filename = display
        cue.media_relpath = relative
        cue.duration_s = duration
        saved = store.save(project)
        stage.sync(saved)
        return {"cue": cue, "project": saved,
                "note": "Playing/pre-scheduled voices retain their original audio samples; fresh GO uses replacement."}

    @app.post("/api/calibration/preview")
    def preview_calibration(project: Project):
        return {"reference": "stage_center_0_0", "speaker_hints": calibration_preview(project.speakers),
                "measured": False, "delay_applied": False,
                "warning": "Geometry is calculated. SPL, latency and acoustic localization are NOT measured."}

    @app.get("/api/projects/{project_id}/autocal")
    def autocal_overview(project_id: str):
        project = store.get(project_id)
        return {"config": autocal.config(project_id),
                "sessions": autocal.sessions(project_id),
                "run": autocal.status(project_id),
                "enabled": project.calibration_enabled,
                "active_calibration_id": project.active_calibration_id,
                "note": "One point: balanced means stage-center matching only; no multi-position correction or EQ."}

    @app.put("/api/projects/{project_id}/autocal/config")
    def autocal_update_config(project_id: str, config: AutoCalConfig):
        return autocal.save_config(project_id, config)

    @app.post("/api/projects/{project_id}/autocal/start")
    def autocal_start(project_id: str, payload: AutoCalStartPayload):
        return autocal.start(project_id, hardware_ready=payload.hardware_ready)

    @app.post("/api/projects/{project_id}/autocal/cancel")
    def autocal_cancel(project_id: str):
        store.get(project_id)
        if autocal.status(project_id)["state"] in {"running", "cancelling"}:
            autocal.cancel()
        return autocal.status(project_id)

    @app.get("/api/projects/{project_id}/autocal/run")
    def autocal_run_status(project_id: str):
        store.get(project_id)
        return autocal.status(project_id)

    @app.get("/api/projects/{project_id}/autocal/sessions/{session_id}")
    def autocal_report(project_id: str, session_id: str):
        store.get(project_id)
        return autocal.session(project_id, session_id)

    @app.post("/api/projects/{project_id}/autocal/sessions/{session_id}/apply")
    def autocal_apply(project_id: str, session_id: str, payload: AutoCalApplyPayload):
        return autocal.apply(project_id, session_id, confirm=payload.confirm)

    @app.post("/api/projects/{project_id}/autocal/disable")
    def autocal_disable(project_id: str):
        return autocal.disable(project_id)

    @app.get("/api/projects/{project_id}/export")
    def export_project(project_id: str):
        stream = store.export_zip(project_id)
        def chunks():
            try:
                while data := stream.read(64 * 1024):
                    yield data
            finally:
                stream.close()
        return StreamingResponse(chunks(), media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="SpatialStage-{project_id}.zip"'
        })

    @app.get("/api/devices")
    def devices():
        return stage.devices()

    @app.post("/api/audio/arm")
    def arm(payload: ArmPayload):
        return stage.arm(payload.project_id, payload.index, payload.cue_id)

    @app.post("/api/audio/connect")
    def connect(payload: DevicePayload):
        return stage.connect(payload.device_index)

    @app.post("/api/simulation/connect")
    def simulation_connect():
        return stage.connect_simulation()

    @app.post("/api/simulation/monitor")
    def simulation_monitor(payload: DevicePayload):
        return stage.connect_simulation(payload.device_index)

    @app.post("/api/simulation/monitor-gains")
    def simulation_monitor_gains(payload: MonitorPayload):
        import numpy as np
        from .simulation import StereoMonitorStream
        if not isinstance(stage.stream, StereoMonitorStream):
            raise ValueError("Connect stereo monitor first")
        gains = np.asarray(payload.gains, dtype=np.float32)
        if not np.isfinite(gains).all() or np.any(gains < 0) or np.any(gains > 1):
            raise ValueError("Monitor gains must be finite values in 0..1")
        stage.stream.gains = gains
        return stage.status()

    def simulation_stream():
        from .simulation import SimulationStream
        if not isinstance(stage.stream, SimulationStream):
            raise ValueError("Connect silent simulation first")
        return stage.stream

    @app.post("/api/simulation/capture")
    def simulation_capture(payload: CapturePayload):
        simulation_stream().capture(payload.recording)
        return stage.status()

    @app.get("/api/simulation/capture.wav")
    def simulation_download():
        return Response(simulation_stream().wav(), media_type="audio/wav", headers={
            "Content-Disposition": 'attachment; filename="SpatialStage-4ch-48000.wav"'})

    @app.post("/api/audio/disconnect")
    def disconnect():
        return stage.disconnect()

    @app.get("/api/audio/status")
    def status():
        return stage.status()

    @app.post("/api/audio/master")
    def master(payload: MasterPayload):
        if stage.measurement_active:
            raise ValueError("Master output is locked while AutoCal measurement runs")
        if stage.mixer is None:
            raise ValueError("Arm a project first")
        if not payload.mute and (not stage._output_active() or stage.audio_error):
            raise ValueError(stage.audio_error or "Connect an active output before unmuting")
        with stage.mixer.lock:
            stage.mixer.master_mute = payload.mute
            stage.mixer.master_db = payload.db
        stage.log("master_changed", mute=payload.mute, db=payload.db)
        return stage.status()

    @app.post("/api/audio/go")
    def go(payload: GoPayload):
        return stage.go(payload.project_id, cut=payload.cut)

    @app.post("/api/audio/skip")
    def skip():
        return stage.skip()

    @app.post("/api/audio/stop")
    def stop():
        if stage.mixer:
            stage.mixer.stop_all(0.04)
        stage.log("operator_stop")
        return stage.status()

    @app.post("/api/audio/panic")
    def panic():
        autocal.cancel()
        if stage.mixer:
            stage.mixer.panic()
        stage.log("operator_panic")
        return stage.status()

    @app.post("/api/audio/test")
    def test(payload: TestPayload):
        if stage.measurement_active:
            raise ValueError("AutoCal currently owns the sound hardware")
        if not stage._output_active() or stage.audio_error:
            raise ValueError(stage.audio_error or "Connect a 4-channel interface first")
        if stage.mixer is None or stage.mixer.master_mute:
            raise ValueError("Unmute at very low volume to test speakers")
        stage.mixer.speaker_test(payload.channel)
        stage.log("speaker_test", channel=payload.channel)
        return stage.status()

    @app.get("/api/projects/{project_id}/preflight")
    def preflight(project_id: str):
        return stage.preflight(project_id)

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def missing_error(request: Request, exc: FileNotFoundError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app



def main():
    import uvicorn
    uvicorn.run("stagespatialcue.server:create_app", factory=True, host="127.0.0.1", port=8765, reload=False, access_log=False)


if __name__ == "__main__":
    main()
