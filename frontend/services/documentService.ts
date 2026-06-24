import { apiFetch } from '@/services/api';
import type { DocumentsResponse, UploadDocumentResponse, UploadJobsResponse } from '@/types/document';

export function listDocuments() {
  return apiFetch<DocumentsResponse>('/documents');
}

export function listUploadJobs() {
  return apiFetch<UploadJobsResponse>('/documents/jobs');
}

export function getUploadJob(jobId: string) {
  return apiFetch<{ job: UploadDocumentResponse['job'] }>(`/documents/jobs/${jobId}`);
}

export function uploadDocumentWithProgress(file: File, onUploadProgress: (progress: number) => void): Promise<UploadDocumentResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', file);

    xhr.open('POST', `${apiUrl}/documents/upload`);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const progress = Math.round((event.loaded / event.total) * 100);
        onUploadProgress(progress);
      }
    };

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);

        if (xhr.status >= 200 && xhr.status < 300) {
          onUploadProgress(100);
          resolve(data);
          return;
        }

        reject(new Error(data?.detail || data?.message || 'Upload failed'));
      } catch {
        reject(new Error('Upload failed'));
      }
    };

    xhr.onerror = () => reject(new Error('Upload failed'));
    xhr.send(formData);
  });
}

export function deleteDocument(documentId: string) {
  return apiFetch<{ message: string; document_id: string }>(`/documents/${documentId}`, {
    method: 'DELETE',
  });
}

export function retryUploadJob(jobId: string) {
  return apiFetch<{ message: string; job: UploadDocumentResponse['job'] }>(`/documents/jobs/${jobId}/retry`, {
    method: 'POST',
  });
}
