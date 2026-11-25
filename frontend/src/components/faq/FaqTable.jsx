// The owner's FAQ entries, 10 per page. `refreshKey` changes after each upload, which makes
// the list load again. While a new page loads the old rows stay visible (dimmed).
import { HelpCircle } from "lucide-react";
import { useCallback, useState } from "react";
import { listFaqEntries } from "@/api/faq";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorMessage } from "@/components/feedback/ErrorMessage";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApiRequest } from "@/hooks/useApiRequest";
import { cn } from "@/utils/cn";
import { formatDateTime } from "@/utils/formatDate";
import { Pagination } from "./Pagination";

const PAGE_SIZE = 10;

export function FaqTable({ token, refreshKey }) {
  const [page, setPage] = useState(1);
  // refreshKey is not used inside, but listing it makes a new function after each upload,
  // and a new function is what tells useApiRequest to load again.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(() => listFaqEntries(token, page, PAGE_SIZE), [token, page, refreshKey]);
  const { data, loading, error, reload } = useApiRequest(load);

  if (error) return <ErrorMessage error={error} onRetry={reload} />;
  if (!data) {
    return (
      <div aria-busy="true" className="grid gap-2">
        <p role="status" className="sr-only">
          Loading FAQ entries…
        </p>
        {[0, 1, 2, 3].map((key) => (
          <Skeleton key={key} className="h-12 w-full" />
        ))}
      </div>
    );
  }
  if (data.total === 0) {
    return (
      <EmptyState icon={HelpCircle} title="No FAQ entries yet">
        Upload a CSV above, or start from the sample template. The assistant answers customer
        questions from these entries.
      </EmptyState>
    );
  }

  const pageCount = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  return (
    <div className="flex flex-col gap-4">
      <div className={cn("rounded-lg border bg-card transition-opacity", loading && "opacity-60")}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-48">Question</TableHead>
              <TableHead className="min-w-64">Answer</TableHead>
              <TableHead className="whitespace-nowrap">Last changed</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell className="font-medium">{entry.question}</TableCell>
                <TableCell className="text-muted-foreground">{entry.answer}</TableCell>
                <TableCell className="whitespace-nowrap text-muted-foreground">
                  {formatDateTime(entry.updated_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Pagination
        shownPage={data.page}
        pageCount={pageCount}
        total={data.total}
        loading={loading}
        onPrevious={() => setPage(data.page - 1)}
        onNext={() => setPage(data.page + 1)}
      />
    </div>
  );
}
