export const MAX_PDF_UPLOAD_BYTES = 25 * 1024 * 1024;

export type FileValidationResult = { valid: true } | { valid: false; message: string };

export function validateDocumentUpload(file: File | null): FileValidationResult {
  if (!file || file.type !== "application/pdf") return { valid: false, message: "Please select a PDF file." };
  if (file.size === 0) return { valid: false, message: "The PDF is empty." };
  if (file.size > MAX_PDF_UPLOAD_BYTES) return { valid: false, message: "The PDF exceeds the 25 MiB upload limit." };
  return { valid: true };
}
