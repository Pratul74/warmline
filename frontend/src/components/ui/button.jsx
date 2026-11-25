// Button (from shadcn/ui, adapted to our tokens). One component for every button and
// button-looking link: `variant` sets the look, `size` the height, and `asChild` lets a
// <Link> or <a> take the button's styles while staying a real link.
import { cva } from "class-variance-authority";
import { Slot } from "radix-ui";
import { cn } from "@/utils/cn";

const buttonVariants = cva(
  // Height 40px by default: easy to tap on phones (WCAG target size is 24px, Apple/Google suggest 44).
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary-hover",
        destructive: "bg-destructive text-white hover:bg-destructive/90",
        outline: "border border-input bg-card hover:bg-accent",
        secondary: "bg-secondary text-secondary-foreground hover:bg-accent",
        ghost: "hover:bg-accent",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-8 px-3",
        lg: "h-11 px-6 text-base",
        icon: "size-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({ className, variant, size, asChild = false, ...props }) {
  const Component = asChild ? Slot.Root : "button";
  return (
    <Component
      data-slot="button"
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export { Button, buttonVariants };
