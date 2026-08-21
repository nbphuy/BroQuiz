import { QuizPlayer } from "@/features/quizzes/components/quiz-player";

type AttemptPageProps = { params: Promise<{ attemptId: string }> };

export default async function AttemptPage({ params }: AttemptPageProps) {
  const { attemptId } = await params;
  return <QuizPlayer attemptId={attemptId} />;
}
