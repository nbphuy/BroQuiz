import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getQuizAttempt: vi.fn(),
  submitQuizAttempt: vi.fn(),
}));

vi.mock("@/lib/api/attempts", () => ({
  QuizAttemptError: class QuizAttemptError extends Error {
    constructor(message: string, readonly statusCode?: number) {
      super(message);
    }
  },
  getQuizAttempt: mocks.getQuizAttempt,
  submitQuizAttempt: mocks.submitQuizAttempt,
}));

import { QuizAttemptError } from "@/lib/api/attempts";
import { QuizPlayer } from "./quiz-player";

const attempt = {
  id: "attempt-123",
  quiz_id: "quiz-456",
  title: "Human interfaces",
  topic: "Interaction design",
  status: "in_progress",
  total_questions: 2,
  started_at: "2026-08-21T10:00:00Z",
  questions: [
    {
      id: "question-1",
      question: "What do interfaces support?",
      position: 0,
      options: [
        { id: "option-1a", position: 0, text: "Interaction" },
        { id: "option-1b", position: 1, text: "Fuel storage" },
      ],
    },
    {
      id: "question-2",
      question: "Which quality matters?",
      position: 1,
      options: [
        { id: "option-2a", position: 0, text: "Usability" },
        { id: "option-2b", position: 1, text: "Road width" },
      ],
    },
  ],
};

const submitted = {
  id: attempt.id,
  quiz_id: attempt.quiz_id,
  status: "submitted",
  score: 2,
  total_questions: 2,
  started_at: attempt.started_at,
  submitted_at: "2026-08-21T10:05:00Z",
  answers: [],
};

function renderPlayer() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <QuizPlayer attemptId={attempt.id} />
    </QueryClientProvider>,
  );
}

function choose(label: string) {
  fireEvent.click(screen.getByRole("radio", { name: label }));
}

describe("QuizPlayer", () => {
  beforeEach(() => {
    mocks.getQuizAttempt.mockReset();
    mocks.submitQuizAttempt.mockReset();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  it("renders loading, ordered answer-safe content, and progress", async () => {
    let resolveAttempt: (value: typeof attempt) => void;
    mocks.getQuizAttempt.mockReturnValue(
      new Promise<typeof attempt>((resolve) => { resolveAttempt = resolve; }),
    );
    renderPlayer();
    expect(screen.getByRole("status")).toHaveTextContent("Loading quiz attempt");
    resolveAttempt!(attempt);

    expect(await screen.findByRole("heading", { name: attempt.title })).toBeInTheDocument();
    expect(screen.getByText("Question 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Quiz progress" })).toHaveValue(1);
    expect(screen.getByRole("radio", { name: "Interaction" })).not.toBeChecked();
    expect(screen.queryByText(/correct|explanation|source/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  });

  it("changes a selection and preserves it across Previous and Next navigation", async () => {
    mocks.getQuizAttempt.mockResolvedValue(attempt);
    renderPlayer();
    choose(await screen.findByText("Interaction").then(() => "Interaction"));
    choose("Fuel storage");
    expect(screen.getByRole("radio", { name: "Interaction" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Fuel storage" })).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Question 2 of 2")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Quiz progress" })).toHaveValue(2);
    choose("Usability");
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(screen.getByRole("radio", { name: "Fuel storage" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("radio", { name: "Usability" })).toBeChecked();
  });

  it("communicates unanswered questions and does not call the backend", async () => {
    mocks.getQuizAttempt.mockResolvedValue(attempt);
    renderPlayer();
    await screen.findByText(attempt.questions[0].question);
    choose("Interaction");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish quiz" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Answer all questions before submitting. 1 question is unanswered.",
    );
    expect(mocks.submitQuizAttempt).not.toHaveBeenCalled();
  });

  it("submits stable IDs once, disables duplicate actions, and renders neutral completion", async () => {
    let resolveSubmit: (value: typeof submitted) => void;
    mocks.getQuizAttempt.mockResolvedValue(attempt);
    mocks.submitQuizAttempt.mockReturnValue(
      new Promise<typeof submitted>((resolve) => { resolveSubmit = resolve; }),
    );
    renderPlayer();
    await screen.findByText(attempt.questions[0].question);
    choose("Interaction");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    choose("Road width");
    fireEvent.click(screen.getByRole("button", { name: "Finish quiz" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Submitting quiz..." })).toBeDisabled());
    expect(screen.getByRole("status")).toHaveTextContent("Submitting your answers");
    fireEvent.click(screen.getByRole("button", { name: "Submitting quiz..." }));
    expect(mocks.submitQuizAttempt).toHaveBeenCalledTimes(1);
    expect(mocks.submitQuizAttempt).toHaveBeenCalledWith(attempt.id, {
      answers: [
        { question_id: "question-1", option_id: "option-1a" },
        { question_id: "question-2", option_id: "option-2b" },
      ],
    });

    resolveSubmit!(submitted);
    expect(await screen.findByRole("heading", { name: "Quiz submitted successfully." })).toBeInTheDocument();
    expect(screen.queryByText(/score|correct|explanation|source|review/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("renders safe load and submission errors", async () => {
    mocks.getQuizAttempt.mockRejectedValueOnce(new QuizAttemptError("private detail", 404));
    const first = renderPlayer();
    expect(await screen.findByRole("alert")).toHaveTextContent("This quiz attempt could not be found.");
    expect(screen.queryByText("private detail")).not.toBeInTheDocument();
    first.unmount();

    mocks.getQuizAttempt.mockResolvedValue(attempt);
    mocks.submitQuizAttempt.mockRejectedValue(new QuizAttemptError("Attempt has already been submitted.", 409));
    renderPlayer();
    await screen.findByText(attempt.questions[0].question);
    choose("Interaction");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    choose("Usability");
    fireEvent.click(screen.getByRole("button", { name: "Finish quiz" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Attempt has already been submitted.");
  });

  it("opens an already submitted attempt in the neutral completion state", async () => {
    mocks.getQuizAttempt.mockResolvedValue(submitted);
    renderPlayer();
    expect(await screen.findByRole("heading", { name: "Quiz submitted successfully." })).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(screen.queryByText(/score|correct|explanation|source|review/i)).not.toBeInTheDocument();
  });
});
