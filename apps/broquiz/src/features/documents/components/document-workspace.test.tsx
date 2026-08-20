import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getDocument: vi.fn() }));

vi.mock("@/lib/api/documents", () => ({
  DocumentFetchError: class DocumentFetchError extends Error {
    constructor(message: string, readonly statusCode?: number) {
      super(message);
    }
  },
  getDocument: mocks.getDocument,
}));

import { DocumentFetchError } from "@/lib/api/documents";
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
  return render(<QueryClientProvider client={queryClient}><DocumentWorkspace documentId="document-123" /></QueryClientProvider>);
}

describe("DocumentWorkspace", () => {
  beforeEach(() => {
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

  it("renders persisted document metadata", async () => {
    mocks.getDocument.mockResolvedValue(document);
    renderWorkspace();
    expect(await screen.findByText("biology-notes.pdf")).toBeInTheDocument();
    expect(screen.getByText("document-123")).toBeInTheDocument();
    expect(screen.getByText("application/pdf")).toBeInTheDocument();
    expect(screen.getByText("1.5 MiB")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Processed")).toBeInTheDocument();
    expect(mocks.getDocument).toHaveBeenCalledWith("document-123");
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