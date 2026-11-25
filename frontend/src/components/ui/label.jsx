// Label (from shadcn/ui). Radix's Label is a real <label>; clicking it focuses its field.
import { Label as LabelPrimitive } from "radix-ui";
import { cn } from "@/utils/cn";

function Label({ className, ...props }) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn("text-sm leading-none font-medium select-none", className)}
      {...props}
    />
  );
}

export { Label };
