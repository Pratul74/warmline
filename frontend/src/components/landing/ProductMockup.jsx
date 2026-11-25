// A picture of the hosted chat, drawn with HTML and CSS instead of a screenshot: it stays
// sharp, costs no image download, and shows a real flow (FAQ answer, then a booking that waits
// for the customer's "yes"). The business and messages are made up and marked as an example.
const MESSAGES = [
  { mine: true, text: "Do you service e-bikes?" },
  {
    mine: false,
    text: "Yes, we service most e-bike brands. A standard service takes about two days.",
  },
  { mine: true, text: "Can I bring mine in on Thursday morning?" },
  { mine: false, text: "Thursday at 10:00 is free. Shall I book it for you, Sam?" },
];

export function ProductMockup() {
  return (
    <figure className="relative mx-auto w-full max-w-sm">
      <div
        aria-hidden="true"
        className="absolute -inset-4 -z-10 rotate-2 rounded-3xl bg-primary-soft"
      />
      <div className="overflow-hidden rounded-2xl border bg-background shadow-raised">
        <div className="flex items-center gap-3 border-b bg-card px-4 py-3">
          <span className="grid size-9 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            CC
          </span>
          <div>
            <p className="font-display leading-tight font-semibold">Corner Cycles</p>
            <p className="text-xs text-muted-foreground">AI assistant · Website chat</p>
          </div>
        </div>
        <ul className="flex flex-col gap-3 px-4 py-5 text-sm">
          {MESSAGES.map(({ mine, text }) => (
            <li
              key={text}
              className={
                mine
                  ? "max-w-[80%] self-end rounded-2xl rounded-br-md bg-secondary px-3.5 py-2"
                  : "max-w-[85%] self-start rounded-2xl rounded-bl-md border bg-card px-3.5 py-2"
              }
            >
              {text}
            </li>
          ))}
        </ul>
        <div className="border-t bg-card px-4 py-3">
          <div className="rounded-full border border-input px-4 py-2 text-sm text-muted-foreground">
            Type your message…
          </div>
        </div>
      </div>
      <figcaption className="mt-6 text-center text-xs text-muted-foreground">
        Example conversation with a made-up business
      </figcaption>
    </figure>
  );
}
