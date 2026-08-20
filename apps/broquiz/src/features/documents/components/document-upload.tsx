"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useId, useState, type ChangeEvent, type FormEvent } from "react";
import { DocumentUploadError, uploadDocument } from "@/lib/api/documents";
import { validateDocumentUpload } from "../validation";

export function DocumentUpload() {
  const router = useRouter();
  const inputId = useId();
  const errorId = useId();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const uploadMutation = useMutation({ mutationFn: uploadDocument, onSuccess: (document) => router.push(`/documents/${document.id}`) });
  const apiError = uploadMutation.error
    ? uploadMutation.error instanceof DocumentUploadError ? uploadMutation.error.message : "Unable to upload the PDF. Please try again."
    : null;

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    const validation = validateDocumentUpload(file);
    uploadMutation.reset();
    setSelectedFile(validation.valid ? file : null);
    setValidationError(validation.valid ? null : validation.message);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = selectedFile;
    if (!file) {
      setValidationError("Please select a PDF file.");
      return;
    }
    const validation = validateDocumentUpload(file);
    if (!validation.valid) {
      setValidationError(validation.message);
      return;
    }
    setValidationError(null);
    uploadMutation.mutate(file);
  }

  const error = validationError ?? apiError;
  return (
    <form className="space-y-4" onSubmit={handleSubmit} noValidate>
      <div className="space-y-2">
        <label className="block text-sm font-medium" htmlFor={inputId}>PDF file</label>
        <input id={inputId} type="file" accept="application/pdf,.pdf" onChange={handleFileChange} disabled={uploadMutation.isPending} aria-describedby={error ? errorId : undefined} className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
        <p className="text-sm text-muted-foreground" aria-live="polite">{selectedFile ? `Selected: ${selectedFile.name}` : "Select a non-empty PDF up to 25 MiB."}</p>
      </div>
      {error ? <p id={errorId} role="alert" className="text-sm text-destructive">{error}</p> : null}
      <button type="submit" disabled={selectedFile === null || uploadMutation.isPending} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50">
        {uploadMutation.isPending ? "Uploading..." : "Upload PDF"}
      </button>
    </form>
  );
}
