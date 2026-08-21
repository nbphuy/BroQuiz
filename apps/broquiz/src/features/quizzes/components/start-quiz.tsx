"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { QuizAttemptError, startQuizAttempt } from "@/lib/api/attempts";

export function StartQuiz({ quizId }: { quizId: string }) {
  const router = useRouter();
  const startMutation = useMutation({
    mutationFn: () => startQuizAttempt(quizId),
    onSuccess: (attempt) => router.push(`/attempts/${attempt.id}`),
  });
  const error = startMutation.error
    ? startMutation.error instanceof QuizAttemptError
      ? startMutation.error.message
      : "Unable to start this quiz. Please try again."
    : null;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16">
      <section className="rounded-lg border bg-card p-6 shadow-sm" aria-labelledby="start-quiz-heading">
        <p className="text-sm font-medium text-muted-foreground">BroQuiz player</p>
        <h1 id="start-quiz-heading" className="mt-1 text-3xl font-semibold tracking-tight">
          Ready to begin?
        </h1>
        <p className="mt-3 text-muted-foreground">
          Starting creates a new attempt. All questions must be answered before submission.
        </p>
        <button
          type="button"
          disabled={startMutation.isPending}
          onClick={() => {
            if (!startMutation.isPending) startMutation.mutate();
          }}
          className="mt-6 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
        >
          {startMutation.isPending ? "Starting quiz..." : "Start quiz"}
        </button>
        {startMutation.isPending ? (
          <p className="mt-3 text-sm text-muted-foreground" role="status">
            Preparing answer-safe questions...
          </p>
        ) : null}
        {error ? <p className="mt-3 text-sm text-destructive" role="alert">{error}</p> : null}
      </section>
    </main>
  );
}
