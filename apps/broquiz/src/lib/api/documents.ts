import { apiClient } from "./client";
import type { components, paths } from "./schema";

export type UploadedDocument = components["schemas"]["DocumentResponse"];
export type DocumentChunkingResult = components["schemas"]["DocumentChunkingResponse"];
export type DocumentEmbeddingResult = components["schemas"]["DocumentEmbeddingResponse"];
export type DocumentSearchRequest = components["schemas"]["DocumentSearchRequest"];
export type DocumentSearchResponse = components["schemas"]["DocumentSearchResponse"];
type UploadDocumentRequest = paths["/documents"]["post"]["requestBody"]["content"]["multipart/form-data"];

export class DocumentUploadError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "DocumentUploadError";
  }
}

export class DocumentFetchError extends Error {
  constructor(message: string, readonly statusCode?: number, options?: ErrorOptions) {
    super(message, options);
    this.name = "DocumentFetchError";
  }
}

export class DocumentChunkingError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "DocumentChunkingError";
  }
}

export class DocumentEmbeddingError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "DocumentEmbeddingError";
  }
}

export class DocumentSearchError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "DocumentSearchError";
  }
}

export function getBackendErrorMessage(error: unknown): string | undefined {
  if (typeof error !== "object" || error === null || !("detail" in error)) return undefined;
  const { detail } = error;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (!Array.isArray(detail)) return undefined;
  const messages = detail
    .filter((item): item is { msg: string } => typeof item === "object" && item !== null && "msg" in item && typeof item.msg === "string")
    .map((item) => item.msg);
  return messages.length > 0 ? messages.join(" ") : undefined;
}

export async function uploadDocument(file: File): Promise<UploadedDocument> {
  const formData = new FormData();
  formData.append("file", file);
  try {
    const { data, error, response } = await apiClient.POST("/documents", {
      body: formData as unknown as UploadDocumentRequest,
    });
    if (!response.ok) throw new DocumentUploadError(getBackendErrorMessage(error) ?? `The BroQuiz API rejected this upload (HTTP ${response.status}).`);
    if (!data) throw new DocumentUploadError("The BroQuiz API completed the upload without document metadata.");
    return data;
  } catch (error) {
    if (error instanceof DocumentUploadError) throw error;
    throw new DocumentUploadError("Unable to reach the BroQuiz API. Check that the backend is running.", { cause: error });
  }
}

export async function getDocument(documentId: string): Promise<UploadedDocument> {
  try {
    const { data, error, response } = await apiClient.GET("/documents/{document_id}", {
      params: { path: { document_id: documentId } },
    });
    if (!response.ok) {
      throw new DocumentFetchError(response.status === 404 ? "Document not found." : getBackendErrorMessage(error) ?? "Unable to load this document.", response.status);
    }
    if (!data) throw new DocumentFetchError("The BroQuiz API returned no document metadata.");
    return data;
  } catch (error) {
    if (error instanceof DocumentFetchError) throw error;
    throw new DocumentFetchError("Unable to reach the BroQuiz API. Check that the backend is running.", undefined, { cause: error });
  }
}

export async function createDocumentChunks(documentId: string): Promise<DocumentChunkingResult> {
  try {
    const { data, error, response } = await apiClient.POST("/documents/{document_id}/chunks", {
      params: { path: { document_id: documentId } },
    });
    if (!response.ok) {
      throw new DocumentChunkingError(
        getBackendErrorMessage(error) ?? "Unable to create document chunks. Please try again.",
      );
    }
    if (!data) throw new DocumentChunkingError("The BroQuiz API completed chunking without a result.");
    return data;
  } catch (error) {
    if (error instanceof DocumentChunkingError) throw error;
    throw new DocumentChunkingError("Unable to reach the BroQuiz API. Check that the backend is running.", { cause: error });
  }
}

export async function createDocumentEmbeddings(documentId: string): Promise<DocumentEmbeddingResult> {
  try {
    const { data, error, response } = await apiClient.POST("/documents/{document_id}/embeddings", {
      params: { path: { document_id: documentId } },
    });
    if (!response.ok) {
      throw new DocumentEmbeddingError(
        getBackendErrorMessage(error) ?? "Unable to create document embeddings. Please try again.",
      );
    }
    if (!data) throw new DocumentEmbeddingError("The BroQuiz API completed embedding without a result.");
    return data;
  } catch (error) {
    if (error instanceof DocumentEmbeddingError) throw error;
    throw new DocumentEmbeddingError("Unable to reach the BroQuiz API. Check that the backend is running.", { cause: error });
  }
}

export async function searchDocument(
  documentId: string,
  request: DocumentSearchRequest,
): Promise<DocumentSearchResponse> {
  try {
    const { data, error, response } = await apiClient.POST(
      "/documents/{document_id}/search",
      {
        params: { path: { document_id: documentId } },
        body: request,
      },
    );
    if (!response.ok) {
      throw new DocumentSearchError(
        getBackendErrorMessage(error) ?? "Unable to search this document. Please try again.",
      );
    }
    if (!data) {
      throw new DocumentSearchError("The BroQuiz API completed the search without a result.");
    }
    return data;
  } catch (error) {
    if (error instanceof DocumentSearchError) throw error;
    throw new DocumentSearchError(
      "Unable to reach the BroQuiz API. Check that the backend is running.",
      { cause: error },
    );
  }
}
