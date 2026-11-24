# Down — PWA personnelle de téléchargement vidéo

Télécharge des vidéos en **qualité maximale (MP4)** depuis Instagram, TikTok, Snapchat, X, Threads et Pinterest, directement depuis le menu **Partager** d'Android.

## Architecture
- **`backend/`** : Python + FastAPI + `yt-dlp` + `ffmpeg`
- **`frontend/`** : Vite + React + TypeScript + PWA (`vite-plugin-pwa` avec `share_target`)
- **`Dockerfile`** : Build multi-stage unique prêt pour Render, Railway, Fly.io ou VPS

## Lancer en local (Dev)

### 1. Backend (Terminal 1)
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8888
```

### 2. Frontend (Terminal 2)
```powershell
cd frontend
npm run dev
```

## Déployer en HTTPS & installer sur Android
1. Déploie le dépôt sur **Render**, **Railway** ou **Fly.io** (détection automatique du `Dockerfile`) et ajoute la variable d'environnement `API_SECRET`.
2. Ouvre l'URL `https://...` dans **Chrome Android** → menu `⋮` → **Installer l'application**.
3. Saisis ta clé `API_SECRET` dans **⚙️** (une seule fois).
4. Depuis Instagram / TikTok / X / Threads / Snap / Pinterest → **Partager** → **Down**.
