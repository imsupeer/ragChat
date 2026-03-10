'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { deleteDocument, listDocuments, uploadDocument } from '@/services/documentService';
import type { DocumentItem } from '@/types/document';

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);

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

  const handleUpload = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        await uploadDocument(file);
        await refreshDocuments();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed');
        throw err;
      } finally {
        setUploading(false);
      }
    },
    [refreshDocuments],
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
      uploading,
      selectedIds,
      refreshDocuments,
      handleUpload,
      handleDelete,
      toggleSelected,
    }),
    [documents, loading, error, uploading, selectedIds, refreshDocuments, handleUpload, handleDelete, toggleSelected],
  );
}
