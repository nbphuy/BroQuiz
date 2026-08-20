type DocumentPageProps = { params: Promise<{ documentId: string }> };

export default async function DocumentPage({ params }: DocumentPageProps) {
  const { documentId } = await params;
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-semibold">Document</h1>
      <p className="mt-2 font-mono text-sm text-muted-foreground">{documentId}</p>
    </main>
  );
}
