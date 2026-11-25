// Text input (from shadcn/ui, adapted). aria-invalid="true" turns the border red, so a field
// with a server error is marked for sighted users and announced as invalid by screen readers.
import { cn } from "@/utils/cn";

const fieldClasses =
  "w-full min-w-0 rounded-md border border-input bg-card px-3 text-base text-foreground transition-colors placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive md:text-sm";

function Input({ className, type = "text", ...props }) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(fieldClasses, "h-10", className)}
      {...props}
    />
  );
}

export { Input, fieldClasses };
