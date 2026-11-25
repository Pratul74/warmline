// /app/faq: upload FAQ entries from a CSV file and browse the saved ones.
import { useState } from "react";
import { useAuth } from "@/auth/AuthContext";
import { FaqTable } from "@/components/faq/FaqTable";
import { UploadDropzone } from "@/components/faq/UploadDropzone";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function FaqPage() {
  const { token } = useAuth();
  // Changed after each successful upload so the table loads again.
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <>
      <PageHeader
        title="FAQ"
        description="Your assistant answers customer questions from these entries, and says so when it doesn't know."
      />
      <div className="flex flex-col gap-10">
        <Card>
          <CardHeader>
            <CardTitle>Upload entries</CardTitle>
            <CardDescription>Add new questions or update answers in one go.</CardDescription>
          </CardHeader>
          <UploadDropzone token={token} onUploaded={() => setRefreshKey((count) => count + 1)} />
        </Card>
        <section aria-labelledby="faq-entries-title" className="flex flex-col gap-4">
          <h2 id="faq-entries-title" className="text-xl font-semibold">
            Your entries
          </h2>
          <FaqTable token={token} refreshKey={refreshKey} />
        </section>
      </div>
    </>
  );
}
