// Asks before rotating a chat link, because the old link stops working at once and the owner
// has to replace it everywhere they put it. Replaces the old window.confirm, which cannot be
// styled and reads poorly on phones.
import { ErrorMessage } from "@/components/feedback/ErrorMessage";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useSubmit } from "@/hooks/useSubmit";

export function RotateLinkDialog({ open, onOpenChange, integrationName, onRotate, onRotated }) {
  const { submit, submitting, error, clearError } = useSubmit(onRotate);

  async function handleRotate() {
    const { ok, result } = await submit();
    if (ok) {
      onRotated(result);
      onOpenChange(false);
    }
  }

  function handleOpenChange(next) {
    if (!next) clearError();
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Get a new link for “{integrationName}”?</DialogTitle>
          <DialogDescription>
            The current link stops working immediately. Anyone who opens it will see that the chat
            is unavailable. Conversations so far are kept.
          </DialogDescription>
        </DialogHeader>
        <p className="text-sm">
          You will need to replace the link everywhere you placed it: your website, app or social
          profiles.
        </p>
        <ErrorMessage error={error} />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Keep the current link</Button>
          </DialogClose>
          <Button variant="destructive" onClick={handleRotate} disabled={submitting}>
            {submitting ? "Rotating…" : "Rotate link"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
