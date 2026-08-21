import { apiClient } from "./client";
import { getBackendErrorMessage } from "./documents";
import type { components } from "./schema";

export type QuizGenerationRequest = components["schemas"]["QuizGenerationRequest"];
export type QuizGenerationResponse = components["schemas"]["QuizGenerationResponse"];

export class QuizGenerationError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "QuizGenerationError";
  }
}

export async function generateDocumentQuiz(
  documentId: string,
  request: QuizGenerationRequest,
): Promise<QuizGenerationResponse> {
  try {
    const { data, error, response } = await apiClient.POST(
      "/documents/{document_id}/quiz/generate",
      {
        params: { path: { document_id: documentId } },
        body: request,
      },
    );
    if (!response.ok) {
      throw new QuizGenerationError(
        getBackendErrorMessage(error) ?? "Unable to generate a quiz. Please try again.",
      );
    }
    if (!data) {
      throw new QuizGenerationError(
        "The BroQuiz API completed generation without a persisted quiz.",
      );
    }
    return data;
  } catch (error) {
    if (error instanceof QuizGenerationError) throw error;
    throw new QuizGenerationError(
      "Unable to reach the BroQuiz API. Check that the backend is running.",
      { cause: error },
    );
  }
}
