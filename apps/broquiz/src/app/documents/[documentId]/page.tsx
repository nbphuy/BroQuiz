import { DocumentWorkspace } from "@/features/documents/components/document-workspace";

type DocumentPageProps = { params: Promise<{ documentId: string }> };

export default async function DocumentPage({ params }: DocumentPageProps) {
  const { documentId } = await params;
  return <DocumentWorkspace documentId={documentId} />;
}