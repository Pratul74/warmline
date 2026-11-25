// Badge (from shadcn/ui, adapted): a small label for a status such as "Active" or "Disabled".
import { cva } from "class-variance-authority";
import { cn } from "@/utils/cn";

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap [&>svg]:size-3",
  {
    variants: {
      variant: {
        success: "border-success/20 bg-success-soft text-success",
        muted: "border-border bg-muted text-muted-foreground",
        danger: "border-destructive/20 bg-destructive-soft text-destructive",
      },
    },
    defaultVariants: { variant: "muted" },
  },
);

function Badge({ className, variant, ...props }) {
  return (
    <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge };
