// What the assistant does. Every item here exists in the backend today (the agent's tools);
// nothing is a plan or a promise.
import { BookOpen, CalendarCheck, CalendarX, UserPlus } from "lucide-react";

const FEATURES = [
  {
    icon: BookOpen,
    title: "Answers from your FAQ",
    text: "It searches your own entries by meaning, not exact words, and says so when it doesn't know instead of guessing.",
  },
  {
    icon: UserPlus,
    title: "Captures leads",
    text: "It collects a name and contact details, reads them back, and saves the lead only after the customer says yes.",
  },
  {
    icon: CalendarCheck,
    title: "Checks availability and books",
    text: "It finds free slots and books one, again after the customer has confirmed the time and details.",
  },
  {
    icon: CalendarX,
    title: "Cancels bookings",
    text: "Customers can cancel through the chat, with the same confirmation step before anything changes.",
  },
];

export function Features() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="grid gap-12 lg:grid-cols-[1fr_2fr]">
        <div>
          <h2 className="text-3xl font-semibold sm:text-4xl">What your assistant does</h2>
          <p className="mt-4 text-muted-foreground">
            Four jobs, done carefully. It works only with the information and tools you give it.
          </p>
        </div>
        <ul className="grid gap-x-10 gap-y-10 sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <li key={title}>
              <Icon className="size-6 text-primary" aria-hidden="true" />
              <h3 className="mt-3 text-lg font-semibold">{title}</h3>
              <p className="mt-1.5 text-muted-foreground">{text}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
