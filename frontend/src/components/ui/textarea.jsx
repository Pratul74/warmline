// Multi-line text field, styled like Input so forms look the same everywhere.
import { cn } from "@/utils/cn";
import { fieldClasses } from "./input";

function Textarea({ className, ...props }) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(fieldClasses, "min-h-20 py-2", className)}
      {...props}
    />
  );
}

export { Textarea };
