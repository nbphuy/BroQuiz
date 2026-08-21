"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import {
  getQuizAttempt,
  QuizAttemptError,
  submitQuizAttempt,
  type AttemptInProgress,
  type QuizAttempt,
} from "@/lib/api/attempts";

function isInProgress(attempt: QuizAttempt): attempt is AttemptInProgress {
  return attempt.status === "in_progress" && "questions" in attempt;
}

function CompletedAttempt({ attemptId }: { attemptId: string }) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16">
      <section className="rounded-lg border bg-card p-6 shadow-sm" aria-labelledby="completed-heading">
        <p className="text-sm font-medium text-muted-foreground">Attempt complete</p>
        <h1 id="completed-heading" className="mt-1 text-3xl font-semibold tracking-tight">
          Quiz submitted successfully.
        </h1>
        <p className="mt-3 text-muted-foreground">
          Your attempt has been saved. You can safely leave this page.
        </p>
        <p className="mt-4 break-all font-mono text-xs text-muted-foreground">Attempt {attemptId}</p>
      </section>
    </main>
  );
}

export function QuizPlayer({ attemptId }: { attemptId: string }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedByQuestion, setSelectedByQuestion] = useState<Record<string, string>>({});
  const [validationError, setValidationError] = useState<string | null>(null);
  const attemptQuery = useQuery({
    queryKey: ["attempt", attemptId],
    queryFn: () => getQuizAttempt(attemptId),
    retry: false,
  });
  const submitMutation = useMutation({
    mutationFn: (attempt: AttemptInProgress) =>
      submitQuizAttempt(attempt.id, {
        answers: attempt.questions.map((question) => ({
          question_id: question.id,
          option_id: selectedByQuestion[question.id],
        })),
      }),
  });

  if (attemptQuery.isPending) {
    return <main className="mx-auto max-w-2xl px-6 py-16" role="status">Loading quiz attempt...</main>;
  }
  if (attemptQuery.isError) {
    const message = attemptQuery.error instanceof QuizAttemptError && attemptQuery.error.statusCode === 404
      ? "This quiz attempt could not be found."
      : "Unable to load this quiz attempt. Please try again.";
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-2xl font-semibold">Unable to open quiz</h1>
        <p className="mt-3 text-destructive" role="alert">{message}</p>
      </main>
    );
  }

  const attempt = attemptQuery.data;
  if (!isInProgress(attempt) || submitMutation.isSuccess) {
    return <CompletedAttempt attemptId={attemptId} />;
  }

  const activeAttempt: AttemptInProgress = attempt;
  const question = attempt.questions[currentIndex];
  const answeredCount = attempt.questions.filter(
    (item) => selectedByQuestion[item.id] !== undefined,
  ).length;
  const unansweredCount = attempt.questions.length - answeredCount;
  const submitError = submitMutation.error
    ? submitMutation.error instanceof QuizAttemptError
      ? submitMutation.error.message
      : "Unable to submit this quiz. Please try again."
    : null;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitMutation.isPending) return;
    const firstUnanswered = activeAttempt.questions.findIndex(
      (item) => selectedByQuestion[item.id] === undefined,
    );
    if (firstUnanswered !== -1) {
      setCurrentIndex(firstUnanswered);
      setValidationError(
        `Answer all questions before submitting. ${unansweredCount} ${unansweredCount === 1 ? "question is" : "questions are"} unanswered.`,
      );
      return;
    }
    setValidationError(null);
    submitMutation.mutate(activeAttempt);
  }

  return (
    <main className="mx-auto min-h-screen w-full max-w-3xl px-6 py-12">
      <form className="rounded-lg border bg-card p-6 shadow-sm" onSubmit={handleSubmit}>
        <header>
          <p className="text-sm font-medium text-muted-foreground">{attempt.topic}</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">{attempt.title}</h1>
          <div className="mt-5 flex items-center justify-between gap-4 text-sm">
            <p aria-live="polite">
              Question {currentIndex + 1} of {attempt.total_questions}
            </p>
            <p>{answeredCount} answered</p>
          </div>
          <progress
            className="mt-2 h-2 w-full"
            aria-label="Quiz progress"
            max={attempt.total_questions}
            value={currentIndex + 1}
          />
        </header>

        <fieldset className="mt-8" disabled={submitMutation.isPending}>
          <legend className="text-xl font-semibold leading-8">{question.question}</legend>
          <div className="mt-5 grid gap-3">
            {question.options.map((option) => (
              <label
                key={option.id}
                className="flex cursor-pointer items-start gap-3 rounded-md border p-4 has-checked:border-primary has-checked:bg-muted"
              >
                <input
                  type="radio"
                  name={`question-${question.id}`}
                  value={option.id}
                  checked={selectedByQuestion[question.id] === option.id}
                  onChange={() => {
                    setSelectedByQuestion((current) => ({
                      ...current,
                      [question.id]: option.id,
                    }));
                    setValidationError(null);
                  }}
                  className="mt-1"
                />
                <span>{option.text}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t pt-5">
          <button
            type="button"
            disabled={currentIndex === 0 || submitMutation.isPending}
            onClick={() => setCurrentIndex((index) => Math.max(0, index - 1))}
            className="rounded-md border px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          >
            Previous
          </button>
          {currentIndex < attempt.questions.length - 1 ? (
            <button
              type="button"
              disabled={submitMutation.isPending}
              onClick={() => setCurrentIndex((index) => Math.min(attempt.questions.length - 1, index + 1))}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
            >
              Next
            </button>
          ) : (
            <button
              type="submit"
              disabled={submitMutation.isPending}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitMutation.isPending ? "Submitting quiz..." : "Finish quiz"}
            </button>
          )}
        </div>

        {validationError ? (
          <p className="mt-4 text-sm text-destructive" role="alert">{validationError}</p>
        ) : null}
        {submitMutation.isPending ? (
          <p className="mt-4 text-sm text-muted-foreground" role="status">
            Submitting your answers...
          </p>
        ) : null}
        {submitError ? <p className="mt-4 text-sm text-destructive" role="alert">{submitError}</p> : null}
      </form>
    </main>
  );
}
