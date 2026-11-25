// The outcome of one upload: the counts, or the server's error exactly as it was sent
// (its message, plus a table of row problems for a 422, so the owner can fix the file).
import { CheckCircle2 } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export function UploadResult({ result, error }) {
  if (result) {
    return (
      <div
        role="status"
        className="flex items-start gap-3 rounded-md bg-success-soft p-4 text-sm text-success"
      >
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <p>
          <strong>Upload saved.</strong> {result.inserted} added, {result.updated} updated,{" "}
          {result.unchanged} unchanged.
        </p>
      </div>
    );
  }
  if (!error) return null;

  return (
    <div
      role="alert"
      className="flex flex-col gap-3 rounded-md border border-destructive/25 bg-destructive-soft p-4"
    >
      <p className="text-sm font-medium text-destructive">{error.message}</p>
      {error.errors.length > 0 && (
        <div className="max-h-72 overflow-y-auto rounded-md border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">Row</TableHead>
                <TableHead className="w-28">Column</TableHead>
                <TableHead>Problem</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {error.errors.map((item, index) => (
                // The server may send two problems for the same row, so the index is the key.
                <TableRow key={index}>
                  <TableCell className="font-mono">{item.row ?? "–"}</TableCell>
                  <TableCell>{item.field ?? "–"}</TableCell>
                  <TableCell>{item.message}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
