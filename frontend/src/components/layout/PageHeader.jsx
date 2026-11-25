// The heading at the top of each owner page, with an optional short description and actions.
// It also sets the browser tab title (React 19 moves <title> into the document head).
export function PageHeader({ title, description, actions }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <title>{`${title} · Warmline`}</title>
      <div>
        <h1 className="text-3xl font-semibold">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-muted-foreground">{description}</p>}
      </div>
      {actions}
    </header>
  );
}
