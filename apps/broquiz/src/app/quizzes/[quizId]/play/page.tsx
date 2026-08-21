import { StartQuiz } from "@/features/quizzes/components/start-quiz";

type StartQuizPageProps = { params: Promise<{ quizId: string }> };

export default async function StartQuizPage({ params }: StartQuizPageProps) {
  const { quizId } = await params;
  return <StartQuiz quizId={quizId} />;
}
