import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ push: vi.fn(), startQuizAttempt: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/lib/api/attempts", () => ({
  QuizAttemptError: class QuizAttemptError extends Error {},
  startQuizAttempt: mocks.startQuizAttempt,
}));

import { QuizAttemptError } from "@/lib/api/attempts";
import { StartQuiz } from "./start-quiz";

function renderStart() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <StartQuiz quizId="quiz-456" />
    </QueryClientProvider>,
  );
}

describe("StartQuiz", () => {
  beforeEach(() => {
    mocks.push.mockReset();
    mocks.startQuizAttempt.mockReset();
  });

  it("starts only once while pending and opens the answer-safe attempt route", async () => {
    let resolveStart: (value: { id: string }) => void;
    mocks.startQuizAttempt.mockReturnValue(
      new Promise<{ id: string }>((resolve) => { resolveStart = resolve; }),
    );
    renderStart();
    const button = screen.getByRole("button", { name: "Start quiz" });
    fireEvent.click(button);

    await waitFor(() => expect(screen.getByRole("button", { name: "Starting quiz..." })).toBeDisabled());
    expect(screen.getByRole("status")).toHaveTextContent("Preparing answer-safe questions");
    fireEvent.click(screen.getByRole("button", { name: "Starting quiz..." }));
    expect(mocks.startQuizAttempt).toHaveBeenCalledTimes(1);
    expect(mocks.startQuizAttempt).toHaveBeenCalledWith("quiz-456");

    resolveStart!({ id: "attempt-123" });
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/attempts/attempt-123"));
  });

  it("shows a safe start error", async () => {
    mocks.startQuizAttempt.mockRejectedValue(new QuizAttemptError("Quiz not found."));
    renderStart();
    fireEvent.click(screen.getByRole("button", { name: "Start quiz" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Quiz not found.");
    expect(mocks.push).not.toHaveBeenCalled();
  });
});
