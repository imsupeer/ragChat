export type DocumentItem = {
  id: string;
  filename: string;
  stored_path?: string;
  total_chunks: number;
};

export type UploadJob = {
  id: string;
  filename: string;
  file_size: number;
  stored_path: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  upload_progress: number;
  index_progress: number;
  error?: string | null;
  document_id?: string | null;
  created_at?: string;
};

export type UploadQueueItem = {
  localId: string;
  filename: string;
  file?: File;
  fileSize?: number;
  uploadProgress: number;
  indexProgress: number;
  status: 'queued' | 'uploading' | 'processing' | 'completed' | 'failed';
  jobId?: string;
  documentId?: string | null;
  storedPath?: string;
  retryCount: number;
  source: 'local' | 'recovered';
  error?: string;
  recoverable?: boolean;
  uploadStartedAt?: number;
  indexingStartedAt?: number;
  lastUploadProgress?: number;
  lastUploadProgressAt?: number;
  lastIndexProgress?: number;
  lastIndexProgressAt?: number;
};

export type UploadDocumentResponse = {
  message: string;
  job: UploadJob;
};

export type DocumentsResponse = {
  documents: DocumentItem[];
};

export type UploadJobsResponse = {
  jobs: UploadJob[];
};
