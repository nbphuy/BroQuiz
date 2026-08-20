import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_PDF_UPLOAD_BYTES } from "../validation";

const mocks = vi.hoisted(() => ({ push: vi.fn(), uploadDocument: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/lib/api/documents", () => ({ DocumentUploadError: class DocumentUploadError extends Error {}, uploadDocument: mocks.uploadDocument }));

import { DocumentUpload } from "./document-upload";

function renderUpload() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}><DocumentUpload /></QueryClientProvider>);
}

function select(file: File) {
  fireEvent.change(screen.getByLabelText("PDF file"), { target: { files: [file] } });
}

describe("DocumentUpload", () => {
  beforeEach(() => mocks.uploadDocument.mockReset());

  it("rejects a non-PDF file", () => {
    renderUpload(); select(new File(["text"], "notes.txt", { type: "text/plain" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Please select a PDF file.");
  });

  it("rejects an empty PDF", () => {
    renderUpload(); select(new File([], "empty.pdf", { type: "application/pdf" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The PDF is empty.");
  });

  it("rejects a PDF larger than 25 MiB", () => {
    renderUpload(); select(new File([new Uint8Array(MAX_PDF_UPLOAD_BYTES + 1)], "large.pdf", { type: "application/pdf" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The PDF exceeds the 25 MiB upload limit.");
  });

  it("accepts a valid PDF", () => {
    renderUpload(); select(new File(["%PDF-1.7"], "lesson.pdf", { type: "application/pdf" }));
    expect(screen.getByText("Selected: lesson.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload PDF" })).toBeEnabled();
  });

  it("disables controls while an upload is pending", async () => {
    let resolveUpload: (value: { id: string }) => void;
    mocks.uploadDocument.mockReturnValue(new Promise<{ id: string }>((resolve) => { resolveUpload = resolve; }));
    renderUpload(); select(new File(["%PDF-1.7"], "lesson.pdf", { type: "application/pdf" }));
    fireEvent.click(screen.getByRole("button", { name: "Upload PDF" }));
    expect(screen.getByRole("button", { name: "Uploading..." })).toBeDisabled();
    expect(screen.getByLabelText("PDF file")).toBeDisabled();
    resolveUpload!({ id: "document-123" });
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/documents/document-123"));
  });
});
