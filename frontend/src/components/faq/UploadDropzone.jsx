// FAQ CSV upload. The drop area is a <label> around a real file input: clicking it or pressing
// Enter/Space on the input opens the file picker, and dropping a file works too. The quick
// file check only saves a round trip; the server checks everything again.
import { FileText, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { TEMPLATE_URL, uploadFaqCsv } from "@/api/faq";
import { Button } from "@/components/ui/button";
import { useSubmit } from "@/hooks/useSubmit";
import { checkCsvFile } from "@/utils/checkCsvFile";
import { cn } from "@/utils/cn";
import { UploadResult } from "./UploadResult";

export function UploadDropzone({ token, onUploaded }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [checkError, setCheckError] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState(null);
  const { submit, submitting, error, clearError } = useSubmit(() => uploadFaqCsv(token, file));

  function choose(chosen) {
    setFile(chosen);
    setResult(null);
    clearError();
    setCheckError(chosen ? checkCsvFile(chosen) : null);
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0] ?? null);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!file || checkError) return;
    setResult(null);
    const { ok, result: counts } = await submit();
    if (!ok) return;
    setResult(counts);
    setFile(null);
    inputRef.current.value = "";
    onUploaded(counts);
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
      <label
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors focus-within:border-ring hover:border-input",
          dragging && "border-primary bg-primary-soft",
        )}
      >
        {file ? (
          <FileText className="size-7 text-primary" aria-hidden="true" />
        ) : (
          <UploadCloud className="size-7 text-muted-foreground" aria-hidden="true" />
        )}
        <span className="text-sm font-medium">
          {file ? file.name : "Drop a CSV file here, or click to choose one"}
        </span>
        <span className="text-xs text-muted-foreground">
          CSV file with the columns question and answer · up to 500 rows and 1 MB
        </span>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          onChange={(event) => choose(event.target.files[0] ?? null)}
        />
      </label>

      {checkError && (
        <p role="alert" className="text-sm text-destructive">
          {checkError}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" disabled={!file || Boolean(checkError) || submitting}>
          {submitting ? "Uploading…" : "Upload"}
        </Button>
        <a
          href={TEMPLATE_URL}
          download
          className="text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          Download sample template
        </a>
      </div>
      <p className="text-sm text-muted-foreground">
        Questions you already have get the new answer; nothing is deleted. If any row has a problem,
        nothing is saved.
      </p>
      <UploadResult result={result} error={error} />
    </form>
  );
}
