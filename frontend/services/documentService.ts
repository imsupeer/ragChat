import { apiFetch } from '@/services/api';
import type { DocumentsResponse, UploadDocumentResponse } from '@/types/document';

export function listDocuments() {
  return apiFetch<DocumentsResponse>('/documents');
}

export async function uploadDocument(file: File) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/documents/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let detail = 'Failed to upload document';
    try {
      const data = await response.json();
      detail = data?.detail ?? detail;
    } catch {}
    throw new Error(detail);
  }

  return response.json() as Promise<UploadDocumentResponse>;
}

export function deleteDocument(documentId: string) {
  return apiFetch<{ message: string; document_id: string }>(`/documents/${documentId}`, {
    method: 'DELETE',
  });
}
