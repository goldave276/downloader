
import html
import http.cookiejar
import os
import re
import shutil
import tempfile
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
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
    created_at: float = field(default_factory=time.time)

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
    cleanup_expired_jobs()
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

def cleanup_expired_jobs(max_age_seconds: int = 900) -> None:
    now = time.time()
    expired = [jid for jid, rec in jobs.items() if (now - rec.created_at) > max_age_seconds]
    for jid in expired:
        cleanup_job_files(jid)
        jobs.pop(jid, None)


BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_META_VIDEO_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']og:video(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:video(?::secure_url)?["\']', re.I),
    re.compile(r'"contentUrl"\s*:\s*"(https?://[^"]+)"', re.I),
    re.compile(r'"video_versions"\s*:\s*\[\s*\{[^}]*"url"\s*:\s*"(https?://[^"]+)"', re.I),
    re.compile(r'"video_url"\s*:\s*"(https?://[^"]+)"', re.I),
    re.compile(r'(https?://[^"\'\s<>]+?\.mp4(?:\?[^"\'\s<>]*)?)', re.I),
]


def _extract_fallback_video_url(page_url: str, cookies_path: Path | None) -> str | None:
    """Extrait l'URL vidéo directe depuis le HTML (secours pour Threads / Snapchat)."""
    handlers: list[urllib.request.BaseHandler] = []
    if cookies_path and cookies_path.is_file():
        jar = http.cookiejar.MozillaCookieJar(str(cookies_path))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            handlers.append(urllib.request.HTTPCookieProcessor(jar))
        except Exception:
            pass

    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        page_url,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        },
    )
    with opener.open(req, timeout=20) as resp:
        raw_html = resp.read().decode("utf-8", errors="ignore")

    normalized = html.unescape(raw_html).replace(r"\/", "/").replace(r"\u0026", "&")
    for pattern in _META_VIDEO_PATTERNS:
        match = pattern.search(normalized)
        if match:
            candidate = match.group(1).strip()
            if candidate.startswith("http"):
                return candidate
    return None


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

    cookies_path = Path(__file__).resolve().parent / "cookies.txt"
    if cookies_path.is_file():
        ydl_opts["cookiefile"] = str(cookies_path)

    try:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(job.url, download=True)
                if isinstance(info, dict):
                    job.title = info.get("title") or job.platform
        except Exception:
            if job.platform not in ("Threads", "Snapchat"):
                raise
            fallback_url = _extract_fallback_video_url(job.url, cookies_path)
            if not fallback_url:
                raise
            fallback_opts = {
                **ydl_opts,
                "outtmpl": str(job_dir / f"{job.platform} [{job_id[:8]}].%(ext)s"),
                "http_headers": {"User-Agent": BROWSER_UA, "Referer": job.url},
            }
            with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                ydl.extract_info(fallback_url, download=True)
                job.title = f"{job.platform} video"

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