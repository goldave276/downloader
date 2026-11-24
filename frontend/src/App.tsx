import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createDownloadJob,
  downloadJobFile,
  extractUrlFromText,
  fetchJobStatus,
  triggerYtDlpUpdate,
} from './api';
import type { HistoryItem, JobRecord } from './types';

const STORAGE_API_KEY = 'down_api_key';
const STORAGE_BACKEND_URL = 'down_backend_url';
const STORAGE_HISTORY = 'down_history';

function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_HISTORY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as HistoryItem[]) : [];
  } catch {
    return [];
  }
}

export default function App() {
  const [urlInput, setUrlInput] = useState('');
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(STORAGE_API_KEY) ?? '');
  const [backendUrl, setBackendUrl] = useState(() => localStorage.getItem(STORAGE_BACKEND_URL) ?? '');
  const [showSettings, setShowSettings] = useState(false);

  const [activeJob, setActiveJob] = useState<JobRecord | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [isUpdatingEngine, setIsUpdatingEngine] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>(loadHistory);

  const pollTimerRef = useRef<number | null>(null);
  const autoShareHandledRef = useRef(false);

  const normalizedBaseUrl = backendUrl.trim().replace(/\/+$/, '');

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const pushHistory = useCallback((job: JobRecord) => {
    const entry: HistoryItem = {
      id: job.job_id,
      title: job.title ?? job.filename ?? job.url,
      platform: job.platform,
      url: job.url,
      downloadedAt: Date.now(),
    };
    setHistory((prev) => {
      const next = [entry, ...prev].slice(0, 25);
      localStorage.setItem(STORAGE_HISTORY, JSON.stringify(next));
      return next;
    });
  }, []);

  const startDownload = useCallback(
    async (rawText: string) => {
      const cleanUrl = extractUrlFromText(rawText);
      if (!cleanUrl) {
        setErrorMsg('Colle un lien vidéo valide (Instagram, TikTok, X, Threads, Snap, Pinterest...).');
        return;
      }

      stopPolling();
      setErrorMsg(null);
      setToastMsg(null);
      setIsBusy(true);
      setUrlInput(cleanUrl);

      try {
        const created = await createDownloadJob(normalizedBaseUrl, apiKey, cleanUrl);
        setActiveJob(created);

        pollTimerRef.current = window.setInterval(async () => {
          try {
            const latest = await fetchJobStatus(normalizedBaseUrl, apiKey, created.job_id);
            setActiveJob(latest);

            if (latest.status === 'ready') {
              stopPolling();
              await downloadJobFile(
                normalizedBaseUrl,
                apiKey,
                latest.job_id,
                latest.filename ?? 'video.mp4',
              );
              pushHistory(latest);
              setIsBusy(false);
              setToastMsg('Vidéo téléchargée en qualité maximale.');
            } else if (latest.status === 'error') {
              stopPolling();
              setIsBusy(false);
              setErrorMsg(latest.error ?? 'Échec du téléchargement.');
            }
          } catch (pollErr) {
            stopPolling();
            setIsBusy(false);
            setErrorMsg(pollErr instanceof Error ? pollErr.message : 'Connexion perdue.');
          }
        }, 1000);
      } catch (err) {
        setIsBusy(false);
        setErrorMsg(err instanceof Error ? err.message : 'Erreur inconnue.');
      }
    },
    [apiKey, normalizedBaseUrl, pushHistory, stopPolling],
  );

  useEffect(() => {
    if (autoShareHandledRef.current) return;
    autoShareHandledRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const sharedRaw = params.get('url') ?? params.get('text') ?? params.get('title');
    if (sharedRaw) {
      window.history.replaceState({}, '', '/');
      void startDownload(sharedRaw);
    }

    return () => stopPolling();
  }, [startDownload, stopPolling]);

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setUrlInput(text);
        setErrorMsg(null);
      }
    } catch {
      setErrorMsg('Impossible de lire le presse-papiers. Colle le lien manuellement.');
    }
  };

  const handleSaveSettings = () => {
    localStorage.setItem(STORAGE_API_KEY, apiKey.trim());
    localStorage.setItem(STORAGE_BACKEND_URL, backendUrl.trim());
    setShowSettings(false);
    setToastMsg('Paramètres enregistrés.');
  };

  const handleUpdateYtDlp = async () => {
    setIsUpdatingEngine(true);
    setErrorMsg(null);
    setToastMsg(null);
    try {
      await triggerYtDlpUpdate(normalizedBaseUrl, apiKey);
      setToastMsg('Moteur yt-dlp mis à jour.');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Échec mise à jour yt-dlp.');
    } finally {
      setIsUpdatingEngine(false);
    }
  };

  const clearHistory = () => {
    setHistory([]);
    localStorage.removeItem(STORAGE_HISTORY);
  };

  const statusLabel = (job: JobRecord): string => {
    switch (job.status) {
      case 'queued':
        return 'En file d’attente...';
      case 'downloading':
        return `Téléchargement (${job.platform})...`;
      case 'merging':
        return 'Fusion qualité max (MP4)...';
      case 'ready':
        return 'Terminé';
      case 'error':
        return 'Erreur';
    }
  };

  return (
    <main className="app">
      <header className="header">
        <div className="brand">
          <img src="/icon-192.png" alt="Down" className="brand-logo" />
          <h1>Down</h1>
          <span className="badge">MAX HD</span>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="icon-btn"
            onClick={() => void handleUpdateYtDlp()}
            disabled={isUpdatingEngine}
          >
            {isUpdatingEngine ? 'MAJ...' : 'MAJ yt-dlp'}
          </button>
          <button
            type="button"
            className="icon-btn"
            onClick={() => setShowSettings((prev) => !prev)}
            title="Paramètres"
          >
            ⚙️
          </button>
        </div>
      </header>

      {showSettings && (
        <section className="card">
          <label className="field-label">
            Clé secrète (X-API-Key)
            <input
              type="password"
              className="input"
              placeholder="Ta clé API_SECRET du serveur"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </label>
          <label className="field-label">
            URL du serveur (laisser vide si même domaine)
            <input
              type="url"
              className="input"
              placeholder="https://mon-serveur.example.com"
              value={backendUrl}
              onChange={(e) => setBackendUrl(e.target.value)}
            />
          </label>
          <button type="button" className="primary-btn" onClick={handleSaveSettings}>
            Enregistrer
          </button>
        </section>
      )}

      <section className="card">
        <div className="input-row">
          <input
            type="url"
            className="input"
            placeholder="Colle un lien Insta, TikTok, X, Threads, Snap..."
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            disabled={isBusy}
          />
          <button type="button" className="secondary-btn" onClick={() => void handlePaste()} disabled={isBusy}>
            Coller
          </button>
        </div>
        <button
          type="button"
          className="primary-btn"
          onClick={() => void startDownload(urlInput)}
          disabled={isBusy || !urlInput.trim()}
        >
          {isBusy ? 'Téléchargement en cours...' : 'Télécharger (Qualité max)'}
        </button>

        {activeJob && (
          <>
            <div className="status-row">
              <span>{statusLabel(activeJob)}</span>
              <span className="status-pct">{Math.round(activeJob.progress)}%</span>
            </div>
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{ width: `${Math.max(4, Math.min(100, activeJob.progress))}%` }}
              />
            </div>
          </>
        )}

        {toastMsg && <div className="info-box">{toastMsg}</div>}
        {errorMsg && <div className="error-box">{errorMsg}</div>}
      </section>

      <section style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div className="section-title">
          <span>Historique ({history.length})</span>
          {history.length > 0 && (
            <button type="button" className="link-btn" onClick={clearHistory}>
              Effacer
            </button>
          )}
        </div>

        {history.length === 0 ? (
          <div className="card empty-hint">
            Partage directement une vidéo depuis Instagram, TikTok, Snapchat, X, Threads ou Pinterest vers <strong>Down</strong>.
          </div>
        ) : (
          <div className="history-list">
            {history.map((item) => (
              <article key={item.id} className="history-item">
                <div className="history-top">
                  <span className="history-title">{item.title}</span>
                  <span className="badge">{item.platform}</span>
                </div>
                <span className="history-meta">
                  {new Date(item.downloadedAt).toLocaleString('fr-FR', {
                    day: '2-digit',
                    month: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
