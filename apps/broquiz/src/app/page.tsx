import { DocumentUpload } from "@/features/documents/components/document-upload";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16">
      <div className="rounded-lg border bg-card p-6 shadow-sm">
        <h1 className="text-3xl font-semibold tracking-tight">BroQuiz</h1>
        <p className="mt-2 text-muted-foreground">Upload a PDF to begin.</p>
        <div className="mt-6"><DocumentUpload /></div>
      </div>
    </main>
  );
}
