// Previous / Next with "Page X of Y". The label uses the page the shown rows belong to,
// not the page being requested, so it never describes rows that are not on screen yet.
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Pagination({ shownPage, pageCount, total, loading, onPrevious, onNext }) {
  return (
    <nav aria-label="FAQ pages" className="flex items-center justify-between gap-4 text-sm">
      <Button variant="outline" size="sm" disabled={shownPage <= 1 || loading} onClick={onPrevious}>
        <ChevronLeft aria-hidden="true" /> Previous
      </Button>
      <p className="text-muted-foreground" aria-live="polite">
        Page {shownPage} of {pageCount} · {total} entries
        {loading && " · loading…"}
      </p>
      <Button
        variant="outline"
        size="sm"
        disabled={shownPage >= pageCount || loading}
        onClick={onNext}
      >
        Next <ChevronRight aria-hidden="true" />
      </Button>
    </nav>
  );
}
