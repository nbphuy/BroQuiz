import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ createDocumentChunks: vi.fn(), getDocument: vi.fn() }));

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
  createDocumentChunks: mocks.createDocumentChunks,
  getDocument: mocks.getDocument,
}));

import { DocumentChunkingError, DocumentFetchError } from "@/lib/api/documents";
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
    mocks.getDocument.mockReset();
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
    failed: "Failed",
    chunked: "Chunked",
    embedded: "Embedded",
  };
  return labels[status] ?? status;
}
