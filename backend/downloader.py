
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yt_dlp

JobStatus = Literal["queued", "downloading", "merging", "ready", "error"]
BASE_TEMP_DIR = Path(tempfile.gettempdir()) / "down_pwa_jobs"
BASE_TEMP_DIR.mkdir(parents=True, exist_ok=True)


# Motif qui repère n'importe quelle URL commençant par http:// ou https://
URL_REGEX = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def extract_url(raw_text: str) -> str | None:
    """Extrait la première URL valide trouvée dans un texte partagé."""
    match = URL_REGEX.search(raw_text.strip())
    if not match:
        return None
    # Enlève d'éventuels signes de ponctuation collés à la fin du lien
    return match.group(0).rstrip(".,);!?")


def detect_platform(url: str) -> str:
    """Détecte le réseau social à partir de l'URL."""
    lower = url.lower()
    if "instagram.com" in lower or "instagr.am" in lower:
        return "Instagram"
    if "tiktok.com" in lower:
        return "TikTok"
    if "snapchat.com" in lower:
        return "Snapchat"
    if "x.com" in lower or "twitter.com" in lower or "t.co" in lower:
        return "X"
    if "threads.net" in lower or "threads.com" in lower:
        return "Threads"
    if "pinterest." in lower or "pin.it" in lower:
        return "Pinterest"
    return "Web"


@dataclass
class JobRecord:
    job_id: str
    url: str
    platform: str
    status: JobStatus = "queued"
    progress: float = 0.0
    title: str | None = None
    filename: str | None = None
    file_path: Path | None = None
    error: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "platform": self.platform,
            "status": self.status,
            "progress": round(self.progress, 1),
            "title": self.title,
            "filename": self.filename,
            "error": self.error,
        }


# Dictionnaire en mémoire qui garde la trace de tous les téléchargements
jobs: dict[str, JobRecord] = {}


def create_job(raw_text: str) -> JobRecord:
    url = extract_url(raw_text)
    if not url:
        raise ValueError("Aucune URL valide trouvée.")

    job_id = uuid.uuid4().hex
    record = JobRecord(job_id=job_id, url=url, platform=detect_platform(url))
    jobs[job_id] = record
    return record


def cleanup_job_files(job_id: str) -> None:
    job_dir = BASE_TEMP_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    job = jobs.get(job_id)
    if job:
        job.file_path = None


def run_download(job_id: str) -> None:
    job = jobs.get(job_id)
    if not job:
        return

    job_dir = BASE_TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    job.status = "downloading"

    # Fonction appelée en direct par yt-dlp à chaque morceau téléchargé
    def on_progress(data: dict[str, Any]) -> None:
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            if total > 0:
                job.progress = min(95.0, (downloaded / total) * 95.0)
        elif data.get("status") == "finished":
            job.status = "merging"
            job.progress = 96.0

    ydl_opts: dict[str, Any] = {
        "format": "bv*+ba/b",                   # Meilleure vidéo + meilleur audio
        "merge_output_format": "mp4",           # Fusion FFmpeg en .mp4
        "remux_video": "mp4",
        "noplaylist": True,
        "retries": 5,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(job_dir / "%(title).80B [%(id)s].%(ext)s"),
        "progress_hooks": [on_progress],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(job.url, download=True)
            if isinstance(info, dict):
                job.title = info.get("title") or job.platform

        files = [p for p in job_dir.iterdir() if p.is_file()]
        if not files:
            raise RuntimeError("Aucun fichier vidéo généré.")

        # Prend le .mp4 généré (ou le plus gros fichier)
        mp4s = [p for p in files if p.suffix.lower() == ".mp4"]
        output_file = max(mp4s or files, key=lambda p: p.stat().st_size)

        job.file_path = output_file
        job.filename = output_file.name
        job.progress = 100.0
        job.status = "ready"
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        cleanup_job_files(job_id)