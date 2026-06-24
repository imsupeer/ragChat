'use client';

import { useCallback, useEffect, useRef } from 'react';
import { deleteDocument, getUploadJob, listDocuments, listUploadJobs, retryUploadJob, uploadDocumentWithProgress } from '@/services/documentService';
import type { UploadQueueItem } from '@/types/document';
import { useAppStore } from '@/store/useAppStore';

const MAX_PARALLEL_UPLOADS = 2;
const MAX_UPLOAD_RETRIES = 1;
const POLL_INTERVAL_MS = 1200;
const MAX_POLL_DURATION_MS = 10 * 60 * 1000;
const STALL_UNCHANGED_POLLS = 300;
const COMPLETED_DISMISS_MS = 5000;

function uid() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function mapJobStatus(status: string): UploadQueueItem['status'] {
  if (status === 'completed' || status === 'failed' || status === 'processing' || status === 'queued') {
    return status;
  }

  return 'processing';
}

function withUploadProgressTiming(item: UploadQueueItem, uploadProgress: number): Partial<UploadQueueItem> {
  const now = Date.now();
  const uploadStartedAt = item.uploadStartedAt ?? (uploadProgress > 0 ? now : undefined);

  let lastUploadProgress = item.lastUploadProgress;
  let lastUploadProgressAt = item.lastUploadProgressAt;
  if (uploadProgress !== item.uploadProgress) {
    lastUploadProgress = item.uploadProgress;
    lastUploadProgressAt = now;
  }

  return { uploadStartedAt, lastUploadProgress, lastUploadProgressAt };
}

function withIndexProgressTiming(item: UploadQueueItem, indexProgress: number): Partial<UploadQueueItem> {
  const now = Date.now();
  const indexingStartedAt = item.indexingStartedAt ?? (indexProgress > 0 ? now : undefined);

  let lastIndexProgress = item.lastIndexProgress;
  let lastIndexProgressAt = item.lastIndexProgressAt;
  if (indexProgress !== item.indexProgress) {
    lastIndexProgress = item.indexProgress;
    lastIndexProgressAt = now;
  }

  return { indexingStartedAt, lastIndexProgress, lastIndexProgressAt };
}

export function useDocuments() {
  const documents = useAppStore((state) => state.documents);
  const loading = useAppStore((state) => state.documentsLoading);
  const error = useAppStore((state) => state.documentsError);
  const selectedIds = useAppStore((state) => state.selectedDocumentIds);
  const queueItems = useAppStore((state) => state.uploadQueue);

  const setDocuments = useAppStore((state) => state.setDocuments);
  const setDocumentsLoading = useAppStore((state) => state.setDocumentsLoading);
  const setDocumentsError = useAppStore((state) => state.setDocumentsError);
  const setSelectedDocumentIds = useAppStore((state) => state.setSelectedDocumentIds);
  const toggleSelected = useAppStore((state) => state.toggleSelectedDocument);
  const updateUploadQueueItem = useAppStore((state) => state.updateUploadQueueItem);
  const upsertUploadQueueItems = useAppStore((state) => state.upsertUploadQueueItems);
  const removeUploadQueueItem = useAppStore((state) => state.removeUploadQueueItem);

  const inFlightUploadsRef = useRef<Set<string>>(new Set());
  const pollingJobsRef = useRef<Set<string>>(new Set());
  const completedDismissTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const refreshDocuments = useCallback(async () => {
    setDocumentsLoading(true);
    setDocumentsError(null);

    try {
      const data = await listDocuments();
      setDocuments(data.documents);

      const currentSelected = useAppStore.getState().selectedDocumentIds;
      setSelectedDocumentIds(currentSelected.filter((id) => data.documents.some((document) => document.id === id)));
    } catch (err) {
      setDocumentsError(err instanceof Error ? err.message : 'Failed to load documents');
    } finally {
      setDocumentsLoading(false);
    }
  }, [setDocuments, setDocumentsError, setDocumentsLoading, setSelectedDocumentIds]);

  const pollUploadJob = useCallback(
    async (jobId: string, localId: string) => {
      if (pollingJobsRef.current.has(jobId)) {
        return;
      }

      pollingJobsRef.current.add(jobId);

      try {
        let isComplete = false;
        let lastIndexProgress = -1;
        let unchangedProgressPolls = 0;
        const pollStarted = Date.now();

        while (!isComplete) {
          const data = await getUploadJob(jobId);
          const job = data.job;

          if (job.index_progress === lastIndexProgress) {
            unchangedProgressPolls += 1;
          } else {
            unchangedProgressPolls = 0;
            lastIndexProgress = job.index_progress;
          }

          const stalled =
            Date.now() - pollStarted > MAX_POLL_DURATION_MS ||
            (job.status !== 'completed' &&
              job.status !== 'failed' &&
              unchangedProgressPolls >= STALL_UNCHANGED_POLLS);

          updateUploadQueueItem(localId, (item) => ({
            ...item,
            jobId,
            documentId: job.document_id ?? item.documentId ?? null,
            storedPath: job.stored_path ?? item.storedPath,
            status: mapJobStatus(job.status),
            uploadProgress: 100,
            indexProgress: job.index_progress,
            error: job.error ?? undefined,
            recoverable: job.status === 'failed' && !!job.stored_path,
            indexingStartedAt: item.indexingStartedAt ?? Date.now(),
            ...withIndexProgressTiming(item, job.index_progress),
          }));

          if (job.status === 'completed') {
            await refreshDocuments();
            isComplete = true;
            continue;
          }

          if (job.status === 'failed') {
            isComplete = true;
            continue;
          }

          if (stalled) {
            updateUploadQueueItem(localId, (item) => ({
              ...item,
              status: 'failed',
              recoverable: !!item.jobId,
              error:
                item.error ||
                'Indexing stalled. Retry if the saved upload file is still available, or upload the document again.',
            }));
            isComplete = true;
            continue;
          }

          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        }
      } catch (err) {
        updateUploadQueueItem(localId, (item) => ({
          ...item,
          status: 'failed',
          error: err instanceof Error ? err.message : 'Failed to track upload job',
        }));
      } finally {
        pollingJobsRef.current.delete(jobId);
      }
    },
    [refreshDocuments, updateUploadQueueItem],
  );

  const processUpload = useCallback(
    async (localId: string) => {
      const item = useAppStore.getState().uploadQueue.find((queueItem) => queueItem.localId === localId);
      if (!item?.file) {
        inFlightUploadsRef.current.delete(localId);
        return;
      }

      updateUploadQueueItem(localId, (current) => ({
        ...current,
        status: 'uploading',
        uploadProgress: Math.max(current.uploadProgress, 1),
        error: undefined,
        uploadStartedAt: current.uploadStartedAt ?? Date.now(),
      }));

      try {
        const response = await uploadDocumentWithProgress(item.file, (progress) => {
          updateUploadQueueItem(localId, (current) => ({
            ...current,
            uploadProgress: progress,
            status: progress >= 100 ? 'processing' : 'uploading',
            ...(progress >= 100 && !current.indexingStartedAt ? { indexingStartedAt: Date.now() } : {}),
            ...withUploadProgressTiming(current, progress),
          }));
        });

        updateUploadQueueItem(localId, (current) => ({
          ...current,
          jobId: response.job.id,
          documentId: response.job.document_id ?? current.documentId ?? null,
          storedPath: response.job.stored_path,
          uploadProgress: 100,
          indexProgress: response.job.index_progress,
          status: 'processing',
          error: undefined,
          indexingStartedAt: current.indexingStartedAt ?? Date.now(),
          ...withIndexProgressTiming(current, response.job.index_progress),
        }));

        await pollUploadJob(response.job.id, localId);
      } catch (err) {
        const current = useAppStore.getState().uploadQueue.find((queueItem) => queueItem.localId === localId);
        const nextRetryCount = (current?.retryCount ?? 0) + 1;

        if ((current?.retryCount ?? 0) < MAX_UPLOAD_RETRIES) {
          updateUploadQueueItem(localId, (queueItem) => ({
            ...queueItem,
            status: 'queued',
            retryCount: nextRetryCount,
            error: 'Retrying upload...',
          }));
        } else {
          updateUploadQueueItem(localId, (queueItem) => ({
            ...queueItem,
            status: 'failed',
            retryCount: nextRetryCount,
            error: err instanceof Error ? err.message : 'Upload failed',
          }));
        }
      } finally {
        inFlightUploadsRef.current.delete(localId);

        const nextQueued = useAppStore.getState().uploadQueue.some((queueItem) => queueItem.status === 'queued' && queueItem.file);

        if (nextQueued) {
          const queuedItems = useAppStore
            .getState()
            .uploadQueue.filter((queueItem) => queueItem.status === 'queued' && queueItem.file && !inFlightUploadsRef.current.has(queueItem.localId));

          while (inFlightUploadsRef.current.size < MAX_PARALLEL_UPLOADS && queuedItems.length > 0) {
            const nextItem = queuedItems.shift();
            if (!nextItem) {
              break;
            }

            inFlightUploadsRef.current.add(nextItem.localId);
            void processUpload(nextItem.localId);
          }
        }
      }
    },
    [pollUploadJob, updateUploadQueueItem],
  );

  const scheduleQueuedUploads = useCallback(() => {
    const queuedItems = useAppStore
      .getState()
      .uploadQueue.filter((item) => item.status === 'queued' && item.file && !inFlightUploadsRef.current.has(item.localId));

    while (inFlightUploadsRef.current.size < MAX_PARALLEL_UPLOADS && queuedItems.length > 0) {
      const nextItem = queuedItems.shift();
      if (!nextItem) {
        break;
      }

      inFlightUploadsRef.current.add(nextItem.localId);
      void processUpload(nextItem.localId);
    }
  }, [processUpload]);

  const refreshUploadJobs = useCallback(async () => {
    try {
      const data = await listUploadJobs();
      const existingByJobId = new Set(
        useAppStore
          .getState()
          .uploadQueue.map((item) => item.jobId)
          .filter((jobId): jobId is string => !!jobId),
      );

      const recoveredItems: UploadQueueItem[] = data.jobs
        .filter((job) => !existingByJobId.has(job.id))
        .map((job) => ({
          localId: job.id,
          filename: job.filename,
          fileSize: job.file_size,
          uploadProgress: job.status === 'queued' ? job.upload_progress : 100,
          indexProgress: job.index_progress,
          status: mapJobStatus(job.status),
          jobId: job.id,
          documentId: job.document_id ?? null,
          storedPath: job.stored_path,
          retryCount: 0,
          source: 'recovered',
          error: job.error ?? undefined,
          recoverable: job.status === 'failed' && !!job.stored_path,
          indexingStartedAt:
            job.status === 'processing' || job.index_progress > 0 ? Date.now() : undefined,
        }));

      if (recoveredItems.length) {
        upsertUploadQueueItems(recoveredItems);
      }

      recoveredItems
        .filter((item) => item.jobId && item.status !== 'completed' && item.status !== 'failed')
        .forEach((item) => {
          if (item.jobId) {
            void pollUploadJob(item.jobId, item.localId);
          }
        });
    } catch {
      // Job recovery is best-effort and should not block normal document loading.
    }
  }, [pollUploadJob, upsertUploadQueueItems]);

  useEffect(() => {
    void refreshDocuments();
    void refreshUploadJobs();
  }, [refreshDocuments, refreshUploadJobs]);

  useEffect(() => {
    scheduleQueuedUploads();
  }, [queueItems, scheduleQueuedUploads]);

  useEffect(() => {
    const timers = completedDismissTimersRef.current;
    const activeIds = new Set(queueItems.map((item) => item.localId));

    queueItems.forEach((item) => {
      if (item.status !== 'completed' || timers.has(item.localId)) {
        return;
      }

      const timer = setTimeout(() => {
        removeUploadQueueItem(item.localId);
        timers.delete(item.localId);
      }, COMPLETED_DISMISS_MS);

      timers.set(item.localId, timer);
    });

    for (const [localId, timer] of [...timers.entries()]) {
      if (!activeIds.has(localId)) {
        clearTimeout(timer);
        timers.delete(localId);
      }
    }
  }, [queueItems, removeUploadQueueItem]);

  useEffect(() => {
    const timers = completedDismissTimersRef.current;
    return () => {
      for (const timer of timers.values()) {
        clearTimeout(timer);
      }
      timers.clear();
    };
  }, []);

  const handleUpload = useCallback(
    async (files: File[]) => {
      setDocumentsError(null);

      const ordered = [...files].sort((left, right) => left.size - right.size);
      const nextItems: UploadQueueItem[] = ordered.map((file) => ({
        localId: uid(),
        filename: file.name,
        file,
        fileSize: file.size,
        uploadProgress: 0,
        indexProgress: 0,
        status: 'queued',
        retryCount: 0,
        source: 'local',
      }));

      upsertUploadQueueItems(nextItems);
    },
    [setDocumentsError, upsertUploadQueueItems],
  );

  const handleDelete = useCallback(
    async (documentId: string) => {
      setDocumentsError(null);

      try {
        await deleteDocument(documentId);
        await refreshDocuments();
      } catch (err) {
        setDocumentsError(err instanceof Error ? err.message : 'Delete failed');
        throw err;
      }
    },
    [refreshDocuments, setDocumentsError],
  );

  const handleRetryJob = useCallback(
    async (localId: string) => {
      const item = useAppStore.getState().uploadQueue.find((queueItem) => queueItem.localId === localId);
      if (!item?.jobId) {
        return;
      }

      setDocumentsError(null);
      updateUploadQueueItem(localId, (current) => ({
        ...current,
        status: 'processing',
        indexProgress: 0,
        error: undefined,
        recoverable: false,
        indexingStartedAt: Date.now(),
        lastIndexProgress: undefined,
        lastIndexProgressAt: undefined,
      }));

      try {
        const response = await retryUploadJob(item.jobId);
        updateUploadQueueItem(localId, (current) => ({
          ...current,
          jobId: response.job.id,
          storedPath: response.job.stored_path,
          status: mapJobStatus(response.job.status),
          indexProgress: response.job.index_progress,
          error: response.job.error ?? undefined,
          recoverable: response.job.status === 'failed',
          indexingStartedAt: current.indexingStartedAt ?? Date.now(),
          ...withIndexProgressTiming(current, response.job.index_progress),
        }));
        await pollUploadJob(response.job.id, localId);
      } catch (err) {
        updateUploadQueueItem(localId, (current) => ({
          ...current,
          status: 'failed',
          recoverable: true,
          error: err instanceof Error ? err.message : 'Retry failed',
        }));
      }
    },
    [pollUploadJob, setDocumentsError, updateUploadQueueItem],
  );

  return {
    documents,
    loading,
    error,
    selectedIds,
    queueItems,
    refreshDocuments,
    handleUpload,
    handleDelete,
    handleRetryJob,
    toggleSelected,
  };
}
