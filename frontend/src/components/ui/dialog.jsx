// Dialog (from shadcn/ui, adapted). Radix handles the hard accessibility parts: focus moves
// into the dialog and stays there, Escape closes it, and the page behind is hidden from screen
// readers. We add one thing: focus goes back to whatever opened the dialog when it closes.
import { XIcon } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { useRef } from "react";
import { cn } from "@/utils/cn";

const Dialog = DialogPrimitive.Root;
const DialogClose = DialogPrimitive.Close;

function DialogContent({ className, children, ...props }) {
  // Radix only returns focus to a <DialogTrigger>. Our dialogs are opened by ordinary buttons
  // through state, so we remember the focused element at the moment the dialog opens (just
  // before Radix moves focus inside) and focus it again on close, if it is still on the page.
  const opener = useRef(null);
  const closeButton = useRef(null);

  function rememberOpener() {
    opener.current = document.activeElement;
  }

  // Radix gives Escape only to the newest "layer". A toast that re-renders while a dialog is
  // open can become that layer and take the key, leaving the dialog open (found in a browser
  // test). So Escape pressed inside the dialog presses its own Close button.
  function closeOnEscape(event) {
    if (event.key === "Escape") closeButton.current?.click();
  }

  function returnFocus(event) {
    if (opener.current instanceof HTMLElement && opener.current.isConnected) {
      event.preventDefault();
      opener.current.focus();
    }
  }

  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 animate-fade-in bg-foreground/40" />
      <DialogPrimitive.Content
        className={cn(
          "fixed top-1/2 left-1/2 z-50 grid w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 animate-pop-in gap-4 rounded-lg border bg-card p-6 shadow-raised",
          className,
        )}
        onOpenAutoFocus={rememberOpener}
        onCloseAutoFocus={returnFocus}
        onKeyDown={closeOnEscape}
        {...props}
      >
        {children}
        <DialogPrimitive.Close
          ref={closeButton}
          className="absolute top-3 right-3 cursor-pointer rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <XIcon className="size-4" aria-hidden="true" />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

function DialogHeader({ className, ...props }) {
  return <div className={cn("flex flex-col gap-2 pr-6", className)} {...props} />;
}

function DialogFooter({ className, ...props }) {
  return (
    <div
      className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)}
      {...props}
    />
  );
}

function DialogTitle({ className, ...props }) {
  return (
    <DialogPrimitive.Title
      className={cn("text-xl leading-snug font-semibold", className)}
      {...props}
    />
  );
}

function DialogDescription({ className, ...props }) {
  return (
    <DialogPrimitive.Description
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
};
