export type JobStatus = 'queued' | 'downloading' | 'merging' | 'ready' | 'error';

export interface JobRecord {
  job_id: string;
  url: string;
  platform: string;
  status: JobStatus;
  progress: number;
  title: string | null;
  filename: string | null;
  error: string | null;
}

export interface HistoryItem {
  id: string;
  title: string;
  platform: string;
  url: string;
  downloadedAt: number;
}

