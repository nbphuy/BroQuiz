"use client";

import { useQuery } from "@tanstack/react-query";
import { DocumentFetchError, getDocument, type UploadedDocument } from "@/lib/api/documents";

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

export function DocumentWorkspace({ documentId }: DocumentWorkspaceProps) {
  const documentQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId),
    retry: false,
  });

  if (documentQuery.isPending) {
    return <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16"><p role="status">Loading document�</p></main>;
  }

  if (documentQuery.error instanceof DocumentFetchError && documentQuery.error.statusCode === 404) {
    return <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16"><section aria-labelledby="not-found-heading"><h1 id="not-found-heading" className="text-2xl font-semibold">Document not found</h1><p className="mt-2 text-muted-foreground">This document may have been removed or the link is incorrect.</p></section></main>;
  }

  if (documentQuery.isError || !documentQuery.data) {
    return <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16"><section aria-labelledby="error-heading"><h1 id="error-heading" className="text-2xl font-semibold">Unable to load document</h1><p className="mt-2 text-muted-foreground">Please try again in a moment.</p></section></main>;
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16">
      <section className="rounded-lg border bg-card p-6 shadow-sm" aria-labelledby="workspace-heading">
        <p className="text-sm font-medium text-muted-foreground">Document Processing Workspace</p>
        <h1 id="workspace-heading" className="mt-1 text-2xl font-semibold tracking-tight">Document details</h1>
        <Metadata document={documentQuery.data} />
      </section>
    </main>
  );
}