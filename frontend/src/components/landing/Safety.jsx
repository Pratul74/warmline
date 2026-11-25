// How the assistant is kept in check. These are real backend safeguards (validated tool
// inputs, an allowlist and step limit, the audit log, per-link rate limits, disable/rotate).
import { ClipboardList, Gauge, KeyRound, ShieldCheck } from "lucide-react";

const SAFEGUARDS = [
  {
    icon: ShieldCheck,
    title: "Checked before it acts",
    text: "Every action the assistant asks for is validated by our code first. It can only use a fixed list of tools, a limited number of times per message.",
  },
  {
    icon: ClipboardList,
    title: "Everything is logged",
    text: "Each tool call, its input and its result are kept in an audit log, so you can see exactly what happened.",
  },
  {
    icon: Gauge,
    title: "Limits per link",
    text: "Each chat link has its own message limits, which protects you from abuse and runaway costs.",
  },
  {
    icon: KeyRound,
    title: "You control the link",
    text: "Turn a link off, or replace it with a new one if it was shared somewhere it shouldn't be. The history stays.",
  },
];

export function Safety() {
  return (
    <section className="bg-foreground text-background">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="max-w-2xl text-3xl font-semibold sm:text-4xl">
          An assistant you can trust with your customers
        </h2>
        <ul className="mt-12 grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          {SAFEGUARDS.map(({ icon: Icon, title, text }) => (
            <li key={title}>
              <Icon className="size-6 text-[#f6b089]" aria-hidden="true" />
              <h3 className="mt-3 text-lg font-semibold">{title}</h3>
              <p className="mt-1.5 text-sm text-[#d8cfc4]">{text}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
