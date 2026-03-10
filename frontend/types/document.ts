export type DocumentItem = {
  id: string;
  filename: string;
  stored_path?: string;
  total_chunks: number;
};

export type UploadDocumentResponse = {
  message: string;
  document: DocumentItem;
};

export type DocumentsResponse = {
  documents: DocumentItem[];
};
