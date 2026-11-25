// The frame around the login and sign-up forms: the form on the left, and on wide screens a
// sand-coloured panel that says what Warmline does (real features only, no made-up numbers).
import { Check } from "lucide-react";
import { Logo } from "./Logo";

const POINTS = [
  "Answers customer questions from your own FAQ",
  "Captures leads, with the customer's confirmation",
  "Books and cancels appointment slots",
  "Every tool call is checked and logged",
];

export function AuthLayout({ title, subtitle, children }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_minmax(0,28rem)]">
      <main className="flex flex-col px-6 py-8 sm:px-10">
        <Logo />
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-12">
          <h1 className="text-3xl font-semibold">{title}</h1>
          {subtitle && <p className="mt-2 text-muted-foreground">{subtitle}</p>}
          <div className="mt-8">{children}</div>
        </div>
      </main>
      <aside className="hidden flex-col justify-center gap-6 border-l bg-secondary px-10 lg:flex">
        <p className="font-display text-2xl leading-snug">
          A sales and support assistant for small businesses, on a link you control.
        </p>
        <ul className="space-y-3 text-sm">
          {POINTS.map((point) => (
            <li key={point} className="flex gap-2">
              <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
              {point}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
