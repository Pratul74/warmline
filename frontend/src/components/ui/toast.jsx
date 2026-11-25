// Toast parts, styled (Radix Toast). A toast is a short "done" message in the corner that
// closes by itself. Radix announces it to screen readers through a live region, pauses the
// timer while it is hovered or focused, and lets keyboard users reach it with F8.
import { XIcon } from "lucide-react";
import { Toast as ToastPrimitive } from "radix-ui";
import { cn } from "@/utils/cn";

const ToastProvider = ToastPrimitive.Provider;

function ToastViewport({ className, ...props }) {
  return (
    <ToastPrimitive.Viewport
      className={cn(
        "fixed right-0 bottom-0 z-[100] flex w-full max-w-sm flex-col gap-2 p-4 outline-none",
        className,
      )}
      {...props}
    />
  );
}

const toastVariants = {
  default: "border-border",
  success: "border-l-4 border-l-success",
  error: "border-l-4 border-l-destructive",
};

// Escape never closes a toast, so one press of Escape closes the open dialog and nothing else
// (see dialog.jsx). Toasts still close by themselves, with their × button, or by swiping.
function ignoreEscape(event) {
  event.preventDefault();
}

function Toast({ className, variant = "default", ...props }) {
  return (
    <ToastPrimitive.Root
      onEscapeKeyDown={ignoreEscape}
      className={cn(
        "relative grid animate-pop-in gap-1 rounded-md border bg-card p-4 pr-10 shadow-raised",
        toastVariants[variant],
        className,
      )}
      {...props}
    />
  );
}

function ToastTitle({ className, ...props }) {
  return <ToastPrimitive.Title className={cn("text-sm font-semibold", className)} {...props} />;
}

function ToastDescription({ className, ...props }) {
  return (
    <ToastPrimitive.Description
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

function ToastClose() {
  return (
    <ToastPrimitive.Close className="absolute top-3 right-3 cursor-pointer rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
      <XIcon className="size-4" aria-hidden="true" />
      <span className="sr-only">Dismiss</span>
    </ToastPrimitive.Close>
  );
}

export { Toast, ToastClose, ToastDescription, ToastProvider, ToastTitle, ToastViewport };
