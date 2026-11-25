// Shows toasts. Wrap the app in <Toaster>, then any component can call
//   const toast = useToast();
//   toast({ title: "Link rotated", description: "The old link no longer works.", variant: "success" });
// Toasts are only for confirming something that worked. Errors that need action stay on the
// page next to what failed, because a toast disappears before people can read it.
import { createContext, useCallback, useContext, useState } from "react";
import {
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from "@/components/ui/toast";

const ToastContext = createContext(null);
let nextId = 1;

export function Toaster({ children }) {
  const [toasts, setToasts] = useState([]);

  const show = useCallback((toast) => {
    setToasts((current) => [...current, { ...toast, id: nextId++ }]);
  }, []);

  function remove(id) {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }

  return (
    <ToastContext.Provider value={show}>
      {children}
      <ToastProvider duration={5000} swipeDirection="right">
        {toasts.map(({ id, title, description, variant }) => (
          <Toast key={id} variant={variant} onOpenChange={(open) => !open && remove(id)}>
            <ToastTitle>{title}</ToastTitle>
            {description && <ToastDescription>{description}</ToastDescription>}
            <ToastClose />
          </Toast>
        ))}
        <ToastViewport />
      </ToastProvider>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const show = useContext(ToastContext);
  if (!show) throw new Error("useToast must be used inside <Toaster>");
  return show;
}
