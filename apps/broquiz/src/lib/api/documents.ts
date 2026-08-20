import { apiClient } from "./client";
import type { components, paths } from "./schema";

export type UploadedDocument = components["schemas"]["DocumentResponse"];
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

function getBackendErrorMessage(error: unknown): string | undefined {
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
