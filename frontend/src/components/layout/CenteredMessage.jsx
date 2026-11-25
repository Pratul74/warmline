// A full-screen centred message, shared by the 404 and error pages and by a closed chat link.
import { LogoMark } from "./Logo";

export function CenteredMessage({ eyebrow, title, children, actions }) {
  return (
    <main className="grid min-h-dvh place-items-center px-6 py-16">
      <div className="max-w-md text-center">
        <LogoMark className="mx-auto size-10" />
        {eyebrow && (
          <p className="mt-6 text-sm font-semibold tracking-wide text-primary uppercase">
            {eyebrow}
          </p>
        )}
        <h1 className="mt-2 text-3xl font-semibold">{title}</h1>
        {children && <div className="mt-3 text-muted-foreground">{children}</div>}
        {actions && <div className="mt-8 flex flex-wrap justify-center gap-3">{actions}</div>}
      </div>
    </main>
  );
}
