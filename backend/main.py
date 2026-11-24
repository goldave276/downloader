import asyncio
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

from downloader import cleanup_job_files, create_job, jobs, run_download

# Charge les variables du fichier .env s'il existe
load_dotenv()

app = FastAPI(title="Down API")

# Autorise le frontend (Vite) à appeler le backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Vérifie la clé secrète si API_SECRET est configurée sur le serveur."""
    expected = os.getenv("API_SECRET", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Clé API invalide.")


class CreateJobRequest(BaseModel):
    url: str


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/jobs", dependencies=[Depends(verify_api_key)])
async def start_download(payload: CreateJobRequest) -> dict[str, object]:
    try:
        job = create_job(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Lance le téléchargement en arrière-plan sans bloquer le serveur
    asyncio.create_task(asyncio.to_thread(run_download, job.job_id))
    return job.to_public_dict()


@app.get("/api/jobs/{job_id}", dependencies=[Depends(verify_api_key)])
def get_job_status(job_id: str) -> dict[str, object]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job introuvable.")
    return job.to_public_dict()


@app.get("/api/jobs/{job_id}/file", dependencies=[Depends(verify_api_key)])
def download_job_file(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if not job or job.status != "ready" or not job.file_path or not job.file_path.is_file():
        raise HTTPException(status_code=404, detail="Fichier non prêt.")

    return FileResponse(
        path=job.file_path,
        media_type="video/mp4",
        filename=job.filename or "video.mp4",
        background=BackgroundTask(cleanup_job_files, job_id),
    )

@app.post("/api/update-ytdlp", dependencies=[Depends(verify_api_key)])
async def update_ytdlp() -> dict[str, str]:
    proc = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=proc.stderr.strip() or "Échec mise à jour.")
    return {"status": "updated"}


# En production, sert le site Vite compilé (frontend/dist)
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str) -> FileResponse:
        target = FRONTEND_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")