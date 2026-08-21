import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createDocumentChunks: vi.fn(),
  createDocumentEmbeddings: vi.fn(),
  generateDocumentQuiz: vi.fn(),
  getDocument: vi.fn(),
  searchDocument: vi.fn(),
}));

vi.mock("@/lib/api/documents", () => ({
  DocumentChunkingError: class DocumentChunkingError extends Error {
    constructor(message: string) {
      super(message);
    }
  },
  DocumentFetchError: class DocumentFetchError extends Error {
    constructor(message: string, readonly statusCode?: number) {
      super(message);
    }
  },
  DocumentEmbeddingError: class DocumentEmbeddingError extends Error {
    constructor(message: string) {
      super(message);
    }
  },
  DocumentSearchError: class DocumentSearchError extends Error {
    constructor(message: string) {
      super(message);
    }
  },
  createDocumentChunks: mocks.createDocumentChunks,
  createDocumentEmbeddings: mocks.createDocumentEmbeddings,
  getDocument: mocks.getDocument,
  searchDocument: mocks.searchDocument,
}));

vi.mock("@/lib/api/quizzes", () => ({
  QuizGenerationError: class QuizGenerationError extends Error {
    constructor(message: string) {
      super(message);
    }
  },
  generateDocumentQuiz: mocks.generateDocumentQuiz,
}));

import { DocumentChunkingError, DocumentEmbeddingError, DocumentFetchError, DocumentSearchError } from "@/lib/api/documents";
import { QuizGenerationError } from "@/lib/api/quizzes";
import { DocumentWorkspace } from "./document-workspace";

const document = {
  id: "document-123",
  filename: "biology-notes.pdf",
  content_type: "application/pdf",
  file_size: 1_572_864,
  status: "processed",
  page_count: 12,
  created_at: "2026-08-20T10:00:00Z",
  updated_at: "2026-08-20T10:05:00Z",
};

const searchResponse = {
  document_id: document.id,
  query: "human interfaces",
  top_k: 5,
  result_count: 2,
  embedding_model: "embeddinggemma",
  embedding_dimensions: 768,
  results: [
    {
      chunk_id: "chunk-1",
      document_id: document.id,
      page_number: 4,
      chunk_index: 2,
      content: "Interfaces let people interact with computer systems.",
      similarity: 0.91234,
    },
    {
      chunk_id: "chunk-2",
      document_id: document.id,
      page_number: 7,
      chunk_index: 5,
      content: "Usability includes effectiveness and efficiency.",
      similarity: 0.74567,
    },
  ],
};

const quizResponse = {
  id: "quiz-456",
  document_id: document.id,
  title: "HCI Quiz",
  topic: "human interfaces",
  status: "ready",
  questions: [
    {
      question: "What do interfaces support?",
      options: ["Interaction", "Fuel storage", "Road building", "Weather prediction"],
      correct_answer: 0,
      explanation: "The retrieved source says interfaces support interaction.",
      sources: [{ chunk_id: "chunk-1", page_number: 4, chunk_index: 2 }],
    },
  ],
};

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, throwOnError: false } } });
  return {
    queryClient,
    ...render(<QueryClientProvider client={queryClient}><DocumentWorkspace documentId="document-123" /></QueryClientProvider>),
  };
}

describe("DocumentWorkspace", () => {
  beforeEach(() => {
    mocks.createDocumentChunks.mockReset();
    mocks.createDocumentEmbeddings.mockReset();
    mocks.generateDocumentQuiz.mockReset();
    mocks.getDocument.mockReset();
    mocks.searchDocument.mockReset();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  it("shows a loading state while metadata is requested", async () => {
    let resolveDocument: (value: typeof document) => void;
    mocks.getDocument.mockReturnValue(new Promise<typeof document>((resolve) => { resolveDocument = resolve; }));
    renderWorkspace();
    expect(screen.getByRole("status")).toHaveTextContent("Loading document");
    resolveDocument!(document);
    await screen.findByText("biology-notes.pdf");
  });

  it("renders persisted document metadata and makes processed documents chunkable", async () => {
    mocks.getDocument.mockResolvedValue(document);
    renderWorkspace();
    expect(await screen.findByText("biology-notes.pdf")).toBeInTheDocument();
    expect(screen.getByText("document-123")).toBeInTheDocument();
    expect(screen.getByText("application/pdf")).toBeInTheDocument();
    expect(screen.getByText("1.5 MiB")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Processed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create chunks" })).toBeEnabled();
    expect(mocks.getDocument).toHaveBeenCalledWith("document-123");
  });

  it.each(["uploaded", "processing", "failed", "chunked", "embedded"])("does not offer chunk creation for %s documents", async (status) => {
    mocks.getDocument.mockResolvedValue({ ...document, status });
    renderWorkspace();
    await screen.findByText(knownLabel(status));
    expect(screen.queryByRole("button", { name: /Create chunks/ })).not.toBeInTheDocument();
  });

  it("disables duplicate submission and reports pending progress", async () => {
    let resolveChunks: () => void;
    mocks.getDocument.mockResolvedValue(document);
    mocks.createDocumentChunks.mockReturnValue(new Promise<void>((resolve) => { resolveChunks = resolve; }));
    renderWorkspace();
    fireEvent.click(await screen.findByRole("button", { name: "Create chunks" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Creating chunks..." })).toBeDisabled());
    expect(screen.getByRole("status")).toHaveTextContent("Creating document chunks...");
    resolveChunks!();
  });

  it("invalidates persisted document metadata after creating chunks", async () => {
    mocks.getDocument.mockResolvedValueOnce(document).mockResolvedValueOnce({ ...document, status: "chunked" });
    mocks.createDocumentChunks.mockResolvedValue({ document_id: document.id, status: "chunked", page_count: 12, chunk_count: 3 });
    const { queryClient } = renderWorkspace();
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries");

    fireEvent.click(await screen.findByRole("button", { name: "Create chunks" }));

    await waitFor(() => expect(mocks.createDocumentChunks).toHaveBeenCalledWith(document.id));
    await waitFor(() => expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["document", document.id] }));
    expect(await screen.findByText("Chunked")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Create chunks/ })).not.toBeInTheDocument();
  });

  it("renders a safe chunking error", async () => {
    mocks.getDocument.mockResolvedValue(document);
    mocks.createDocumentChunks.mockRejectedValue(new DocumentChunkingError("Document is not ready for chunking."));
    renderWorkspace();

    fireEvent.click(await screen.findByRole("button", { name: "Create chunks" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Document is not ready for chunking.");
  });

  it("offers embedding creation only for a chunked document", async () => {
    mocks.getDocument.mockResolvedValue({ ...document, status: "chunked" });
    renderWorkspace();

    expect(await screen.findByRole("button", { name: "Create embeddings" })).toBeEnabled();
  });

  it.each(["uploaded", "processing", "processed", "failed", "embedded"])(
    "does not offer embedding creation for %s documents",
    async (status) => {
      mocks.getDocument.mockResolvedValue({ ...document, status });
      renderWorkspace();

      await screen.findByText(knownLabel(status));
      expect(screen.queryByRole("button", { name: /Create embeddings/ })).not.toBeInTheDocument();
    },
  );

  it("disables duplicate embedding submission and reports pending progress", async () => {
    let resolveEmbeddings: () => void;
    mocks.getDocument.mockResolvedValue({ ...document, status: "chunked" });
    mocks.createDocumentEmbeddings.mockReturnValue(
      new Promise<void>((resolve) => { resolveEmbeddings = resolve; }),
    );
    renderWorkspace();

    fireEvent.click(await screen.findByRole("button", { name: "Create embeddings" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Creating embeddings..." })).toBeDisabled());
    expect(screen.getByRole("status")).toHaveTextContent("Creating document embeddings...");
    expect(mocks.createDocumentEmbeddings).toHaveBeenCalledTimes(1);
    resolveEmbeddings!();
  });

  it("refetches metadata and renders the persisted embedded state", async () => {
    mocks.getDocument
      .mockResolvedValueOnce({ ...document, status: "chunked" })
      .mockResolvedValueOnce({ ...document, status: "embedded" });
    mocks.createDocumentEmbeddings.mockResolvedValue({
      document_id: document.id,
      status: "embedded",
      chunk_count: 3,
      embedded_count: 3,
      model: "embeddinggemma",
      dimensions: 768,
    });
    const { queryClient } = renderWorkspace();
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries");

    fireEvent.click(await screen.findByRole("button", { name: "Create embeddings" }));

    await waitFor(() => expect(mocks.createDocumentEmbeddings).toHaveBeenCalledWith(document.id));
    await waitFor(() => expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["document", document.id] }));
    expect(await screen.findByText("Embedded")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Create embeddings/ })).not.toBeInTheDocument();
  });

  it("renders a safe embedding error", async () => {
    mocks.getDocument.mockResolvedValue({ ...document, status: "chunked" });
    mocks.createDocumentEmbeddings.mockRejectedValue(
      new DocumentEmbeddingError("Embedding service unavailable"),
    );
    renderWorkspace();

    fireEvent.click(await screen.findByRole("button", { name: "Create embeddings" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Embedding service unavailable");
  });

  it("shows semantic search only for embedded documents with a default top_k of five", async () => {
    mocks.getDocument.mockResolvedValue({ ...document, status: "embedded" });
    renderWorkspace();

    expect(await screen.findByRole("heading", { name: "Semantic search" })).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "Top results" })).toHaveValue(5);

    mocks.getDocument.mockResolvedValue({ ...document, status: "processed" });
    renderWorkspace();
    await screen.findAllByText("Processed");
    expect(screen.getAllByRole("heading", { name: "Semantic search" })).toHaveLength(1);
  });

  it("submits the query and top_k and renders ranked score and chunk provenance", async () => {
    mocks.getDocument.mockResolvedValue({ ...document, status: "embedded" });
    mocks.searchDocument.mockResolvedValue({ ...searchResponse, top_k: 2 });
    renderWorkspace();

    fireEvent.change(await screen.findByRole("searchbox", { name: "Query" }), {
      target: { value: "  human interfaces  " },
    });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Top results" }), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(mocks.searchDocument).toHaveBeenCalledWith(
      document.id,
      { query: "human interfaces", top_k: 2 },
    ));
    expect(await screen.findByText("Rank 1")).toBeInTheDocument();
    expect(screen.getByText("Similarity 0.912")).toBeInTheDocument();
    expect(screen.getByText("Chunk index 2")).toBeInTheDocument();
    expect(screen.getByText("Page 4")).toBeInTheDocument();
    expect(screen.getByText(searchResponse.results[0].content)).toBeInTheDocument();
    expect(screen.getByText(/2 ranked results using embeddinggemma/)).toBeInTheDocument();
  });

  it("disables duplicate searches and announces pending progress", async () => {
    let resolveSearch: (value: typeof searchResponse) => void;
    mocks.getDocument.mockResolvedValue({ ...document, status: "embedded" });
    mocks.searchDocument.mockReturnValue(
      new Promise<typeof searchResponse>((resolve) => { resolveSearch = resolve; }),
    );
    renderWorkspace();

    fireEvent.change(await screen.findByRole("searchbox", { name: "Query" }), {
      target: { value: "interfaces" },
    });
    const searchButton = screen.getByRole("button", { name: "Search" });
    fireEvent.click(searchButton);

    await waitFor(() => expect(screen.getByRole("button", { name: "Searching..." })).toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Searching..." }));
    expect(mocks.searchDocument).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toHaveTextContent("Searching embedded chunks...");
    resolveSearch!(searchResponse);
  });

  it("renders an empty retrieval state", async () => {
    mocks.getDocument.mockResolvedValue({ ...document, status: "embedded" });
    mocks.searchDocument.mockResolvedValue({ ...searchResponse, result_count: 0, results: [] });
    renderWorkspace();

    fireEvent.change(await screen.findByRole("searchbox", { name: "Query" }), {
      target: { value: "unrelated topic" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("status")).toHaveTextContent("No matching chunks found.");
  });

  it("renders a safe semantic search error", async () => {
    mocks.getDocument.mockResolvedValue({ ...document, status: "embedded" });
    mocks.searchDocument.mockRejectedValue(new DocumentSearchError("Embedding service unavailable."));
    renderWorkspace();

    fireEvent.change(await screen.findByRole("searchbox", { name: "Query" }), {
      target: { value: "interfaces" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Embedding service unavailable.");
  });

  it("shows quiz generation only for embedded documents with conservative defaults", async () => {
    mocks.getDocument.mockResolvedValue({ ...document, status: "embedded" });
    renderWorkspace();

    expect(await screen.findByRole("heading", { name: "Generate quiz" })).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "Questions" })).toHaveValue(5);
    expect(screen.getByRole("spinbutton", { name: "Source chunks" })).toHaveValue(5);

    mocks.getDocument.mockResolvedValue({ ...document, status: "processed" });
    renderWorkspace();
    await screen.findAllByText("Processed");
    expect(screen.getAllByRole("heading", { name: "Generate quiz" })).toHaveLength(1);
  });

  it("generates a typed quiz and renders a read-only persisted preview", async () => {
    mocks.getDocument.mockResolvedValue({ ...document, status: "embedded" });
    mocks.generateDocumentQuiz.mockResolvedValue(quizResponse);
    renderWorkspace();

    fireEvent.change(await screen.findByRole("textbox", { name: "Topic" }), {
      target: { value: "  human interfaces  " },
    });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Questions" }), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Source chunks" }), {
      target: { value: "7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate quiz" }));

    await waitFor(() => expect(mocks.generateDocumentQuiz).toHaveBeenCalledWith(
      document.id,
      { topic: "human interfaces", question_count: 1, top_k: 7 },
    ));
    expect(await screen.findByRole("heading", { name: "HCI Quiz" })).toBeInTheDocument();
    expect(screen.getByText(/Persisted quiz/)).toHaveTextContent("quiz-456");
    expect(screen.getByText("Interaction (correct)")).toBeInTheDocument();
    expect(screen.getByText(/page 4, chunk 2/)).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("prevents duplicate quiz generation and announces progress", async () => {
    let resolveGeneration: (value: typeof quizResponse) => void;
    mocks.getDocument.mockResolvedValue({ ...document, status: "embedded" });
    mocks.generateDocumentQuiz.mockReturnValue(
      new Promise<typeof quizResponse>((resolve) => { resolveGeneration = resolve; }),
    );
    renderWorkspace();

    fireEvent.change(await screen.findByRole("textbox", { name: "Topic" }), {
      target: { value: "interfaces" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate quiz" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Generating quiz..." })).toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Generating quiz..." }));
    expect(mocks.generateDocumentQuiz).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toHaveTextContent("Retrieving source chunks and generating the quiz...");
    resolveGeneration!(quizResponse);
  });

  it("renders a safe quiz-generation error", async () => {
    mocks.getDocument.mockResolvedValue({ ...document, status: "embedded" });
    mocks.generateDocumentQuiz.mockRejectedValue(
      new QuizGenerationError("Quiz generation service is unavailable."),
    );
    renderWorkspace();

    fireEvent.change(await screen.findByRole("textbox", { name: "Topic" }), {
      target: { value: "interfaces" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate quiz" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Quiz generation service is unavailable.");
  });

  it("renders unknown backend statuses safely", async () => {
    mocks.getDocument.mockResolvedValue({ ...document, status: "archived" });
    renderWorkspace();
    expect(await screen.findByText("Unrecognized status: archived")).toBeInTheDocument();
  });

  it("shows a not-found state for a missing document", async () => {
    const request = Promise.reject(new DocumentFetchError("Document not found.", 404));
    request.catch(() => undefined);
    mocks.getDocument.mockReturnValue(request);
    renderWorkspace();
    expect(await screen.findByRole("heading", { name: "Document not found" })).toBeInTheDocument();
  });

  it("shows a safe error state for API failures", async () => {
    const request = Promise.reject(new Error("internal error"));
    request.catch(() => undefined);
    mocks.getDocument.mockReturnValue(request);
    renderWorkspace();
    expect(await screen.findByRole("heading", { name: "Unable to load document" })).toBeInTheDocument();
    expect(screen.getByText("Please try again in a moment.")).toBeInTheDocument();
  });
});

function knownLabel(status: string): string {
  const labels: Record<string, string> = {
    uploaded: "Uploaded",
    processing: "Processing",
    processed: "Processed",
    failed: "Failed",
    chunked: "Chunked",
    embedded: "Embedded",
  };
  return labels[status] ?? status;
}
