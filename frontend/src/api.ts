import type { JobRecord } from './types';

const URL_REGEX = /https?:\/\/[^\s<>"']+/i;

export function extractUrlFromText(raw: string): string | null {
  const match = raw.trim().match(URL_REGEX);
  if (!match) return null;
  return match[0].replace(/[.,);!?]+$/, '');
}

function buildHeaders(apiKey: string, includeJson = false): HeadersInit {
  const headers: Record<string, string> = {};
  if (includeJson) {
    headers['Content-Type'] = 'application/json';
  }
  if (apiKey.trim()) {
    headers['X-API-Key'] = apiKey.trim();
  }
  return headers;
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string };
    if (typeof data.detail === 'string' && data.detail.trim()) {
      return data.detail;
    }
  } catch {
    // ignore non-JSON body
  }
  return `Erreur serveur (${response.status})`;
}

export async function createDownloadJob(
  baseUrl: string,
  apiKey: string,
  url: string,
): Promise<JobRecord> {
  const res = await fetch(`${baseUrl}/api/jobs`, {
    method: 'POST',
    headers: buildHeaders(apiKey, true),
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
  return (await res.json()) as JobRecord;
}

export async function fetchJobStatus(
  baseUrl: string,
  apiKey: string,
  jobId: string,
): Promise<JobRecord> {
  const res = await fetch(`${baseUrl}/api/jobs/${encodeURIComponent(jobId)}`, {
    headers: buildHeaders(apiKey),
  });
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
  return (await res.json()) as JobRecord;
}

export async function downloadJobFile(
  baseUrl: string,
  apiKey: string,
  jobId: string,
  fallbackFilename: string,
): Promise<void> {
  const res = await fetch(`${baseUrl}/api/jobs/${encodeURIComponent(jobId)}/file`, {
    headers: buildHeaders(apiKey),
  });
  if (!res.ok) {
    throw new Error(await parseError(res));
  }

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = fallbackFilename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
}

export async function triggerYtDlpUpdate(baseUrl: string, apiKey: string): Promise<void> {
  const res = await fetch(`${baseUrl}/api/update-ytdlp`, {
    method: 'POST',
    headers: buildHeaders(apiKey),
  });
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
}

