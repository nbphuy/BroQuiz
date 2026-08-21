"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import {
  createDocumentChunks,
  createDocumentEmbeddings,
  DocumentChunkingError,
  DocumentEmbeddingError,
  DocumentFetchError,
  DocumentSearchError,
  getDocument,
  searchDocument,
  type DocumentSearchResponse,
  type UploadedDocument,
} from "@/lib/api/documents";
import {
  generateDocumentQuiz,
  QuizGenerationError,
  type QuizGenerationResponse,
} from "@/lib/api/quizzes";

type DocumentWorkspaceProps = { documentId: string };

const knownStatusLabels: Record<string, string> = {
  uploaded: "Uploaded",
  processing: "Processing",
  processed: "Processed",
  failed: "Failed",
  chunked: "Chunked",
  embedded: "Embedded",
};

function formatFileSize(fileSize: number | null): string {
  if (fileSize === null) return "Not available";
  if (fileSize < 1024) return `${fileSize} B`;
  const units = ["KiB", "MiB", "GiB"];
  const unitIndex = Math.min(Math.floor(Math.log(fileSize) / Math.log(1024)) - 1, units.length - 1);
  const value = fileSize / 1024 ** (unitIndex + 1);
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)} ${units[unitIndex]}`;
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function Status({ status }: Pick<UploadedDocument, "status">) {
  const label = knownStatusLabels[status];
  return label ? <span>{label}</span> : <span>Unrecognized status: {status}</span>;
}

function Metadata({ document }: { document: UploadedDocument }) {
  return (
    <dl className="mt-6 grid gap-x-8 gap-y-5 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <dt className="text-sm font-medium text-muted-foreground">Filename</dt>
        <dd className="mt-1 break-words text-lg font-semibold">{document.filename}</dd>
      </div>
      <div>
        <dt className="text-sm font-medium text-muted-foreground">Status</dt>
        <dd className="mt-1"><Status status={document.status} /></dd>
      </div>
      <div>
        <dt className="text-sm font-medium text-muted-foreground">Document ID</dt>
        <dd className="mt-1 break-all font-mono text-sm">{document.id}</dd>
      </div>
      <div>
        <dt className="text-sm font-medium text-muted-foreground">Content type</dt>
        <dd className="mt-1">{document.content_type ?? "Not available"}</dd>
      </div>
      <div>
        <dt className="text-sm font-medium text-muted-foreground">File size</dt>
        <dd className="mt-1">{formatFileSize(document.file_size)}</dd>
      </div>
      {document.page_count !== null ? <div><dt className="text-sm font-medium text-muted-foreground">Page count</dt><dd className="mt-1">{document.page_count}</dd></div> : null}
      <div>
        <dt className="text-sm font-medium text-muted-foreground">Created</dt>
        <dd className="mt-1"><time dateTime={document.created_at}>{formatTimestamp(document.created_at)}</time></dd>
      </div>
      {document.updated_at !== document.created_at ? <div><dt className="text-sm font-medium text-muted-foreground">Updated</dt><dd className="mt-1"><time dateTime={document.updated_at}>{formatTimestamp(document.updated_at)}</time></dd></div> : null}
    </dl>
  );
}

function SearchResults({ result }: { result: DocumentSearchResponse | undefined }) {
  if (!result) return null;
  if (result.result_count === 0) {
    return <p className="mt-4 text-sm text-muted-foreground" role="status">No matching chunks found.</p>;
  }

  return (
    <div className="mt-5" aria-live="polite">
      <p className="text-sm text-muted-foreground" role="status">
        {result.result_count} ranked {result.result_count === 1 ? "result" : "results"} using {result.embedding_model} ({result.embedding_dimensions} dimensions).
      </p>
      <ol className="mt-3 space-y-3">
        {result.results.map((chunk, index) => (
          <li key={chunk.chunk_id} className="rounded-md border bg-background p-4">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <span className="font-semibold">Rank {index + 1}</span>
              <span>Similarity {chunk.similarity.toFixed(3)}</span>
              <span>Chunk index {chunk.chunk_index}</span>
              <span>Page {chunk.page_number}</span>
            </div>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-6">{chunk.content}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function SemanticSearch({ documentId }: { documentId: string }) {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const searchMutation = useMutation({
    mutationFn: ({ query, topK }: { query: string; topK: number }) =>
      searchDocument(documentId, { query, top_k: topK }),
  });
  const searchError = searchMutation.error
    ? searchMutation.error instanceof DocumentSearchError
      ? searchMutation.error.message
      : "Unable to search this document. Please try again."
    : null;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (!trimmedQuery || topK < 1 || topK > 20 || searchMutation.isPending) return;
    searchMutation.mutate({ query: trimmedQuery, topK });
  }

  return (
    <section className="mt-8 border-t pt-6" aria-labelledby="semantic-search-heading">
      <h2 id="semantic-search-heading" className="text-xl font-semibold">Semantic search</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Inspect the chunks most similar to a query. Higher similarity scores are better.
      </p>
      <form className="mt-4 grid gap-4 sm:grid-cols-[1fr_7rem_auto] sm:items-end" onSubmit={handleSubmit}>
        <div>
          <label htmlFor="semantic-query" className="text-sm font-medium">Query</label>
          <input
            id="semantic-query"
            name="query"
            type="search"
            required
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            disabled={searchMutation.isPending}
            className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            placeholder="What concept are you looking for?"
          />
        </div>
        <div>
          <label htmlFor="semantic-top-k" className="text-sm font-medium">Top results</label>
          <input
            id="semantic-top-k"
            name="top_k"
            type="number"
            min={1}
            max={20}
            required
            value={topK}
            onChange={(event) => setTopK(Number(event.target.value))}
            disabled={searchMutation.isPending}
            className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>
        <button
          type="submit"
          disabled={searchMutation.isPending || !query.trim()}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
        >
          {searchMutation.isPending ? "Searching..." : "Search"}
        </button>
      </form>
      {searchMutation.isPending ? (
        <p className="mt-3 text-sm text-muted-foreground" role="status">Searching embedded chunks...</p>
      ) : null}
      {searchError ? <p className="mt-3 text-sm text-destructive" role="alert">{searchError}</p> : null}
      <SearchResults result={searchMutation.data} />
    </section>
  );
}

function QuizPreview({ quiz }: { quiz: QuizGenerationResponse | undefined }) {
  if (!quiz) return null;

  return (
    <section className="mt-6 rounded-md border bg-background p-4" aria-labelledby="generated-quiz-heading">
      <p className="text-sm text-muted-foreground" role="status">
        Persisted quiz <span className="font-mono">{quiz.id}</span>
      </p>
      <h3 id="generated-quiz-heading" className="mt-1 text-lg font-semibold">{quiz.title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        {quiz.questions.length} {quiz.questions.length === 1 ? "question" : "questions"} · Status: {quiz.status}
      </p>
      <ol className="mt-4 space-y-5">
        {quiz.questions.map((question, questionIndex) => (
          <li key={`${question.question}-${questionIndex}`}>
            <p className="font-medium">{questionIndex + 1}. {question.question}</p>
            <ol className="mt-2 grid gap-1 pl-5 text-sm" type="A">
              {question.options.map((option, optionIndex) => (
                <li key={`${option}-${optionIndex}`} className={optionIndex === question.correct_answer ? "font-semibold text-primary" : undefined}>
                  {option}{optionIndex === question.correct_answer ? " (correct)" : ""}
                </li>
              ))}
            </ol>
            <p className="mt-2 text-sm"><span className="font-medium">Explanation:</span> {question.explanation}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Sources: {question.sources.map((source) => `page ${source.page_number}, chunk ${source.chunk_index ?? "unknown"}`).join("; ")}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function QuizGeneration({ documentId }: { documentId: string }) {
  const [topic, setTopic] = useState("");
  const [questionCount, setQuestionCount] = useState(5);
  const [topK, setTopK] = useState(5);
  const generationMutation = useMutation({
    mutationFn: ({ topic, questionCount, topK }: { topic: string; questionCount: number; topK: number }) =>
      generateDocumentQuiz(documentId, {
        topic,
        question_count: questionCount,
        top_k: topK,
      }),
  });
  const generationError = generationMutation.error
    ? generationMutation.error instanceof QuizGenerationError
      ? generationMutation.error.message
      : "Unable to generate a quiz. Please try again."
    : null;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedTopic = topic.trim();
    if (
      !trimmedTopic
      || questionCount < 1
      || questionCount > 10
      || topK < 1
      || topK > 20
      || generationMutation.isPending
    ) return;
    generationMutation.mutate({ topic: trimmedTopic, questionCount, topK });
  }

  return (
    <section className="mt-8 border-t pt-6" aria-labelledby="quiz-generation-heading">
      <h2 id="quiz-generation-heading" className="text-xl font-semibold">Generate quiz</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Create and persist a grounded multiple-choice quiz from the most relevant embedded chunks.
      </p>
      <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit}>
        <div className="sm:col-span-2">
          <label htmlFor="quiz-topic" className="text-sm font-medium">Topic</label>
          <input
            id="quiz-topic"
            name="topic"
            type="text"
            required
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            disabled={generationMutation.isPending}
            className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            placeholder="What should the quiz focus on?"
          />
        </div>
        <div>
          <label htmlFor="quiz-question-count" className="text-sm font-medium">Questions</label>
          <input
            id="quiz-question-count"
            name="question_count"
            type="number"
            min={1}
            max={10}
            required
            value={questionCount}
            onChange={(event) => setQuestionCount(Number(event.target.value))}
            disabled={generationMutation.isPending}
            className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>
        <div>
          <label htmlFor="quiz-top-k" className="text-sm font-medium">Source chunks</label>
          <input
            id="quiz-top-k"
            name="top_k"
            type="number"
            min={1}
            max={20}
            required
            value={topK}
            onChange={(event) => setTopK(Number(event.target.value))}
            disabled={generationMutation.isPending}
            className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>
        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={generationMutation.isPending || !topic.trim()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generationMutation.isPending ? "Generating quiz..." : "Generate quiz"}
          </button>
        </div>
      </form>
      {generationMutation.isPending ? (
        <p className="mt-3 text-sm text-muted-foreground" role="status">Retrieving source chunks and generating the quiz...</p>
      ) : null}
      {generationError ? <p className="mt-3 text-sm text-destructive" role="alert">{generationError}</p> : null}
      <QuizPreview quiz={generationMutation.data} />
    </section>
  );
}

export function DocumentWorkspace({ documentId }: DocumentWorkspaceProps) {
  const queryClient = useQueryClient();
  const documentQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId),
    retry: false,
  });
  const chunkingMutation = useMutation({
    mutationFn: () => createDocumentChunks(documentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["document", documentId] }),
  });
  const embeddingMutation = useMutation({
    mutationFn: () => createDocumentEmbeddings(documentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["document", documentId] }),
  });

  if (documentQuery.isPending) {
    return <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16"><p role="status">Loading document...</p></main>;
  }

  if (documentQuery.error instanceof DocumentFetchError && documentQuery.error.statusCode === 404) {
    return <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16"><section aria-labelledby="not-found-heading"><h1 id="not-found-heading" className="text-2xl font-semibold">Document not found</h1><p className="mt-2 text-muted-foreground">This document may have been removed or the link is incorrect.</p></section></main>;
  }

  if (documentQuery.isError || !documentQuery.data) {
    return <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16"><section aria-labelledby="error-heading"><h1 id="error-heading" className="text-2xl font-semibold">Unable to load document</h1><p className="mt-2 text-muted-foreground">Please try again in a moment.</p></section></main>;
  }

  const canCreateChunks = documentQuery.data.status === "processed";
  const canCreateEmbeddings = documentQuery.data.status === "chunked";
  const canSearch = documentQuery.data.status === "embedded";
  const chunkingError = chunkingMutation.error
    ? chunkingMutation.error instanceof DocumentChunkingError
      ? chunkingMutation.error.message
      : "Unable to create document chunks. Please try again."
    : null;
  const embeddingError = embeddingMutation.error
    ? embeddingMutation.error instanceof DocumentEmbeddingError
      ? embeddingMutation.error.message
      : "Unable to create document embeddings. Please try again."
    : null;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col justify-center px-6 py-16">
      <section className="rounded-lg border bg-card p-6 shadow-sm" aria-labelledby="workspace-heading">
        <p className="text-sm font-medium text-muted-foreground">Document Processing Workspace</p>
        <h1 id="workspace-heading" className="mt-1 text-2xl font-semibold tracking-tight">Document details</h1>
        <Metadata document={documentQuery.data} />
        {canCreateChunks ? (
          <div className="mt-6">
            <button
              type="button"
              onClick={() => chunkingMutation.mutate()}
              disabled={chunkingMutation.isPending}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
            >
              {chunkingMutation.isPending ? "Creating chunks..." : "Create chunks"}
            </button>
            {chunkingMutation.isPending ? <p className="mt-2 text-sm text-muted-foreground" role="status">Creating document chunks...</p> : null}
            {chunkingError ? <p className="mt-2 text-sm text-destructive" role="alert">{chunkingError}</p> : null}
          </div>
        ) : null}
        {canCreateEmbeddings ? (
          <div className="mt-6">
            <button
              type="button"
              onClick={() => embeddingMutation.mutate()}
              disabled={embeddingMutation.isPending}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
            >
              {embeddingMutation.isPending ? "Creating embeddings..." : "Create embeddings"}
            </button>
            {embeddingMutation.isPending ? <p className="mt-2 text-sm text-muted-foreground" role="status">Creating document embeddings...</p> : null}
            {embeddingError ? <p className="mt-2 text-sm text-destructive" role="alert">{embeddingError}</p> : null}
          </div>
        ) : null}
        {canSearch ? <SemanticSearch documentId={documentId} /> : null}
        {canSearch ? <QuizGeneration documentId={documentId} /> : null}
      </section>
    </main>
  );
}
