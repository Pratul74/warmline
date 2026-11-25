// What a list shows when it has nothing yet: what is missing and what to do next, instead of
// an empty white box.
import { cn } from "@/utils/cn";

export function EmptyState({ icon: Icon, title, children, action, className }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-lg border border-dashed px-6 py-10 text-center",
        className,
      )}
    >
      {Icon && (
        <span className="rounded-full bg-primary-soft p-3 text-primary">
          <Icon className="size-5" aria-hidden="true" />
        </span>
      )}
      <h3 className="text-lg font-semibold">{title}</h3>
      {children && <p className="max-w-sm text-sm text-muted-foreground">{children}</p>}
      {action}
    </div>
  );
}
