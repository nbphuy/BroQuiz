import { apiClient } from "./client";
import { getBackendErrorMessage } from "./documents";
import type { components } from "./schema";

export type AttemptInProgress = components["schemas"]["AttemptInProgressResponse"];
export type AttemptSubmitted = components["schemas"]["AttemptSubmittedResponse"];
export type AttemptSubmissionRequest = components["schemas"]["AttemptSubmissionRequest"];
export type QuizAttempt = AttemptInProgress | AttemptSubmitted;

export class QuizAttemptError extends Error {
  constructor(message: string, readonly statusCode?: number, options?: ErrorOptions) {
    super(message, options);
    this.name = "QuizAttemptError";
  }
}

function attemptError(error: unknown, statusCode: number, fallback: string): QuizAttemptError {
  return new QuizAttemptError(getBackendErrorMessage(error) ?? fallback, statusCode);
}

export async function startQuizAttempt(quizId: string): Promise<AttemptInProgress> {
  try {
    const { data, error, response } = await apiClient.POST("/quizzes/{quiz_id}/attempts", {
      params: { path: { quiz_id: quizId } },
    });
    if (!response.ok) throw attemptError(error, response.status, "Unable to start this quiz.");
    if (!data) throw new QuizAttemptError("The BroQuiz API started an attempt without player data.");
    return data;
  } catch (error) {
    if (error instanceof QuizAttemptError) throw error;
    throw new QuizAttemptError(
      "Unable to reach the BroQuiz API. Check that the backend is running.",
      undefined,
      { cause: error },
    );
  }
}

export async function getQuizAttempt(attemptId: string): Promise<QuizAttempt> {
  try {
    const { data, error, response } = await apiClient.GET("/attempts/{attempt_id}", {
      params: { path: { attempt_id: attemptId } },
    });
    if (!response.ok) throw attemptError(error, response.status, "Unable to load this quiz attempt.");
    if (!data) throw new QuizAttemptError("The BroQuiz API returned no attempt data.");
    return data;
  } catch (error) {
    if (error instanceof QuizAttemptError) throw error;
    throw new QuizAttemptError(
      "Unable to reach the BroQuiz API. Check that the backend is running.",
      undefined,
      { cause: error },
    );
  }
}

export async function submitQuizAttempt(
  attemptId: string,
  request: AttemptSubmissionRequest,
): Promise<AttemptSubmitted> {
  try {
    const { data, error, response } = await apiClient.POST("/attempts/{attempt_id}/submit", {
      params: { path: { attempt_id: attemptId } },
      body: request,
    });
    if (!response.ok) throw attemptError(error, response.status, "Unable to submit this quiz.");
    if (!data) throw new QuizAttemptError("The BroQuiz API submitted the attempt without confirmation.");
    return data;
  } catch (error) {
    if (error instanceof QuizAttemptError) throw error;
    throw new QuizAttemptError(
      "Unable to reach the BroQuiz API. Check that the backend is running.",
      undefined,
      { cause: error },
    );
  }
}
