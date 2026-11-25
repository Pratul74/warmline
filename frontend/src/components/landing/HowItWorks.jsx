// Three numbered steps, from sign-up to a live chat link.
const STEPS = [
  {
    title: "Add your answers",
    text: "Upload your frequently asked questions as a CSV file. Update them any time by uploading again.",
  },
  {
    title: "Create a chat link",
    text: "Give it a name and a greeting. Each link is unique and can be disabled or replaced whenever you want.",
  },
  {
    title: "Put it behind a Chat button",
    text: "On your website, in your app or in a social profile. Customers tap it and start talking.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="scroll-mt-8 border-y bg-card">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="max-w-xl text-3xl font-semibold sm:text-4xl">Live in three steps</h2>
        <ol className="mt-12 grid gap-10 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="border-t-2 border-primary pt-5">
              <span className="font-display text-sm font-semibold text-primary">0{index + 1}</span>
              <h3 className="mt-2 text-xl font-semibold">{step.title}</h3>
              <p className="mt-2 text-muted-foreground">{step.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
