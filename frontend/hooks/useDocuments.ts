'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { deleteDocument, getUploadJob, listDocuments, uploadDocumentWithProgress } from '@/services/documentService';
import type { DocumentItem, UploadQueueItem } from '@/types/document';

function uid() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [queueItems, setQueueItems] = useState<UploadQueueItem[]>([]);

  const processingRef = useRef(false);
  const queueRef = useRef<UploadQueueItem[]>([]);

  useEffect(() => {
    queueRef.current = queueItems;
  }, [queueItems]);

  const refreshDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await listDocuments();
      setDocuments(data.documents);
      setSelectedIds((current) => current.filter((id) => data.documents.some((doc) => doc.id === id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load documents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);

  const processQueue = useCallback(async () => {
    if (processingRef.current) return;
    processingRef.current = true;

    try {
      while (true) {
        const nextItem = queueRef.current.find((item) => item.status === 'queued');

        if (!nextItem) {
          break;
        }

        setQueueItems((current) =>
          current.map((item) => (item.localId === nextItem.localId ? { ...item, status: 'uploading', uploadProgress: 0, indexProgress: 0 } : item)),
        );

        try {
          const uploadResponse = await uploadDocumentWithProgress(nextItem.file, (progress) => {
            setQueueItems((current) => current.map((item) => (item.localId === nextItem.localId ? { ...item, uploadProgress: progress } : item)));
          });

          const jobId = uploadResponse.job.id;

          setQueueItems((current) =>
            current.map((item) =>
              item.localId === nextItem.localId
                ? {
                    ...item,
                    status: 'processing',
                    uploadProgress: 100,
                    jobId,
                  }
                : item,
            ),
          );

          let completed = false;

          while (!completed) {
            await new Promise((resolve) => setTimeout(resolve, 1000));

            const data = await getUploadJob(jobId);
            const job = data.job;

            setQueueItems((current) =>
              current.map((item) =>
                item.localId === nextItem.localId
                  ? {
                      ...item,
                      status: job.status === 'completed' ? 'completed' : job.status === 'failed' ? 'failed' : 'processing',
                      indexProgress: job.index_progress,
                      error: job.error ?? undefined,
                    }
                  : item,
              ),
            );

            if (job.status === 'completed') {
              completed = true;
              await refreshDocuments();
            }

            if (job.status === 'failed') {
              completed = true;
            }
          }
        } catch (err) {
          setQueueItems((current) =>
            current.map((item) =>
              item.localId === nextItem.localId
                ? {
                    ...item,
                    status: 'failed',
                    error: err instanceof Error ? err.message : 'Upload failed',
                  }
                : item,
            ),
          );
        }
      }
    } finally {
      processingRef.current = false;

      const stillQueued = queueRef.current.some((item) => item.status === 'queued');
      if (stillQueued) {
        void processQueue();
      }
    }
  }, [refreshDocuments]);

  const handleUpload = useCallback(
    async (files: File[]) => {
      setError(null);

      const ordered = [...files].sort((a, b) => a.size - b.size);

      const newItems: UploadQueueItem[] = ordered.map((file) => ({
        localId: uid(),
        file,
        uploadProgress: 0,
        indexProgress: 0,
        status: 'queued',
      }));

      setQueueItems((current) => {
        const next = [...current, ...newItems];
        queueRef.current = next;
        return next;
      });

      if (!processingRef.current) {
        void processQueue();
      }
    },
    [processQueue],
  );

  const handleDelete = useCallback(
    async (documentId: string) => {
      setError(null);

      try {
        await deleteDocument(documentId);
        await refreshDocuments();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Delete failed');
        throw err;
      }
    },
    [refreshDocuments],
  );

  const toggleSelected = useCallback((documentId: string) => {
    setSelectedIds((current) => (current.includes(documentId) ? current.filter((id) => id !== documentId) : [...current, documentId]));
  }, []);

  return useMemo(
    () => ({
      documents,
      loading,
      error,
      selectedIds,
      queueItems,
      refreshDocuments,
      handleUpload,
      handleDelete,
      toggleSelected,
    }),
    [documents, loading, error, selectedIds, queueItems, refreshDocuments, handleUpload, handleDelete, toggleSelected],
  );
}
